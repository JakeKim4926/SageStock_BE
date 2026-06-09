from dataclasses import dataclass

from fastapi import Query, Response

from app.constants.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, TOTAL_COUNT_HEADER


@dataclass(frozen=True)
class PageParams:
    """api-spec §0 offset/limit 페이지네이션 파라미터."""

    offset: int
    limit: int


def get_page_params(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageParams:
    return PageParams(offset=offset, limit=limit)


def set_total_count(response: Response, total: int) -> None:
    """총 개수를 X-Total-Count 응답 헤더로 노출 (api-spec §0)."""
    response.headers[TOTAL_COUNT_HEADER] = str(total)
