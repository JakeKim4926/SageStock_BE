"""SEC Form 4 collector — INSTITUTIONAL_CAPITAL_SHIFT (SPEC §6.4).

수집 조건(정본: config/macro_events/event_type_rules.yaml → US_SEC_FORM4.collect_if):
- transaction_code P(공개시장 매수)만, 합산 거래금액 >= min_transaction_value_usd
- roles: officer / director / ten_percent_owner 중 하나 이상
- option 행사·grant 등은 transaction_code 필터(P only)로 배제된다

주의: 지분 공시는 실제 매수 시점 선점 데이터가 아니다 — 엣지는 filing 공개 후
확산 전 포착이며 publicly_observable_at = filing accepted time (SPEC §4).
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
    iter_embedded_xml,
)
from app.constants.macro_enums import (
    CertaintyLevel,
    LatencyReferenceType,
    MacroEventType,
)
from app.services.macro_events.config_loader import load_event_type_rules
from app.services.macro_events.normalize import NormalizedMacroEvent

logger = logging.getLogger(__name__)

_FORM_TYPE = "4"


@dataclass(frozen=True)
class Form4Summary:
    """Form 4 XML에서 추출한 필터 판정 재료."""

    issuer_name: str
    issuer_cik: str
    issuer_ticker: str | None
    owner_name: str
    owner_cik: str | None
    is_officer: bool
    is_director: bool
    is_ten_percent_owner: bool
    total_purchase_value_usd: float


def _collect_rules() -> dict[str, Any]:
    sources = load_event_type_rules().event_types["INSTITUTIONAL_CAPITAL_SHIFT"]["sources"]
    return dict(sources["US_SEC_FORM4"])


def extract_ownership_xml(filing_text: str) -> str | None:
    for candidate in iter_embedded_xml(filing_text):
        if "<ownershipDocument" in candidate:
            return candidate
    return None


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true")


def parse_form4(ownership_xml: str) -> Form4Summary | None:
    """ownershipDocument XML → 요약. 형식이 어긋나면 None (수집 안 함, 추측 금지)."""
    try:
        root = ET.fromstring(ownership_xml)
    except ET.ParseError:
        logger.warning("Form 4 XML 파싱 실패", exc_info=True)
        return None

    issuer = root.find("issuer")
    owner = root.find("reportingOwner")
    if issuer is None or owner is None:
        return None

    issuer_cik = (issuer.findtext("issuerCik") or "").strip()
    issuer_name = (issuer.findtext("issuerName") or "").strip()
    if not issuer_cik or not issuer_name:
        return None

    relationship = owner.find("reportingOwnerRelationship")
    purchase_total = 0.0
    for transaction in root.iter("nonDerivativeTransaction"):
        code = (transaction.findtext("transactionCoding/transactionCode") or "").strip()
        if code != "P":
            continue
        shares = transaction.findtext(
            "transactionAmounts/transactionShares/value", default="0"
        )
        price = transaction.findtext(
            "transactionAmounts/transactionPricePerShare/value", default="0"
        )
        try:
            purchase_total += float(shares) * float(price)
        except ValueError:
            continue

    return Form4Summary(
        issuer_name=issuer_name,
        issuer_cik=issuer_cik.zfill(10),
        issuer_ticker=(issuer.findtext("issuerTradingSymbol") or "").strip() or None,
        owner_name=(owner.findtext("reportingOwnerId/rptOwnerName") or "").strip(),
        owner_cik=((owner.findtext("reportingOwnerId/rptOwnerCik") or "").strip() or None),
        is_officer=_is_true(
            relationship.findtext("isOfficer") if relationship is not None else None
        ),
        is_director=_is_true(
            relationship.findtext("isDirector") if relationship is not None else None
        ),
        is_ten_percent_owner=_is_true(
            relationship.findtext("isTenPercentOwner") if relationship is not None else None
        ),
        total_purchase_value_usd=purchase_total,
    )


def passes_collect_filter(summary: Form4Summary, collect_if: dict[str, Any]) -> bool:
    """SPEC §6.4 필터. 조건 값의 정본은 event_type_rules.yaml."""
    min_value = float(collect_if["min_transaction_value_usd"])
    if summary.total_purchase_value_usd < min_value:
        return False

    role_flags = {
        "officer": summary.is_officer,
        "director": summary.is_director,
        "ten_percent_owner": summary.is_ten_percent_owner,
    }
    allowed_roles = collect_if["allowed_roles"]
    return any(role_flags.get(role, False) for role in allowed_roles)


class EdgarForm4Collector(MacroCollector):
    source_id = "US_SEC_EDGAR"

    def __init__(self, feed_count: int = 100) -> None:
        self._feed_count = feed_count
        self._rules = _collect_rules()

    async def collect(self, session: AsyncSession) -> list[NormalizedMacroEvent]:
        events: list[NormalizedMacroEvent] = []
        async with EdgarClient() as client:
            filings = await client.fetch_recent_filings(_FORM_TYPE, count=self._feed_count)
            logger.info("EDGAR Form 4 피드 %d건 조회", len(filings))
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
        ownership_xml = extract_ownership_xml(filing_text)
        accepted_at_kst = extract_acceptance_datetime(filing_text)
        if ownership_xml is None or accepted_at_kst is None:
            logger.warning(
                "Form 4 문서 추출 실패 accession=%s — 수집 제외", filing.accession_number
            )
            return None

        summary = parse_form4(ownership_xml)
        if summary is None:
            return None
        if not passes_collect_filter(summary, self._rules["collect_if"]):
            return None

        # linked_entities는 원문 명시 entity만 (issuer + reporting owner). 추론 추가 금지.
        linked_entities: list[dict[str, Any]] = [
            {
                "role": "ISSUER",
                "name": summary.issuer_name,
                "cik": summary.issuer_cik,
                "ticker": summary.issuer_ticker,
            },
            {
                "role": "REPORTING_OWNER",
                "name": summary.owner_name,
                "cik": summary.owner_cik,
            },
        ]
        return NormalizedMacroEvent(
            event_unique_id=filing.accession_number,
            event_type=MacroEventType.INSTITUTIONAL_CAPITAL_SHIFT,
            title=(
                f"Form 4: {summary.owner_name} open-market purchase "
                f"~${summary.total_purchase_value_usd:,.0f} of {summary.issuer_name}"
            ),
            summary=None,
            source_published_at=accepted_at_kst,
            publicly_observable_at=accepted_at_kst,
            latency_reference_type=LatencyReferenceType.FILING_ACCEPTED_AT,
            certainty_level=CertaintyLevel(str(self._rules["certainty_level"])),
            linked_entities=linked_entities,
            raw_payload={
                "form_type": _FORM_TYPE,
                "accession_number": filing.accession_number,
                "issuer_cik": summary.issuer_cik,
                "issuer_ticker": summary.issuer_ticker,
                "owner_cik": summary.owner_cik,
                "total_purchase_value_usd": summary.total_purchase_value_usd,
                "is_officer": summary.is_officer,
                "is_director": summary.is_director,
                "is_ten_percent_owner": summary.is_ten_percent_owner,
            },
            source_url=filing.filing_url,
        )
