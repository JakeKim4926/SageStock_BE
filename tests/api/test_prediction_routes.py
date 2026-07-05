import numpy as np
import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Market
from app.data import market_source, supply_source
from app.ml import features
from tests.conftest import make_ohlcv, seed_stock_meta

_SIGNUP = {"email": "pred@example.com", "password": "s3cret-pw", "name": "예측"}
_ROWS = [("005930", "삼성전자", Market.KR, "KOSPI")]


async def _access_token(client: AsyncClient) -> str:
    response = await client.post("/v1/auth/signup", json=_SIGNUP)
    return response.json()["accessToken"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _market_features(rows: int = 250) -> pd.DataFrame:
    index = pd.bdate_range(end="2026-06-10", periods=rows)
    return pd.DataFrame(
        {
            "Mkt_Ret20": np.linspace(-1.0, 5.0, rows),
            "Mkt_Ret60": np.linspace(-2.0, 8.0, rows),
            "Mkt_Vol20": np.full(rows, 1.5),
        },
        index=index,
    )


def _empty_supply() -> pd.DataFrame:
    return pd.DataFrame(columns=["Code", "Date", "Frgn", "Inst"])


@pytest.mark.asyncio
async def test_predictions_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/v1/predictions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_predictions_returns_feed_with_contract_fields(
    client: AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))
    monkeypatch.setattr(features, "get_market_features", lambda: _market_features(250))
    monkeypatch.setattr(supply_source, "get_recent_supply", lambda lookback: _empty_supply())
    await seed_stock_meta(session, _ROWS)
    token = await _access_token(client)

    await client.put("/v1/watchlist/005930", headers=_auth(token))
    response = await client.get("/v1/predictions", headers=_auth(token))

    assert response.status_code == 200
    assert "x-total-count" in response.headers
    body = response.json()
    assert body  # 관심종목이 있으므로 예측 피드가 비어 있지 않다.
    item = body[0]
    assert item["status"] == "READY"
    # 와이어 camelCase (api-spec §0).
    assert "riseProbability" in item
    assert "expectedReturnPercent" in item
    assert "confidence" in item
    assert "reasons" in item
    assert "riskFactors" in item
    assert item["expectedReturnPercent"] == 0  # 1단계 미산출.


@pytest.mark.asyncio
async def test_predictions_non_kr_is_unavailable(
    client: AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(features, "get_market_features", lambda: _market_features(250))
    monkeypatch.setattr(supply_source, "get_recent_supply", lambda lookback: _empty_supply())
    await seed_stock_meta(session, [("AAPL", "Apple", Market.US, "NASDAQ")])
    token = await _access_token(client)

    await client.put("/v1/watchlist/AAPL", headers=_auth(token))
    response = await client.get("/v1/predictions", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body[0]["status"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_predictions_empty_watchlist_returns_empty(
    client: AsyncClient, monkeypatch
) -> None:
    token = await _access_token(client)

    response = await client.get("/v1/predictions", headers=_auth(token))

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "0"
    assert response.json() == []
