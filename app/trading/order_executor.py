from decimal import ROUND_DOWN, Decimal
import time
from app.notifier import send_telegram_message
from app.utils.log_helper import log_maker
from pybit.unified_trading import HTTP
from app.services.bybit_service import BybitService
from app.config import BYBIT_API_KEY, BYBIT_API_SECRET, IS_TESTNET

client = HTTP(
    testnet=IS_TESTNET,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET,
    recv_window=15000,
)
bybit = BybitService()

class OrderExecutor:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bybit = BybitService()
        self.last_buy_price = 0.0
        self.last_buy_quantity = 0.0
        
    def execute_force_close(self) -> bool:
        coin = self.symbol.replace("USDT", "")
        balance = self.bybit.get_balance(coin)
        if not balance or balance <= 0:
            log_maker(f"⏩ Нет позиции для принудительного закрытия {self.symbol}")
            return False
            
        log_maker(f"🆘 [FORCE CLOSE] Продаем {balance} {coin}", buy_sell=True)
        return self.execute_sell(None)
        
    def execute_buy(self, trading_system=None):
        usdt_balance = self.bybit.get_balance("USDT")
        if not usdt_balance:
            log_maker("❌ Не удалось получить баланс USDT")
            return False
            
        usdt_balance = max(0, usdt_balance - 0.1)
        usdt_balance = round(usdt_balance, 2)

        if usdt_balance < 5:
            log_maker("⏩ Пропуск BUY: недостаточно средств")
            return False

        price = self.bybit.get_reliable_price(self.symbol)
        if not price:
            log_maker("⏩ Пропуск BUY: не удалось получить цену")
            return False

        log_maker(f"🟢 [BOT] Покупаем {self.symbol} на {usdt_balance:.2f} USDT", buy_sell=True)
        order_response = self.bybit.market_order(
            self.symbol, "Buy", usdt_balance, is_quote=True
        )

        if order_response and order_response.get("retCode") == 0:
            log_maker("✅ Ордер на покупку успешно размещен")
            if trading_system:
                trading_system.position_open_time = time.time()
                trading_system.position_coin = self.symbol.replace('USDT', '')
            
            filled_order = self.bybit.get_last_filled_order(self.symbol)
            if filled_order:
                qty_coin = float(filled_order.get("cumExecQty", 0))
                avg_price = float(filled_order.get("avg_price", 0))
                self.last_buy_price = avg_price
                self.last_buy_quantity = qty_coin
                
                if trading_system:
                    trading_system.position_open_time = time.time()
                
                log_maker(
                    f"✅ Куплено: {qty_coin} {self.symbol.replace('USDT', '')} по {avg_price:.5f} USDT",
                    buy_sell=True,
                )
                return True
        return False

    def execute_sell(self, strategy=None):
        coin = self.symbol.replace("USDT", "")
        balance = self.bybit.get_balance(coin)
        if not balance:
            log_maker(f"🤷 Нет позиции по {coin}")
            return False

        min_qty = self.bybit.get_min_order_qty(self.symbol)
        if balance < min_qty:
            log_maker(f"⏩ Пропуск SELL: баланс {balance} < минимального {min_qty}")
            return False

        log_maker(f"🔻 [BOT] Продаём {balance} {coin}", buy_sell=True)
        order_response = self.bybit.market_order(
            self.symbol, "Sell", balance, is_quote=False
        )

        if order_response and order_response.get("retCode") == 0:
            log_maker("✅ Ордер на продажу успешно размещен", buy_sell=True)
            filled_order = self.bybit.get_last_filled_order(self.symbol)
            if filled_order:
                qty_coin = float(filled_order.get("cumExecQty", 0))
                avg_price = float(filled_order.get("avg_price", 0))
                exec_fee = float(filled_order.get("cumExecFee", 0))
                
                profit = 0.0
                if self.last_buy_price > 0:
                    buy_value = self.last_buy_price * qty_coin
                    sell_value = avg_price * qty_coin
                    profit = sell_value - buy_value - exec_fee
                    
                    if hasattr(strategy, "rotator") and strategy.rotator:
                        strategy.rotator.record_trade_result(profit)
                    
                    profit_pct = (profit / buy_value) * 100
                    profit_msg = (f"🟢 Чистая прибыль: +{profit:.4f} USDT (+{profit_pct:.2f}%)" 
                                if profit >= 0 else 
                                f"🔴 Чистый убыток: {profit:.4f} USDT ({profit_pct:.2f}%)")
                    
                    log_maker(
                        f"💰 Продано: {qty_coin} {coin} по {avg_price:.5f} USDT\n"
                        f"  • {profit_msg}\n"
                        f"  • Комиссии: {exec_fee:.4f} USDT",
                        buy_sell=True,
                    )
                return True
        return False
    
    def clean_residuals(self, threshold=0.0001):
        coin = self.symbol.replace('USDT', '')
        balance = self.bybit.get_balance(coin)
        if not balance:
            return
                
        min_qty = self.bybit.get_min_order_qty(self.symbol)
        
        # Если баланс меньше минимального лота ИЛИ меньше порогового значения
        if balance < min_qty or balance < threshold:
            precision = self.bybit.get_qty_precision(self.symbol)
            # Округляем до допустимой точности
            qty = round(balance, precision)
            
            if qty <= 0:
                log_maker(f"⏩ Остаток {balance} {coin} слишком мал для продажи")
                return
                
            log_maker(f"🧹 Очистка остатка {qty} {coin}", buy_sell=True)
            order_response = self.bybit.market_order(
                self.symbol, "Sell", qty, is_quote=False
            )

            if order_response and order_response.get("retCode") == 0:
                log_maker(f"✅ Остаток {qty} {coin} успешно продан", buy_sell=True)
            else:
                error = order_response.get("retMsg") if order_response else "Unknown error"
                log_maker(f"❌ Не удалось продать остаток: {error}", buy_sell=True)