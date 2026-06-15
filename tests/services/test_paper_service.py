from app.models.paper_trade_model import PaperTrade
from app.services.paper_service import _aggregate_holdings


def _trade(side: str, price: float, quantity: int) -> PaperTrade:
    return PaperTrade(
        ticker="005930",
        name="삼성전자",
        market="KR",
        side=side,
        price=price,
        quantity=quantity,
        timestamp=0,
    )


def test_buys_use_weighted_average() -> None:
    trades = [_trade("BUY", 100.0, 10), _trade("BUY", 200.0, 10)]

    holdings = _aggregate_holdings(trades)

    assert holdings["005930"].quantity == 20
    assert holdings["005930"].avg_price == 150.0


def test_sell_keeps_avg_and_reduces_quantity() -> None:
    trades = [_trade("BUY", 100.0, 10), _trade("BUY", 200.0, 10), _trade("SELL", 300.0, 5)]

    holdings = _aggregate_holdings(trades)

    assert holdings["005930"].quantity == 15
    assert holdings["005930"].avg_price == 150.0


def test_full_sell_clears_holding() -> None:
    trades = [_trade("BUY", 100.0, 10), _trade("SELL", 150.0, 10)]

    assert _aggregate_holdings(trades) == {}
