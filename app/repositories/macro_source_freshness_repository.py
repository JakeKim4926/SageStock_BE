from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.macro_enums import FreshnessStatus
from app.models.macro_source_freshness_model import MacroSourceFreshness

# last_error 저장 상한 — 원문 전체는 로그로 남기고 DB에는 진단용 머리만 둔다.
_MAX_ERROR_LENGTH = 500


async def _get_or_create(db: AsyncSession, source_id: str) -> MacroSourceFreshness:
    statement = select(MacroSourceFreshness).where(
        MacroSourceFreshness.source_id == source_id
    )
    result = await db.execute(statement)
    row = result.scalar_one_or_none()
    if row is None:
        row = MacroSourceFreshness(source_id=source_id, freshness_status=FreshnessStatus.STALE.value)
        db.add(row)
    return row


async def mark_success(
    db: AsyncSession,
    source_id: str,
    succeeded_at_kst: datetime,
) -> None:
    row = await _get_or_create(db, source_id)
    row.freshness_status = FreshnessStatus.FRESH.value
    row.last_success_at_kst = succeeded_at_kst
    row.last_error = None


async def mark_failed(
    db: AsyncSession,
    source_id: str,
    error: str,
) -> None:
    """실패를 조용히 숨기지 않는다 (SPEC §5.5) — FAILED + last_error 기록."""
    row = await _get_or_create(db, source_id)
    row.freshness_status = FreshnessStatus.FAILED.value
    row.last_error = error[:_MAX_ERROR_LENGTH]


async def get_status(db: AsyncSession, source_id: str) -> MacroSourceFreshness | None:
    statement = select(MacroSourceFreshness).where(
        MacroSourceFreshness.source_id == source_id
    )
    result = await db.execute(statement)
    return result.scalar_one_or_none()
