"""USAspending collector — MEGA_CONTRACT CONFIRMATION/OUTCOME (SPEC §6.2).

수집 조건(정본: event_type_rules.yaml → US_USASPENDING):
- 신규 award만 (time_period date_type=new_awards_only) + 금액 >= min_award_amount_usd($50M)
- modification은 새 이벤트 생성 금지 (create_new_event=false) — 이 collector는 신규만
  조회하므로 mod로 이벤트가 만들어질 경로가 없다. delta $10M+ 체인 follow-through 반영은
  Phase 2 Chain Resolve 잡(연결 키: award_id / contract_award_unique_key, 없으면 버림)

키 불필요 공개 API. 계약(award_type_codes A~D)만 대상.
publicly_observable_at은 award publication 기준(§4) — Base Obligation Date를 쓰고
없으면 Start Date로 폴백한다(date 단위 → ET 자정 → KST).
"""
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

_API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
_HTTP_TIMEOUT = 30.0
_US_EASTERN = ZoneInfo("America/New_York")
# 계약 award 타입 (BPA Call / Purchase Order / Delivery Order / Definitive Contract)
_CONTRACT_AWARD_TYPE_CODES = ("A", "B", "C", "D")
_PAGE_LIMIT = 100
_MAX_PAGES = 5
_FIELDS = (
    "Award ID",
    "Recipient Name",
    "Recipient UEI",
    "Award Amount",
    "Description",
    "Start Date",
    "End Date",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Base Obligation Date",
    "generated_internal_id",
)


@dataclass(frozen=True)
class UsaSpendingRules:
    min_award_amount_usd: float
    certainty_level: str


def load_usaspending_rules() -> UsaSpendingRules:
    source = load_event_type_rules().event_types["MEGA_CONTRACT"]["sources"]["US_USASPENDING"]
    return UsaSpendingRules(
        min_award_amount_usd=float(source["collect_if"]["min_award_amount_usd"]),
        certainty_level=str(source["certainty_level"]),
    )


def build_search_payload(
    start_date: str, end_date: str, min_amount: float, page: int
) -> dict[str, Any]:
    """spending_by_award 요청 — 신규 award만(new_awards_only) + 금액 하한 서버 필터."""
    return {
        "filters": {
            "time_period": [
                {
                    "start_date": start_date,
                    "end_date": end_date,
                    "date_type": "new_awards_only",
                }
            ],
            "award_type_codes": list(_CONTRACT_AWARD_TYPE_CODES),
            "award_amounts": [{"lower_bound": min_amount}],
        },
        "fields": list(_FIELDS),
        "sort": "Award Amount",
        "order": "desc",
        "limit": _PAGE_LIMIT,
        "page": page,
    }


def build_event(
    result: dict[str, Any], rules: UsaSpendingRules
) -> NormalizedMacroEvent | None:
    """검색 결과 한 건 → 이벤트. 식별자·금액·날짜가 부족하면 None (추측 금지)."""
    unique_key = str(result.get("generated_internal_id") or "").strip()
    recipient = str(result.get("Recipient Name") or "").strip()
    amount_raw = result.get("Award Amount")
    if not unique_key or not recipient or amount_raw is None:
        return None

    amount = float(amount_raw)
    if amount < rules.min_award_amount_usd:
        return None  # 서버 필터가 있어도 정본 config 기준으로 재확인

    observable_date = str(
        result.get("Base Obligation Date") or result.get("Start Date") or ""
    ).strip()
    if not observable_date:
        return None
    observable_at = to_kst(
        datetime.strptime(observable_date[:10], "%Y-%m-%d"), source_tz=_US_EASTERN
    )

    agency = str(result.get("Awarding Agency") or "").strip()
    sub_agency = str(result.get("Awarding Sub Agency") or "").strip()
    award_id = str(result.get("Award ID") or "").strip() or None
    recipient_uei = str(result.get("Recipient UEI") or "").strip() or None

    return NormalizedMacroEvent(
        event_unique_id=unique_key,
        event_type=MacroEventType.MEGA_CONTRACT,
        title=(
            f"USAspending award: {recipient} — ${amount:,.0f}"
            f" ({sub_agency or agency})"
        ),
        summary=(str(result.get("Description") or "").strip() or None),
        source_published_at=observable_at,
        publicly_observable_at=observable_at,
        latency_reference_type=LatencyReferenceType.PUBLISHED_AT,
        certainty_level=CertaintyLevel(rules.certainty_level),
        linked_entities=[
            {"role": "RECIPIENT", "name": recipient, "uei": recipient_uei}
        ],
        raw_payload={
            # 체인 연결 키 (§7.2): award_id 또는 contract_award_unique_key
            "award_id": award_id,
            "contract_award_unique_key": unique_key,
            "award_amount_usd": amount,
            "awarding_agency": agency,
            "awarding_sub_agency": sub_agency,
            "base_obligation_date": str(result.get("Base Obligation Date") or "") or None,
            "start_date": str(result.get("Start Date") or "") or None,
            "end_date": str(result.get("End Date") or "") or None,
        },
        source_url=f"https://www.usaspending.gov/award/{unique_key}",
    )


class UsaSpendingCollector(MacroCollector):
    source_id = "US_USASPENDING"

    def __init__(self, lookback_days: int = 7) -> None:
        self._lookback_days = lookback_days
        self._rules = load_usaspending_rules()

    async def collect(self, session: AsyncSession) -> list[NormalizedMacroEvent]:
        results = await self._fetch_new_awards()
        logger.info("USAspending 신규 award %d건 조회", len(results))

        events = []
        for result in results:
            event = build_event(result, self._rules)
            if event is not None:
                events.append(event)
        return events

    async def _fetch_new_awards(self) -> list[dict[str, Any]]:
        today = now_kst().date()
        start_date = (today - timedelta(days=self._lookback_days)).isoformat()
        end_date = today.isoformat()

        results: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            for page in range(1, _MAX_PAGES + 1):
                payload = build_search_payload(
                    start_date, end_date, self._rules.min_award_amount_usd, page
                )
                response = await client.post(_API_URL, json=payload)
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                results.extend(data.get("results") or [])
                if not (data.get("page_metadata") or {}).get("hasNext"):
                    break
        return results
