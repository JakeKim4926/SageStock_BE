import pytest
from httpx import AsyncClient

from app.data import market_source
from tests.conftest import make_ohlcv

_SIGNUP = {"email": "signals@example.com", "password": "s3cret-pw", "name": "시그"}


async def _access_token(client: AsyncClient) -> str:
    response = await client.post("/v1/auth/signup", json=_SIGNUP)
    return response.json()["accessToken"]


@pytest.mark.asyncio
async def test_signals_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/v1/signals")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_signals_returns_feed_with_total_count(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))
    token = await _access_token(client)

    response = await client.get(
        "/v1/signals",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert "x-total-count" in response.headers
    body = response.json()
    if body:
        # 와이어 camelCase (api-spec §0).
        assert "stockName" in body[0]
        assert "riskLevel" in body[0]
        assert "candleIndex" in body[0]
