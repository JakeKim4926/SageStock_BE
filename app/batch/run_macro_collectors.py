"""macro collector 실행 진입점 (PLAN Phase 1) — Phase 0 스모크와 동일한 실행 경로.

    python -m app.batch.run_macro_collectors edgar_form4
    python -m app.batch.run_macro_collectors all

실패한 collector가 있으면 exit 1 (freshness에는 FAILED로 이미 기록됨).
"""
import argparse
import asyncio
import logging
import sys

from app.batch.macro_collectors.base import CollectorRunResult, MacroCollector
from app.batch.macro_collectors.edgar_form4_collector import EdgarForm4Collector
from app.batch.macro_collectors.edgar_schedule13_collector import EdgarSchedule13Collector
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)

COLLECTORS: dict[str, type[MacroCollector]] = {
    "edgar_form4": EdgarForm4Collector,
    "edgar_13dg": EdgarSchedule13Collector,
}


async def _run(names: list[str]) -> list[CollectorRunResult]:
    results = []
    for name in names:
        results.append(await COLLECTORS[name]().run())
    return results


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="macro collector 실행")
    parser.add_argument("collector", choices=[*COLLECTORS, "all"])
    args = parser.parse_args()

    names = list(COLLECTORS) if args.collector == "all" else [args.collector]
    results = asyncio.run(_run(names))

    for result in results:
        logger.info(
            "결과 source=%s success=%s collected=%d inserted=%d updated=%d error=%s",
            result.source_id,
            result.success,
            result.collected,
            result.inserted,
            result.updated,
            result.error,
        )

    if any(not result.success for result in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
