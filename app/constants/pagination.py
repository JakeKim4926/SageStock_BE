from typing import Final

# api-spec §0 페이지네이션: limit 기본 20, 최대 100. 총 개수는 X-Total-Count 헤더.
DEFAULT_PAGE_SIZE: Final = 20
MAX_PAGE_SIZE: Final = 100
TOTAL_COUNT_HEADER: Final = "X-Total-Count"
