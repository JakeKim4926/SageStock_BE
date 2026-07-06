"""White House Presidential Actions collector — PRESIDENTIAL_ACTION LEAD (SPEC §6.8).

수집 경로: presidential-actions WordPress RSS 피드(content:encoded에 전문 포함).
문서 타입 판정(router)은 피드 category → config document_types 매핑으로만 한다 —
Executive Order / Presidential Memorandum / Proclamation 외(지명 등)는 수집하지 않는다.

식별 번호(§7.3 presidential_document_number):
- EO 자체 번호: 본문의 다운로드 링크(wp-content/uploads/.../eo-14414.pdf)에서 추출 —
  발표 시점에 확인되는 명시 식별자라 event_status=ACTIVE(Phase 2 체인 후보)
- 자체 번호가 없으면 ACTIVE_UNLINKED로 독립 저장 (잘못된 자동 체인보다 중복 허용)
- 본문에 인용된 EO/Proclamation 번호는 후보 목록으로만 raw_payload에 보존
  (자체 번호와 구분 — 인용 번호로 체인을 만들면 안 된다)

파싱 실패 처리(config parse_failure_handling=no_event_or_partial):
- 필수(제목/링크/발행시각/문서타입) 결손 → 이벤트 생성 금지 + 경고 로그
- 본문 추출만 실패 → parse_status=PARTIAL로 저장 (조용히 숨기지 않는다)
"""
import html as html_lib
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.batch.macro_collectors.base import MacroCollector
from app.constants.macro_enums import (
    CertaintyLevel,
    EventStatus,
    LatencyReferenceType,
    MacroEventType,
)
from app.services.macro_events.config_loader import load_event_type_rules
from app.services.macro_events.normalize import NormalizedMacroEvent, now_kst, to_kst

logger = logging.getLogger(__name__)

_FEED_URL = "https://www.whitehouse.gov/presidential-actions/feed/"
_USER_AGENT = "SageStock-macro-event-engine/1.0 (batch collector)"
_HTTP_TIMEOUT = 30.0
_CONTENT_NS = {"content": "http://purl.org/rss/1.0/modules/content/"}
# 피드 category 표기(복수형) → config document_types 표기(단수형).
# config에 없는 타입은 로드 시 걸러진다 — document_types 정본은 event_type_rules.yaml.
_CATEGORY_TO_TYPE = {
    "Executive Orders": "Executive Order",
    "Presidential Memoranda": "Presidential Memorandum",
    "Proclamations": "Proclamation",
}
_POST_ID_PATTERN = re.compile(r"[?&]p=(\d+)")
_TOPPER_MARKER = '<div class="alignfull has-wide-width wp-block-whitehouse-topper"'
_DIV_PATTERN = re.compile(r"<div\b|</div>")
_TAG_PATTERN = re.compile(r"<[^>]+>")
# EO 자체 번호 — 다운로드 PDF 링크에서만 (본문 인용과 구분)
_OWN_EO_PATTERN = re.compile(r"/wp-content/uploads/[^\"]*/eo-(\d{4,5})\.pdf")
_EO_REFERENCE_PATTERN = re.compile(r"Executive Order\s+(\d{4,5})")
_PROCLAMATION_REFERENCE_PATTERN = re.compile(r"Proclamation\s+(\d{4,5})")
_TRAILING_BOILERPLATE_PATTERN = re.compile(
    r"\s*The post .{0,200} appeared first on The White House\s*\.?\s*$"
)
_RAW_TEXT_MAX_CHARS = 5_000


@dataclass(frozen=True)
class PresidentialAction:
    """피드 item 한 건에서 판정·저장에 쓰는 필드."""

    post_id: str
    title: str
    link: str
    document_type: str  # config document_types 표기 (Executive Order 등)
    published_at_kst: datetime
    summary: str | None
    body_text: str  # 추출 실패면 빈 문자열 (PARTIAL)
    own_eo_number: str | None
    eo_number_references: list[str]
    proclamation_number_references: list[str]


@dataclass(frozen=True)
class WhiteHouseRules:
    """event_type_rules.yaml US_WHITE_HOUSE에서 뽑은 값."""

    document_types: tuple[str, ...]
    certainty_level: str


def load_white_house_rules() -> WhiteHouseRules:
    source = load_event_type_rules().event_types["PRESIDENTIAL_ACTION"]["sources"][
        "US_WHITE_HOUSE"
    ]
    return WhiteHouseRules(
        document_types=tuple(source["document_types"]),
        certainty_level=str(source["certainty_level"]),
    )


def detect_document_type(
    categories: list[str], allowed_types: tuple[str, ...]
) -> str | None:
    """category → 문서 타입 router. config에 없는 타입이면 None(수집 안 함)."""
    for category in categories:
        document_type = _CATEGORY_TO_TYPE.get(category)
        if document_type is not None and document_type in allowed_types:
            return document_type
    return None


def _cut_topper_block(content_html: str) -> str:
    """상단 네비게이션(topper) div 블록을 depth 스캔으로 제거."""
    start = content_html.find(_TOPPER_MARKER)
    if start < 0:
        return content_html
    depth, index = 0, start
    while True:
        match = _DIV_PATTERN.search(content_html, index)
        if match is None:
            return content_html
        depth += 1 if match.group(0) != "</div>" else -1
        index = match.end()
        if depth == 0:
            return content_html[:start] + content_html[index:]


def extract_body_text(content_html: str) -> str:
    """content:encoded HTML → 본문 평문 (topper·트레일러 보일러플레이트 제거)."""
    stripped = _TAG_PATTERN.sub(" ", _cut_topper_block(content_html))
    text = " ".join(html_lib.unescape(stripped).split())
    return _TRAILING_BOILERPLATE_PATTERN.sub("", text)


def parse_feed_actions(
    feed_xml: str, allowed_types: tuple[str, ...]
) -> list[PresidentialAction]:
    """피드 → 수집 대상 문서 타입의 action 목록.

    필수 필드(제목/링크/발행시각/타입) 결손 항목은 이벤트 생성 금지(경고 로그)."""
    actions: list[PresidentialAction] = []
    for item in ET.fromstring(feed_xml).iter("item"):
        categories = [
            category.text.strip()
            for category in item.findall("category")
            if category.text
        ]
        document_type = detect_document_type(categories, allowed_types)
        if document_type is None:
            continue  # 지명(Nominations) 등 대상 외 타입

        title = " ".join((item.findtext("title") or "").split())
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        post_id_match = _POST_ID_PATTERN.search(guid)
        if not title or not link or not pub_date or post_id_match is None:
            logger.warning(
                "WH 피드 필수 필드 결손 — 이벤트 생성 금지 (§6.8): link=%s guid=%s",
                link,
                guid,
            )
            continue

        content_html = item.findtext("content:encoded", namespaces=_CONTENT_NS) or ""
        body_text = extract_body_text(content_html) if content_html else ""
        description = item.findtext("description") or ""
        summary = " ".join(
            html_lib.unescape(_TAG_PATTERN.sub(" ", description)).split()
        ) or None

        actions.append(
            PresidentialAction(
                post_id=post_id_match.group(1),
                title=title,
                link=link,
                document_type=document_type,
                published_at_kst=to_kst(parsedate_to_datetime(pub_date)),
                summary=summary,
                body_text=body_text,
                own_eo_number=(
                    match.group(1)
                    if (match := _OWN_EO_PATTERN.search(content_html))
                    else None
                ),
                eo_number_references=sorted(set(_EO_REFERENCE_PATTERN.findall(body_text))),
                proclamation_number_references=sorted(
                    set(_PROCLAMATION_REFERENCE_PATTERN.findall(body_text))
                ),
            )
        )
    return actions


class WhiteHouseCollector(MacroCollector):
    source_id = "US_WHITE_HOUSE"

    def __init__(self, lookback_days: int = 2) -> None:
        self._lookback_days = lookback_days
        self._rules = load_white_house_rules()

    async def collect(self, session: AsyncSession) -> list[NormalizedMacroEvent]:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.get(_FEED_URL)
            response.raise_for_status()

        cutoff = now_kst() - timedelta(days=self._lookback_days)
        actions = [
            action
            for action in parse_feed_actions(response.text, self._rules.document_types)
            if action.published_at_kst >= cutoff
        ]
        logger.info(
            "WH Presidential Actions %d건 (lookback %d일)", len(actions), self._lookback_days
        )
        return [self._build_event(action) for action in actions]

    def _build_event(self, action: PresidentialAction) -> NormalizedMacroEvent:
        if not action.body_text:
            logger.warning(
                "WH 본문 추출 실패 — PARTIAL 저장 (§6.8): post_id=%s", action.post_id
            )

        return NormalizedMacroEvent(
            event_unique_id=action.post_id,
            event_type=MacroEventType.PRESIDENTIAL_ACTION,
            title=f"{action.document_type}: {action.title}",
            summary=action.summary,
            source_published_at=action.published_at_kst,
            publicly_observable_at=action.published_at_kst,
            latency_reference_type=LatencyReferenceType.PUBLISHED_AT,
            certainty_level=CertaintyLevel(self._rules.certainty_level),
            # 자체 번호(명시 식별자)가 있어야 체인 후보 — 인용 번호로는 연결하지 않는다 (§7.3)
            event_status=(
                EventStatus.ACTIVE
                if action.own_eo_number is not None
                else EventStatus.ACTIVE_UNLINKED
            ),
            linked_entities=None,  # WH 원문엔 구조화 entity 없음 (§11 매핑: 없음)
            raw_payload={
                "post_id": action.post_id,
                "document_type": action.document_type,
                "executive_order_number": action.own_eo_number,
                "eo_number_references": action.eo_number_references,
                "proclamation_number_references": action.proclamation_number_references,
                "parse_status": "FULL" if action.body_text else "PARTIAL",
            },
            raw_text=action.body_text[:_RAW_TEXT_MAX_CHARS] or None,
            source_url=action.link,
        )
