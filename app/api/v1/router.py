from fastapi import APIRouter

from app.api.v1.endpoints import auth_routes, market_routes, stock_routes

# /v1 도메인 라우터 조립 지점. B2~B3에서 signals/watchlist/paper 추가.
api_router = APIRouter()
api_router.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
api_router.include_router(stock_routes.router, prefix="/stocks", tags=["stocks"])
api_router.include_router(market_routes.router, prefix="/market", tags=["market"])
