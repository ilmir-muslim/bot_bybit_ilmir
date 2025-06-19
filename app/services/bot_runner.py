from app.services.bybit_service import BybitService
from app.trader import place_market_order, get_price_history, round_qty
from app.strategies.ma_crossover import MovingAverageStrategy
import time
import traceback


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

                print(f"[DEBUG] USDT баланс: {usdt_balance}")

                if price is None or usdt_balance < 1:
                    print("[BOT] Пропускаем BUY: нет цены или недостаточно USDT (<1)")
                    return

                raw_qty = usdt_balance / price
                qty_precision = self.bybit.get_qty_precision(self.symbol)
                qty = round_qty(raw_qty, qty_precision)

                print(f"[BOT] BUY на {qty} {self.symbol}")
                place_market_order(self.symbol, "Buy", qty)

            elif action == "SELL":
                coin = self.symbol.replace("USDT", "")
                balance = self.bybit.get_balance(coin)
                if balance == 0:
                    print("[BOT] Нечего продавать.")
                    return

                qty_precision = self.bybit.get_qty_precision(self.symbol)
                qty = round_qty(balance, qty_precision)

                print(f"[BOT] SELL на {qty} {self.symbol}")
                place_market_order(self.symbol, "Sell", qty)

            else:
                print("[BOT] Ничего не делаем")

        except Exception as e:
            print(f"[ERROR] Сбой в run_once: {e}")
            traceback.print_exc()

    def run_loop(self, interval_seconds: int = 60):
        while True:
            self.run_once()
            time.sleep(interval_seconds)
