"""EDGAR Form 4 파서·필터 테스트 (SPEC §6.4) — 네트워크 미사용."""
from app.batch.macro_collectors.edgar_client import parse_getcurrent_feed
from app.batch.macro_collectors.edgar_form4_collector import (
    extract_acceptance_datetime,
    extract_ownership_xml,
    parse_form4,
    passes_collect_filter,
)
from app.services.macro_events.normalize import KST

COLLECT_IF = {
    "transaction_codes": ["P"],
    "min_transaction_value_usd": 1_000_000,
    "allowed_roles": ["officer", "director", "ten_percent_owner"],
    "exclude": ["option_exercise", "grant", "automatic_transaction"],
}


def form4_xml(
    code: str = "P",
    shares: str = "100000",
    price: str = "15.00",
    is_officer: str = "1",
    is_director: str = "0",
    is_ten_percent: str = "0",
) -> str:
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>936468</issuerCik>
    <issuerName>LOCKHEED MARTIN CORP</issuerName>
    <issuerTradingSymbol>LMT</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001234567</rptOwnerCik>
      <rptOwnerName>DOE JOHN</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>{is_director}</isDirector>
      <isOfficer>{is_officer}</isOfficer>
      <isTenPercentOwner>{is_ten_percent}</isTenPercentOwner>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>{shares}</value></transactionShares>
        <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def filing_text(xml_body: str) -> str:
    return (
        "<SEC-DOCUMENT>0001234567-26-000001.txt\n"
        "<ACCEPTANCE-DATETIME>20260702213045\n"
        "<DOCUMENT>\n<TYPE>4\n<XML>\n" + xml_body + "\n</XML>\n</DOCUMENT>\n"
    )


def test_parse_form4_open_market_purchase() -> None:
    summary = parse_form4(form4_xml())

    assert summary is not None
    assert summary.issuer_cik == "0000936468"
    assert summary.issuer_ticker == "LMT"
    assert summary.owner_name == "DOE JOHN"
    assert summary.is_officer is True
    assert summary.total_purchase_value_usd == 1_500_000.0


def test_filter_passes_officer_large_purchase() -> None:
    summary = parse_form4(form4_xml())
    assert summary is not None

    assert passes_collect_filter(summary, COLLECT_IF) is True


def test_filter_rejects_sale_code() -> None:
    summary = parse_form4(form4_xml(code="S"))
    assert summary is not None

    # 코드 S는 매수 합산 0 → 최소 금액 미달로 거부
    assert summary.total_purchase_value_usd == 0.0
    assert passes_collect_filter(summary, COLLECT_IF) is False


def test_filter_rejects_below_minimum_value() -> None:
    summary = parse_form4(form4_xml(shares="1000", price="15.00"))
    assert summary is not None

    assert passes_collect_filter(summary, COLLECT_IF) is False


def test_filter_rejects_when_no_allowed_role() -> None:
    summary = parse_form4(form4_xml(is_officer="0", is_director="0", is_ten_percent="0"))
    assert summary is not None

    assert passes_collect_filter(summary, COLLECT_IF) is False


def test_filter_accepts_ten_percent_owner_only() -> None:
    summary = parse_form4(form4_xml(is_officer="0", is_ten_percent="1"))
    assert summary is not None

    assert passes_collect_filter(summary, COLLECT_IF) is True


def test_parse_form4_returns_none_on_malformed_xml() -> None:
    assert parse_form4("<ownershipDocument><issuer>") is None
    assert parse_form4("<other/>") is None


def test_extract_ownership_xml_and_acceptance() -> None:
    text = filing_text(form4_xml())

    xml_body = extract_ownership_xml(text)
    accepted = extract_acceptance_datetime(text)

    assert xml_body is not None and "<ownershipDocument" in xml_body
    assert accepted is not None
    assert accepted.tzinfo == KST
    # ET 2026-07-02 21:30 = KST 2026-07-03 10:30 (EDT, UTC-4)
    assert (accepted.day, accepted.hour, accepted.minute) == (3, 10, 30)


def test_extract_returns_none_when_missing() -> None:
    assert extract_ownership_xml("no xml here") is None
    assert extract_acceptance_datetime("no header") is None


GETCURRENT_FEED = """<?xml version="1.0" encoding="ISO-8859-1"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Latest Filings</title>
  <entry>
    <title>4 - DOE JOHN (0001234567) (Reporting)</title>
    <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001-index.htm"/>
    <category term="4" label="form type"/>
    <id>urn:tag:sec.gov,2008:accession-number=0001234567-26-000001</id>
  </entry>
  <entry>
    <title>4 - LOCKHEED MARTIN CORP (0000936468) (Issuer)</title>
    <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/936468/000123456726000001-index.htm"/>
    <category term="4" label="form type"/>
    <id>urn:tag:sec.gov,2008:accession-number=0001234567-26-000001</id>
  </entry>
  <entry>
    <title>4/A - SMITH JANE (0007654321) (Reporting)</title>
    <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/7654321/000765432126000002-index.htm"/>
    <category term="4/A" label="form type"/>
    <id>urn:tag:sec.gov,2008:accession-number=0007654321-26-000002</id>
  </entry>
</feed>"""


def test_parse_getcurrent_feed_dedups_and_filters_form_type() -> None:
    filings = parse_getcurrent_feed(GETCURRENT_FEED, "4")

    # 같은 filing의 Reporting/Issuer 중복 entry는 1건으로, 4/A는 제외.
    assert len(filings) == 1
    assert filings[0].accession_number == "0001234567-26-000001"
    assert filings[0].cik == "0001234567"
    assert filings[0].form_type == "4"
