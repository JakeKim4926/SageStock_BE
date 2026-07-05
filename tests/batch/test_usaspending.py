"""USAspending collector 테스트 (SPEC §6.2) — 네트워크 미사용."""
from typing import Any

from app.batch.macro_collectors.usaspending_collector import (
    build_event,
    build_search_payload,
    load_usaspending_rules,
)

RULES = load_usaspending_rules()


def award_result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "generated_internal_id": "CONT_AWD_FA861126C0001_9700",
        "Award ID": "FA861126C0001",
        "Recipient Name": "LOCKHEED MARTIN CORPORATION",
        "Recipient UEI": "UEI0000000001",
        "Award Amount": 250_000_000.0,
        "Description": "HYPERSONIC MISSILE PROTOTYPE",
        "Start Date": "2026-07-01",
        "End Date": "2029-06-30",
        "Awarding Agency": "Department of Defense",
        "Awarding Sub Agency": "Department of the Air Force",
        "Base Obligation Date": "2026-07-02",
    }
    result.update(overrides)
    return result


def test_rules_loaded_from_config() -> None:
    assert RULES.min_award_amount_usd == 50_000_000
    assert RULES.certainty_level == "L6"


def test_payload_requests_new_awards_only_with_config_threshold() -> None:
    payload = build_search_payload("2026-06-28", "2026-07-05", RULES.min_award_amount_usd, 1)

    time_period = payload["filters"]["time_period"][0]
    assert time_period["date_type"] == "new_awards_only"  # 신규 award만 (§6.2)
    assert payload["filters"]["award_amounts"][0]["lower_bound"] == 50_000_000
    assert set(payload["filters"]["award_type_codes"]) == {"A", "B", "C", "D"}


def test_build_event_maps_fields() -> None:
    event = build_event(award_result(), RULES)

    assert event is not None
    assert event.event_type.value == "MEGA_CONTRACT"
    assert event.certainty_level.value == "L6"
    assert event.event_unique_id == "CONT_AWD_FA861126C0001_9700"
    assert event.raw_payload is not None
    assert event.raw_payload["award_id"] == "FA861126C0001"
    assert event.raw_payload["contract_award_unique_key"] == "CONT_AWD_FA861126C0001_9700"
    assert event.linked_entities == [
        {
            "role": "RECIPIENT",
            "name": "LOCKHEED MARTIN CORPORATION",
            "uei": "UEI0000000001",
        }
    ]
    # Base Obligation Date(ET 자정) → KST
    assert event.publicly_observable_at.tzinfo is not None
    assert event.publicly_observable_at.day == 2


def test_build_event_rejects_below_config_minimum() -> None:
    assert build_event(award_result(**{"Award Amount": 49_999_999.0}), RULES) is None


def test_build_event_requires_unique_key_and_recipient() -> None:
    assert build_event(award_result(generated_internal_id=""), RULES) is None
    assert build_event(award_result(**{"Recipient Name": ""}), RULES) is None


def test_build_event_falls_back_to_start_date() -> None:
    event = build_event(award_result(**{"Base Obligation Date": None}), RULES)

    assert event is not None
    assert event.publicly_observable_at.day == 1  # Start Date 2026-07-01 (ET) 기준


def test_build_event_rejects_when_no_dates() -> None:
    result = award_result(**{"Base Obligation Date": None, "Start Date": None})

    assert build_event(result, RULES) is None
