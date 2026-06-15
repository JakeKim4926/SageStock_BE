from app.data import market_source


def _raise(*args, **kwargs):
    raise RuntimeError("fdr down")


def test_get_ohlcv_returns_empty_on_source_failure(monkeypatch) -> None:
    monkeypatch.setattr(market_source.fdr, "DataReader", _raise)

    df = market_source.get_ohlcv("UNKNOWN-TICKER", 10)

    # 외부 소스 실패 시 빈 프레임 — 호출부가 데이터 없음으로 graceful 처리(§6).
    assert df.empty
