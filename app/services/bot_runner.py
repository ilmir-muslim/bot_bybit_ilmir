from email import message
from app.notifier import send_telegram_message
from app.services.bybit_service import BybitService
from app.trader import place_market_order, get_price_history, round_qty
from app.strategies.ma_crossover import MovingAverageStrategy
import time
import traceback

from app.utils.log_helper import log_maker


class TradingBot:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bybit = BybitService()
        self.strategy = MovingAverageStrategy(symbol)

    def run_once(self):
        try:
            candles = get_price_history(self.symbol)
            action = self.strategy.should_trade(candles)

            if action == "BUY":
                usdt_balance = self.bybit.get_balance("USDT")
                price = self.bybit.get_price(self.symbol)

                log_maker(f"💵 [DEBUG] Баланс USDT: {usdt_balance:.8f}")

                if price is None or usdt_balance < 1:
                    log_maker(
                        "⏩ [BOT] Пропуск BUY: нет цены или недостаточно средств (USDT < 1)"
                    )

                    return

                raw_qty = usdt_balance
                qty_precision = self.bybit.get_qty_precision(self.symbol)
                qty = round_qty(raw_qty, qty_precision)

                log_maker(
                    f"🟢 [BOT] Покупаем {self.symbol} на {usdt_balance:.8f} USDT (вся доступная сумма)"
                )
                place_market_order(self.symbol, "Buy", qty)

                # Получаем и выводим инфу о последней покупке
                filled_orders = self.bybit.get_filled_orders(self.symbol)
                if filled_orders:
                    last_order = filled_orders[0]
                    qty_filled = float(last_order.get("cumExecQty", 0))
                    avg_price = float(last_order.get("avgPrice", 0))
                    message = (
                        f"✅ [INFO] Куплено: {qty_filled} {self.symbol.replace('USDT', '')} "
                        f"по цене {avg_price:.5f} USDT"
                    )
                    log_maker(message)
                else:
                    log_maker(
                        "⚠️ [WARNING] Не удалось получить информацию о фактической покупке"
                    )

            elif action == "SELL":
                coin = self.symbol.replace("USDT", "")
                balance = self.bybit.get_balance(coin)
                if balance == 0:
                    log_maker("🤷 [BOT] Нечего продавать.")
                    return

                qty_precision = self.bybit.get_qty_precision(self.symbol)
                qty = round_qty(balance, qty_precision)

                log_maker(f"🔻 [BOT] Продаём {qty} {coin}")
                place_market_order(self.symbol, "Sell", qty)

                # Получаем и выводим инфу о последней продаже
                filled_orders = self.bybit.get_filled_orders(self.symbol)
                if filled_orders:
                    last_order = filled_orders[0]
                    qty_filled = float(last_order.get("cumExecQty", 0))
                    avg_price = float(last_order.get("avgPrice", 0))
                    message = f"💰 [INFO] Продано: {qty_filled} {coin} по цене {avg_price:.5f} USDT"
                    log_maker(message)
                else:
                    log_maker(
                        "⚠️ [WARNING] Не удалось получить информацию о фактической продаже"
                    )

            else:
                log_maker("⏸️ [BOT] Ничего не делаем")

        except Exception as e:
            log_maker(f"💥 [ERROR] Сбой в run_once: {e}")
            traceback.print_exc()

    def run_loop(self, interval_seconds: int = 60):
        while True:
            self.run_once()
            time.sleep(interval_seconds)
