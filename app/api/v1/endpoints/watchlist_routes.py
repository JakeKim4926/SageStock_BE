from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.models.user_model import User
from app.schemas.stock_schema import StockResponse
from app.services import watchlist_service

router = APIRouter()


@router.get("", response_model=list[StockResponse])
async def get_watchlist(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StockResponse]:
    return await watchlist_service.get_watchlist(db, user.id)


@router.put("/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def add_watchlist(
    ticker: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await watchlist_service.add_to_watchlist(db, user.id, ticker)


@router.delete("/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_watchlist(
    ticker: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await watchlist_service.remove_from_watchlist(db, user.id, ticker)
