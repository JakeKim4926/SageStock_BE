import pandas as pd

from app.constants.enums import SignalType
from app.services.signal_detector import detect_signals


def _window(overrides: dict[str, list[float]]) -> pd.DataFrame:
    length = len(next(iter(overrides.values())))
    columns: dict[str, list[float]] = {
        "Close": [100.0] * length,
        "High": [101.0] * length,
        "Low": [99.0] * length,
        "RSI": [50.0] * length,
        "EMA5": [100.0] * length,
        "EMA20": [100.0] * length,
        "BB_Upper": [110.0] * length,
        "BB_Lower": [90.0] * length,
    }
    columns.update(overrides)
    index = pd.bdate_range(end="2026-06-10", periods=length)
    return pd.DataFrame(columns, index=index)


def _types(window: pd.DataFrame) -> list[SignalType]:
    return [signal.type for signal in detect_signals(window)]


def test_flat_window_has_no_signals() -> None:
    assert detect_signals(_window({"Close": [100.0] * 10})) == []


def test_golden_cross_detected() -> None:
    window = _window({"EMA5": [98.0, 98.0, 99.0, 100.0, 101.0]})
    signals = detect_signals(window)

    assert [s.type for s in signals] == [SignalType.GOLDEN_CROSS]
    assert signals[0].candle_index == 4


def test_dead_cross_detected() -> None:
    window = _window({"EMA5": [102.0, 102.0, 101.0, 100.0, 99.0]})
    assert _types(window) == [SignalType.DEAD_CROSS]


def test_rsi_oversold_on_entry() -> None:
    window = _window({"RSI": [50.0, 35.0, 28.0]})
    assert _types(window) == [SignalType.RSI_OVERSOLD]


def test_rsi_overbought_on_entry() -> None:
    window = _window({"RSI": [50.0, 65.0, 72.0]})
    assert _types(window) == [SignalType.RSI_OVERBOUGHT]


def test_bollinger_breakout_upper() -> None:
    window = _window({"Close": [100.0, 100.0, 111.0]})
    assert _types(window) == [SignalType.BOLLINGER_BREAKOUT]


def test_bullish_divergence_detected() -> None:
    window = _window(
        {
            "Low": [100.0, 95.0, 100.0, 100.0, 90.0, 100.0],
            "RSI": [50.0, 40.0, 50.0, 50.0, 45.0, 50.0],
        }
    )
    signals = detect_signals(window)

    assert [s.type for s in signals] == [SignalType.BULLISH_DIVERGENCE]
    assert signals[0].candle_index == 4
