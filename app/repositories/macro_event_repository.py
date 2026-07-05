from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.macro_event_model import MacroEvent

# 재수집 시 갱신하는 컬럼. chain/domain/점수 필드는 파이프라인(Phase 2~3) 소유라 제외.
_UPDATABLE_COLUMNS = (
    "event_type",
    "title",
    "summary",
    "event_effective_at",
    "document_signed_at",
    "source_published_at",
    "collected_at_kst",
    "publicly_observable_at",
    "latency_reference_type",
    "certainty_level",
    "linked_entities",
    "raw_payload",
    "raw_text",
    "source_url",
)


async def get_by_unique_id(
    db: AsyncSession,
    source_id: str,
    event_unique_id: str,
) -> MacroEvent | None:
    statement = select(MacroEvent).where(
        MacroEvent.source_id == source_id,
        MacroEvent.event_unique_id == event_unique_id,
    )
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def upsert_events(
    db: AsyncSession,
    rows: list[MacroEvent],
) -> tuple[int, int]:
    """(source_id, event_unique_id) 기준 upsert. 반환 = (inserted, updated).

    동일 event_unique_id 재수집은 기존 이벤트 업데이트로 처리한다
    (SPEC §6.1 동일 type 재게시 규칙과 정합). 커밋은 호출측(배치/서비스) 소유."""
    inserted = 0
    updated = 0
    for row in rows:
        existing = await get_by_unique_id(db, row.source_id, row.event_unique_id)
        if existing is None:
            db.add(row)
            inserted += 1
            continue

        for column in _UPDATABLE_COLUMNS:
            setattr(existing, column, getattr(row, column))
        updated += 1

    return inserted, updated
