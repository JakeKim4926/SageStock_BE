"""배치 실행 경로 스모크 테스트 (macro-event-engine PLAN Phase 0 게이트).

GH Actions 러너가 코드를 직접 실행해 Neon DB에 직결되는지 확인한다 (SPEC §3).
SELECT 1만 실행하며 아무것도 쓰지 않는다.

    python -m app.batch.smoke
"""
import asyncio
import logging
import sys

from sqlalchemy import text

from app.core.database import async_session_factory
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


async def _check_db() -> None:
    async with async_session_factory() as session:
        await session.execute(text("SELECT 1"))


def main() -> None:
    configure_logging()
    try:
        asyncio.run(_check_db())
    except Exception:
        logger.exception("스모크 실패: DB 연결 불가")
        sys.exit(1)

    logger.info("스모크 성공: 러너→DB 직결 확인")


if __name__ == "__main__":
    main()
