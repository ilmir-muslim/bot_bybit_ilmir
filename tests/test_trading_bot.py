import pytest
from unittest.mock import patch, MagicMock


@patch("app.services.bot_runner.place_market_order")
@patch("app.services.bot_runner.round_qty")
@patch("app.services.bot_runner.get_price_history")
@patch("app.services.bot_runner.BybitService")
def test_buy_rounding_logic(mock_service, mock_get_price_history, mock_round_qty, mock_place_market_order):
    from app.services.bot_runner import TradingBot
    bot = TradingBot("DOGEUSDT")

    # Мокаем методы
    mock_service.return_value.get_balance.return_value = 100  # USDT
    mock_service.return_value.get_price.return_value = 0.1
    mock_service.return_value.get_qty_precision.return_value = 2
    mock_get_price_history.return_value = [{"close": 0.1}] * 30
    mock_round_qty.return_value = 999.99

    bot.strategy.should_trade = MagicMock(return_value="BUY")

    bot.run_once()

    mock_round_qty.assert_called_once_with(1000.0, 2)
    mock_place_market_order.assert_called_once_with("DOGEUSDT", "Buy", 999.99)


@patch("app.services.bot_runner.place_market_order")
@patch("app.services.bot_runner.round_qty")
@patch("app.services.bot_runner.get_price_history")
@patch("app.services.bot_runner.BybitService")
def test_sell_rounding_logic(mock_service, mock_get_price_history, mock_round_qty, mock_place_market_order):
    from app.services.bot_runner import TradingBot
    bot = TradingBot("DOGEUSDT")

    # Правильная настройка
    mock_service.return_value.get_balance.return_value = 57.8956
    mock_service.return_value.get_qty_precision.return_value = 1
    mock_get_price_history.return_value = [{"close": 0.1}] * 30
    mock_round_qty.return_value = 57.8

    bot.strategy.should_trade = MagicMock(return_value="SELL")

    bot.run_once()

    mock_round_qty.assert_called_once_with(57.8956, 1)
    mock_place_market_order.assert_called_once_with("DOGEUSDT", "Sell", 57.8)
