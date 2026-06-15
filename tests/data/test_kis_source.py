import pytest

from app.core.config import settings
from app.data.kis_source import _parse_quote, get_current_quote


def _output(**overrides: str) -> dict[str, str]:
    base = {
        "stck_prpr": "80000",
        "prdy_vrss": "1500",
        "prdy_vrss_sign": "2",  # 상승
        "stck_oprc": "79000",
        "stck_hgpr": "80500",
        "stck_lwpr": "78500",
        "acml_vol": "1234567",
    }
    base.update(overrides)
    return base


def test_parse_quote_up() -> None:
    quote = _parse_quote(_output())

    assert quote.price == 80000.0
    assert quote.change == 1500.0
    assert quote.change_percent == pytest.approx(1500 / 78500 * 100)
    assert quote.open == 79000.0
    assert quote.volume == 1234567


def test_parse_quote_down_uses_sign() -> None:
    # prdy_vrss는 절댓값, 부호는 prdy_vrss_sign(5=하락)에서 온다.
    quote = _parse_quote(_output(prdy_vrss="1500", prdy_vrss_sign="5"))

    assert quote.change == -1500.0
    assert quote.change_percent < 0


@pytest.mark.asyncio
async def test_get_current_quote_none_when_not_configured() -> None:
    # 기본 설정은 KIS 키가 비어 있음 → 네트워크 호출 없이 None.
    assert await get_current_quote("005930") is None


@pytest.mark.asyncio
async def test_get_current_quote_none_for_non_kr_ticker(monkeypatch) -> None:
    monkeypatch.setattr(settings, "KIS_APP_KEY", "key")
    monkeypatch.setattr(settings, "KIS_APP_SECRET", "secret")

    # 미국 티커(비6자리 숫자)는 KIS 국내 현재가 대상 아님 → None.
    assert await get_current_quote("AAPL") is None
