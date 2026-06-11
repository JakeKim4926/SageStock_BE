import pytest
from httpx import AsyncClient

from app.constants.enums import Market
from app.data import market_source
from tests.conftest import make_ohlcv

_SIGNUP = {"email": "signals@example.com", "password": "s3cret-pw", "name": "시그"}
_INDEX = {"005930": market_source.StockMeta("005930", "삼성전자", Market.KR, "KOSPI")}


async def _access_token(client: AsyncClient) -> str:
    response = await client.post("/v1/auth/signup", json=_SIGNUP)
    return response.json()["accessToken"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_signals_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/v1/signals")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_signals_returns_feed_with_total_count(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_listing_index", lambda: _INDEX)
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))
    token = await _access_token(client)

    await client.put("/v1/watchlist/005930", headers=_auth(token))
    response = await client.get("/v1/signals", headers=_auth(token))

    assert response.status_code == 200
    assert "x-total-count" in response.headers
    body = response.json()
    assert body  # 관심종목이 있으므로 시그널 피드가 비어 있지 않다.
    # 와이어 camelCase (api-spec §0).
    assert "stockName" in body[0]
    assert "riskLevel" in body[0]
    assert "candleIndex" in body[0]


@pytest.mark.asyncio
async def test_signals_empty_watchlist_returns_empty(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))
    token = await _access_token(client)

    response = await client.get("/v1/signals", headers=_auth(token))

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "0"
    assert response.json() == []
