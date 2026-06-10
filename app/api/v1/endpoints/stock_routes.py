from fastapi import APIRouter, Depends, Query, Response

from app.constants.enums import Market
from app.dependencies.auth_dependency import get_current_user
from app.dependencies.pagination_dependency import PageParams, get_page_params, set_total_count
from app.models.user_model import User
from app.schemas.indicator_schema import IndicatorSetResponse
from app.schemas.stock_schema import QuoteResponse, StockResponse
from app.services import stock_service

router = APIRouter()


# /search 는 /{ticker} 보다 먼저 선언해야 "search"가 ticker로 매칭되지 않는다.
@router.get("/search", response_model=list[StockResponse])
async def search_stocks(
    response: Response,
    q: str = Query(min_length=1),
    market: Market | None = Query(default=None),
    page: PageParams = Depends(get_page_params),
    _: User = Depends(get_current_user),
) -> list[StockResponse]:
    results, total = await stock_service.search_stocks(q, market, page)
    set_total_count(response, total)
    return results


@router.get("/{ticker}", response_model=StockResponse)
async def get_stock(
    ticker: str,
    _: User = Depends(get_current_user),
) -> StockResponse:
    return await stock_service.get_stock_meta(ticker)


@router.get("/{ticker}/quote", response_model=QuoteResponse)
async def get_quote(
    ticker: str,
    _: User = Depends(get_current_user),
) -> QuoteResponse:
    return await stock_service.get_quote(ticker)


@router.get("/{ticker}/indicators", response_model=IndicatorSetResponse)
async def get_indicators(
    ticker: str,
    _: User = Depends(get_current_user),
) -> IndicatorSetResponse:
    return await stock_service.get_indicators(ticker)
