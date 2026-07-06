"""Defense.gov Daily Contracts collector — MEGA_CONTRACT LEAD/CONFIRMATION (SPEC §6.7).

수집 경로: Contracts RSS 피드(ContentType=400)로 일별 발표 기사 링크를 얻고,
기사 HTML의 <div class="body">에서 기관 섹션 헤더(가운데 정렬 <strong>)와
계약 항목 <p> 단락을 분리해 항목별 이벤트를 만든다.

수집 조건(정본: event_type_rules.yaml → US_DEFENSE_CONTRACTS):
- amount >= $50M, 또는 amount >= $7.5M AND strong domain keyword match
- 금액을 추출하지 못한 항목은 수집 경로가 없다(보수적) — 사유를 로그로 남긴다
- 수주사/금액/기관/설명 4필드 중 3개 이상 추출돼야 저장 (min_extracted_fields)

chain 관련(§7.2 Defense.gov): 명시적 계약번호가 있으면 ACTIVE(Phase 2 체인 후보),
없으면 ACTIVE_UNLINKED. modification은 is_modification + previously awarded 번호를
raw_payload에 보존하고 follow-through 연결은 Phase 2 소유.

접근 제약(2026-07 확인): defense.gov는 war.gov로 301 리다이렉트되며, Akamai가
비미국 IP의 /News/* HTML 접근을 403으로 차단한다(RSS.ashx는 허용). 운영 실행은
GH Actions 미국 러너 기준이고, 한국 로컬에서는 기사 조회가 403으로 실패한다.
"""
import hashlib
import html as html_lib
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.batch.macro_collectors.base import MacroCollector
from app.constants.macro_enums import (
    CertaintyLevel,
    EventStatus,
    LatencyReferenceType,
    MacroEventType,
)
from app.services.macro_events.config_loader import (
    KeywordDomainMap,
    load_event_type_rules,
    load_keyword_domain_map,
)
from app.services.macro_events.keyword_match import strong_keyword_match
from app.services.macro_events.normalize import NormalizedMacroEvent, now_kst, to_kst

logger = logging.getLogger(__name__)

# defense.gov가 war.gov로 301 중 — 원 도메인 유지 + follow_redirects로 개명/환원 양쪽 대응.
_RSS_URL = "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx"
_RSS_PARAMS = {"ContentType": "400", "Site": "945", "max": "10"}
# Akamai가 비브라우저 UA를 403 처리해 브라우저 UA가 필요하다 (공개 페이지, 인증 없음).
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_HTTP_TIMEOUT = 30.0

_ARTICLE_ID_PATTERN = re.compile(r"/Article/(\d+)/")
_BODY_DIV_MARKER = '<div class="body">'
_PARAGRAPH_PATTERN = re.compile(r"<p\b[^>]*>.*?</p>", re.DOTALL)
_TAG_PATTERN = re.compile(r"<[^>]+>")
_AMOUNT_PATTERN = re.compile(r"\$([\d,]+)")
# 괄호 안 영숫자 토큰 — 계약번호(HQ003426DE016, W9126G-26-D-A042)와
# modification 번호(P00003)를 모두 잡은 뒤 분류한다
_PAREN_TOKEN_PATTERN = re.compile(r"\(([A-Z0-9][A-Z0-9-]{4,24})\)")
_MODIFICATION_NUMBER_PATTERN = re.compile(r"^[A-Z]\d{5}$")
# 변형 둘 다 실데이터에 있다: "previously awarded (FA8106-25-D-B003)" /
# "previously awarded contract N00024-19-C-2216"
_PREVIOUSLY_AWARDED_PATTERN = re.compile(
    r"previously awarded(?:\s+contract)?\s*\(?([A-Z][A-Z0-9-]{5,24})\)?"
)
_RAW_TEXT_MAX_CHARS = 5_000
_TITLE_EXCERPT_CHARS = 80


@dataclass(frozen=True)
class ContractArticle:
    """RSS 피드의 일별 계약 발표 기사 한 건."""

    article_id: str
    url: str
    title: str
    published_at_kst: datetime  # RSS pubDate(GMT) 변환값


@dataclass(frozen=True)
class ContractItem:
    """기사 본문에서 분리한 계약 항목 하나 (§6.7 추출 필드)."""

    agency: str | None
    text: str
    amount_usd: int | None
    awardee_name: str | None
    contract_numbers: list[str]
    modification_number: str | None
    is_modification: bool
    previously_awarded_number: str | None
    indefinite_delivery: bool
    ceiling_value: bool


@dataclass(frozen=True)
class DefenseCollectRules:
    """event_type_rules.yaml US_DEFENSE_CONTRACTS에서 뽑은 필터 값."""

    large_value_threshold: float
    small_value_threshold: float
    min_extracted_fields: int
    certainty_level: str


def load_defense_rules() -> DefenseCollectRules:
    source = load_event_type_rules().event_types["MEGA_CONTRACT"]["sources"][
        "US_DEFENSE_CONTRACTS"
    ]

    thresholds: list[float] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "amount_usd_gte":
                    thresholds.append(float(value))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(source["collect_if"])
    if len(thresholds) < 2:
        raise ValueError("US_DEFENSE_CONTRACTS collect_if에서 금액 임계값 2종을 찾지 못함")

    return DefenseCollectRules(
        large_value_threshold=max(thresholds),
        small_value_threshold=min(thresholds),
        min_extracted_fields=int(source["min_extracted_fields"]),
        certainty_level=str(source["certainty_level"]),
    )


def parse_rss_articles(rss_xml: str) -> list[ContractArticle]:
    """Contracts RSS → 일별 기사 목록. 기사 ID를 못 뽑는 항목은 제외."""
    articles: list[ContractArticle] = []
    for item in ET.fromstring(rss_xml).iter("item"):
        link = (item.findtext("link") or "").strip()
        title = " ".join((item.findtext("title") or "").split())
        pub_date = (item.findtext("pubDate") or "").strip()
        id_match = _ARTICLE_ID_PATTERN.search(link)
        if id_match is None or not pub_date:
            logger.warning("Contracts RSS 항목 식별 실패 — link=%s", link)
            continue
        articles.append(
            ContractArticle(
                article_id=id_match.group(1),
                url=link,
                title=title,
                published_at_kst=to_kst(parsedate_to_datetime(pub_date)),
            )
        )
    return articles


def _paragraph_text(paragraph_html: str) -> str:
    stripped = _TAG_PATTERN.sub(" ", paragraph_html)
    return " ".join(html_lib.unescape(stripped).split())


def _extract_awardee(text: str) -> str | None:
    """항목 첫 문장의 'Awardee Name, City, State' 패턴에서 수주사명만.

    multi-awardee 항목(회사; 회사; ...)은 첫 회사만 대표로 뽑는다 —
    전체 목록은 raw_text에 보존되고 entity 확장은 원문 명시 범위라 Phase 2 소유."""
    first_comma = text.find(",")
    if first_comma <= 0 or first_comma > 120:
        return None
    name = text[:first_comma].strip().rstrip("*").strip()
    return name or None


def parse_contract_items(article_html: str) -> list[ContractItem]:
    """기사 HTML → 계약 항목 목록. 섹션 헤더(가운데 정렬 <strong>)가 기관명이 된다."""
    start = article_html.find(_BODY_DIV_MARKER)
    if start < 0:
        return []
    body = article_html[start : article_html.find("</div>", start)]

    items: list[ContractItem] = []
    current_agency: str | None = None
    for match in _PARAGRAPH_PATTERN.finditer(body):
        paragraph = match.group(0)
        text = _paragraph_text(paragraph)
        if not text:
            continue
        if "text-align: center" in paragraph and "<strong>" in paragraph:
            current_agency = text
            continue
        if text.startswith("*"):
            continue  # 하단 각주 (*Small business 등)

        amount_match = _AMOUNT_PATTERN.search(text)
        contract_numbers: list[str] = []
        modification_numbers: list[str] = []
        for token in _PAREN_TOKEN_PATTERN.findall(text):
            if _MODIFICATION_NUMBER_PATTERN.match(token):
                modification_numbers.append(token)
            elif sum(ch.isdigit() for ch in token) >= 6 and any(ch.isalpha() for ch in token):
                # 계약번호는 숫자 6자리 이상 + 영문 포함 — (FY2026) 같은 괄호 표기는 제외
                contract_numbers.append(token)
        previously = _PREVIOUSLY_AWARDED_PATTERN.search(text)
        lowered = text.lower()

        items.append(
            ContractItem(
                agency=current_agency,
                text=text,
                amount_usd=(
                    int(amount_match.group(1).replace(",", "")) if amount_match else None
                ),
                awardee_name=_extract_awardee(text),
                contract_numbers=contract_numbers,
                modification_number=(
                    modification_numbers[0] if modification_numbers else None
                ),
                is_modification="modification" in lowered,
                previously_awarded_number=previously.group(1) if previously else None,
                indefinite_delivery="indefinite-delivery" in lowered,
                ceiling_value=(
                    "if all options are exercised" in lowered or "ceiling" in lowered
                ),
            )
        )
    return items


def passes_collect_filter(
    item: ContractItem,
    rules: DefenseCollectRules,
    keyword_map: KeywordDomainMap,
) -> tuple[bool, dict[str, Any]]:
    """§6.7 수집 조건. (수집 여부, 판정 근거) 반환 — 금액 없으면 수집 경로 없음."""
    strong_matched, matched_keywords = strong_keyword_match(item.text, keyword_map)
    amount = item.amount_usd

    if amount is None:
        collected = False
    else:
        collected = amount >= rules.large_value_threshold or (
            amount >= rules.small_value_threshold and strong_matched
        )

    extracted_fields = sum(
        1
        for value in (item.amount_usd, item.awardee_name, item.agency, item.text)
        if value
    )
    if collected and extracted_fields < rules.min_extracted_fields:
        logger.warning(
            "Defense.gov 항목 필드 부족(%d/%d)으로 제외 — %s",
            extracted_fields,
            rules.min_extracted_fields,
            item.text[:80],
        )
        collected = False

    reasons = {
        "amount_usd": amount,
        "strong_keyword_matched": strong_matched,
        "matched_keywords": matched_keywords,
        "extracted_fields": extracted_fields,
    }
    return collected, reasons


class DefenseGovCollector(MacroCollector):
    source_id = "US_DEFENSE_CONTRACTS"

    # lookback 7일: 주말·연방 공휴일 연휴에 발표 갭이 생겨도 다음 실행이 포착하도록
    # 넉넉히 잡는다 — upsert가 멱등이라 재수집 비용은 없다 (RSS max=10 ≈ 2주 분량).
    def __init__(self, lookback_days: int = 7) -> None:
        self._lookback_days = lookback_days
        self._rules = load_defense_rules()
        self._keyword_map = load_keyword_domain_map()

    async def collect(self, session: AsyncSession) -> list[NormalizedMacroEvent]:
        events: list[NormalizedMacroEvent] = []
        cutoff = now_kst() - timedelta(days=self._lookback_days)

        async with httpx.AsyncClient(
            headers={"User-Agent": _BROWSER_UA},
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        ) as client:
            rss_response = await client.get(_RSS_URL, params=_RSS_PARAMS)
            rss_response.raise_for_status()
            articles = [
                article
                for article in parse_rss_articles(rss_response.text)
                if article.published_at_kst >= cutoff
            ]
            logger.info(
                "Defense.gov Contracts 기사 %d건 (lookback %d일)",
                len(articles),
                self._lookback_days,
            )

            for article in articles:
                article_response = await client.get(article.url)
                article_response.raise_for_status()
                items = parse_contract_items(article_response.text)
                if not items:
                    logger.warning(
                        "Defense.gov 기사 본문 파싱 0건 — article_id=%s", article.article_id
                    )
                    continue
                for item in items:
                    collected, reasons = passes_collect_filter(
                        item, self._rules, self._keyword_map
                    )
                    if not collected:
                        continue
                    events.append(self._build_event(article, item, reasons))
        return events

    def _build_event(
        self,
        article: ContractArticle,
        item: ContractItem,
        filter_reasons: dict[str, Any],
    ) -> NormalizedMacroEvent:
        # 기사 내 항목에는 고유 ID가 없어 본문 해시로 정의한다(§7.2 발표 항목 ID [정의 신규]).
        # 항목 순서 변경에 흔들리지 않고, 본문 수정 시 새 이벤트가 된다(오연결보다 중복 허용).
        text_digest = hashlib.sha256(item.text.encode("utf-8")).hexdigest()[:16]

        linked_entities: list[dict[str, Any]] | None = None
        if item.awardee_name is not None:
            linked_entities = [{"role": "AWARDEE", "name": item.awardee_name}]

        amount_label = f"${item.amount_usd:,}" if item.amount_usd is not None else ""
        headline = item.awardee_name or item.text[:_TITLE_EXCERPT_CHARS]
        return NormalizedMacroEvent(
            event_unique_id=f"{article.article_id}-{text_digest}",
            event_type=MacroEventType.MEGA_CONTRACT,
            title=f"DoD contract ({item.agency or 'UNKNOWN'}): {headline} {amount_label}".strip(),
            summary=None,
            source_published_at=article.published_at_kst,
            publicly_observable_at=article.published_at_kst,
            latency_reference_type=LatencyReferenceType.PUBLISHED_AT,
            certainty_level=CertaintyLevel(self._rules.certainty_level),
            event_status=(
                EventStatus.ACTIVE if item.contract_numbers else EventStatus.ACTIVE_UNLINKED
            ),
            linked_entities=linked_entities,
            raw_payload={
                "article_id": article.article_id,
                "article_title": article.title,
                "agency": item.agency,
                "amount_usd": item.amount_usd,
                "awardee_name": item.awardee_name,
                "contract_numbers": item.contract_numbers,
                "modification_number": item.modification_number,
                "is_modification": item.is_modification,
                "previously_awarded_number": item.previously_awarded_number,
                # Magnitude·Certainty 조정 플래그 (§6.7) — 판정은 Phase 3
                "indefinite_delivery": item.indefinite_delivery,
                "ceiling_value": item.ceiling_value,
                "filter_reasons": filter_reasons,
            },
            raw_text=item.text[:_RAW_TEXT_MAX_CHARS],
            source_url=article.url,
        )
