"""MacroCollector 베이스 실행 골격 테스트 — 저장·freshness·실패 격리."""
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.batch.macro_collectors.base import MacroCollector
from app.constants.macro_enums import (
    CertaintyLevel,
    FreshnessStatus,
    LatencyReferenceType,
    MacroEventType,
)
from app.models.macro_event_model import MacroEvent
from app.models.macro_event_source_model import MacroEventSource
from app.repositories import macro_source_freshness_repository
from app.services.macro_events.normalize import KST, NormalizedMacroEvent

TEST_SOURCE_ID = "US_DEFENSE_CONTRACTS"


def make_event(unique_id: str, title: str = "Contract award") -> NormalizedMacroEvent:
    return NormalizedMacroEvent(
        event_unique_id=unique_id,
        event_type=MacroEventType.MEGA_CONTRACT,
        title=title,
        publicly_observable_at=datetime(2026, 7, 4, 6, 0, tzinfo=KST),
        latency_reference_type=LatencyReferenceType.PUBLISHED_AT,
        certainty_level=CertaintyLevel.L5,
        raw_payload={"raw": title},
        source_url="https://example.gov/1",
    )


class FakeCollector(MacroCollector):
    source_id = TEST_SOURCE_ID

    def __init__(self, events: list[NormalizedMacroEvent]) -> None:
        self._events = events

    async def collect(self) -> list[NormalizedMacroEvent]:
        return self._events


class FailingCollector(MacroCollector):
    source_id = TEST_SOURCE_ID

    async def collect(self) -> list[NormalizedMacroEvent]:
        raise RuntimeError("source unreachable")


async def seed_source(session: AsyncSession) -> None:
    session.add(
        MacroEventSource(
            source_id=TEST_SOURCE_ID,
            target_description="일일 국방 계약 발표",
            source_roles=["LEAD", "CONFIRMATION"],
            collection_interval="1일 1회",
            observable_at_basis="발표 게시 시각",
            is_active=True,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_run_stores_events_and_marks_fresh(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
) -> None:
    await seed_source(session)
    collector = FakeCollector([make_event("c-1"), make_event("c-2")])

    result = await collector.run(session_factory)

    assert result.success is True
    assert (result.collected, result.inserted, result.updated) == (2, 2, 0)

    stored = (await session.execute(select(MacroEvent))).scalars().all()
    assert {row.event_unique_id for row in stored} == {"c-1", "c-2"}
    assert all(row.publicly_observable_at is not None for row in stored)

    freshness = await macro_source_freshness_repository.get_status(session, TEST_SOURCE_ID)
    assert freshness is not None
    assert freshness.freshness_status == FreshnessStatus.FRESH.value
    assert freshness.last_error is None


@pytest.mark.asyncio
async def test_rerun_updates_existing_event_without_duplicate(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
) -> None:
    await seed_source(session)
    await FakeCollector([make_event("c-1", title="v1")]).run(session_factory)

    result = await FakeCollector([make_event("c-1", title="v2 재게시")]).run(session_factory)

    assert (result.inserted, result.updated) == (0, 1)
    stored = (await session.execute(select(MacroEvent))).scalars().all()
    assert len(stored) == 1
    assert stored[0].title == "v2 재게시"


@pytest.mark.asyncio
async def test_run_failure_marks_failed_with_last_error(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
) -> None:
    await seed_source(session)

    result = await FailingCollector().run(session_factory)

    assert result.success is False
    assert result.error is not None and "source unreachable" in result.error

    stored = (await session.execute(select(MacroEvent))).scalars().all()
    assert stored == []

    freshness = await macro_source_freshness_repository.get_status(session, TEST_SOURCE_ID)
    assert freshness is not None
    assert freshness.freshness_status == FreshnessStatus.FAILED.value
    assert freshness.last_error is not None and "source unreachable" in freshness.last_error
