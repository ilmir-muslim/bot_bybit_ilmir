from abc import ABC, abstractmethod
from typing import Optional


class Strategy(ABC):
    """Базовый интерфейс для торговой стратегии."""

    @abstractmethod
    def should_trade(self, prices: list[float]) -> Optional[str]:
        """Решает, стоит ли покупать или продавать.
        :param prices: список последних цен
        :return: "BUY", "SELL" или None
        """
        pass
