"""White House Presidential Actions 파싱·router 테스트 (SPEC §6.8, §7.3).

fixture는 2026-06~07 실피드 구조 발췌: topper 네비게이션, category 태그,
EO 자체 번호 다운로드 링크(eo-14414.pdf), 본문 인용 번호(Executive Order 14212).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.batch.macro_collectors.white_house_collector import (
    WhiteHouseCollector,
    detect_document_type,
    extract_body_text,
    load_white_house_rules,
    parse_feed_actions,
)
from app.constants.macro_enums import EventStatus

RULES = load_white_house_rules()
KST = ZoneInfo("Asia/Seoul")

TOPPER = (
    '<div class="alignfull has-wide-width wp-block-whitehouse-topper">'
    '<div class="wp-block-whitehouse-topper__inner-container">'
    '<h1 class="wp-block-whitehouse-topper__headline">Presidential Actions</h1>'
    "<nav>Search Select Category All News</nav></div></div>"
)

FEED_FIXTURE = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel>
  <title>Presidential Actions - The White House</title>
  <item>
    <title>Advancing Regenerative Agriculture</title>
    <link>https://www.whitehouse.gov/presidential-actions/2026/06/advancing-regenerative-agriculture/</link>
    <pubDate>Thu, 25 Jun 2026 23:00:00 +0000</pubDate>
    <category><![CDATA[Presidential Actions]]></category>
    <category><![CDATA[Executive Orders]]></category>
    <guid isPermaLink="false">https://www.whitehouse.gov/?p=44092</guid>
    <description><![CDATA[<p>By the authority vested in me as President [&#8230;]</p>]]></description>
    <content:encoded><![CDATA[{TOPPER}
<p>By the authority vested in me as President, it is hereby ordered: Executive Order 14212
of February 13, 2025 established the Commission.</p>
<p>DONALD J. TRUMP THE WHITE HOUSE, June 25, 2026.</p>
<a href="https://www.whitehouse.gov/wp-content/uploads/2026/06/eo-14414.pdf">Download</a>
<p>The post Advancing Regenerative Agriculture appeared first on <a href="https://www.whitehouse.gov">The White House</a>.</p>
]]></content:encoded>
  </item>
  <item>
    <title>National Homeownership Month, 2026</title>
    <link>https://www.whitehouse.gov/presidential-actions/2026/06/national-homeownership-month/</link>
    <pubDate>Fri, 12 Jun 2026 19:24:00 +0000</pubDate>
    <category><![CDATA[Presidential Actions]]></category>
    <category><![CDATA[Proclamations]]></category>
    <guid isPermaLink="false">https://www.whitehouse.gov/?p=43102</guid>
    <content:encoded><![CDATA[{TOPPER}<p>BY THE PRESIDENT OF THE UNITED STATES
OF AMERICA A PROCLAMATION National Homeownership Month text.</p>]]></content:encoded>
  </item>
  <item>
    <title>Nominations Sent to the Senate</title>
    <link>https://www.whitehouse.gov/presidential-actions/2026/06/nominations-sent/</link>
    <pubDate>Tue, 23 Jun 2026 16:18:00 +0000</pubDate>
    <category><![CDATA[Presidential Actions]]></category>
    <category><![CDATA[Nominations &#038; Appointments]]></category>
    <guid isPermaLink="false">https://www.whitehouse.gov/?p=43937</guid>
    <content:encoded><![CDATA[<p>nominations body</p>]]></content:encoded>
  </item>
  <item>
    <title>Broken Item Without Guid Post Id</title>
    <link>https://www.whitehouse.gov/presidential-actions/2026/06/broken/</link>
    <pubDate>Tue, 23 Jun 2026 16:18:00 +0000</pubDate>
    <category><![CDATA[Executive Orders]]></category>
    <guid isPermaLink="false">https://www.whitehouse.gov/broken-guid/</guid>
  </item>
  <item>
    <title>Memo With Empty Body</title>
    <link>https://www.whitehouse.gov/presidential-actions/2026/06/memo-empty/</link>
    <pubDate>Mon, 29 Jun 2026 19:53:00 +0000</pubDate>
    <category><![CDATA[Presidential Memoranda]]></category>
    <guid isPermaLink="false">https://www.whitehouse.gov/?p=44226</guid>
  </item>
</channel>
</rss>
"""


def test_rules_loaded_from_config() -> None:
    assert set(RULES.document_types) == {
        "Executive Order",
        "Presidential Memorandum",
        "Proclamation",
    }
    assert RULES.certainty_level == "L4"


def test_document_type_router_only_configured_types() -> None:
    assert (
        detect_document_type(["Presidential Actions", "Executive Orders"], RULES.document_types)
        == "Executive Order"
    )
    assert (
        detect_document_type(["Proclamations"], RULES.document_types) == "Proclamation"
    )
    # 지명 등 config 밖 타입은 수집하지 않는다
    assert (
        detect_document_type(
            ["Presidential Actions", "Nominations & Appointments"], RULES.document_types
        )
        is None
    )


def test_parse_feed_actions_filters_and_extracts() -> None:
    actions = parse_feed_actions(FEED_FIXTURE, RULES.document_types)

    # 지명 1건(타입 밖)·guid 결손 1건(생성 금지) 제외 → 3건
    assert [action.post_id for action in actions] == ["44092", "43102", "44226"]

    eo = actions[0]
    assert eo.document_type == "Executive Order"
    assert eo.published_at_kst == datetime(2026, 6, 26, 8, 0, 0, tzinfo=KST)
    assert eo.own_eo_number == "14414"  # 다운로드 링크에서 — 자체 번호
    assert eo.eo_number_references == ["14212"]  # 본문 인용 — 후보로만
    assert "topper" not in eo.body_text.lower()
    assert "Select Category" not in eo.body_text  # 네비게이션 제거
    assert "appeared first on" not in eo.body_text  # 트레일러 제거
    assert eo.body_text.startswith("By the authority vested")

    proclamation = actions[1]
    assert proclamation.document_type == "Proclamation"
    assert proclamation.own_eo_number is None

    memo = actions[2]
    assert memo.document_type == "Presidential Memorandum"
    assert memo.body_text == ""  # content:encoded 없음 → PARTIAL 후보


def test_extract_body_text_removes_topper_and_boilerplate() -> None:
    content = (
        TOPPER + "<p>Body sentence one.</p>"
        "<p>The post Some Title appeared first on "
        '<a href="https://www.whitehouse.gov">The White House</a>.</p>'
    )
    assert extract_body_text(content) == "Body sentence one."


def test_build_event_status_and_partial() -> None:
    collector = WhiteHouseCollector()
    actions = parse_feed_actions(FEED_FIXTURE, RULES.document_types)

    eo_event = collector._build_event(actions[0])
    assert eo_event.event_unique_id == "44092"
    assert eo_event.title == "Executive Order: Advancing Regenerative Agriculture"
    assert eo_event.event_status is EventStatus.ACTIVE  # 자체 번호 있음 (§7.3)
    assert eo_event.linked_entities is None
    assert eo_event.raw_payload is not None
    assert eo_event.raw_payload["executive_order_number"] == "14414"
    assert eo_event.raw_payload["parse_status"] == "FULL"
    assert eo_event.publicly_observable_at == actions[0].published_at_kst

    proclamation_event = collector._build_event(actions[1])
    assert proclamation_event.event_status is EventStatus.ACTIVE_UNLINKED  # 번호 없음

    partial_event = collector._build_event(actions[2])
    assert partial_event.raw_payload is not None
    assert partial_event.raw_payload["parse_status"] == "PARTIAL"
    assert partial_event.raw_text is None  # raw_payload가 보존 요건 충족
