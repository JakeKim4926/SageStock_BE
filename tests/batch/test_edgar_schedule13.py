"""EDGAR 13D/13G 파서·amendment 필터 테스트 (SPEC §6.5) — 네트워크 미사용."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.batch.macro_collectors.edgar_client import EdgarFiling
from app.batch.macro_collectors.edgar_schedule13_collector import (
    EdgarSchedule13Collector,
    extract_percent_of_class,
    parse_schedule13,
)
from app.repositories import macro_event_repository
from app.services.macro_events.normalize import now_kst, to_model


def schedule13_text(
    form_type: str = "SCHEDULE 13D",
    percent: str = "12.5",
    subject_cik: str = "0000936468",
    filer_cik: str = "0001111111",
) -> str:
    return f"""<SEC-DOCUMENT>0001111111-26-000010.txt
<ACCEPTANCE-DATETIME>20260702180000
SUBJECT COMPANY:
	COMPANY DATA:
		COMPANY CONFORMED NAME:			LOCKHEED MARTIN CORP
		CENTRAL INDEX KEY:			{subject_cik}
FILED BY:
	COMPANY DATA:
		COMPANY CONFORMED NAME:			BIG CAPITAL LP
		CENTRAL INDEX KEY:			{filer_cik}
<DOCUMENT>
<TYPE>{form_type}
<XML>
<edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13">
  <formData>
    <reportingPersonInfo>
      <percentOfClass>{percent}</percentOfClass>
    </reportingPersonInfo>
  </formData>
</edgarSubmission>
</XML>
</DOCUMENT>"""


def make_filing(
    form_type: str = "SCHEDULE 13D", accession: str = "0001111111-26-000010"
) -> EdgarFiling:
    return EdgarFiling(
        accession_number=accession,
        cik="0001111111",
        form_type=form_type,
        filing_url="https://www.sec.gov/Archives/edgar/data/1111111/idx.htm",
    )


def test_parse_schedule13_extracts_both_ciks_and_percent() -> None:
    summary = parse_schedule13(schedule13_text(), "SCHEDULE 13D")

    assert summary is not None
    assert summary.subject_company_cik == "0000936468"
    assert summary.filer_cik == "0001111111"
    assert summary.subject_company_name == "LOCKHEED MARTIN CORP"
    assert summary.filer_name == "BIG CAPITAL LP"
    assert summary.form_family == "13D"
    assert summary.is_amendment is False
    assert summary.percent_of_class == 12.5


def test_parse_schedule13_amendment_and_13g_family() -> None:
    summary = parse_schedule13(
        schedule13_text(form_type="SCHEDULE 13G/A"), "SCHEDULE 13G/A"
    )

    assert summary is not None
    assert summary.form_family == "13G"
    assert summary.is_amendment is True


def test_parse_schedule13_requires_both_ciks() -> None:
    text = "<ACCEPTANCE-DATETIME>20260702180000\nno header sections"

    assert parse_schedule13(text, "SCHEDULE 13D") is None


def test_extract_percent_handles_percent_sign_and_multiple_persons() -> None:
    text = schedule13_text().replace(
        "<percentOfClass>12.5</percentOfClass>",
        "<percentOfClass>8.1%</percentOfClass><percentOfClass>12.5</percentOfClass>",
    )

    assert extract_percent_of_class(text) == 12.5


@pytest.mark.asyncio
async def test_new_13d_is_collected(session: AsyncSession) -> None:
    collector = EdgarSchedule13Collector()

    event = await collector._build_event(session, make_filing(), schedule13_text())

    assert event is not None
    assert event.event_type.value == "INSTITUTIONAL_CAPITAL_SHIFT"
    assert event.raw_payload is not None
    assert event.raw_payload["form_family"] == "13D"
    roles = {entity["role"] for entity in event.linked_entities or []}
    assert roles == {"SUBJECT_COMPANY", "FILER"}


async def seed_previous_13d(session: AsyncSession, percent: float) -> None:
    collector = EdgarSchedule13Collector()
    previous = await collector._build_event(
        session,
        make_filing(accession="0001111111-26-000001"),
        schedule13_text(percent=str(percent)),
    )
    assert previous is not None
    rows = [to_model(previous, "US_SEC_EDGAR", now_kst())]
    await macro_event_repository.upsert_events(session, rows)
    await session.commit()


@pytest.mark.asyncio
async def test_amendment_collected_when_change_at_least_1pct_point(
    session: AsyncSession,
) -> None:
    await seed_previous_13d(session, percent=10.0)
    collector = EdgarSchedule13Collector()

    event = await collector._build_event(
        session,
        make_filing(form_type="SCHEDULE 13D/A", accession="0001111111-26-000011"),
        schedule13_text(form_type="SCHEDULE 13D/A", percent="12.5"),
    )

    assert event is not None  # 변화 2.5%p >= 1.0%p → 수집


@pytest.mark.asyncio
async def test_amendment_skipped_when_change_below_1pct_point(
    session: AsyncSession,
) -> None:
    await seed_previous_13d(session, percent=12.0)
    collector = EdgarSchedule13Collector()

    event = await collector._build_event(
        session,
        make_filing(form_type="SCHEDULE 13D/A", accession="0001111111-26-000011"),
        schedule13_text(form_type="SCHEDULE 13D/A", percent="12.5"),
    )

    assert event is None  # 변화 0.5%p < 1.0%p → 제외


@pytest.mark.asyncio
async def test_amendment_without_baseline_is_collected(session: AsyncSession) -> None:
    collector = EdgarSchedule13Collector()

    event = await collector._build_event(
        session,
        make_filing(form_type="SCHEDULE 13D/A", accession="0001111111-26-000011"),
        schedule13_text(form_type="SCHEDULE 13D/A", percent="12.5"),
    )

    assert event is not None  # 직전 관찰 없음 → 첫 관찰로 수집


@pytest.mark.asyncio
async def test_amendment_without_percent_is_skipped(session: AsyncSession) -> None:
    collector = EdgarSchedule13Collector()
    text = schedule13_text(form_type="SCHEDULE 13D/A").replace(
        "<percentOfClass>12.5</percentOfClass>", ""
    )

    event = await collector._build_event(
        session,
        make_filing(form_type="SCHEDULE 13D/A", accession="0001111111-26-000011"),
        text,
    )

    assert event is None
