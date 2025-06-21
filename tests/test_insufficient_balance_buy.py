import pytest
from unittest.mock import MagicMock
from app.services.bybit_service import BybitService
from app.services.bot_runner import TradingBot


@pytest.fixture
def mock_bybit(monkeypatch):
    service = BybitService()
    
    # Поддельные данные
    mock_price = 0.24963
    mock_balance = 10.54
    mock_precision = 1

    service.get_price = MagicMock(return_value=mock_price)
    service.get_qty_precision = MagicMock(return_value=mock_precision)
    service.get_balance = MagicMock(side_effect=lambda coin: mock_balance if coin == "USDT" else 0)

    placed_orders = []

    def mock_place_market_order(symbol, side, qty):
        placed_orders.append(qty)

    monkeypatch.setattr("app.services.bot_runner.place_market_order", mock_place_market_order)

    return service, placed_orders, mock_price, mock_balance


def test_insufficient_balance_avoided(mock_bybit):
    service, placed_orders, price, balance = mock_bybit

    bot = TradingBot("XLMUSDT")
    bot.bybit = service
    bot.strategy.should_trade = lambda candles: "BUY"

    bot.run_once()

    assert placed_orders, "Ордер не был размещён"
    qty = placed_orders[0]
    total_value = qty * price
    max_allowed = balance * 0.99

    assert total_value <= max_allowed, (
        f"Итоговая стоимость ордера {total_value:.5f} превышает лимит {max_allowed:.5f}"
    )
