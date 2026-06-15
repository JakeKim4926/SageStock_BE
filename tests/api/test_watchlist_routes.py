import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Market
from tests.conftest import seed_stock_meta

_SIGNUP = {"email": "watch@example.com", "password": "s3cret-pw", "name": "관심"}
_ROWS = [
    ("005930", "삼성전자", Market.KR, "KOSPI"),
    ("AAPL", "Apple Inc.", Market.US, "NASDAQ"),
]


async def _token(client: AsyncClient) -> str:
    response = await client.post("/v1/auth/signup", json=_SIGNUP)
    return response.json()["accessToken"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_watchlist_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/v1/watchlist")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_add_then_get_returns_stock(client: AsyncClient, session: AsyncSession) -> None:
    await seed_stock_meta(session, _ROWS)
    token = await _token(client)

    put = await client.put("/v1/watchlist/005930", headers=_auth(token))
    assert put.status_code == 204

    get = await client.get("/v1/watchlist", headers=_auth(token))
    assert get.status_code == 200
    body = get.json()
    assert len(body) == 1
    assert body[0]["ticker"] == "005930"
    assert body[0]["exchange"] == "KOSPI"


@pytest.mark.asyncio
async def test_put_is_idempotent(client: AsyncClient, session: AsyncSession) -> None:
    await seed_stock_meta(session, _ROWS)
    token = await _token(client)

    await client.put("/v1/watchlist/005930", headers=_auth(token))
    second = await client.put("/v1/watchlist/005930", headers=_auth(token))
    assert second.status_code == 204

    get = await client.get("/v1/watchlist", headers=_auth(token))
    assert len(get.json()) == 1


@pytest.mark.asyncio
async def test_delete_removes_and_is_idempotent(client: AsyncClient, session: AsyncSession) -> None:
    await seed_stock_meta(session, _ROWS)
    token = await _token(client)

    await client.put("/v1/watchlist/005930", headers=_auth(token))
    delete = await client.delete("/v1/watchlist/005930", headers=_auth(token))
    assert delete.status_code == 204

    get = await client.get("/v1/watchlist", headers=_auth(token))
    assert get.json() == []

    # 없는 티커 제거도 204(멱등).
    again = await client.delete("/v1/watchlist/005930", headers=_auth(token))
    assert again.status_code == 204
