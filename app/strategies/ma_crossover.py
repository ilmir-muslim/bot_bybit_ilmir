import time
import numpy as np
from typing import Optional
from app.services.bybit_service import BybitService
from app.database.engine import SessionLocal
from app.database.models import TradeLog


class MovingAverageStrategy:
    """
    Стратегия "пересечения скользящих" + фильтры: не продавать в минус и стоп-лосс.
    """
    def __init__(self, symbol: str, short_window: int = 7, long_window: int = 25):
        self.symbol = symbol
        self.short_window = short_window
        self.long_window = long_window
        self.bybit = BybitService()
        self.last_action = self._load_last_action()
        self.min_profit_margin = 0.002
        self.max_loss = 0.03  # Уменьшен стоп-лосс
        self.trailing_stop_activation = 0.01  # Включается при +1%
        self.trailing_stop_distance = 0.005   # Сработает, если цена упадёт на 0.5% от пика
        self.max_price_since_buy = None
        self.last_trade_time = time.time()

    def _load_last_action(self) -> str | None:
        """
        Определяет последнее действие по логам, если их нет — через API.
        """
        print("[DEBUG] Нет последней покупки в логах — ищем через API...")

        try:
            filled_orders = self.bybit.get_filled_orders(self.symbol)
            if filled_orders:
                last_order = filled_orders[0]  # последний по времени
                side = last_order["side"].upper()
                print(f"[DEBUG] Последнее действие через API: {side}")
                return side
        except Exception as e:
            print(f"[ERROR] Ошибка при получении последней сделки с API: {e}")

        return None


    def _get_last_buy_price(self) -> float | None:
        db = SessionLocal()
        try:
            last_buy = (
                db.query(TradeLog)
                .filter(
                    TradeLog.symbol == self.symbol,
                    TradeLog.side == "BUY"
                )
                .order_by(TradeLog.timestamp.desc())
                .first()
            )

            if last_buy:
                return last_buy.avg_price

            # 👉 если нет записи в логах, пробуем через API
            last_action = self._load_last_action()
            if last_action == "BUY":
                # Можно попробовать также достать цену последнего BUY
                filled_orders = self.bybit.get_filled_orders(self.symbol)
                for order in filled_orders:
                    if order["side"].upper() == "BUY" and order["orderStatus"] == "Filled":
                        return float(order["avgPrice"])
            
            return None
        finally:
            db.close()


    def should_trade(self, prices: list[float]) -> Optional[str]:
        if len(prices) < self.long_window:
            return None

        short_ma = np.mean(prices[-self.short_window:])
        long_ma = np.mean(prices[-self.long_window:])
        current_price = self.bybit.get_price(self.symbol)

        if current_price is None:
            print("[ERROR] Нет цены.")
            return None

        print(f"[DEBUG] short MA: {short_ma:.6f}, long MA: {long_ma:.6f}")

        if short_ma > long_ma and self.last_action != "BUY":
            self.last_action = "BUY"
            self.max_price_since_buy = current_price
            self.last_trade_time = time.time()
            return "BUY"

        elif short_ma < long_ma and self.last_action == "BUY":
            balance = self.bybit.get_balance(self.symbol.replace("USDT", ""))
            last_buy_price = self._get_last_buy_price()

            if balance > 0 and last_buy_price:
                profit_ratio = current_price / last_buy_price - 1

                # Обновление максимальной цены
                if self.max_price_since_buy is None or current_price > self.max_price_since_buy:
                    self.max_price_since_buy = current_price

                # 📉 Трейлинг-стоп
                if (
                    self.max_price_since_buy >= last_buy_price * (1 + self.trailing_stop_activation)
                    and current_price <= self.max_price_since_buy * (1 - self.trailing_stop_distance)
                ):
                    print("[INFO] Трейлинг-стоп активирован.")
                    self.last_action = "SELL"
                    self.last_trade_time = time.time()
                    return "SELL"

                # ⛔ Стоп-лосс
                if profit_ratio <= -self.max_loss:
                    print("[WARNING] Стоп-лосс активирован.")
                    self.last_action = "SELL"
                    self.last_trade_time = time.time()
                    return "SELL"

                # ✅ Фиксация прибыли
                if profit_ratio >= self.min_profit_margin:
                    print("[INFO] Достаточная прибыль — продаём.")
                    self.last_action = "SELL"
                    self.last_trade_time = time.time()
                    return "SELL"

        # 💤 Проверка длительного простоя
        inactivity_seconds = time.time() - self.last_trade_time
        if inactivity_seconds > 60 * 60:  # 1 час бездействия
            print(f"[INFO] Бот бездействует {int(inactivity_seconds/60)} мин — принудительная проверка.")
            if self.last_action == "BUY":
                current_price = self.bybit.get_price(self.symbol)
                last_buy_price = self._get_last_buy_price()
                if current_price and last_buy_price:
                    profit_ratio = current_price / last_buy_price - 1
                    if profit_ratio > 0:
                        print("[INFO] Продаём из-за простоя с прибылью.")
                        self.last_action = "SELL"
                        self.last_trade_time = time.time()
                        return "SELL"
                    elif profit_ratio < -self.max_loss / 2:
                        print("[WARNING] Продаём из-за простоя и просадки.")
                        self.last_action = "SELL"
                        self.last_trade_time = time.time()
                        return "SELL"

        return None