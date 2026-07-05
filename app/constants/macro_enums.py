from enum import StrEnum

# Macro Event Engine 상태/분류 enum. 정본: docs/macro-event-engine/SPEC.md (각 클래스에 섹션 표기).
# DB 저장 값 = enum value 그대로. 기존 값 rename/삭제 금지, 추가만 허용.


class MacroEventType(StrEnum):
    """SPEC §2.1 — v1 taxonomy는 이 3종뿐. 밖의 타입 생성은 버그."""

    MEGA_CONTRACT = "MEGA_CONTRACT"
    PRESIDENTIAL_ACTION = "PRESIDENTIAL_ACTION"
    INSTITUTIONAL_CAPITAL_SHIFT = "INSTITUTIONAL_CAPITAL_SHIFT"


class SourceRole(StrEnum):
    """SPEC §4 — 소스 역할."""

    LEAD = "LEAD"
    CONFIRMATION = "CONFIRMATION"
    OUTCOME = "OUTCOME"


class CertaintyLevel(StrEnum):
    """SPEC §8 Certainty Ladder. L1(루머)은 v1 수집 제외지만 ladder 정의상 포함."""

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"
    L6 = "L6"

    @property
    def rank(self) -> int:
        """레벨 비교용 (예: P1 조건 certainty_level >= L4, SPEC §5.4)."""
        return int(self.value[1])


class EventStatus(StrEnum):
    """SPEC §7.3/§16 — 체인 연결 상태. 식별자 없으면 ACTIVE_UNLINKED로 두고 중복 표시 허용."""

    ACTIVE = "ACTIVE"
    ACTIVE_UNLINKED = "ACTIVE_UNLINKED"


class MarketLatencyStatus(StrEnum):
    """SPEC §13.2 — 기준 시각은 publicly_observable_at."""

    PRE_REACTION = "PRE_REACTION"
    POST_REACTION = "POST_REACTION"
    UNKNOWN = "UNKNOWN"


class LatencyDataQuality(StrEnum):
    """SPEC §13.3 — 데이터 없으면 POST_REACTION 억지 판정 금지, DATA_UNAVAILABLE."""

    PREMARKET_AVAILABLE = "PREMARKET_AVAILABLE"
    DELAYED = "DELAYED"
    EOD_ONLY = "EOD_ONLY"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class LatencyReferenceType(StrEnum):
    """SPEC §13.1 — publicly_observable_at 산정 근거."""

    SIGNED_AT = "SIGNED_AT"
    PUBLISHED_AT = "PUBLISHED_AT"
    FILING_ACCEPTED_AT = "FILING_ACCEPTED_AT"
    COLLECTED_AT = "COLLECTED_AT"


class PropagationDataQuality(StrEnum):
    """SPEC §14 — GDELT 등 실패 시 OFFICIAL_ONLY로 강등하고 파이프라인은 계속."""

    OFFICIAL_ONLY = "OFFICIAL_ONLY"
    NEWS_DELAYED = "NEWS_DELAYED"
    SEARCH_DAILY = "SEARCH_DAILY"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class ResolutionStatus(StrEnum):
    """SPEC §11.3 — entity 해석 결과. 실패를 조용히 숨기지 않는다."""

    RESOLVED_STRUCTURED_ID = "RESOLVED_STRUCTURED_ID"
    RESOLVED_ALIAS_EXACT = "RESOLVED_ALIAS_EXACT"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class BasketMappingStatus(StrEnum):
    """SPEC §10.4 — basket 단계 실패 진단용 (+reason 저장)."""

    MAPPED = "MAPPED"
    NO_DOMAIN = "NO_DOMAIN"
    NO_BASKET = "NO_BASKET"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class ReactionTargetType(StrEnum):
    """SPEC §13.3 — 측정 대상 종류. MARKET_INDEX = broad_market."""

    LINKED_ENTITY = "LINKED_ENTITY"
    DOMAIN_BASKET = "DOMAIN_BASKET"
    MARKET_INDEX = "MARKET_INDEX"
    UNKNOWN = "UNKNOWN"


class ReactionTargetStatus(StrEnum):
    """SPEC §12 — 최종 측정 대상 선정 결과. NO_TARGET 비율이 운영 실패 지표(§19)."""

    LINKED_ENTITY_RESOLVED = "LINKED_ENTITY_RESOLVED"
    DOMAIN_BASKET_MAPPED = "DOMAIN_BASKET_MAPPED"
    MARKET_INDEX_MAPPED = "MARKET_INDEX_MAPPED"
    NO_TARGET = "NO_TARGET"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class FreshnessStatus(StrEnum):
    """SPEC §5.5 — 4개로 고정. 시간 조건은 max_age_hours 파라미터로 표현."""

    FRESH = "FRESH"
    STALE = "STALE"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


class OutcomeLabel(StrEnum):
    """SPEC §16 event_outcomes — 사후 결과 라벨 (점수 보정 원료)."""

    MOVED = "MOVED"
    IGNORED = "IGNORED"
    DELAYED = "DELAYED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    UNKNOWN = "UNKNOWN"


class OutcomeHorizon(StrEnum):
    """SPEC §16 event_outcomes.horizon — 사후 측정 기간."""

    D1 = "1D"
    D3 = "3D"
    D5 = "5D"
    D10 = "10D"
    D20 = "20D"
