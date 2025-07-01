from decimal import ROUND_DOWN, Decimal
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



def validate_qty_precision(symbol: str, qty: float):
    precision = bybit.get_qty_precision(symbol)
    parts = str(qty).split(".")
    decimal_digits = len(parts[1]) if len(parts) == 2 else 0

    if decimal_digits > precision:
        send_telegram_message(
            f"🚨 [CRITICAL] qty = {qty} содержит {decimal_digits} знаков после запятой, "
            f"что превышает допустимую точность ({precision}) для {symbol}. "
            f"Убедись, что используется `round_qty(...)`!"
        )
        raise ValueError(
            f"[CRITICAL] qty={qty} содержит {decimal_digits} знаков после запятой, "
            f"что превышает допустимую точность ({precision}) для {symbol}. "
            f"Проверь, что используется round_qty(...)!"
        )



def translate_status(status):
    return {
        "Filled": "исполнено",
        "Cancelled": "отменено",
        "Rejected": "отклонено",
        "New": "новый",
        "PartiallyFilled": "частично исполнено",
    }.get(status, status)




def get_price_history(symbol: str, interval: str = "3", limit: int = 100):
    """ТОЛЬКО API-данные"""
    try:
        return bybit.get_candles(
            symbol=symbol,
            interval=interval,  # Используем параметр
            limit=limit
        )
    except Exception as e:
        log_maker(f"📉 [ERROR] Ошибка получения истории цен: {e}")
        return []

