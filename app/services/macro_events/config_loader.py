"""Macro Event Engine config 로더 (PLAN Phase 0).

config/macro_events/ 의 yaml·csv를 파싱하고 스키마와 불변 규칙을 검증한다.
정본 명세: docs/macro-event-engine/SPEC.md (§6~§8 규칙, §9.5 keyword, §10.2 basket, §11.4 alias).

에러 규약:
- 스키마 위반(잘못된 domain, 필드 누락, 타입 오류) → pydantic.ValidationError
- 파일 간/행 간 불변 규칙 위반 → MacroConfigError
둘 다 조용히 넘기지 않고 로드 시점에 실패한다.
"""
import csv
from datetime import date
from pathlib import Path
from typing import Any, Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.constants.enums import Market
from app.constants.macro_domains import MacroDomain
from app.constants.macro_enums import MacroEventType

CONFIG_DIR: Final = Path(__file__).parents[3] / "config" / "macro_events"

KEYWORD_DOMAIN_MAP_PATH: Final = CONFIG_DIR / "keyword_domain_map.yaml"
EVENT_TYPE_RULES_PATH: Final = CONFIG_DIR / "event_type_rules.yaml"
DOMAIN_BASKET_MAP_PATH: Final = CONFIG_DIR / "domain_basket_map.csv"
ENTITY_ALIAS_MAP_PATH: Final = CONFIG_DIR / "entity_alias_map.csv"

# entity_alias_map.csv에서 빈 문자열이면 None으로 취급하는 선택 컬럼
_ALIAS_OPTIONAL_COLUMNS: Final = ("cik", "corp_code", "uei")


class MacroConfigError(ValueError):
    """config 불변 규칙 위반 (스키마는 맞지만 규칙상 허용 불가)."""


def normalize_entity_name(name: str) -> str:
    """alias 정규화: 소문자화 + 마침표/쉼표 제거 + 공백 축약 (&·하이픈 유지).

    entity_alias_map.csv의 normalized_alias 생성 규칙과 동일해야 하며,
    Entity Resolution(SPEC §11)의 exact match도 이 규칙으로 정규화한 뒤 비교한다.
    """
    cleaned = name.replace(".", "").replace(",", "")
    return " ".join(cleaned.lower().split())


class KeywordDomainRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phrase_keywords: list[str] = []
    keywords: list[str] = []
    ambiguous_keywords: list[str] = []


class KeywordDomainMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    ambiguous_keywords: list[str] = Field(min_length=1)
    domains: dict[MacroDomain, KeywordDomainRules]


class ClampTotal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: int
    max: int


class ScoreRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clamp_total: ClampTotal
    clamp_components: dict[str, tuple[float, float]]
    priority_bands: dict[str, tuple[int, int]]


class ChainRule(BaseModel):
    # chain_key_fields 외 소스별 부가 필드(fallback 등)는 Phase 2 소비자가 해석한다
    model_config = ConfigDict(extra="allow")

    chain_key_fields: list[str] = Field(min_length=1)
    allow_fuzzy_matching: bool


class EventTypeRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    event_types_allowed: list[MacroEventType]
    score: ScoreRules
    chain_rules: dict[str, ChainRule]
    chain_promotion: dict[str, Any] = {}
    event_types: dict[str, Any]


class DomainBasketMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: MacroDomain
    region: Market
    basket_type: Literal["ETF", "INDEX"]
    symbol: str = Field(min_length=1)
    priority: int = Field(ge=1)


class EntityAlias(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_entity_name: str = Field(min_length=1)
    alias_name: str = Field(min_length=1)
    normalized_alias: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    cik: str | None = Field(default=None, pattern=r"^\d{10}$")
    corp_code: str | None = None
    uei: str | None = None
    country: Market
    entity_type: str = Field(min_length=1)
    mapping_confidence: Literal["HIGH", "MEDIUM", "LOW"]
    verified_by: str = Field(min_length=1)
    verified_at: date
    is_active: bool
    version: int = Field(ge=1)


class MacroEventConfig(BaseModel):
    keyword_domain_map: KeywordDomainMap
    event_type_rules: EventTypeRules
    domain_basket_map: list[DomainBasketMapping]
    entity_alias_map: list[EntityAlias]


def load_keyword_domain_map(path: Path = KEYWORD_DOMAIN_MAP_PATH) -> KeywordDomainMap:
    with open(path, encoding="utf-8") as f:
        loaded = KeywordDomainMap.model_validate(yaml.safe_load(f))

    ambiguous_cf = [k.casefold() for k in loaded.ambiguous_keywords]
    if len(set(ambiguous_cf)) != len(ambiguous_cf):
        raise MacroConfigError("ambiguous_keywords 단일 목록에 중복 항목이 있음")

    ambiguous_set = set(ambiguous_cf)
    for domain, rules in loaded.domains.items():
        not_in_master = [
            k for k in rules.ambiguous_keywords if k.casefold() not in ambiguous_set
        ]
        if not_in_master:
            raise MacroConfigError(
                f"{domain} ambiguous_keywords {not_in_master}가 최상위 단일 목록에 없음 (SPEC §9.3)"
            )

        strong_cf = {k.casefold() for k in rules.keywords} | {
            k.casefold() for k in rules.phrase_keywords
        }
        duplicated = sorted(ambiguous_set & strong_cf)
        if duplicated:
            raise MacroConfigError(
                f"{domain}: ambiguous 키워드 {duplicated}가 keywords/phrase_keywords에 중복 등재됨 (SPEC §10.5)"
            )

    return loaded


def load_event_type_rules(path: Path = EVENT_TYPE_RULES_PATH) -> EventTypeRules:
    with open(path, encoding="utf-8") as f:
        loaded = EventTypeRules.model_validate(yaml.safe_load(f))

    if set(loaded.event_types_allowed) != set(MacroEventType):
        raise MacroConfigError(
            f"event_types_allowed {sorted(loaded.event_types_allowed)}가 "
            f"v1 taxonomy {sorted(MacroEventType)}와 다름 (SPEC §2.1)"
        )

    fuzzy_enabled = [
        name for name, rule in loaded.chain_rules.items() if rule.allow_fuzzy_matching
    ]
    if fuzzy_enabled:
        raise MacroConfigError(
            f"chain_rules {fuzzy_enabled}에 allow_fuzzy_matching=true — fuzzy 체인 연결 금지 (SPEC §7)"
        )

    for name, (low, high) in loaded.score.clamp_components.items():
        if low > high:
            raise MacroConfigError(f"clamp_components.{name}: min {low} > max {high}")

    return loaded


def load_domain_basket_map(path: Path = DOMAIN_BASKET_MAP_PATH) -> list[DomainBasketMapping]:
    with open(path, encoding="utf-8", newline="") as f:
        rows = [DomainBasketMapping.model_validate(row) for row in csv.DictReader(f)]

    if not rows:
        raise MacroConfigError(f"{path.name}: 매핑 행이 없음")

    seen: set[tuple[MacroDomain, Market, int]] = set()
    for row in rows:
        key = (row.domain, row.region, row.priority)
        if key in seen:
            raise MacroConfigError(
                f"domain_basket_map: (domain={row.domain}, region={row.region}, "
                f"priority={row.priority}) 중복"
            )
        seen.add(key)

    return rows


def load_entity_alias_map(path: Path = ENTITY_ALIAS_MAP_PATH) -> list[EntityAlias]:
    with open(path, encoding="utf-8", newline="") as f:
        raw_rows = list(csv.DictReader(f))

    if not raw_rows:
        raise MacroConfigError(f"{path.name}: alias 행이 없음")

    rows: list[EntityAlias] = []
    for raw in raw_rows:
        for column in _ALIAS_OPTIONAL_COLUMNS:
            if raw.get(column) == "":
                raw[column] = None
        rows.append(EntityAlias.model_validate(raw))

    active_seen: set[str] = set()
    for row in rows:
        expected = normalize_entity_name(row.alias_name)
        if row.normalized_alias != expected:
            raise MacroConfigError(
                f"alias '{row.alias_name}': normalized_alias '{row.normalized_alias}'가 "
                f"정규화 규칙 결과 '{expected}'와 다름"
            )
        if not row.is_active:
            continue
        if row.normalized_alias in active_seen:
            raise MacroConfigError(
                f"활성 alias 중복: normalized_alias '{row.normalized_alias}' (exact match 모호성)"
            )
        active_seen.add(row.normalized_alias)

    return rows


def load_all() -> MacroEventConfig:
    """config 4종 전체 로드 — 배치 스모크와 파이프라인 초기화 진입점."""
    return MacroEventConfig(
        keyword_domain_map=load_keyword_domain_map(),
        event_type_rules=load_event_type_rules(),
        domain_basket_map=load_domain_basket_map(),
        entity_alias_map=load_entity_alias_map(),
    )
