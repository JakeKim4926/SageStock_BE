from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth_routes,
    market_routes,
    paper_routes,
    signal_routes,
    stock_routes,
    watchlist_routes,
)

# /v1 도메인 라우터 조립 지점.
api_router = APIRouter()
api_router.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
api_router.include_router(stock_routes.router, prefix="/stocks", tags=["stocks"])
api_router.include_router(market_routes.router, prefix="/market", tags=["market"])
api_router.include_router(signal_routes.router, prefix="/signals", tags=["signals"])
api_router.include_router(watchlist_routes.router, prefix="/watchlist", tags=["watchlist"])
api_router.include_router(paper_routes.router, prefix="/paper", tags=["paper"])
