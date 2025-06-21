from app.notifier import send_telegram_message
from app.utils.log_helper import log_maker
from pybit.unified_trading import HTTP
import requests
from app.config import BYBIT_API_KEY, BYBIT_API_SECRET, IS_TESTNET


class BybitService:
    def __init__(self):
        self.client = HTTP(
            testnet=IS_TESTNET,
            api_key=BYBIT_API_KEY,
            api_secret=BYBIT_API_SECRET,
            recv_window=15000,
        )

    def get_price(self, symbol: str) -> float | None:
        try:
            data = self.client.get_tickers(category="spot", symbol=symbol)
            return float(data["result"]["list"][0]["lastPrice"])
        except Exception as e:
            log_maker(f"💥 [ERROR] Ошибка получения цены: {e}")
            return None

    def market_order(self, symbol: str, side: str, qty: float) -> dict:
        try:
            response = self.client.place_order(
                category="spot",
                symbol=symbol,
                side=side,
                order_type="MARKET",
                qty=str(qty),
                accountType="UNIFIED",
            )
            return response
        except Exception as e:
            log_maker(f"🚫 [ERROR] Ошибка размещения ордера: {e}")
            return {}

    def get_balance(self, coin: str) -> float:
        try:
            data = self.client.get_wallet_balance(accountType="UNIFIED", coin=coin)
            coin_info = data["result"]["list"][0]["coin"]
            for item in coin_info:
                if item["coin"] == coin:
                    return float(
                        item.get("availableToTrade")
                        or item.get("availableBalance")
                        or item.get("walletBalance")
                        or 0.0
                    )
        except Exception as e:
            log_maker(f"💰❌ [ERROR] Ошибка получения баланса: {e}")
        return 0.0

    def get_filled_orders(self, symbol: str, limit: int = 5) -> list[dict]:
        try:
            orders = self.client.get_order_history(
                category="spot", symbol=symbol, limit=limit
            )["result"]["list"]
            return [order for order in orders if order["orderStatus"] == "Filled"]
        except Exception as e:
            log_maker(f"📜❌ [ERROR] Не удалось получить историю ордеров: {e}")
            return []

    def get_last_filled_price(self, symbol: str) -> float | None:
        orders = self.get_filled_orders(symbol)
        if not orders:
            return None
        return float(orders[0]["avgPrice"])

    def get_qty_precision(self, symbol: str) -> int:
        try:
            url = "https://api.bybit.com/v5/market/instruments-info"
            params = {"category": "spot", "symbol": symbol}
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            base_precision = data["result"]["list"][0]["lotSizeFilter"]["basePrecision"]
            decimal_places = len(base_precision.split(".")[-1].rstrip("0"))
            return decimal_places
        except Exception as e:
            log_maker(f"📏⚠️ [ERROR] Ошибка получения точности количества: {e}")
            return 4

    def get_price_precision(self, symbol: str) -> int:
        """
        Получает точность отображения цены (pricePrecision) с биржи.
        """
        try:
            url = "https://api.bybit.com/v5/market/instruments-info"
            params = {"category": "spot", "symbol": symbol}
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            price_filter = data["result"]["list"][0]["priceFilter"]
            tick_size = price_filter["tickSize"]
            decimal_places = len(tick_size.split(".")[-1].rstrip("0"))
            return decimal_places
        except Exception as e:
            log_maker(f"🎯⚠️ [ERROR] Ошибка получения точности цены: {e}")
            return 4

    def get_order_by_id(self, symbol: str, order_id: str) -> dict | None:
        try:
            orders = self.client.get_order_history(category="spot", symbol=symbol)[
                "result"
            ]["list"]
            for order in orders:
                if order["orderId"] == order_id:
                    return order
        except Exception as e:
            log_maker(f"🆔❌ [ERROR] Не удалось получить ордер по ID: {e}")
        return None
