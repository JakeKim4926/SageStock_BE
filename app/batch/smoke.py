"""배치 실행 경로 스모크 테스트 (macro-event-engine PLAN Phase 0 게이트).

GH Actions 러너가 코드를 직접 실행해 Neon DB에 직결되는지 확인한다 (SPEC §3).
DB에는 SELECT 1만 실행하며 아무것도 쓰지 않는다. 추가로 macro config 4종을
1회 로드해 스키마·불변 규칙 검증까지 통과하는지 확인한다.

    python -m app.batch.smoke
"""
import asyncio
import logging
import sys

from sqlalchemy import text

from app.core.database import async_session_factory
from app.core.logging import configure_logging
from app.services.macro_events.config_loader import load_all

logger = logging.getLogger(__name__)


async def _check_db() -> None:
    async with async_session_factory() as session:
        await session.execute(text("SELECT 1"))


def main() -> None:
    configure_logging()
    try:
        config = load_all()
    except Exception:
        logger.exception("스모크 실패: macro config 로드 불가")
        sys.exit(1)

    try:
        asyncio.run(_check_db())
    except Exception:
        logger.exception("스모크 실패: DB 연결 불가")
        sys.exit(1)

    logger.info(
        "스모크 성공: 러너→DB 직결 + config 로드 확인 (basket %d행, alias %d행)",
        len(config.domain_basket_map),
        len(config.entity_alias_map),
    )


if __name__ == "__main__":
    main()
