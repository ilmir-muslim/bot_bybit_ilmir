import pytest
from unittest.mock import patch, MagicMock
from app.services.bot_runner import TradingBot


@patch("app.services.bot_runner.place_market_order")
@patch("app.services.bot_runner.get_price_history")
@patch("app.services.bot_runner.BybitService")
def test_qty_adjustment_on_insufficient_balance(
    mock_service, mock_get_price_history, mock_place_order
):
    bot = TradingBot(symbol="XLMUSDT")

    # Подменяем стратегию вручную
    mock_strategy = MagicMock()
    mock_strategy.should_trade.return_value = "BUY"
    bot.strategy = mock_strategy

    # История цен
    mock_get_price_history.return_value = [{"close": 0.25} for _ in range(30)]

    # Баланс и цена
    fake_balance = 10.0
    fake_price = 0.25  # qty = 10 / 0.25 = 40
    mock_service.return_value.get_balance.return_value = fake_balance
    mock_service.return_value.get_price.return_value = fake_price
    mock_service.return_value.get_qty_precision.return_value = 1

    # Запуск
    bot.run_once()

    # Проверка: ордер был вызван
    assert mock_place_order.called, "Ожидался вызов place_market_order"

    # Извлекаем аргументы
    args, _ = mock_place_order.call_args
    qty = float(args[2])
    assert qty < 40.0, f"Ожидали qty < 40, но получили {qty}"
    assert qty == round(qty, 1), f"Ожидали округление до 1 знака, но получили {qty}"
