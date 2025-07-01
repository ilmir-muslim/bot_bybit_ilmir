import os
import json
import time
import traceback
import requests
import numpy as np
import ccxt  # Добавляем импорт CCXT

from pybit.unified_trading import HTTP
from typing import List, Dict, Optional, Literal
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.utils.log_helper import log_maker
from app.config import IS_TESTNET


class BybitService:
    def __init__(self, api_key=None, api_secret=None):
        self.session = requests.Session()
        self.session.timeout = 60
        self.min_order_cache = {}
        self.api_key = api_key or os.getenv("BYBIT_API_KEY")
        self.api_secret = api_secret or os.getenv("BYBIT_API_SECRET")
        self.recv_window = "5000"

        self.ccxt_exchange = ccxt.bybit(
            {
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )

        self.client = HTTP(
            testnet=IS_TESTNET,
            api_key=self.api_key,
            api_secret=self.api_secret,
            recv_window=15000,
            timeout=10,
        )

        retry_strategy = Retry(
            total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def get_candles(self, symbol: str, interval: str, limit: int = 100) -> List[Dict]:
        # Для больших лимитов используем CCXT
        if limit > 200:
            return self._get_candles_via_ccxt(symbol, interval, min(limit, 1000))

        cache_key = f"{symbol}_{interval}_{limit}"
        cache_duration = 60 if interval == "15" else 300

        if hasattr(self, "candle_cache") and cache_key in self.candle_cache:
            cached = self.candle_cache[cache_key]
            if time.time() - cached["timestamp"] < cache_duration:
                return cached["data"]

        limit = min(limit, 100)

        url = "https://api.bybit.com/v5/market/kline"
        params = {
            "category": "spot",
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "simple": "true",
        }

        for attempt in range(5):
            try:
                start_time = time.time()
                response = self.session.get(url, params=params, timeout=(15, 45))

                duration = time.time() - start_time
                if duration > 3:
                    log_maker(
                        f"⏱️ Запрос {symbol} занял {duration:.2f} сек (попытка {attempt+1})"
                    )

                if response.status_code != 200:
                    log_maker(f"📊❌ HTTP {response.status_code} для {symbol}")
                    # Повторяем попытку для временных ошибок
                    if response.status_code in [429, 500, 502, 503, 504]:
                        time.sleep(2**attempt)  # Exponential backoff
                        continue
                    return []  # Для других ошибок возвращаем пустой список

                data = response.json()

                if data.get("retCode") != 0:
                    error_msg = data.get("retMsg", "Unknown error")
                    log_maker(f"📊❌ API: {error_msg}")

                    # Если это временная ошибка, пробуем снова
                    if (
                        "too many requests" in error_msg.lower()
                        or "service unavailable" in error_msg.lower()
                    ):
                        time.sleep(2**attempt)  # Exponential backoff
                        continue
                    return []  # Для других ошибок возвращаем пустой список

                candles = []
                for item in data["result"]["list"]:
                    try:
                        candles.append(
                            {
                                "timestamp": int(item[0]),
                                "open": float(item[1]),
                                "high": float(item[2]),
                                "low": float(item[3]),
                                "close": float(item[4]),
                                "volume": float(item[5]),
                            }
                        )
                    except (ValueError, IndexError) as e:
                        log_maker(f"📊⚠️ Ошибка парсинга свечи: {e}")

                candles = candles[::-1]
                if not hasattr(self, "candle_cache"):
                    self.candle_cache = {}
                self.candle_cache[cache_key] = {
                    "data": candles,
                    "timestamp": time.time(),
                }

                return candles

            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ) as e:
                wait_time = min(2**attempt, 10)
                log_maker(
                    f"📊⚠️ Сетевая ошибка ({attempt+1}): {type(e).__name__} - жду {wait_time} сек"
                )
                time.sleep(wait_time)
            except Exception as e:
                error_type = type(e).__name__
                log_maker(f"📊🔥 Критическая ошибка ({error_type}): {str(e)}")
                if attempt == 4:
                    break

        if hasattr(self, "candle_cache") and cache_key in self.candle_cache:
            log_maker(f"📊⚠️ Использую кэш для {symbol}")
            return self.candle_cache[cache_key]["data"]

        log_maker("📊❌ Не удалось получить свечи, возвращаю пустой список")
        return []

    def _get_candles_via_ccxt(
        self, symbol: str, interval: str, limit: int
    ) -> List[Dict]:
        """Получение свечей через CCXT (до 1000 свечей)"""
        try:
            # Преобразование интервалов
            interval_map = {
                "1": "1m",
                "3": "3m",
                "5": "5m",
                "15": "15m",
                "30": "30m",
                "60": "1h",
                "120": "2h",
                "240": "4h",
                "360": "6h",
                "720": "12h",
                "D": "1d",
                "W": "1w",
                "M": "1M",
            }
            ccxt_interval = interval_map.get(interval, interval)

            log_maker(f"📊 Запрос CCXT: {symbol} {ccxt_interval} x{limit}")
            ohlcv = self.ccxt_exchange.fetch_ohlcv(symbol, ccxt_interval, limit=limit)

            candles = []
            for candle in ohlcv:
                candles.append(
                    {
                        "timestamp": candle[0],
                        "open": candle[1],
                        "high": candle[2],
                        "low": candle[3],
                        "close": candle[4],
                        "volume": candle[5],
                    }
                )

            log_maker(f"📊 Получено {len(candles)} свечей через CCXT")
            return candles
        except Exception as e:
            log_maker(f"🔥 CCXT ошибка получения свечей: {str(e)}")
            return []

    # Остальные методы остаются без изменений
    def get_price(self, symbol: str) -> float | None:
        try:
            url = "https://api.bybit.com/v5/market/tickers"
            params = {"category": "spot", "symbol": symbol}
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            return float(data["result"]["list"][0]["lastPrice"])
        except Exception as e:
            log_maker(f"💥 [ERROR] Ошибка получения цены: {e}")
            return None

    def market_order(
        self, symbol: str, side: str, quantity: float, is_quote: bool = False
    ) -> dict:
        try:
            params = {
                "category": "spot",
                "symbol": symbol,
                "side": side.capitalize(),
                "orderType": "Market",
            }

            if side.lower() == "buy" and is_quote:
                params["marketUnit"] = "quoteCoin"
                quantity = round(quantity, 2)
                params["qty"] = str(quantity)
            else:
                params["qty"] = str(quantity)

            response = self.client.place_order(**params)
            return response
        except Exception as e:
            log_maker(f"🚫 [ERROR] Ошибка размещения ордера: {e}")
            return {}

    def get_balance(self, coin: str, retries: int = 3) -> float:
        for attempt in range(retries):
            try:
                data = self.client.get_wallet_balance(accountType="UNIFIED", coin=coin)
                coin_info = data["result"]["list"][0]["coin"]
                for item in coin_info:
                    if item["coin"] == coin:
                        # Проверяем и обрабатываем пустые значения
                        value = item.get("availableToTrade") or \
                                item.get("availableBalance") or \
                                item.get("walletBalance")
                        
                        # Обрабатываем случаи с пустой строкой
                        if value == '':
                            return 0.0
                        return float(value) if value else 0.0
                return 0.0
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(1.5 ** attempt)
                else:
                    log_maker(f"💰❌ [ERROR] Ошибка получения баланса: {e}")
        return 0.0

    def get_filled_orders(self, symbol: str, limit: int = 5) -> list[dict]:
        try:
            response = self.client.get_order_history(
                category="spot", symbol=symbol, limit=limit, orderStatus="Filled"
            )
            orders = response["result"]["list"]

            return sorted(orders, key=lambda x: int(x["createdTime"]), reverse=True)
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

            if "." in base_precision:
                decimal_part = base_precision.split(".")[1]
                decimal_places = len(decimal_part.rstrip("0"))
            else:
                decimal_places = 0

            return decimal_places
        except Exception as e:
            log_maker(f"📏⚠️ [ERROR] Ошибка получения точности количества: {e}")
            return 4

    def get_price_precision(self, symbol: str) -> int:
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

    def get_last_filled_order(self, symbol: str, limit=1) -> dict:
        try:
            response = self.client.get_order_history(
                category="spot", symbol=symbol, limit=limit, orderStatus="Filled"
            )
            with open("last_filled_orders_full.json", "w") as f:
                json.dump(response, f, indent=2)

            if response["retCode"] != 0:
                return None

            orders = response["result"]["list"]
            if not orders:
                return None

            return {
                "symbol": orders[0]["symbol"],
                "side": orders[0]["side"],
                "qty": orders[0]["qty"],
                "cumExecValue": orders[0]["cumExecValue"],
                "cumExecFee": orders[0]["cumExecFee"],
                "cumExecQty": orders[0]["cumExecQty"],
                "avg_price": orders[0]["avgPrice"],
                "timestamp": int(orders[0]["createdTime"]),
                "order_id": orders[0]["orderId"],
            }
        except Exception as e:
            log_maker(f"🔥 КРИТИЧЕСКАЯ ОШИБКА получения ордера: {e}")
            return None

    def get_min_order_qty(self, symbol: str) -> float:
        if symbol in self.min_order_cache:
            cached = self.min_order_cache[symbol]
            if time.time() - cached["timestamp"] < 3600:
                return cached["value"]

        try:
            url = "https://api.bybit.com/v5/market/instruments-info"
            params = {"category": "spot", "symbol": symbol}
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()

            # Проверка наличия данных
            if (
                not data.get("result")
                or not data["result"].get("list")
                or len(data["result"]["list"]) == 0
            ):
                return 0.001  # Значение по умолчанию

            min_order_qty = float(
                data["result"]["list"][0]["lotSizeFilter"]["minOrderQty"]
            )

            self.min_order_cache[symbol] = {
                "value": min_order_qty,
                "timestamp": time.time(),
            }
            return min_order_qty
        except Exception as e:
            log_maker(f"📏⚠️ [ERROR] Ошибка получения минимального количества: {e}")
            return 0.001  # Значение по умолчанию

    def validate_price(self, price: float, symbol: str) -> bool:
        if price is None or price < 0.1 or price > 100000:
            return False

        current_price = self.get_price(symbol)
        if current_price is None:
            return False

        price_diff = abs(price - current_price) / current_price
        return price_diff < 0.1

    def get_reliable_price(self, symbol: str) -> float:
        prices = []
        for _ in range(3):
            price = self.get_price(symbol)
            if price:
                prices.append(price)
            time.sleep(0.1)

        if not prices:
            log_maker("🚨 Не удалось получить надежную цену")
            return 0.0

        return float(np.median(prices))

    def get_best_bid_ask(
        self, symbol: str
    ) -> tuple[float | Literal[0], float | Literal[0]] | tuple[Literal[0], Literal[0]]:
        try:
            url = "https://api.bybit.com/v5/market/orderbook"
            params = {"category": "spot", "symbol": symbol, "limit": 1}
            response = requests.get(url, params=params, timeout=5)
            data = response.json()

            if data["retCode"] == 0:
                orderbook = data["result"]
                best_bid = float(orderbook["b"][0][0]) if orderbook.get("b") else 0
                best_ask = float(orderbook["a"][0][0]) if orderbook.get("a") else 0
                return best_bid, best_ask
        except Exception as e:
            log_maker(f"📊❌ Ошибка получения стакана: {e}")
        return 0, 0

    def get_open_positions(self) -> list:
        try:
            response = self.client.get_wallet_balance(accountType="UNIFIED")
            coins = response["result"]["list"][0]["coin"]
            return [
                {
                    'symbol': f"{item['coin']}USDT",
                    'coin': item['coin'],
                    'size': float(item['availableToWithdraw']) if item['availableToWithdraw'] != '' else 0.0,
                    'avg_price': 0.0
                }
                for item in coins
                if float(item['availableToWithdraw'] or 0) > 0 and item['coin'] != 'USDT'
            ]

        except Exception as e:
            log_maker(f"🔥 Ошибка получения позиций: {str(e)}")
            return []

    def get_last_filled_order_for_coin(self, coin: str) -> Optional[dict]:
        """Получает последний исполненный ордер для монеты через API"""
        symbol = f"{coin}USDT"
        try:
            response = self.client.get_order_history(
                category="spot", symbol=symbol, limit=1, orderStatus="Filled"
            )

            if response["retCode"] != 0:
                return None

            orders = response["result"]["list"]
            if not orders:
                return None

            order = orders[0]
            return {
                "symbol": order["symbol"],
                "side": order["side"],
                "qty": float(order["qty"]),
                "price": float(order["avgPrice"]),
                "timestamp": int(order["createdTime"]),
            }
        except Exception as e:
            log_maker(f"🔥 Ошибка получения ордера: {e}")
            return None
