from app.trader import get_price_history
from typing import Optional
from .base import Strategy


class SimpleMovingAverageStrategy(Strategy):
    """
    Простая стратегия, основанная на средней цене за два периода.

    Сравнивает среднюю цену за короткий период (например, последние 5 минут)
    и за длинный период (например, последние 20 минут).

    Если цена за короткий период выше — значит цена растёт, можно купить.
    Если цена за короткий период ниже — цена падает, можно продать.

    Это попытка поймать тренд — покупать, когда цена растёт, и продавать, когда падает.
    """


    def __init__(self, symbol: str, short_window: int = 5, long_window: int = 15):
        self.symbol = symbol
        self.short_window = short_window
        self.long_window = long_window

    def should_trade(self, _: list[float] = None) -> Optional[str]:
        prices = get_price_history(self.symbol, limit=max(self.short_window, self.long_window))
        if len(prices) < self.long_window:
            return None

        short_avg = sum(prices[-self.short_window:]) / self.short_window
        long_avg = sum(prices[-self.long_window:]) / self.long_window

        if short_avg > long_avg:
            return "BUY"
        elif short_avg < long_avg:
            return "SELL"
        return None
