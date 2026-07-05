"""Macro Event Engine config 로더 테스트.

- 정합성 테스트(SPEC §10.5): 실제 config/macro_events/ 파일 대상 — Phase 0 통과 게이트
- 단위 테스트: 잘못된 domain·필드 누락·불변 규칙 위반 시 명시적 에러
"""
import csv
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from app.constants.enums import Market
from app.constants.macro_domains import MacroDomain
from app.services.macro_events.config_loader import (
    MacroConfigError,
    load_all,
    load_domain_basket_map,
    load_entity_alias_map,
    load_event_type_rules,
    load_keyword_domain_map,
    normalize_entity_name,
)

# ---------------------------------------------------------------------------
# 정합성 테스트 — 실제 config 파일 (SPEC §10.5)
# ---------------------------------------------------------------------------


def test_load_all_real_configs() -> None:
    config = load_all()

    assert len(config.domain_basket_map) == 17
    assert len(config.entity_alias_map) == 50
    assert config.keyword_domain_map.domains


def test_keyword_domains_are_canonical() -> None:
    loaded = load_keyword_domain_map()

    assert set(loaded.domains) <= set(MacroDomain)


def test_basket_domains_are_canonical() -> None:
    rows = load_domain_basket_map()

    assert {row.domain for row in rows} <= set(MacroDomain)


def test_every_domain_except_unknown_has_us_basket() -> None:
    us_domains = {
        row.domain for row in load_domain_basket_map() if row.region == Market.US
    }

    assert us_domains == set(MacroDomain) - {MacroDomain.UNKNOWN}


def test_ambiguous_keywords_not_duplicated_in_domain_keywords() -> None:
    loaded = load_keyword_domain_map()
    ambiguous = {k.casefold() for k in loaded.ambiguous_keywords}

    for domain, rules in loaded.domains.items():
        strong = {k.casefold() for k in rules.keywords + rules.phrase_keywords}
        assert not (ambiguous & strong), f"{domain}: ambiguous 키워드가 keywords에 중복"


def test_domain_ambiguous_is_subset_of_master_list() -> None:
    loaded = load_keyword_domain_map()
    ambiguous = {k.casefold() for k in loaded.ambiguous_keywords}

    for domain, rules in loaded.domains.items():
        domain_ambiguous = {k.casefold() for k in rules.ambiguous_keywords}
        assert domain_ambiguous <= ambiguous, f"{domain}: 단일 목록 밖 ambiguous"


def test_active_aliases_match_normalization_rule() -> None:
    for row in load_entity_alias_map():
        assert row.normalized_alias == normalize_entity_name(row.alias_name)


# ---------------------------------------------------------------------------
# 단위 테스트 — 불량 config fixture
# ---------------------------------------------------------------------------

VALID_KEYWORD_MAP: dict[str, Any] = {
    "version": "test",
    "ambiguous_keywords": ["power"],
    "domains": {
        "space": {"phrase_keywords": ["space station"], "keywords": ["NASA"]},
        "power_grid": {"keywords": ["substation"], "ambiguous_keywords": ["power"]},
    },
}

VALID_RULES: dict[str, Any] = {
    "version": "test",
    "event_types_allowed": [
        "MEGA_CONTRACT",
        "PRESIDENTIAL_ACTION",
        "INSTITUTIONAL_CAPITAL_SHIFT",
    ],
    "score": {
        "clamp_total": {"min": 0, "max": 100},
        "clamp_components": {"SourceAuthority": [0, 20]},
        "priority_bands": {"P1": [85, 100]},
    },
    "chain_rules": {
        "SAM_GOV": {
            "chain_key_fields": ["agency_code", "solicitation_number"],
            "allow_fuzzy_matching": False,
        },
    },
    "event_types": {},
}

ALIAS_COLUMNS = [
    "canonical_entity_name",
    "alias_name",
    "normalized_alias",
    "ticker",
    "exchange",
    "cik",
    "corp_code",
    "uei",
    "country",
    "entity_type",
    "mapping_confidence",
    "verified_by",
    "verified_at",
    "is_active",
    "version",
]

VALID_ALIAS_ROW: dict[str, str] = {
    "canonical_entity_name": "Lockheed Martin Corporation",
    "alias_name": "Lockheed Martin Corp.",
    "normalized_alias": "lockheed martin corp",
    "ticker": "LMT",
    "exchange": "NYSE",
    "cik": "0000936468",
    "corp_code": "",
    "uei": "",
    "country": "US",
    "entity_type": "PUBLIC_COMPANY",
    "mapping_confidence": "HIGH",
    "verified_by": "test",
    "verified_at": "2026-07-05",
    "is_active": "true",
    "version": "1",
}


def write_yaml(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def write_alias_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ALIAS_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_basket_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["domain", "region", "basket_type", "symbol", "priority"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def basket_row(**overrides: str) -> dict[str, str]:
    row = {
        "domain": "space",
        "region": "US",
        "basket_type": "ETF",
        "symbol": "ITA",
        "priority": "1",
    }
    return row | overrides


def test_keyword_map_rejects_unknown_domain(tmp_path: Path) -> None:
    data = {**VALID_KEYWORD_MAP, "domains": {"warp_drive": {"keywords": ["x"]}}}

    with pytest.raises(ValidationError):
        load_keyword_domain_map(write_yaml(tmp_path / "kw.yaml", data))


def test_keyword_map_rejects_domain_ambiguous_outside_master(tmp_path: Path) -> None:
    data = {
        **VALID_KEYWORD_MAP,
        "domains": {"space": {"ambiguous_keywords": ["launch"]}},
    }

    with pytest.raises(MacroConfigError, match="단일 목록에 없음"):
        load_keyword_domain_map(write_yaml(tmp_path / "kw.yaml", data))


def test_keyword_map_rejects_ambiguous_duplicated_into_keywords(tmp_path: Path) -> None:
    data = {
        **VALID_KEYWORD_MAP,
        "domains": {"power_grid": {"keywords": ["Power"], "ambiguous_keywords": ["power"]}},
    }

    with pytest.raises(MacroConfigError, match="중복 등재"):
        load_keyword_domain_map(write_yaml(tmp_path / "kw.yaml", data))


def test_rules_reject_fuzzy_matching(tmp_path: Path) -> None:
    data = {
        **VALID_RULES,
        "chain_rules": {
            "SAM_GOV": {"chain_key_fields": ["x"], "allow_fuzzy_matching": True},
        },
    }

    with pytest.raises(MacroConfigError, match="fuzzy"):
        load_event_type_rules(write_yaml(tmp_path / "rules.yaml", data))


def test_rules_reject_taxonomy_mismatch(tmp_path: Path) -> None:
    data = {**VALID_RULES, "event_types_allowed": ["MEGA_CONTRACT"]}

    with pytest.raises(MacroConfigError, match="taxonomy"):
        load_event_type_rules(write_yaml(tmp_path / "rules.yaml", data))


def test_rules_reject_missing_score_section(tmp_path: Path) -> None:
    data = {k: v for k, v in VALID_RULES.items() if k != "score"}

    with pytest.raises(ValidationError):
        load_event_type_rules(write_yaml(tmp_path / "rules.yaml", data))


def test_basket_rejects_unknown_domain(tmp_path: Path) -> None:
    path = write_basket_csv(tmp_path / "b.csv", [basket_row(domain="warp_drive")])

    with pytest.raises(ValidationError):
        load_domain_basket_map(path)


def test_basket_rejects_empty_symbol(tmp_path: Path) -> None:
    path = write_basket_csv(tmp_path / "b.csv", [basket_row(symbol="")])

    with pytest.raises(ValidationError):
        load_domain_basket_map(path)


def test_basket_rejects_duplicate_priority(tmp_path: Path) -> None:
    path = write_basket_csv(
        tmp_path / "b.csv", [basket_row(), basket_row(symbol="XLU")]
    )

    with pytest.raises(MacroConfigError, match="중복"):
        load_domain_basket_map(path)


def test_alias_rejects_normalization_mismatch(tmp_path: Path) -> None:
    row = VALID_ALIAS_ROW | {"normalized_alias": "lockheed"}
    path = write_alias_csv(tmp_path / "a.csv", [row])

    with pytest.raises(MacroConfigError, match="정규화 규칙"):
        load_entity_alias_map(path)


def test_alias_rejects_duplicate_active_normalized_alias(tmp_path: Path) -> None:
    path = write_alias_csv(tmp_path / "a.csv", [VALID_ALIAS_ROW, dict(VALID_ALIAS_ROW)])

    with pytest.raises(MacroConfigError, match="활성 alias 중복"):
        load_entity_alias_map(path)


def test_alias_allows_duplicate_when_inactive(tmp_path: Path) -> None:
    inactive = VALID_ALIAS_ROW | {"is_active": "false"}
    path = write_alias_csv(tmp_path / "a.csv", [VALID_ALIAS_ROW, inactive])

    rows = load_entity_alias_map(path)

    assert len(rows) == 2


def test_alias_rejects_malformed_cik(tmp_path: Path) -> None:
    row = VALID_ALIAS_ROW | {"cik": "936468"}
    path = write_alias_csv(tmp_path / "a.csv", [row])

    with pytest.raises(ValidationError):
        load_entity_alias_map(path)


def test_alias_rejects_missing_required_field(tmp_path: Path) -> None:
    row = VALID_ALIAS_ROW | {"ticker": ""}
    path = write_alias_csv(tmp_path / "a.csv", [row])

    with pytest.raises(ValidationError):
        load_entity_alias_map(path)


def test_normalize_entity_name_rule() -> None:
    assert normalize_entity_name("CACI, Inc.-Federal") == "caci inc-federal"
    assert normalize_entity_name("  Kratos Defense &  Security ") == (
        "kratos defense & security"
    )
