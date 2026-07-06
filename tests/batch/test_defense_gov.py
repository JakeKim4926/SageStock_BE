"""Defense.gov Contracts 파싱·필터 테스트 (SPEC §6.7).

기사 fixture는 2026-07-02 실발표(war.gov Article 4532515)에서 발췌한 원문이다.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.batch.macro_collectors.defense_gov_collector import (
    ContractItem,
    DefenseGovCollector,
    load_defense_rules,
    parse_contract_items,
    parse_rss_articles,
    passes_collect_filter,
)
from app.constants.macro_enums import EventStatus
from app.services.macro_events.config_loader import load_keyword_domain_map

RULES = load_defense_rules()
KEYWORD_MAP = load_keyword_domain_map()
KST = ZoneInfo("Asia/Seoul")

RSS_FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>Contracts - U.S. Dept. of War</title>
    <item>
      <title>
Contracts for July 2, 2026
</title>
      <link>https://www.war.gov/News/Contracts/Contract/Article/4532515/contracts-for-july-2-2026/</link>
      <pubDate>Thu, 02 Jul 2026 21:00:21 GMT</pubDate>
    </item>
    <item>
      <title>Contracts for July 1, 2026</title>
      <link>https://www.war.gov/News/Contracts/Contract/Article/4531882/contracts-for-july-1-2026/</link>
      <pubDate>Wed, 01 Jul 2026 21:00:11 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

ARTICLE_FIXTURE = """
<html><body>
<div class="adetail abanner content-type-400">
<header class="content-wrap"><h1 class="maintitle">Contracts for July 2, 2026</h1></header>
<div class="body">
<p style="text-align: center;"><strong>WASHINGTON HEADQUARTERS SERVICES</strong></p>

<p>The RAND National Defense Research Institute, Santa Monica, California, has been awarded a \
task order contract (HQ003426DE016) with a value of $452,461,776. The purpose of this contract \
is to provide research, studies, analysis, analytic models, simulations, and wargaming \
exercises. The total amount of the contract if all options are exercised is $985,625,480. \
Washington Headquarters Services, Arlington, Virginia, is the contracting activity.</p>

<p style="text-align: center;"><strong>NAVY</strong></p>

<p>SMIT Singapore Pte Ltd., Singapore, is awarded a $180,000,000 cost-plus-award-fee, \
cost-plus-fixed-fee, indefinite-delivery/indefinite-quantity contract for salvage-related \
towing, harbor clearance, ocean engineering projects, and point-to-point towing services. \
Naval Sea Systems Command, Washington, D.C., is the contracting activity (N00024-26-D-4308).</p>

<p>Thoma-Sea Marine Constructors LLC,* Houma, Louisiana, is awarded $26,625,622 \
firm-fixed-price modification to previously awarded contract N00024-19-C-2216 for the \
definitization of an engineering change. Naval Sea Systems Command, Washington, D.C., \
is the contracting activity (N00024-19-C-2216).</p>

<p style="text-align: center;"><strong>AIR FORCE</strong></p>

<p>Vertex Aerospace LLC, Madison, Mississippi, has been awarded a $22,573,762 modification \
(P00003) to previously awarded (FA8106-25-D-B003) for contractor operated and maintained \
base supply services. The Air Force Life Cycle Management Center, Tinker AFB, Oklahoma, \
is the contracting activity.</p>

<p>*Small business<br />
**Small-disadvantaged business</p>
</div>
</div>
</body></html>
"""


def make_item(**overrides) -> ContractItem:
    values = {
        "agency": "NAVY",
        "text": "Example Corp., Norfolk, Virginia, is awarded a contract for services.",
        "amount_usd": 60_000_000,
        "awardee_name": "Example Corp.",
        "contract_numbers": ["N00024-26-D-0001"],
        "modification_number": None,
        "is_modification": False,
        "previously_awarded_number": None,
        "indefinite_delivery": False,
        "ceiling_value": False,
    }
    values.update(overrides)
    return ContractItem(**values)


def test_rules_loaded_from_config() -> None:
    assert RULES.large_value_threshold == 50_000_000
    assert RULES.small_value_threshold == 7_500_000
    assert RULES.min_extracted_fields == 3
    assert RULES.certainty_level == "L5"


def test_parse_rss_articles_extracts_id_and_kst_time() -> None:
    articles = parse_rss_articles(RSS_FIXTURE)

    assert [article.article_id for article in articles] == ["4532515", "4531882"]
    assert articles[0].title == "Contracts for July 2, 2026"
    # 21:00 GMT 발표 → 다음날 06:00 KST (SPEC §4 ≈06:00 KST 발표와 일치)
    assert articles[0].published_at_kst == datetime(2026, 7, 3, 6, 0, 21, tzinfo=KST)


def test_parse_contract_items_sections_and_fields() -> None:
    items = parse_contract_items(ARTICLE_FIXTURE)

    # 헤더 3개·각주 1개 제외, 계약 항목 4건
    assert len(items) == 4
    assert [item.agency for item in items] == [
        "WASHINGTON HEADQUARTERS SERVICES",
        "NAVY",
        "NAVY",
        "AIR FORCE",
    ]

    rand = items[0]
    assert rand.awardee_name == "The RAND National Defense Research Institute"
    assert rand.amount_usd == 452_461_776  # 첫 금액 = 수주 금액 (총액 아님)
    assert rand.contract_numbers == ["HQ003426DE016"]
    assert rand.ceiling_value is True  # "if all options are exercised"
    assert rand.is_modification is False

    smit = items[1]
    assert smit.awardee_name == "SMIT Singapore Pte Ltd."
    assert smit.indefinite_delivery is True
    assert smit.contract_numbers == ["N00024-26-D-4308"]

    thoma = items[2]
    assert thoma.is_modification is True
    assert thoma.previously_awarded_number == "N00024-19-C-2216"  # 괄호 없는 표기

    vertex = items[3]
    assert vertex.is_modification is True
    assert vertex.modification_number == "P00003"  # 계약번호로 오분류 금지
    assert vertex.contract_numbers == ["FA8106-25-D-B003"]
    assert vertex.previously_awarded_number == "FA8106-25-D-B003"


def test_collect_filter_amount_and_strong_keyword_paths() -> None:
    large_ok, _ = passes_collect_filter(make_item(amount_usd=60_000_000), RULES, KEYWORD_MAP)
    small_strong_ok, reasons = passes_collect_filter(
        make_item(
            amount_usd=10_000_000,
            text="Example Corp., Norfolk, Virginia, Small Modular Reactor deployment support.",
        ),
        RULES,
        KEYWORD_MAP,
    )
    small_plain_no, _ = passes_collect_filter(
        make_item(amount_usd=10_000_000), RULES, KEYWORD_MAP
    )
    below_threshold_no, _ = passes_collect_filter(
        make_item(amount_usd=5_000_000), RULES, KEYWORD_MAP
    )
    no_amount_no, _ = passes_collect_filter(
        make_item(
            amount_usd=None,
            text="Example Corp., Norfolk, Virginia, Small Modular Reactor deployment support.",
        ),
        RULES,
        KEYWORD_MAP,
    )

    assert large_ok is True
    assert small_strong_ok is True and reasons["matched_keywords"]
    assert small_plain_no is False
    assert below_threshold_no is False
    assert no_amount_no is False  # 금액 없으면 수집 경로 없음 (§6.7)


def test_collect_filter_requires_min_extracted_fields() -> None:
    # 금액+설명만 있으면 2/4 필드 — min_extracted_fields=3 미달로 제외
    insufficient, reasons = passes_collect_filter(
        make_item(amount_usd=60_000_000, awardee_name=None, agency=None),
        RULES,
        KEYWORD_MAP,
    )
    assert insufficient is False
    assert reasons["extracted_fields"] == 2


def test_build_event_status_and_identity() -> None:
    collector = DefenseGovCollector()
    articles = parse_rss_articles(RSS_FIXTURE)
    items = parse_contract_items(ARTICLE_FIXTURE)
    _, reasons = passes_collect_filter(items[0], RULES, KEYWORD_MAP)

    event = collector._build_event(articles[0], items[0], reasons)
    assert event.event_unique_id.startswith("4532515-")
    assert len(event.event_unique_id) == len("4532515-") + 16
    assert event.event_status is EventStatus.ACTIVE  # 계약번호 있음 → 체인 후보
    assert event.linked_entities == [
        {"role": "AWARDEE", "name": "The RAND National Defense Research Institute"}
    ]
    assert event.publicly_observable_at == articles[0].published_at_kst
    assert event.source_url == articles[0].url
    assert event.raw_payload is not None
    assert event.raw_payload["ceiling_value"] is True

    unlinked = collector._build_event(
        articles[0], make_item(contract_numbers=[]), reasons
    )
    assert unlinked.event_status is EventStatus.ACTIVE_UNLINKED  # 계약번호 없음 (§7.2)
