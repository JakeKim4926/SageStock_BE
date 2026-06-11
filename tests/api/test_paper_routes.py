import pytest
from httpx import AsyncClient

from app.constants.enums import Market
from app.data import market_source
from tests.conftest import make_ohlcv

_SIGNUP = {"email": "paper@example.com", "password": "s3cret-pw", "name": "가상"}
_INDEX = {"005930": market_source.StockMeta("005930", "삼성전자", Market.KR, "KOSPI")}


async def _token(client: AsyncClient) -> str:
    response = await client.post("/v1/auth/signup", json=_SIGNUP)
    return response.json()["accessToken"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _trade(side: str = "BUY", price: float = 100.0, quantity: int = 10) -> dict:
    return {
        "ticker": "005930",
        "name": "삼성전자",
        "market": "KR",
        "side": side,
        "price": price,
        "quantity": quantity,
    }


@pytest.mark.asyncio
async def test_paper_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/v1/paper/account")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_account_defaults_to_seed(client: AsyncClient) -> None:
    token = await _token(client)
    response = await client.get("/v1/paper/account", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["cash"] == 10_000_000
    assert body["seed"] == 10_000_000


@pytest.mark.asyncio
async def test_buy_records_trade_and_reduces_cash(client: AsyncClient) -> None:
    token = await _token(client)

    post = await client.post("/v1/paper/trades", json=_trade(), headers=_auth(token))
    assert post.status_code == 201
    created = post.json()
    assert created["id"] > 0
    assert created["timestamp"] > 0

    trades = await client.get("/v1/paper/trades", headers=_auth(token))
    assert trades.status_code == 200
    assert trades.headers["X-Total-Count"] == "1"
    assert len(trades.json()) == 1

    account = await client.get("/v1/paper/account", headers=_auth(token))
    assert account.json()["cash"] == 10_000_000 - 100 * 10


@pytest.mark.asyncio
async def test_buy_insufficient_cash_returns_422(client: AsyncClient) -> None:
    token = await _token(client)

    response = await client.post(
        "/v1/paper/trades",
        json=_trade(price=2_000_000, quantity=10),
        headers=_auth(token),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_sell_without_holding_returns_422(client: AsyncClient) -> None:
    token = await _token(client)

    response = await client.post(
        "/v1/paper/trades",
        json=_trade(side="SELL"),
        headers=_auth(token),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_quantity_returns_400(client: AsyncClient) -> None:
    token = await _token(client)

    response = await client.post(
        "/v1/paper/trades",
        json=_trade(quantity=0),
        headers=_auth(token),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_holdings_aggregate_weighted_average(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(10))
    monkeypatch.setattr(market_source, "get_listing_index", lambda: _INDEX)
    token = await _token(client)

    await client.post("/v1/paper/trades", json=_trade(price=100, quantity=10), headers=_auth(token))
    await client.post("/v1/paper/trades", json=_trade(price=200, quantity=10), headers=_auth(token))

    holdings = await client.get("/v1/paper/holdings", headers=_auth(token))
    assert holdings.status_code == 200
    body = holdings.json()
    assert len(body) == 1
    holding = body[0]
    assert holding["quantity"] == 20
    assert holding["avgPrice"] == 150.0
    assert holding["currentPrice"] > 0
    assert holding["stock"]["exchange"] == "KOSPI"
