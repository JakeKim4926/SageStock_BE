from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import error_codes
from app.constants.enums import Market, TradeSide
from app.constants.market import QUOTE_LOOKBACK_DAYS
from app.constants.paper import VIRTUAL_CASH_SEED
from app.core.exceptions import AppError
from app.data import market_source
from app.dependencies.pagination_dependency import PageParams
from app.models.paper_account_model import PaperAccount
from app.models.paper_trade_model import PaperTrade
from app.repositories import paper_repository
from app.schemas.paper_schema import (
    AccountResponse,
    HoldingResponse,
    PaperTradeCreateRequest,
    PaperTradeResponse,
)
from app.schemas.stock_schema import StockResponse


async def get_trades(
    db: AsyncSession,
    user_id: int,
    page: PageParams,
) -> tuple[list[PaperTradeResponse], int]:
    trades = await paper_repository.list_trades(db, user_id, page.offset, page.limit)
    total = await paper_repository.count_trades(db, user_id)
    return [_to_trade_response(trade) for trade in trades], total


async def record_trade(
    db: AsyncSession,
    user_id: int,
    request: PaperTradeCreateRequest,
) -> PaperTradeResponse:
    account = await _get_or_create_account(db, user_id)
    cost = request.price * request.quantity

    if request.side is TradeSide.BUY:
        if account.cash < cost:
            raise AppError(error_codes.INSUFFICIENT_DATA, "예수금이 부족합니다.", 422)
        account.cash -= cost
    else:
        held = _quantity_for_ticker(
            await paper_repository.list_all_trades_asc(db, user_id),
            request.ticker,
        )
        if held < request.quantity:
            raise AppError(error_codes.INSUFFICIENT_DATA, "보유 수량이 부족합니다.", 422)
        account.cash += cost

    trade = PaperTrade(
        user_id=user_id,
        ticker=request.ticker,
        name=request.name,
        market=request.market.value,
        side=request.side.value,
        price=request.price,
        quantity=request.quantity,
        timestamp=_now_epoch_ms(),
    )
    paper_repository.add_trade(db, trade)
    await db.commit()
    await db.refresh(trade)

    return _to_trade_response(trade)


async def get_holdings(db: AsyncSession, user_id: int) -> list[HoldingResponse]:
    trades = await paper_repository.list_all_trades_asc(db, user_id)
    holdings = _aggregate_holdings(trades)
    if not holdings:
        return []

    # 현재가는 quote(§4.2)와 동일 소스 재사용, exchange는 리스팅 인덱스에서 조인.
    index = await run_in_threadpool(market_source.get_listing_index)

    responses: list[HoldingResponse] = []
    for ticker, agg in holdings.items():
        current_price = await run_in_threadpool(_current_price, ticker)
        meta = index.get(ticker)
        exchange = meta.exchange if meta is not None else ""
        responses.append(
            HoldingResponse(
                stock=StockResponse(
                    ticker=ticker,
                    name=agg.name,
                    market=Market(agg.market),
                    exchange=exchange,
                ),
                quantity=agg.quantity,
                avg_price=agg.avg_price,
                current_price=current_price,
            )
        )
    return responses


async def get_account(db: AsyncSession, user_id: int) -> AccountResponse:
    account = await _get_or_create_account(db, user_id)
    return AccountResponse(cash=account.cash, seed=account.seed)


@dataclass
class _HoldingAgg:
    name: str
    market: str
    quantity: int
    avg_price: float


def _aggregate_holdings(trades: list[PaperTrade]) -> dict[str, _HoldingAgg]:
    """체결 순서대로 보유수량·평단을 누적. 매수는 가중평균, 매도는 평단 유지·수량 차감."""
    holdings: dict[str, _HoldingAgg] = {}

    for trade in trades:
        agg = holdings.get(trade.ticker)
        if agg is None:
            agg = _HoldingAgg(name=trade.name, market=trade.market, quantity=0, avg_price=0.0)
            holdings[trade.ticker] = agg

        agg.name = trade.name
        agg.market = trade.market

        if trade.side == TradeSide.BUY:
            new_quantity = agg.quantity + trade.quantity
            agg.avg_price = (agg.avg_price * agg.quantity + trade.price * trade.quantity) / new_quantity
            agg.quantity = new_quantity
        else:
            agg.quantity -= trade.quantity
            if agg.quantity <= 0:
                agg.quantity = 0
                agg.avg_price = 0.0

    return {ticker: agg for ticker, agg in holdings.items() if agg.quantity > 0}


def _quantity_for_ticker(trades: list[PaperTrade], ticker: str) -> int:
    agg = _aggregate_holdings(trades).get(ticker)
    return agg.quantity if agg is not None else 0


def _current_price(ticker: str) -> float:
    df = market_source.get_ohlcv(ticker, QUOTE_LOOKBACK_DAYS)
    if df.empty:
        return 0.0
    return float(df.iloc[-1]["Close"])


async def _get_or_create_account(db: AsyncSession, user_id: int) -> PaperAccount:
    account = await paper_repository.get_account(db, user_id)
    if account is not None:
        return account

    # 시드 예수금으로 계정 지연 생성(가입 시 미생성 — feature-spec §4.6 cash=seed).
    account = PaperAccount(user_id=user_id, cash=VIRTUAL_CASH_SEED, seed=VIRTUAL_CASH_SEED)
    paper_repository.add_account(db, account)
    await db.commit()
    await db.refresh(account)
    return account


def _to_trade_response(trade: PaperTrade) -> PaperTradeResponse:
    return PaperTradeResponse(
        id=trade.id,
        ticker=trade.ticker,
        name=trade.name,
        market=Market(trade.market),
        side=TradeSide(trade.side),
        price=trade.price,
        quantity=trade.quantity,
        timestamp=trade.timestamp,
    )


def _now_epoch_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)
