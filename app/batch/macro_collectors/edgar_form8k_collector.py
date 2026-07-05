"""SEC 8-K collector — MEGA_CONTRACT (SPEC §6.3).

수집 대상(정본: event_type_rules.yaml → US_SEC_8K.items):
- Item 1.01 (Entry into a Material Definitive Agreement): 기본 L4 수집.
  상대방·금액·기간 여부는 raw_payload 플래그로 기록 (L5 승격 판단은 Phase 2~3)
- Item 8.01 (Other Events): 조건부 L3 — 안전장치 전부 충족해야 수집:
  strong signal 키워드 2개 이상 + (금액/기관/award 문구 중 1개 이상).
  contract/government/agreement 같은 일반 단어는 strong 목록에 없어 단독 수집 불가
- excluded_items(1.02, 2.01 등)만 있는 filing은 수집 안 함. 8-K/A는 v1 제외

주의: counterparty_named 검출은 v1 미구현(NER 필요) — require_one_of 판정은
금액/기관/award로만 하며 그만큼 보수적(과소 수집 방향)이다.
"""
import html
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.batch.macro_collectors.base import MacroCollector
from app.batch.macro_collectors.edgar_client import (
    EdgarClient,
    EdgarFiling,
    extract_acceptance_datetime,
    extract_header_cik,
    extract_header_company_name,
)
from app.constants.macro_enums import (
    CertaintyLevel,
    LatencyReferenceType,
    MacroEventType,
)
from app.services.macro_events.config_loader import load_event_type_rules
from app.services.macro_events.normalize import NormalizedMacroEvent

logger = logging.getLogger(__name__)

_FORM_TYPE = "8-K"
# SGML 헤더 ITEM INFORMATION 설명 → item 코드 (수집 대상 2종만 매핑)
_ITEM_DESCRIPTIONS = {
    "Entry into a Material Definitive Agreement": "1.01",
    "Other Events": "8.01",
}
_ITEM_INFORMATION_PATTERN = re.compile(r"ITEM INFORMATION:\s*([^\r\n]+)")
_DOCUMENT_PATTERN = re.compile(
    r"<DOCUMENT>\s*<TYPE>8-K.*?<TEXT>(.*?)</TEXT>", re.DOTALL
)
_TAG_PATTERN = re.compile(r"<[^>]+>")
_AMOUNT_PATTERN = re.compile(r"\$\s?\d")
_AWARD_PATTERN = re.compile(r"\baward(?:ed|s)?\b", re.IGNORECASE)
# require_one_of의 agency_named 판정용 (§6.3 안전장치 4)
_AGENCY_TERMS = (
    "NASA",
    "DoD",
    "DOE",
    "DARPA",
    "Department of Defense",
    "Department of Energy",
)
# raw_text 보존 상한 — 도메인 할당(§9.2)은 본문 전체 매칭 금지라 감사용으로만 둔다.
_RAW_TEXT_MAX_CHARS = 5_000
_TITLE_EXCERPT_CHARS = 120


@dataclass(frozen=True)
class Form8KSignals:
    """8.01 안전장치·1.01 L5 후보 판정 재료."""

    matched_strong_keywords: list[str]
    amount_stated: bool
    agency_named: bool
    award_language: bool


def _collect_rules() -> dict[str, Any]:
    sources = load_event_type_rules().event_types["MEGA_CONTRACT"]["sources"]
    return dict(sources["US_SEC_8K"])


def extract_item_codes(filing_text: str) -> set[str]:
    """SGML 헤더 ITEM INFORMATION → 수집 대상 item 코드 집합(1.01/8.01만)."""
    codes: set[str] = set()
    for description in _ITEM_INFORMATION_PATTERN.findall(filing_text):
        code = _ITEM_DESCRIPTIONS.get(description.strip())
        if code is not None:
            codes.add(code)
    return codes


def extract_body_text(filing_text: str) -> str:
    """8-K 본문 문서(HTML)를 평문으로. 문서 블록이 없으면 빈 문자열."""
    match = _DOCUMENT_PATTERN.search(filing_text)
    if match is None:
        return ""
    stripped = _TAG_PATTERN.sub(" ", match.group(1))
    return " ".join(html.unescape(stripped).split())


def match_strong_keywords(body_text: str, strong_keywords: list[str]) -> list[str]:
    """strong signal 키워드 매칭 — 구(phrase)는 부분 문자열, 단어는 word boundary.

    contract/government/agreement 같은 일반 단어는 strong 목록에 없으므로
    여기서 절대 매칭되지 않는다 (§6.3 안전장치 3)."""
    lowered = body_text.lower()
    matched = []
    for keyword in strong_keywords:
        needle = keyword.lower()
        if " " in needle or "-" in needle:
            if needle in lowered:
                matched.append(keyword)
        elif re.search(rf"\b{re.escape(needle)}\b", lowered):
            matched.append(keyword)
    return matched


def detect_signals(body_text: str, strong_keywords: list[str]) -> Form8KSignals:
    return Form8KSignals(
        matched_strong_keywords=match_strong_keywords(body_text, strong_keywords),
        amount_stated=_AMOUNT_PATTERN.search(body_text) is not None,
        agency_named=any(
            re.search(rf"\b{re.escape(term)}\b", body_text, re.IGNORECASE)
            for term in _AGENCY_TERMS
        ),
        award_language=_AWARD_PATTERN.search(body_text) is not None,
    )


def passes_801_filter(signals: Form8KSignals, item_rules: dict[str, Any]) -> bool:
    """Item 8.01 안전장치 (SPEC §6.3 — 전부 충족해야 수집)."""
    collect_if = item_rules["collect_if"]
    if len(signals.matched_strong_keywords) < int(collect_if["min_strong_signal_keywords"]):
        return False
    # require_one_of 중 counterparty_named는 v1 미구현 — 나머지 3개로 판정(보수적).
    return signals.amount_stated or signals.agency_named or signals.award_language


class EdgarForm8KCollector(MacroCollector):
    source_id = "US_SEC_EDGAR"

    def __init__(self, feed_count: int = 100) -> None:
        self._feed_count = feed_count
        self._rules = _collect_rules()

    async def collect(self, session: AsyncSession) -> list[NormalizedMacroEvent]:
        events: list[NormalizedMacroEvent] = []
        async with EdgarClient() as client:
            filings = await client.fetch_recent_filings(
                _FORM_TYPE, count=self._feed_count, include_types=(_FORM_TYPE,)
            )
            logger.info("EDGAR 8-K 피드 %d건 조회", len(filings))
            for filing in filings:
                filing_text = await client.fetch_filing_text(
                    filing.cik, filing.accession_number
                )
                event = self._build_event(filing, filing_text)
                if event is not None:
                    events.append(event)
        return events

    def _build_event(
        self, filing: EdgarFiling, filing_text: str
    ) -> NormalizedMacroEvent | None:
        item_codes = extract_item_codes(filing_text)
        if not item_codes:
            return None  # 수집 대상 item(1.01/8.01) 없음 — excluded item만 있는 filing 포함

        accepted_at_kst = extract_acceptance_datetime(filing_text)
        issuer_cik = extract_header_cik(filing_text, "FILER")
        issuer_name = extract_header_company_name(filing_text, "FILER")
        if accepted_at_kst is None or issuer_cik is None or issuer_name is None:
            logger.warning(
                "8-K 헤더 추출 실패 accession=%s — 수집 제외", filing.accession_number
            )
            return None

        body_text = extract_body_text(filing_text)
        item_rules = self._rules["items"]

        if "1.01" in item_codes:
            item_code = "1.01"
            signals = detect_signals(body_text, [])
        else:
            item_code = "8.01"
            signals = detect_signals(
                body_text, list(item_rules["8.01"]["strong_signal_keywords"])
            )
            if not passes_801_filter(signals, item_rules["8.01"]):
                return None

        certainty = CertaintyLevel(str(item_rules[item_code]["certainty_level"]))
        item_label = _ITEM_LABELS[item_code]
        excerpt = body_text[:_TITLE_EXCERPT_CHARS]
        return NormalizedMacroEvent(
            event_unique_id=filing.accession_number,
            event_type=MacroEventType.MEGA_CONTRACT,
            title=f"8-K Item {item_code} ({item_label}): {issuer_name} — {excerpt}",
            summary=None,
            source_published_at=accepted_at_kst,
            publicly_observable_at=accepted_at_kst,
            latency_reference_type=LatencyReferenceType.FILING_ACCEPTED_AT,
            certainty_level=certainty,
            linked_entities=[
                {"role": "ISSUER", "name": issuer_name, "cik": issuer_cik}
            ],
            raw_payload={
                "form_type": _FORM_TYPE,
                "accession_number": filing.accession_number,
                "item_code": item_code,
                "item_codes_present": sorted(item_codes),
                "issuer_cik": issuer_cik,
                # L5 승격 후보 판단 재료 (1.01, SPEC §6.3) — 판정은 Phase 2~3
                "amount_stated": signals.amount_stated,
                "agency_named": signals.agency_named,
                "award_language": signals.award_language,
                "matched_strong_keywords": signals.matched_strong_keywords,
            },
            raw_text=body_text[:_RAW_TEXT_MAX_CHARS] or None,
            source_url=filing.filing_url,
        )


_ITEM_LABELS = {
    "1.01": "Material Definitive Agreement",
    "8.01": "Other Events",
}
