import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Market
from app.core.exceptions import AppError
from app.dependencies.pagination_dependency import PageParams
from app.services import stock_meta_service
from tests.conftest import seed_stock_meta

_ROWS = [
    ("005930", "삼성전자", Market.KR, "KOSPI"),
    ("AAPL", "Apple Inc.", Market.US, "NASDAQ"),
]


@pytest.mark.asyncio
async def test_search_filters_by_query_and_market(session: AsyncSession) -> None:
    await seed_stock_meta(session, _ROWS)

    results, total = await stock_meta_service.search(
        session, "apple", None, PageParams(offset=0, limit=20)
    )

    assert total == 1
    assert results[0].ticker == "AAPL"


@pytest.mark.asyncio
async def test_search_market_filter(session: AsyncSession) -> None:
    await seed_stock_meta(session, _ROWS)

    results, total = await stock_meta_service.search(
        session, "0", Market.KR, PageParams(offset=0, limit=20)
    )

    assert total == 1
    assert results[0].ticker == "005930"


@pytest.mark.asyncio
async def test_search_empty_query_returns_empty(session: AsyncSession) -> None:
    await seed_stock_meta(session, _ROWS)

    results, total = await stock_meta_service.search(
        session, "   ", None, PageParams(offset=0, limit=20)
    )

    assert results == []
    assert total == 0


@pytest.mark.asyncio
async def test_get_meta_returns_stock(session: AsyncSession) -> None:
    await seed_stock_meta(session, _ROWS)

    meta = await stock_meta_service.get_meta(session, "005930")

    assert meta.name == "삼성전자"
    assert meta.market == Market.KR


@pytest.mark.asyncio
async def test_get_meta_not_found(session: AsyncSession) -> None:
    with pytest.raises(AppError) as exc_info:
        await stock_meta_service.get_meta(session, "XXXX")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_many_omits_missing(session: AsyncSession) -> None:
    await seed_stock_meta(session, _ROWS)

    metas = await stock_meta_service.resolve_many(session, ["005930", "UNKNOWN"])

    assert set(metas) == {"005930"}
