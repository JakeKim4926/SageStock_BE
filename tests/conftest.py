from collections.abc import AsyncGenerator

import numpy as np
import pandas as pd
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  테이블 등록
from app.core.database import Base, get_db
from app.main import app


def make_ohlcv(rows: int, start_price: float = 100.0) -> pd.DataFrame:
    """테스트용 합성 일봉 OHLCV. fdr 응답을 대체한다(네트워크 미사용)."""
    index = pd.bdate_range(end="2026-06-10", periods=rows)
    steps = np.sin(np.linspace(0, 12, rows)) * 5 + np.linspace(0, 20, rows)
    close = start_price + steps
    open_ = close - 0.5
    high = np.maximum(open_, close) + 1.0
    low = np.minimum(open_, close) - 1.0
    volume = np.full(rows, 1_000_000)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=index,
    )


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    # in-memory SQLite. StaticPool로 단일 커넥션 유지 → 세션 간 동일 DB 공유.
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    await engine.dispose()


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """서비스 레이어 단위 테스트용 세션(client와 동일 in-memory DB 공유)."""
    async with session_factory() as db_session:
        yield db_session
