from app.services.bybit_service import BybitService
from app.trader import place_market_order, get_price_history
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
            prices = [item["close"] for item in get_price_history(self.symbol, limit=30)]
            action = self.strategy.should_trade(prices)

            if action == "BUY":
                usdt_balance = self.bybit.get_balance("USDT")
                price = self.bybit.get_price(self.symbol)
                if price is None or usdt_balance == 0:
                    print("[BOT] Невозможно купить: нет цены или нулевой баланс")
                    return

                qty = round(usdt_balance / price, 4)
                print(f"[BOT] BUY на {qty} {self.symbol}")
                place_market_order(self.symbol, "Buy", qty)

            elif action == "SELL":
                coin = self.symbol.replace("USDT", "")
                balance = self.bybit.get_balance(coin)
                if balance == 0:
                    print("[BOT] Нечего продавать.")
                    return

                qty = round(balance, 4)
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
