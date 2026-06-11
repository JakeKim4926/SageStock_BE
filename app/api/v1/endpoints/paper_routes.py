from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.dependencies.pagination_dependency import PageParams, get_page_params, set_total_count
from app.models.user_model import User
from app.schemas.paper_schema import (
    AccountResponse,
    HoldingResponse,
    PaperTradeCreateRequest,
    PaperTradeResponse,
)
from app.services import paper_service

router = APIRouter()


@router.get("/trades", response_model=list[PaperTradeResponse])
async def get_trades(
    response: Response,
    page: PageParams = Depends(get_page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PaperTradeResponse]:
    results, total = await paper_service.get_trades(db, user.id, page)
    set_total_count(response, total)
    return results


@router.post(
    "/trades",
    response_model=PaperTradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_trade(
    request: PaperTradeCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaperTradeResponse:
    return await paper_service.record_trade(db, user.id, request)


@router.get("/holdings", response_model=list[HoldingResponse])
async def get_holdings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[HoldingResponse]:
    return await paper_service.get_holdings(db, user.id)


@router.get("/account", response_model=AccountResponse)
async def get_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    return await paper_service.get_account(db, user.id)
