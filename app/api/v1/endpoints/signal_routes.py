from fastapi import APIRouter, Depends, Query, Response

from app.constants.enums import Market
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
    _: User = Depends(get_current_user),
) -> list[SignalResponse]:
    results, total = await signal_service.get_signals(market, page)
    set_total_count(response, total)
    return results
