import pytest
from httpx import AsyncClient

from app.data import kis_source, market_source
from app.data.kis_source import KisQuote
from tests.conftest import make_ohlcv

_SIGNUP = {"email": "market@example.com", "password": "s3cret-pw", "name": "메이"}


async def _access_token(client: AsyncClient) -> str:
    response = await client.post("/v1/auth/signup", json=_SIGNUP)
    return response.json()["accessToken"]


@pytest.mark.asyncio
async def test_quote_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/v1/stocks/005930/quote")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_quote_returns_camel_case(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(10))
    token = await _access_token(client)

    response = await client.get(
        "/v1/stocks/005930/quote",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "005930"
    assert "changePercent" in body  # 와이어 camelCase (api-spec §0)


@pytest.mark.asyncio
async def test_quote_uses_kis_realtime_when_available(client: AsyncClient, monkeypatch) -> None:
    async def fake_quote(ticker: str) -> KisQuote:
        return KisQuote(
            price=80000.0,
            change=1500.0,
            change_percent=1.91,
            open=79000.0,
            high=80500.0,
            low=78500.0,
            volume=1234567,
        )

    monkeypatch.setattr(kis_source, "get_current_quote", fake_quote)
    token = await _access_token(client)

    response = await client.get(
        "/v1/stocks/005930/quote",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["price"] == 80000.0
    assert body["isDelayed"] is False  # KIS 실시간이면 지연 아님


@pytest.mark.asyncio
async def test_quote_falls_back_to_delayed_when_kis_unavailable(
    client: AsyncClient, monkeypatch
) -> None:
    async def no_quote(ticker: str) -> None:
        return None

    monkeypatch.setattr(kis_source, "get_current_quote", no_quote)
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(10))
    token = await _access_token(client)

    response = await client.get(
        "/v1/stocks/005930/quote",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["isDelayed"] is True  # 폴백 시 지연 시세


@pytest.mark.asyncio
async def test_indicators_insufficient_data_returns_422(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(30))
    token = await _access_token(client)

    response = await client.get(
        "/v1/stocks/005930/indicators",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_market_status_returns_both_markets(client: AsyncClient) -> None:
    token = await _access_token(client)

    response = await client.get(
        "/v1/market/status",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert len(response.json()) == 2
