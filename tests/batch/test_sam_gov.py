"""SAM.gov 필터 테스트 (SPEC §6.1) — 특히 agency 단독·solicitation_number 단독 수집 0건."""
from typing import Any

from app.batch.macro_collectors.sam_gov_collector import (
    load_sam_rules,
    matches_priority_agency,
    parse_opportunity,
    passes_collect_filter,
)
from app.services.macro_events.config_loader import load_keyword_domain_map
from app.services.macro_events.keyword_match import strong_keyword_match

RULES = load_sam_rules()
KEYWORD_MAP = load_keyword_domain_map()


def opportunity_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "noticeId": "n-0001",
        "title": "Generic office furniture request",
        "type": "Solicitation",
        "solicitationNumber": "FA8611-26-R-0001",
        "fullParentPathName": "GENERAL SERVICES ADMINISTRATION.FEDERAL ACQUISITION SERVICE",
        "fullParentPathCode": "047.4732",
        "postedDate": "2026-07-02",
        "responseDeadLine": "2026-08-01",
        "uiLink": "https://sam.gov/opp/n-0001/view",
    }
    data.update(overrides)
    return data


def parse(**overrides: Any):
    opportunity = parse_opportunity(opportunity_data(**overrides))
    assert opportunity is not None
    return opportunity


def test_rules_loaded_from_config() -> None:
    assert RULES.large_value_threshold == 50_000_000
    assert RULES.small_value_threshold == 10_000_000
    assert set(RULES.priority_agencies) == {"NASA", "DoD", "DOE", "DARPA"}
    assert RULES.certainty_by_type["award_notice"] == "L5"


def test_agency_matching_uses_department_and_subtier() -> None:
    assert matches_priority_agency("DEPT OF DEFENSE.DEPT OF THE ARMY", RULES.priority_agencies)
    assert matches_priority_agency(
        "DEPT OF DEFENSE.DEFENSE ADVANCED RESEARCH PROJECTS AGENCY",
        RULES.priority_agencies,
    )
    assert not matches_priority_agency(
        "GENERAL SERVICES ADMINISTRATION.FEDERAL ACQUISITION SERVICE",
        RULES.priority_agencies,
    )
    # 3단계 이하 계층에 우연히 이름이 있어도 department+sub-tier만 본다.
    assert not matches_priority_agency(
        "GENERAL SERVICES ADMINISTRATION.REGION 5.NASA LIAISON OFFICE",
        RULES.priority_agencies,
    )


def test_title_strong_match_phrase_and_core_keywords() -> None:
    phrase_ok, _ = strong_keyword_match(
        "Small Modular Reactor deployment support", KEYWORD_MAP
    )
    two_core_ok, matched = strong_keyword_match(
        "Uranium supply for reactor operations", KEYWORD_MAP
    )
    single_core_no, _ = strong_keyword_match("Uranium enrichment study", KEYWORD_MAP)
    ambiguous_no, _ = strong_keyword_match(
        "Power and energy for infrastructure", KEYWORD_MAP
    )

    assert phrase_ok is True
    assert two_core_ok is True and len(matched) >= 2
    assert single_core_no is False
    assert ambiguous_no is False  # ambiguous keyword는 핵심 keyword로 세지 않음


def test_condition_a_large_value_alone() -> None:
    opportunity = parse(
        type="Award Notice",
        award={"amount": "75,000,000", "awardee": {"name": "ACME", "ueiSAM": "U1"}},
    )

    collected, reasons = passes_collect_filter(opportunity, RULES, KEYWORD_MAP)

    assert collected is True
    assert reasons["estimated_value_usd"] == 75_000_000.0


def test_condition_b_agency_and_mid_value() -> None:
    opportunity = parse(
        type="Award Notice",
        fullParentPathName="DEPT OF DEFENSE.DEPT OF THE NAVY",
        award={"amount": "12000000"},
    )

    collected, _ = passes_collect_filter(opportunity, RULES, KEYWORD_MAP)

    assert collected is True


def test_condition_c_agency_and_strong_keyword_without_value() -> None:
    opportunity = parse(
        title="Hypersonic missile defense integration",
        fullParentPathName="DEPT OF DEFENSE.DEFENSE ADVANCED RESEARCH PROJECTS AGENCY",
    )

    collected, reasons = passes_collect_filter(opportunity, RULES, KEYWORD_MAP)

    assert collected is True
    assert reasons["agency_matched"] is True and reasons["strong_keyword_matched"] is True


def test_condition_d_strong_keyword_and_mid_value() -> None:
    opportunity = parse(
        title="Data center cloud infrastructure buildout",
        type="Award Notice",
        award={"amount": "15000000"},
    )

    collected, _ = passes_collect_filter(opportunity, RULES, KEYWORD_MAP)

    assert collected is True


def test_agency_only_is_rejected() -> None:
    # §6.1 금지: agency 단독 매칭 수집 (값 없음 + 키워드 없음)
    opportunity = parse(fullParentPathName="DEPT OF DEFENSE.DEPT OF THE ARMY")

    collected, reasons = passes_collect_filter(opportunity, RULES, KEYWORD_MAP)

    assert collected is False
    assert reasons["agency_matched"] is True


def test_solicitation_number_alone_is_rejected() -> None:
    # §6.1 금지: solicitation_number 존재만으로 수집 — 번호는 저장 필드일 뿐이다.
    opportunity = parse(solicitationNumber="HUGE-SOL-99999")

    collected, _ = passes_collect_filter(opportunity, RULES, KEYWORD_MAP)

    assert collected is False


def test_weak_keyword_without_value_is_rejected() -> None:
    opportunity = parse(title="Uranium handling gloves")  # 핵심 keyword 1개뿐

    collected, _ = passes_collect_filter(opportunity, RULES, KEYWORD_MAP)

    assert collected is False


def test_parse_skips_non_target_types() -> None:
    assert parse_opportunity(opportunity_data(type="Special Notice")) is None
    assert parse_opportunity(opportunity_data(type="Justification")) is None


def test_parse_extracts_awardee() -> None:
    opportunity = parse(
        type="Award Notice",
        award={"amount": "60000000", "awardee": {"name": "Lockheed Martin Corp.", "ueiSAM": "UEI123"}},
    )

    assert opportunity.awardee_name == "Lockheed Martin Corp."
    assert opportunity.awardee_uei == "UEI123"
    assert opportunity.opportunity_type == "award_notice"
