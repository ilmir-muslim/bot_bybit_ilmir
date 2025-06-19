import time
import numpy as np
from typing import Optional
from app.services.bybit_service import BybitService
from app.database.engine import SessionLocal
from app.database.models import TradeLog


class MovingAverageStrategy:
    def __init__(self, symbol: str, short_window: int = 7, long_window: int = 25):
        self.symbol = symbol
        self.short_window = short_window
        self.long_window = long_window
        self.bybit = BybitService()
        self.last_action = self._load_last_action()
        self.min_profit_margin = 0.002
        self.max_loss = 0.03
        self.trailing_stop_activation = 2.0  # × ATR
        self.trailing_stop_distance = 1.5    # × ATR
        self.max_price_since_buy = None
        self.last_trade_time = time.time()
        self.prev_short_ma = None
        self.ma_crossed_down = False
        self.flat_volatility_threshold = 0.0005
        self.flat_max_duration = 300

    def _load_last_action(self) -> str | None:
        print("[DEBUG] Нет последней покупки в логах — ищем через API...")
        try:
            filled_orders = self.bybit.get_filled_orders(self.symbol)
            if filled_orders:
                last_order = filled_orders[0]
                side = last_order["side"].upper()
                print(f"[DEBUG] Последнее действие через API: {side}")
                return side
        except Exception as e:
            print(f"[ERROR] Ошибка при получении последней сделки с API: {e}")
        return None

    def _get_last_buy_price(self, last_action: Optional[str] = None) -> float | None:
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

            if last_action is None:
                last_action = self._load_last_action()

            if last_action == "BUY":
                filled_orders = self.bybit.get_filled_orders(self.symbol)
                for order in filled_orders:
                    if order["side"].upper() == "BUY" and order["orderStatus"] == "Filled":
                        return float(order["avgPrice"])
            return None
        finally:
            db.close()

    def _calculate_atr(self, prices: list[float]) -> float:
        highs = prices[-self.long_window:]
        lows = prices[-self.long_window:]
        closes = prices[-self.long_window:]

        trs = []
        for i in range(1, len(closes)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        return np.mean(trs)

    def should_trade(self, prices: list[float]) -> Optional[str]:
        if len(prices) < self.long_window:
            return None

        short_ma = np.mean(prices[-self.short_window:])
        long_ma = np.mean(prices[-self.long_window:])
        volatility = np.std(prices[-self.long_window:])
        atr = self._calculate_atr(prices)

        self.max_loss = min(0.05, max(0.01, volatility * 3))
        self.min_profit_margin = max(0.001, volatility * 2)

        current_price = self.bybit.get_price(self.symbol)
        if current_price is None:
            print("[ERROR] Нет текущей цены, пропускаем итерацию.")
            return None
        
        print(f"[DEBUG] short MA: {short_ma:.6f}, long MA: {long_ma:.6f}")
        print(f'[DEBUG] текущая цена: {current_price}')
        print(f"[DEBUG] Волатильность: {volatility:.6f}, ATR: {atr:.6f}, min_profit_margin: {self.min_profit_margin:.4f}, max_loss: {self.max_loss:.4f}")


        # Флэт
        time_since_buy = time.time() - self.last_trade_time
        if (
            self.last_action == "BUY"
            and volatility < self.flat_volatility_threshold
            and time_since_buy > self.flat_max_duration
        ):
            last_buy_price = self._get_last_buy_price(self.last_action)
            if last_buy_price:
                profit_ratio = current_price / last_buy_price
                if profit_ratio >= 1:
                    print(f"[INFO] Закрываем позицию из-за флэта: прибыль {profit_ratio - 1:.4%}")
                    self.last_action = "SELL"
                    self.ma_crossed_down = False
                    return "SELL"

        # Трейлинг-стоп логика
        if self.last_action == "BUY":
            if self.max_price_since_buy is None:
                self.max_price_since_buy = current_price

            if current_price > self.max_price_since_buy:
                self.max_price_since_buy = current_price

            last_buy_price = self._get_last_buy_price(self.last_action)
            if last_buy_price:
                if current_price >= last_buy_price + atr * self.trailing_stop_activation:
                    trailing_stop_price = self.max_price_since_buy - atr * self.trailing_stop_distance
                    if current_price <= trailing_stop_price:
                        print(f"[TRAILING STOP] Цена упала до {current_price:.6f}, активируем трейлинг-стоп от пика {self.max_price_since_buy:.6f}")
                        self.last_action = "SELL"
                        self.ma_crossed_down = False
                        self.max_price_since_buy = None
                        return "SELL"

        # MA кросс
        if short_ma > long_ma and self.last_action != "BUY":
            self.last_action = "BUY"
            self.last_trade_time = time.time()
            self.max_price_since_buy = None  # сброс при новом входе
            return "BUY"

        elif self.ma_crossed_down and self.last_action == "BUY":
            coin = self.symbol.replace("USDT", "")
            balance = self.bybit.get_balance(coin)
            print(f"[DEBUG] Баланс {coin}: {balance}")
            if balance > 0:
                last_buy_price = self._get_last_buy_price(self.last_action)
                if last_buy_price:
                    profit_ratio = current_price / last_buy_price

                    if profit_ratio >= (1 + self.min_profit_margin):
                        print(f"[INFO] Продаем: цена выросла с {last_buy_price:.4f} до {current_price:.4f}")
                        self.last_action = "SELL"
                        self.ma_crossed_down = False
                        self.max_price_since_buy = None
                        return "SELL"

                    elif profit_ratio <= (1 - self.max_loss):
                        print(f"[WARNING] Stop-loss: цена упала более чем на {self.max_loss*100:.1f}%, продаем")
                        self.last_action = "SELL"
                        self.ma_crossed_down = False
                        self.max_price_since_buy = None
                        return "SELL"

                    else:
                        print(f"[DEBUG] Не продаем: цена {current_price:.4f}, куплено по {last_buy_price:.4f}")
                else:
                    print("[DEBUG] Нет последней покупки в логах")

        return None
