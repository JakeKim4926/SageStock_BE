"""EDGAR 8-K 안전장치 테스트 (SPEC §6.3) — 특히 8.01 단독 키워드 수집 0건 게이트."""
from app.batch.macro_collectors.edgar_client import EdgarFiling
from app.batch.macro_collectors.edgar_form8k_collector import (
    EdgarForm8KCollector,
    detect_signals,
    extract_body_text,
    extract_item_codes,
    match_strong_keywords,
    passes_801_filter,
)

STRONG_KEYWORDS = [
    "award",
    "definitive agreement",
    "government contract",
    "NASA",
    "DoD",
    "DOE",
    "contract value",
    "purchase order",
    "supply agreement",
    "multi-year",
]

ITEM_801_RULES = {
    "certainty_level": "L3",
    "collect_if": {
        "min_strong_signal_keywords": 2,
        "require_one_of": [
            "amount_stated",
            "counterparty_named",
            "agency_named",
            "award_language",
        ],
    },
    "strong_signal_keywords": STRONG_KEYWORDS,
}


def filing_text(items: list[str], body_html: str) -> str:
    item_lines = "\n".join(f"ITEM INFORMATION:\t\t{item}" for item in items)
    return f"""<SEC-DOCUMENT>0000320193-26-000099.txt
<ACCEPTANCE-DATETIME>20260702163000
FILER:
	COMPANY DATA:
		COMPANY CONFORMED NAME:			ACME DEFENSE SYSTEMS INC
		CENTRAL INDEX KEY:			0000320193
{item_lines}
<DOCUMENT>
<TYPE>8-K
<SEQUENCE>1
<TEXT>
<html><body>{body_html}</body></html>
</TEXT>
</DOCUMENT>"""


def make_filing() -> EdgarFiling:
    return EdgarFiling(
        accession_number="0000320193-26-000099",
        cik="0000320193",
        form_type="8-K",
        filing_url="https://www.sec.gov/Archives/edgar/data/320193/idx.htm",
    )


def test_extract_item_codes_maps_descriptions() -> None:
    text = filing_text(
        ["Entry into a Material Definitive Agreement", "Other Events"], "<p>x</p>"
    )

    assert extract_item_codes(text) == {"1.01", "8.01"}


def test_extract_item_codes_ignores_excluded_items() -> None:
    text = filing_text(
        ["Results of Operations and Financial Condition", "Financial Statements and Exhibits"],
        "<p>x</p>",
    )

    assert extract_item_codes(text) == set()


def test_extract_body_text_strips_html() -> None:
    text = filing_text(["Other Events"], "<p>The Company received an   award&nbsp;of $75 million.</p>")

    body = extract_body_text(text)

    assert "award" in body and "$75 million" in body
    assert "<p>" not in body


def test_generic_words_never_match_strong_keywords() -> None:
    # §6.3 안전장치 3: contract/government/agreement 단독은 strong 신호가 아니다.
    body = "The company signed a contract with the government under a new agreement."

    assert match_strong_keywords(body, STRONG_KEYWORDS) == []


def test_phrase_keywords_match_as_phrases() -> None:
    body = "Entered into a definitive agreement establishing a multi-year supply agreement."

    matched = match_strong_keywords(body, STRONG_KEYWORDS)

    assert set(matched) == {"definitive agreement", "multi-year", "supply agreement"}


def test_801_filter_passes_with_two_strong_and_amount() -> None:
    body = "NASA award of $120,000,000 for lunar systems."
    signals = detect_signals(body, STRONG_KEYWORDS)

    assert len(signals.matched_strong_keywords) >= 2  # NASA + award
    assert passes_801_filter(signals, ITEM_801_RULES) is True


def test_801_filter_rejects_single_strong_keyword() -> None:
    body = "The company announced an award of $5 million."
    signals = detect_signals(body, STRONG_KEYWORDS)

    assert len(signals.matched_strong_keywords) == 1
    assert passes_801_filter(signals, ITEM_801_RULES) is False


def test_801_filter_rejects_generic_words_only() -> None:
    body = "New government contract agreement was discussed."  # government contract는 phrase 매칭 1개
    signals = detect_signals(body, STRONG_KEYWORDS)

    assert passes_801_filter(signals, ITEM_801_RULES) is False


def test_801_filter_rejects_without_require_one_of() -> None:
    body = "A multi-year supply agreement was extended."  # strong 2개, 금액/기관/award 없음
    signals = detect_signals(body, STRONG_KEYWORDS)

    assert len(signals.matched_strong_keywords) == 2
    assert passes_801_filter(signals, ITEM_801_RULES) is False


def test_build_event_item_101_collected_as_l4() -> None:
    collector = EdgarForm8KCollector()
    text = filing_text(
        ["Entry into a Material Definitive Agreement"],
        "<p>Agreement with the U.S. Navy valued at $250 million over five years.</p>",
    )

    event = collector._build_event(make_filing(), text)

    assert event is not None
    assert event.event_type.value == "MEGA_CONTRACT"
    assert event.certainty_level.value == "L4"
    assert event.raw_payload is not None
    assert event.raw_payload["item_code"] == "1.01"
    assert event.raw_payload["amount_stated"] is True


def test_build_event_801_rejected_on_generic_body() -> None:
    collector = EdgarForm8KCollector()
    text = filing_text(
        ["Other Events"],
        "<p>The company entered into a contract with a government agency.</p>",
    )

    assert collector._build_event(make_filing(), text) is None


def test_build_event_801_collected_with_safeguards_met() -> None:
    collector = EdgarForm8KCollector()
    text = filing_text(
        ["Other Events"],
        "<p>DoD purchase order awarded, contract value $80 million.</p>",
    )

    event = collector._build_event(make_filing(), text)

    assert event is not None
    assert event.certainty_level.value == "L3"
    assert event.raw_payload is not None
    assert event.raw_payload["item_code"] == "8.01"


def test_build_event_skips_excluded_items_only() -> None:
    collector = EdgarForm8KCollector()
    text = filing_text(
        ["Results of Operations and Financial Condition"],
        "<p>NASA award of $120 million.</p>",
    )

    assert collector._build_event(make_filing(), text) is None
