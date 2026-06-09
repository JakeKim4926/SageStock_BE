from fastapi import APIRouter

from app.api.v1.endpoints import auth_routes

# /v1 도메인 라우터 조립 지점. B1~B3에서 stocks/market/signals/watchlist/paper 추가.
api_router = APIRouter()
api_router.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
