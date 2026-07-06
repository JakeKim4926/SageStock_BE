"""Federal Register collector — PRESIDENTIAL_ACTION CONFIRMATION (SPEC §6.8).

공식 JSON API(federalregister.gov/api/v1/documents)로 Presidential Documents를 수집한다.
문서 타입은 서버 필터(presidential_document_type) + 응답 subtype 재확인 이중으로,
config document_types(EO/Memorandum/Proclamation) 밖(Determination/Notice 등)은 수집 안 함.

체인 식별자(§7.2): document_number(FR 단독 chain key)가 항상 있어 event_status=ACTIVE.
executive_order_number / proclamation_number는 WH↔FR 체인(§7.3) 재료로 raw_payload 보존 —
연결 자체는 Phase 2 Chain Resolve 소유.

시각: publication_date는 날짜뿐이라 SAM.gov posted_date와 같은 규약으로 ET 자정 기준
KST 변환. signing_date는 document_signed_at으로 별도 저장하되 latency 기준으로 쓰지
않는다(§13.1 — 서명 시점은 비공개였을 수 있음).
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.batch.macro_collectors.base import MacroCollector
from app.constants.macro_enums import (
    CertaintyLevel,
    LatencyReferenceType,
    MacroEventType,
)
from app.services.macro_events.config_loader import load_event_type_rules
from app.services.macro_events.normalize import NormalizedMacroEvent, now_kst, to_kst

logger = logging.getLogger(__name__)

_API_URL = "https://www.federalregister.gov/api/v1/documents.json"
_USER_AGENT = "SageStock-macro-event-engine/1.0 (batch collector)"
_HTTP_TIMEOUT = 30.0
# 프로브 중 일시적 503 관찰 — 일 1~2회 cadence라 실행 1회 실패 비용이 커서 짧게 재시도
_RETRY_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 3.0
_US_EASTERN = ZoneInfo("America/New_York")
# API presidential_document_type 조건값 ↔ 응답 subtype ↔ config document_types 표기
_QUERY_DOCUMENT_TYPES = ("executive_order", "memorandum", "proclamation")
_SUBTYPE_TO_DOCUMENT_TYPE = {
    "Executive Order": "Executive Order",
    "Memorandum": "Presidential Memorandum",
    "Proclamation": "Proclamation",
}
_RESPONSE_FIELDS = (
    "document_number",
    "title",
    "abstract",
    "subtype",
    "executive_order_number",
    "proclamation_number",
    "presidential_document_number",
    "signing_date",
    "publication_date",
    "citation",
    "html_url",
    "raw_text_url",
)


@dataclass(frozen=True)
class FederalRegisterRules:
    """event_type_rules.yaml US_FEDERAL_REGISTER에서 뽑은 값."""

    document_types: tuple[str, ...]
    certainty_level: str


def load_federal_register_rules() -> FederalRegisterRules:
    source = load_event_type_rules().event_types["PRESIDENTIAL_ACTION"]["sources"][
        "US_FEDERAL_REGISTER"
    ]
    return FederalRegisterRules(
        document_types=tuple(source["document_types"]),
        certainty_level=str(source["certainty_level"]),
    )


def detect_document_type(
    subtype: str, allowed_types: tuple[str, ...]
) -> str | None:
    """응답 subtype → config 문서 타입. config 밖 타입이면 None(수집 안 함)."""
    document_type = _SUBTYPE_TO_DOCUMENT_TYPE.get(subtype)
    if document_type is None or document_type not in allowed_types:
        return None
    return document_type


def _date_to_kst(date_text: str | None) -> datetime | None:
    """YYYY-MM-DD(날짜만) → ET 자정 기준 KST (SAM.gov posted_date와 동일 규약)."""
    if not date_text:
        return None
    return to_kst(datetime.strptime(date_text, "%Y-%m-%d"), source_tz=_US_EASTERN)


class FederalRegisterCollector(MacroCollector):
    source_id = "US_FEDERAL_REGISTER"

    def __init__(self, lookback_days: int = 3) -> None:
        self._lookback_days = lookback_days
        self._rules = load_federal_register_rules()

    async def collect(self, session: AsyncSession) -> list[NormalizedMacroEvent]:
        documents = await self._fetch_documents()
        logger.info(
            "Federal Register Presidential Documents %d건 (lookback %d일)",
            len(documents),
            self._lookback_days,
        )

        events: list[NormalizedMacroEvent] = []
        for document in documents:
            event = self._build_event(document)
            if event is not None:
                events.append(event)
        return events

    async def _fetch_documents(self) -> list[dict[str, Any]]:
        publication_from = (now_kst() - timedelta(days=self._lookback_days)).date()
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("per_page", "100"),
            ("order", "newest"),
            ("conditions[type][]", "PRESDOCU"),
            ("conditions[publication_date][gte]", publication_from.isoformat()),
        ]
        params += [
            ("conditions[presidential_document_type][]", value)
            for value in _QUERY_DOCUMENT_TYPES
        ]
        params += [("fields[]", field) for field in _RESPONSE_FIELDS]

        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT}, timeout=_HTTP_TIMEOUT
        ) as client:
            for attempt in range(1, _RETRY_ATTEMPTS + 1):
                response = await client.get(_API_URL, params=params)
                if response.status_code < 500 or attempt == _RETRY_ATTEMPTS:
                    break
                logger.warning(
                    "Federal Register API %d — 재시도 %d/%d",
                    response.status_code,
                    attempt,
                    _RETRY_ATTEMPTS,
                )
                await asyncio.sleep(_RETRY_DELAY_SECONDS)
            response.raise_for_status()

        data: dict[str, Any] = response.json()
        results: list[dict[str, Any]] = data.get("results") or []
        total = int(data.get("count") or 0)
        if total > len(results):
            # lookback 며칠치 Presidential Documents가 100건을 넘는 일은 사실상 없다
            logger.warning(
                "Federal Register 페이지 상한 — count=%d 중 %d건만 처리", total, len(results)
            )
        return results

    def _build_event(self, document: dict[str, Any]) -> NormalizedMacroEvent | None:
        document_type = detect_document_type(
            str(document.get("subtype") or ""), self._rules.document_types
        )
        if document_type is None:
            return None  # 서버 필터를 통과했어도 config 밖 타입은 재확인 후 제외

        document_number = str(document.get("document_number") or "").strip()
        title = str(document.get("title") or "").strip()
        observable_at = _date_to_kst(document.get("publication_date"))
        source_url = str(document.get("html_url") or "").strip()
        if not document_number or not title or observable_at is None or not source_url:
            logger.warning(
                "Federal Register 필수 필드 결손 — 수집 제외: document_number=%s",
                document_number or "(없음)",
            )
            return None

        abstract = str(document.get("abstract") or "").strip() or None
        return NormalizedMacroEvent(
            event_unique_id=document_number,
            event_type=MacroEventType.PRESIDENTIAL_ACTION,
            title=f"Federal Register {document_type}: {title}",
            summary=abstract,
            document_signed_at=_date_to_kst(document.get("signing_date")),
            source_published_at=observable_at,
            publicly_observable_at=observable_at,
            latency_reference_type=LatencyReferenceType.PUBLISHED_AT,
            certainty_level=CertaintyLevel(self._rules.certainty_level),
            # document_number가 FR 단독 chain key(§7.2) — 명시 식별자 항상 존재
            linked_entities=None,  # FR 원문 매핑에 구조화 entity 없음 (§11)
            raw_payload={
                "document_number": document_number,
                "document_type": document_type,
                "subtype": document.get("subtype"),
                "executive_order_number": document.get("executive_order_number"),
                "proclamation_number": document.get("proclamation_number"),
                "presidential_document_number": document.get(
                    "presidential_document_number"
                ),
                "signing_date": document.get("signing_date"),
                "publication_date": document.get("publication_date"),
                "citation": document.get("citation"),
                "raw_text_url": document.get("raw_text_url"),
            },
            source_url=source_url,
        )
