"""Normalize Service 테스트 — KST 변환, 공통 스키마 불변 규칙, ORM 변환."""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.constants.macro_enums import (
    CertaintyLevel,
    EventStatus,
    LatencyReferenceType,
    MacroEventType,
)
from app.services.macro_events.normalize import (
    KST,
    NormalizedMacroEvent,
    to_kst,
    to_model,
)

US_EASTERN = ZoneInfo("America/New_York")


def make_event(**overrides: object) -> NormalizedMacroEvent:
    fields: dict = {
        "event_unique_id": "0001193125-26-000001",
        "event_type": MacroEventType.MEGA_CONTRACT,
        "title": "Contract award announcement",
        "publicly_observable_at": datetime(2026, 7, 3, 22, 0, tzinfo=KST),
        "latency_reference_type": LatencyReferenceType.PUBLISHED_AT,
        "certainty_level": CertaintyLevel.L5,
        "raw_payload": {"amount": 50_000_000},
        "source_url": "https://example.gov/contract/1",
    }
    fields.update(overrides)
    return NormalizedMacroEvent(**fields)


def test_to_kst_converts_aware_datetime() -> None:
    moment = datetime(2026, 7, 3, 17, 0, tzinfo=US_EASTERN)  # ET 17:00 = KST 익일 06:00

    converted = to_kst(moment)

    assert converted.tzinfo == KST
    assert (converted.day, converted.hour) == (4, 6)


def test_to_kst_applies_source_tz_for_naive() -> None:
    naive = datetime(2026, 7, 3, 17, 0)

    converted = to_kst(naive, source_tz=US_EASTERN)

    assert converted == to_kst(datetime(2026, 7, 3, 17, 0, tzinfo=US_EASTERN))


def test_to_kst_rejects_naive_without_source_tz() -> None:
    with pytest.raises(ValueError, match="source_tz"):
        to_kst(datetime(2026, 7, 3, 17, 0))


def test_event_requires_raw_payload_or_text() -> None:
    with pytest.raises(ValidationError, match="raw_payload"):
        make_event(raw_payload=None, raw_text=None)


def test_event_rejects_naive_observable_at() -> None:
    with pytest.raises(ValidationError, match="naive"):
        make_event(publicly_observable_at=datetime(2026, 7, 3, 22, 0))


def test_event_rejects_naive_optional_datetime() -> None:
    with pytest.raises(ValidationError, match="document_signed_at"):
        make_event(document_signed_at=datetime(2026, 7, 3, 12, 0))


def test_to_model_maps_fields_and_leaves_pipeline_fields_empty() -> None:
    event = make_event(raw_text="original text", event_status=EventStatus.ACTIVE_UNLINKED)
    collected_at = datetime(2026, 7, 4, 6, 30, tzinfo=KST)

    row = to_model(event, source_id="US_DEFENSE_CONTRACTS", collected_at_kst=collected_at)

    assert row.source_id == "US_DEFENSE_CONTRACTS"
    assert row.event_unique_id == event.event_unique_id
    assert row.event_type == "MEGA_CONTRACT"
    assert row.event_status == "ACTIVE_UNLINKED"
    assert row.certainty_level == "L5"
    assert row.collected_at_kst == collected_at
    assert row.raw_text == "original text"
    # 파이프라인(Phase 2~3) 소유 필드는 수집 시점에 비워 둔다.
    assert row.event_chain_id is None
    assert row.primary_domain is None
    assert row.priority_score is None


def test_utc_roundtrip_matches_kst() -> None:
    utc_moment = datetime(2026, 7, 3, 13, 0, tzinfo=UTC)

    assert to_kst(utc_moment).hour == 22
