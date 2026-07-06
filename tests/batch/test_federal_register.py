"""Federal Register 문서 타입 router·이벤트 변환 테스트 (SPEC §6.8, §7.2).

fixture는 2026-06~07 실 API 응답(fields[] 지정) 형태를 그대로 따른다.
"""
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.batch.macro_collectors.federal_register_collector import (
    FederalRegisterCollector,
    detect_document_type,
    load_federal_register_rules,
)
from app.constants.macro_enums import EventStatus

RULES = load_federal_register_rules()
KST = ZoneInfo("Asia/Seoul")


def document_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "document_number": "2026-13254",
        "title": "Advancing Regenerative Agriculture and Strengthening American Farm Resilience",
        "abstract": None,
        "subtype": "Executive Order",
        "executive_order_number": "14414",
        "proclamation_number": None,
        "presidential_document_number": "14414",
        "signing_date": "2026-06-25",
        "publication_date": "2026-06-30",
        "citation": "91 FR 12345",
        "html_url": "https://www.federalregister.gov/documents/2026/06/30/2026-13254/advancing",
        "raw_text_url": "https://www.federalregister.gov/documents/full_text/text/2026/06/30/2026-13254.txt",
    }
    data.update(overrides)
    return data


def test_rules_loaded_from_config() -> None:
    assert set(RULES.document_types) == {
        "Executive Order",
        "Presidential Memorandum",
        "Proclamation",
    }
    assert RULES.certainty_level == "L4"


def test_document_type_router_maps_subtypes_and_rejects_others() -> None:
    assert detect_document_type("Executive Order", RULES.document_types) == "Executive Order"
    assert detect_document_type("Proclamation", RULES.document_types) == "Proclamation"
    # API subtype 표기(Memorandum) → config 표기(Presidential Memorandum)
    assert (
        detect_document_type("Memorandum", RULES.document_types) == "Presidential Memorandum"
    )
    # Determination/Notice 등 config 밖 타입은 수집 안 함
    assert detect_document_type("Determination", RULES.document_types) is None
    assert detect_document_type("Notice", RULES.document_types) is None


def test_build_event_fields_and_chain_identifiers() -> None:
    collector = FederalRegisterCollector()

    event = collector._build_event(document_data())
    assert event is not None
    assert event.event_unique_id == "2026-13254"  # FR 단독 chain key (§7.2)
    assert event.title.startswith("Federal Register Executive Order:")
    assert event.event_status is EventStatus.ACTIVE
    # publication_date(날짜만)는 ET 자정 기준 KST — 6월 EDT(UTC-4) 자정 = 13:00 KST
    assert event.publicly_observable_at == datetime(2026, 6, 30, 13, 0, tzinfo=KST)
    assert event.document_signed_at == datetime(2026, 6, 25, 13, 0, tzinfo=KST)
    assert event.raw_payload is not None
    assert event.raw_payload["executive_order_number"] == "14414"  # WH↔FR 체인 재료(§7.3)
    assert event.linked_entities is None

    memo_event = collector._build_event(
        document_data(subtype="Memorandum", executive_order_number=None)
    )
    assert memo_event is not None
    assert memo_event.title.startswith("Federal Register Presidential Memorandum:")


def test_build_event_rejects_out_of_scope_and_missing_fields() -> None:
    collector = FederalRegisterCollector()

    assert collector._build_event(document_data(subtype="Determination")) is None
    assert collector._build_event(document_data(subtype="Notice")) is None
    assert collector._build_event(document_data(document_number="")) is None
    assert collector._build_event(document_data(publication_date=None)) is None
    assert collector._build_event(document_data(html_url="")) is None
