from fastapi import APIRouter, Depends, Query

from app.constants.enums import Market
from app.dependencies.auth_dependency import get_current_user
from app.models.user_model import User
from app.schemas.stock_schema import MarketStatusResponse, StockSnapshotResponse
from app.services import market_service

router = APIRouter()


@router.get("/snapshots", response_model=list[StockSnapshotResponse])
async def get_snapshots(
    market: Market | None = Query(default=None),
    _: User = Depends(get_current_user),
) -> list[StockSnapshotResponse]:
    return await market_service.get_snapshots(market)


@router.get("/status", response_model=list[MarketStatusResponse])
async def get_market_status(
    _: User = Depends(get_current_user),
) -> list[MarketStatusResponse]:
    return market_service.get_market_statuses()
