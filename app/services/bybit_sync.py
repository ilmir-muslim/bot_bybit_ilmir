
from app.config import BYBIT_API_KEY, BYBIT_API_SECRET, IS_TESTNET
from pybit.unified_trading import HTTP
from app.utils.log_helper import log_maker

client = HTTP(
    testnet=IS_TESTNET,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET,
    recv_window=15000,
)

def get_order_history(symbol: str, limit: int = 50):
    try:
        response = client.get_order_history(category="spot", symbol=symbol, limit=limit)
        return response["result"]["list"]
    except Exception as e:
        log_maker(f"❌ Ошибка получения истории ордеров: {e}")
        return []
