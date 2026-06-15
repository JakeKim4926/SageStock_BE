import logging
from typing import Final

# 운영 로깅 기본 설정 (feature-spec §6). 외부 소스(fdr) 실패·타임아웃을 기록한다.
_LOG_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """루트 로거 포맷·레벨 설정. 핸들러가 이미 있으면 basicConfig는 무시된다(멱등)."""
    logging.basicConfig(level=level, format=_LOG_FORMAT)
