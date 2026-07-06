"""SAM.gov Opportunities collector — MEGA_CONTRACT LEAD (SPEC §6.1).

수집 조건(정본: event_type_rules.yaml → US_SAM_GOV, 임계값·agency 목록은 yaml에서 로드):
- 조건 A: estimated_value >= 대형 임계값($50M)
- 조건 B: 우선 agency AND estimated_value >= 소형 임계값($10M)
- 조건 C: 우선 agency AND strong domain keyword match
- 조건 D: strong keyword match AND estimated_value >= 소형 임계값
- estimated_value 부재 시: 우선 agency AND strong match만 수집
- 금지: agency 단독 매칭, solicitation_number 존재만으로 수집 (§6.1 — 필터에 그 경로 없음)

strong keyword 매칭(§6.1)은 keyword_domain_map.yaml 기준:
- title에서 phrase keyword 1개, 또는 title에서 같은 domain 핵심 keyword 2개 이상.
- summary 기반 기준(§6.1 세 번째)은 v1 미적용 — SAM 설명 본문은 별도 API 호출이 필요해
  일일 쿼터를 소모하므로 title만 쓴다(과소 수집 방향, description URL은 raw_payload 보존).

agency 매칭은 department + sub-tier 계층(fullParentPathName) 기준.
notice 갱신: 같은 noticeId 재게시=upsert 업데이트, type 전환은 새 notice로 들어와
새 이벤트가 되고 체인 승격은 Phase 2(chain_key = agency_code + solicitation_number).
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
from app.core.config import settings
from app.services.macro_events.config_loader import (
    KeywordDomainMap,
    load_event_type_rules,
    load_keyword_domain_map,
)
from app.services.macro_events.keyword_match import strong_keyword_match
from app.services.macro_events.normalize import NormalizedMacroEvent, now_kst, to_kst

logger = logging.getLogger(__name__)

_API_URL = "https://api.sam.gov/opportunities/v2/search"
_HTTP_TIMEOUT = 30.0
_US_EASTERN = ZoneInfo("America/New_York")
# SAM API ptype 코드 ↔ SPEC opportunity_type (r=sources sought, p=presolicitation,
# o=solicitation, a=award notice). Combined Synopsis 등 그 외 타입은 v1 제외.
_PTYPE_CODES = "r,p,o,a"
_TYPE_NORMALIZATION = {
    "Sources Sought": "sources_sought",
    "Presolicitation": "pre_solicitation",
    "Solicitation": "solicitation",
    "Award Notice": "award_notice",
}
# 우선 agency(NASA/DoD/DOE/DARPA)의 SAM fullParentPathName 표기 별칭.
# canonical 목록의 정본은 event_type_rules.yaml(agency_in) — 이건 SAM 표기 매핑이다.
_AGENCY_PATH_ALIASES: dict[str, tuple[str, ...]] = {
    "NASA": ("NATIONAL AERONAUTICS AND SPACE ADMINISTRATION", "NASA"),
    "DoD": ("DEPT OF DEFENSE", "DEPARTMENT OF DEFENSE"),
    "DOE": ("ENERGY, DEPARTMENT OF", "DEPARTMENT OF ENERGY"),
    "DARPA": ("DEFENSE ADVANCED RESEARCH PROJECTS AGENCY", "DARPA"),
}


@dataclass(frozen=True)
class SamOpportunity:
    """search 응답 opportunitiesData 한 건에서 필터·저장에 쓰는 필드."""

    notice_id: str
    title: str
    opportunity_type: str  # 정규화된 값 (sources_sought 등)
    solicitation_number: str | None
    agency_path_name: str
    agency_path_code: str
    posted_date: str
    response_deadline: str | None
    estimated_value_usd: float | None
    awardee_name: str | None
    awardee_uei: str | None
    description_url: str | None
    ui_link: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class SamCollectRules:
    """event_type_rules.yaml US_SAM_GOV에서 뽑은 필터 값."""

    priority_agencies: tuple[str, ...]
    large_value_threshold: float
    small_value_threshold: float
    certainty_by_type: dict[str, str]


def load_sam_rules() -> SamCollectRules:
    source = load_event_type_rules().event_types["MEGA_CONTRACT"]["sources"]["US_SAM_GOV"]

    thresholds: list[float] = []
    agencies: tuple[str, ...] = ()

    def walk(node: Any) -> None:
        nonlocal agencies
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "estimated_value_usd_gte":
                    thresholds.append(float(value))
                elif key == "agency_in" and not agencies:
                    agencies = tuple(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(source["collect_if"])
    if not thresholds or not agencies:
        raise ValueError("US_SAM_GOV collect_if에서 임계값/agency 목록을 찾지 못함")

    certainty_by_type = {
        name: str(rule["certainty_level"])
        for name, rule in source["opportunity_types"].items()
    }
    return SamCollectRules(
        priority_agencies=agencies,
        large_value_threshold=max(thresholds),
        small_value_threshold=min(thresholds),
        certainty_by_type=certainty_by_type,
    )


def parse_opportunity(data: dict[str, Any]) -> SamOpportunity | None:
    """응답 항목 → SamOpportunity. 수집 대상 4종 외 타입이면 None."""
    normalized_type = _TYPE_NORMALIZATION.get(str(data.get("type", "")))
    notice_id = str(data.get("noticeId", "")).strip()
    title = str(data.get("title", "")).strip()
    posted_date = str(data.get("postedDate", "")).strip()
    if normalized_type is None or not notice_id or not title or not posted_date:
        return None

    award = data.get("award") or {}
    awardee = award.get("awardee") or {}
    amount_text = str(award.get("amount", "")).replace(",", "").strip()
    try:
        estimated_value = float(amount_text) if amount_text else None
    except ValueError:
        estimated_value = None

    return SamOpportunity(
        notice_id=notice_id,
        title=title,
        opportunity_type=normalized_type,
        solicitation_number=(str(data.get("solicitationNumber") or "").strip() or None),
        agency_path_name=str(data.get("fullParentPathName", "")),
        agency_path_code=str(data.get("fullParentPathCode", "")),
        posted_date=posted_date,
        response_deadline=(str(data.get("responseDeadLine") or "").strip() or None),
        estimated_value_usd=estimated_value,
        awardee_name=(str(awardee.get("name") or "").strip() or None),
        awardee_uei=(str(awardee.get("ueiSAM") or "").strip() or None),
        description_url=(str(data.get("description") or "").strip() or None),
        ui_link=(str(data.get("uiLink") or "").strip() or None),
        raw=data,
    )


def matches_priority_agency(agency_path_name: str, priority_agencies: tuple[str, ...]) -> bool:
    """department + sub-tier 계층 매칭 (§6.1). path는 '.' 구분."""
    tiers = [tier.strip().upper() for tier in agency_path_name.split(".") if tier.strip()]
    department_and_subtier = tiers[:2]
    for agency in priority_agencies:
        aliases = _AGENCY_PATH_ALIASES.get(agency, (agency,))
        for alias in aliases:
            if alias.upper() in department_and_subtier:
                return True
    return False


def passes_collect_filter(
    opportunity: SamOpportunity,
    rules: SamCollectRules,
    keyword_map: KeywordDomainMap,
) -> tuple[bool, dict[str, Any]]:
    """§6.1 조건 A~D + estimated_value 부재 규칙. (수집 여부, 판정 근거) 반환.

    agency 단독·solicitation_number 단독으로 통과하는 경로는 존재하지 않는다."""
    agency_matched = matches_priority_agency(
        opportunity.agency_path_name, rules.priority_agencies
    )
    strong_matched, matched_keywords = strong_keyword_match(opportunity.title, keyword_map)
    value = opportunity.estimated_value_usd

    if value is None:
        collected = agency_matched and strong_matched
    else:
        collected = (
            value >= rules.large_value_threshold  # A
            or (agency_matched and value >= rules.small_value_threshold)  # B
            or (agency_matched and strong_matched)  # C
            or (strong_matched and value >= rules.small_value_threshold)  # D
        )

    reasons = {
        "agency_matched": agency_matched,
        "strong_keyword_matched": strong_matched,
        "matched_keywords": matched_keywords,
        "estimated_value_usd": value,
    }
    return collected, reasons


class SamGovCollector(MacroCollector):
    source_id = "US_SAM_GOV"

    def __init__(
        self, lookback_days: int = 2, page_limit: int = 1000, max_pages: int = 3
    ) -> None:
        self._lookback_days = lookback_days
        self._page_limit = page_limit
        self._max_pages = max_pages
        self._rules = load_sam_rules()
        self._keyword_map = load_keyword_domain_map()

    async def collect(self, session: AsyncSession) -> list[NormalizedMacroEvent]:
        if not settings.SAM_API_KEY:
            raise RuntimeError("SAM_API_KEY 미설정 — SAM.gov collector 실행 불가")

        raw_items = await self._fetch_opportunities()
        logger.info("SAM.gov 응답 %d건", len(raw_items))

        events: list[NormalizedMacroEvent] = []
        for item in raw_items:
            opportunity = parse_opportunity(item)
            if opportunity is None:
                continue
            collected, reasons = passes_collect_filter(
                opportunity, self._rules, self._keyword_map
            )
            if not collected:
                continue
            events.append(self._build_event(opportunity, reasons))
        return events

    async def _fetch_opportunities(self) -> list[dict[str, Any]]:
        """offset 페이지네이션 조회 — 주중 2일 물량이 페이지 한도(1000)를 넘을 수 있다."""
        today = now_kst().date()
        posted_from = today - timedelta(days=self._lookback_days)
        base_params = {
            "api_key": settings.SAM_API_KEY,
            "postedFrom": posted_from.strftime("%m/%d/%Y"),
            "postedTo": today.strftime("%m/%d/%Y"),
            "ptype": _PTYPE_CODES,
            "limit": str(self._page_limit),
        }

        items: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            for page in range(self._max_pages):
                response = await client.get(
                    _API_URL, params={**base_params, "offset": str(page * self._page_limit)}
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                page_items = data.get("opportunitiesData") or []
                items.extend(page_items)
                total = int(data.get("totalRecords") or 0)
                if len(items) >= total or not page_items:
                    break
            if total > len(items):
                logger.warning(
                    "SAM.gov 페이지 상한 도달 — total=%d 중 %d건만 처리 (max_pages=%d)",
                    total,
                    len(items),
                    self._max_pages,
                )
        return items

    def _build_event(
        self, opportunity: SamOpportunity, filter_reasons: dict[str, Any]
    ) -> NormalizedMacroEvent:
        posted = datetime.strptime(opportunity.posted_date[:10], "%Y-%m-%d")
        observable_at = to_kst(posted, source_tz=_US_EASTERN)

        linked_entities: list[dict[str, Any]] | None = None
        if opportunity.awardee_name is not None:
            linked_entities = [
                {
                    "role": "AWARDEE",
                    "name": opportunity.awardee_name,
                    "uei": opportunity.awardee_uei,
                }
            ]

        certainty = CertaintyLevel(
            self._rules.certainty_by_type[opportunity.opportunity_type]
        )
        return NormalizedMacroEvent(
            event_unique_id=opportunity.notice_id,
            event_type=MacroEventType.MEGA_CONTRACT,
            title=f"SAM.gov {opportunity.opportunity_type}: {opportunity.title}",
            summary=None,
            source_published_at=observable_at,
            publicly_observable_at=observable_at,
            latency_reference_type=LatencyReferenceType.PUBLISHED_AT,
            certainty_level=certainty,
            linked_entities=linked_entities,
            raw_payload={
                # 필수 저장 필드 12종 (§6.1) — 나머지는 이벤트 컬럼(title/source_url 등)
                "solicitation_number": opportunity.solicitation_number,
                "notice_id": opportunity.notice_id,
                "agency_code": opportunity.agency_path_code,
                "agency_name": opportunity.agency_path_name,
                "posted_date": opportunity.posted_date,
                "response_deadline": opportunity.response_deadline,
                "opportunity_type": opportunity.opportunity_type,
                "estimated_value": opportunity.estimated_value_usd,
                "description_url": opportunity.description_url,
                "filter_reasons": filter_reasons,
            },
            source_url=opportunity.ui_link or "https://sam.gov/opportunities",
        )
