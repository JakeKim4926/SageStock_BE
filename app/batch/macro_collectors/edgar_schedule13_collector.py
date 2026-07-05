"""SEC 13D/13G collector — INSTITUTIONAL_CAPITAL_SHIFT (SPEC §6.5).

수집 조건(정본: event_type_rules.yaml → US_SEC_13D_13G.collect_if):
- 신규 SC 13D / SC 13G 수집
- amendment(SC 13D/A·SC 13G/A)는 직전 관찰 지분율 대비
  min_amendment_ownership_change_pct_point(1.0%p) 이상 변화만.
  직전 관찰이 DB에 없으면 첫 관찰로 보고 수집, 현재 지분율을 못 읽으면 수집 제외.
- 13G 분기 마감 급증은 장애가 아니라 예상 부하 — feed_count가 회당 처리 상한 역할
  (batch_surge_policy.daily_processing_cap_allowed)

CIK는 피드 entry가 Subject/Filed-by로 갈려 모호하므로 filing 전문 SGML 헤더의
SUBJECT COMPANY / FILED BY 섹션에서 추출한다.
"""
import logging
import xml.etree.ElementTree as ET
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
    iter_embedded_xml,
)
from app.constants.macro_enums import (
    CertaintyLevel,
    LatencyReferenceType,
    MacroEventType,
)
from app.repositories import macro_event_repository
from app.services.macro_events.config_loader import load_event_type_rules
from app.services.macro_events.normalize import NormalizedMacroEvent

logger = logging.getLogger(__name__)

# getcurrent type 파라미터는 prefix 매칭 → 쿼리별로 본형+amendment만 수용.
# 주의: 2024-12 구조화 데이터 의무화 이후 EDGAR 폼 타입은 "SC 13D"가 아니라
# "SCHEDULE 13D"다 (실피드 확인 2026-07-05).
_QUERIES: dict[str, tuple[str, ...]] = {
    "SCHEDULE 13D": ("SCHEDULE 13D", "SCHEDULE 13D/A"),
    "SCHEDULE 13G": ("SCHEDULE 13G", "SCHEDULE 13G/A"),
}


@dataclass(frozen=True)
class Schedule13Summary:
    form_type: str
    form_family: str  # "13D" | "13G" (chain_key 구성요소, §7.2)
    is_amendment: bool
    subject_company_name: str
    subject_company_cik: str
    filer_name: str
    filer_cik: str
    percent_of_class: float | None


def _collect_rules() -> dict[str, Any]:
    sources = load_event_type_rules().event_types["INSTITUTIONAL_CAPITAL_SHIFT"]["sources"]
    return dict(sources["US_SEC_13D_13G"])


def _parse_percent(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = text.strip().rstrip("%").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_percent_of_class(filing_text: str) -> float | None:
    """내장 구조화 XML에서 percentOfClass(로컬 네임 매칭, 네임스페이스 무관).

    reporting person이 여럿이면 최대값을 대표 지분율로 쓴다."""
    percents: list[float] = []
    for xml_body in iter_embedded_xml(filing_text):
        if "percentOfClass" not in xml_body:
            continue
        try:
            root = ET.fromstring(xml_body)
        except ET.ParseError:
            continue
        for element in root.iter():
            if element.tag.split("}")[-1] == "percentOfClass":
                value = _parse_percent(element.text)
                if value is not None:
                    percents.append(value)
    return max(percents) if percents else None


def parse_schedule13(filing_text: str, form_type: str) -> Schedule13Summary | None:
    """SGML 헤더 + 내장 XML → 요약. 필수 식별자(양쪽 CIK) 없으면 None."""
    subject_cik = extract_header_cik(filing_text, "SUBJECT COMPANY")
    filer_cik = extract_header_cik(filing_text, "FILED BY")
    if subject_cik is None or filer_cik is None:
        return None

    return Schedule13Summary(
        form_type=form_type,
        form_family="13D" if "13D" in form_type else "13G",
        is_amendment=form_type.endswith("/A"),
        subject_company_name=(
            extract_header_company_name(filing_text, "SUBJECT COMPANY") or "UNKNOWN"
        ),
        subject_company_cik=subject_cik,
        filer_name=extract_header_company_name(filing_text, "FILED BY") or "UNKNOWN",
        filer_cik=filer_cik,
        percent_of_class=extract_percent_of_class(filing_text),
    )


class EdgarSchedule13Collector(MacroCollector):
    source_id = "US_SEC_EDGAR"

    def __init__(self, feed_count: int = 100) -> None:
        self._feed_count = feed_count
        self._rules = _collect_rules()

    async def collect(self, session: AsyncSession) -> list[NormalizedMacroEvent]:
        events: list[NormalizedMacroEvent] = []
        async with EdgarClient() as client:
            for query_type, include_types in _QUERIES.items():
                filings = await client.fetch_recent_filings(
                    query_type, count=self._feed_count, include_types=include_types
                )
                logger.info("EDGAR %s 피드 %d건 조회", query_type, len(filings))
                for filing in filings:
                    filing_text = await client.fetch_filing_text(
                        filing.cik, filing.accession_number
                    )
                    event = await self._build_event(session, filing, filing_text)
                    if event is not None:
                        events.append(event)
        return events

    async def _build_event(
        self,
        session: AsyncSession,
        filing: EdgarFiling,
        filing_text: str,
    ) -> NormalizedMacroEvent | None:
        accepted_at_kst = extract_acceptance_datetime(filing_text)
        summary = parse_schedule13(filing_text, filing.form_type)
        if accepted_at_kst is None or summary is None:
            logger.warning(
                "13D/G 문서 추출 실패 accession=%s — 수집 제외", filing.accession_number
            )
            return None

        if not await self._passes_filter(session, summary):
            return None

        percent_label = (
            f"{summary.percent_of_class:.1f}%"
            if summary.percent_of_class is not None
            else "지분율 미표기"
        )
        linked_entities: list[dict[str, Any]] = [
            {
                "role": "SUBJECT_COMPANY",
                "name": summary.subject_company_name,
                "cik": summary.subject_company_cik,
            },
            {"role": "FILER", "name": summary.filer_name, "cik": summary.filer_cik},
        ]
        return NormalizedMacroEvent(
            event_unique_id=filing.accession_number,
            event_type=MacroEventType.INSTITUTIONAL_CAPITAL_SHIFT,
            title=(
                f"{summary.form_type}: {summary.filer_name} → "
                f"{summary.subject_company_name} ({percent_label})"
            ),
            summary=None,
            source_published_at=accepted_at_kst,
            publicly_observable_at=accepted_at_kst,
            latency_reference_type=LatencyReferenceType.FILING_ACCEPTED_AT,
            certainty_level=CertaintyLevel(str(self._rules["certainty_level"])),
            linked_entities=linked_entities,
            raw_payload={
                "form_type": summary.form_type,
                "form_family": summary.form_family,
                "is_amendment": summary.is_amendment,
                "accession_number": filing.accession_number,
                "subject_company_cik": summary.subject_company_cik,
                "subject_company_name": summary.subject_company_name,
                "filer_cik": summary.filer_cik,
                "filer_name": summary.filer_name,
                "percent_of_class": summary.percent_of_class,
            },
            source_url=filing.filing_url,
        )

    async def _passes_filter(
        self, session: AsyncSession, summary: Schedule13Summary
    ) -> bool:
        collect_if = self._rules["collect_if"]

        if not summary.is_amendment:
            flag = "collect_new_13d" if summary.form_family == "13D" else "collect_new_13g"
            return bool(collect_if[flag])

        # amendment: 직전 관찰 지분율과 비교 (SPEC §6.5)
        if summary.percent_of_class is None:
            logger.info(
                "%s/A 지분율 미확인 → 수집 제외 filer=%s subject=%s",
                summary.form_family,
                summary.filer_cik,
                summary.subject_company_cik,
            )
            return False

        previous = await macro_event_repository.get_latest_13dg_event(
            session,
            source_id=self.source_id,
            filer_cik=summary.filer_cik,
            subject_company_cik=summary.subject_company_cik,
            form_family=summary.form_family,
        )
        if previous is None or previous.raw_payload is None:
            return True  # 직전 관찰 없음 → 첫 관찰로 수집

        previous_percent = previous.raw_payload.get("percent_of_class")
        if previous_percent is None:
            return True

        min_change = float(collect_if["min_amendment_ownership_change_pct_point"])
        return abs(summary.percent_of_class - float(previous_percent)) >= min_change
