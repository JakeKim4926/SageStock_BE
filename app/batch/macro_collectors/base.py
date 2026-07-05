"""macro collector 공통 실행 골격 (PLAN Phase 1 공통 기반).

각 collector는 collect()만 구현한다: 소스 조회 → 파싱 → 수집 조건 필터(SPEC §6) →
NormalizedMacroEvent 목록 반환. 저장(upsert)·freshness 갱신·실패 기록은 run()이
공통 처리한다.

- 성공: 이벤트 upsert + freshness FRESH를 한 트랜잭션으로 커밋
- 실패: 예외를 로그에 남기고 freshness FAILED + last_error 기록 (SPEC §5.5) —
  예외를 다시 던지지 않아 한 소스 실패가 다른 collector 실행을 막지 않는다
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import async_session_factory
from app.repositories import macro_event_repository, macro_source_freshness_repository
from app.services.macro_events.normalize import NormalizedMacroEvent, now_kst, to_model

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectorRunResult:
    source_id: str
    success: bool
    collected: int = 0
    inserted: int = 0
    updated: int = 0
    error: str | None = None


class MacroCollector(ABC):
    """소스별 collector 베이스. source_id는 macro_event_sources 레지스트리(§4)와 일치해야 한다."""

    source_id: ClassVar[str]

    @abstractmethod
    async def collect(self) -> list[NormalizedMacroEvent]:
        """소스 조회→파싱→필터→정규화. 저장·freshness는 run()이 처리한다."""

    async def run(
        self,
        session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
    ) -> CollectorRunResult:
        collected_at = now_kst()
        try:
            events = await self.collect()
            rows = [to_model(event, self.source_id, collected_at) for event in events]
            async with session_factory() as session:
                inserted, updated = await macro_event_repository.upsert_events(session, rows)
                await macro_source_freshness_repository.mark_success(
                    session, self.source_id, collected_at
                )
                await session.commit()
        except Exception as exc:
            logger.exception("collector 실패 source_id=%s", self.source_id)
            await self._record_failure(session_factory, repr(exc))
            return CollectorRunResult(
                source_id=self.source_id, success=False, error=repr(exc)
            )

        logger.info(
            "collector 성공 source_id=%s collected=%d inserted=%d updated=%d",
            self.source_id,
            len(events),
            inserted,
            updated,
        )
        return CollectorRunResult(
            source_id=self.source_id,
            success=True,
            collected=len(events),
            inserted=inserted,
            updated=updated,
        )

    async def _record_failure(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        error: str,
    ) -> None:
        try:
            async with session_factory() as session:
                await macro_source_freshness_repository.mark_failed(
                    session, self.source_id, error
                )
                await session.commit()
        except Exception:
            # freshness 기록조차 실패(DB 다운 등)해도 다른 collector 실행은 계속돼야 한다.
            logger.exception("freshness FAILED 기록 실패 source_id=%s", self.source_id)
