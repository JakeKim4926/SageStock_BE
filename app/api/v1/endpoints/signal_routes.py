from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Market
from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.dependencies.pagination_dependency import PageParams, get_page_params, set_total_count
from app.models.user_model import User
from app.schemas.signal_schema import SignalResponse
from app.services import signal_service

router = APIRouter()


@router.get("", response_model=list[SignalResponse])
async def get_signals(
    response: Response,
    market: Market | None = Query(default=None),
    page: PageParams = Depends(get_page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SignalResponse]:
    results, total = await signal_service.get_signals(db, user.id, market, page)
    set_total_count(response, total)
    return results
