import pytest
from httpx import AsyncClient

_SIGNUP = {"email": "user@example.com", "password": "s3cret-pw", "name": "홍길동"}


async def _signup(client: AsyncClient) -> dict:
    response = await client.post("/v1/auth/signup", json=_SIGNUP)
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_signup_returns_tokens(client: AsyncClient) -> None:
    body = await _signup(client)

    assert body["accessToken"]
    assert body["refreshToken"]
    assert body["accessExpiresIn"] == 1800


@pytest.mark.asyncio
async def test_signup_duplicate_email_conflicts(client: AsyncClient) -> None:
    await _signup(client)
    response = await client.post("/v1/auth/signup", json=_SIGNUP)

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_login_wrong_password_unauthorized(client: AsyncClient) -> None:
    await _signup(client)
    response = await client.post(
        "/v1/auth/login",
        json={"email": _SIGNUP["email"], "password": "wrong", "autoLogin": True},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_refresh_returns_access_only(client: AsyncClient) -> None:
    tokens = await _signup(client)
    response = await client.post(
        "/v1/auth/refresh",
        json={"refreshToken": tokens["refreshToken"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["accessToken"]
    assert body["accessExpiresIn"] == 1800
    # api-spec §1: refresh 응답에 refreshToken 없음(회전 안 함)
    assert "refreshToken" not in body


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    tokens = await _signup(client)

    logout = await client.post(
        "/v1/auth/logout",
        json={"refreshToken": tokens["refreshToken"]},
        headers={"Authorization": f"Bearer {tokens['accessToken']}"},
    )
    assert logout.status_code == 204

    # 무효화된 refresh로 재발급 시도 → 401
    refresh = await client.post(
        "/v1/auth/refresh",
        json={"refreshToken": tokens["refreshToken"]},
    )
    assert refresh.status_code == 401


@pytest.mark.asyncio
async def test_logout_requires_auth(client: AsyncClient) -> None:
    tokens = await _signup(client)
    response = await client.post(
        "/v1/auth/logout",
        json={"refreshToken": tokens["refreshToken"]},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
