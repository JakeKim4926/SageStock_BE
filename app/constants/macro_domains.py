from enum import StrEnum

# SPEC §9.1 canonical_domain enum — 이것 밖의 domain 저장 금지.
# keyword_domain_map.yaml / domain_basket_map.csv의 domain 값과 일치해야 한다 (정합성 테스트 §10.5).
# 와이어/DB/config 값은 소문자 스네이크 그대로.


class MacroDomain(StrEnum):
    SPACE = "space"
    DEFENSE = "defense"
    POWER_GRID = "power_grid"
    ENERGY = "energy"
    NUCLEAR = "nuclear"
    AI_INFRASTRUCTURE = "ai_infrastructure"
    DATA_CENTER = "data_center"
    SEMICONDUCTOR = "semiconductor"
    CRITICAL_MINERALS = "critical_minerals"
    BATTERY = "battery"
    QUANTUM = "quantum"
    CYBERSECURITY = "cybersecurity"
    INFRASTRUCTURE = "infrastructure"
    FINANCIALS = "financials"
    BROAD_MARKET = "broad_market"
    UNKNOWN = "unknown"
