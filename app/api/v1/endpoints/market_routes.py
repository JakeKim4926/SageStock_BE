from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Market
from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.models.user_model import User
from app.schemas.stock_schema import MarketStatusResponse, StockSnapshotResponse
from app.services import market_service

router = APIRouter()


@router.get("/snapshots", response_model=list[StockSnapshotResponse])
async def get_snapshots(
    market: Market | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StockSnapshotResponse]:
    return await market_service.get_snapshots(db, user.id, market)


@router.get("/status", response_model=list[MarketStatusResponse])
async def get_market_status(
    _: User = Depends(get_current_user),
) -> list[MarketStatusResponse]:
    return market_service.get_market_statuses()
