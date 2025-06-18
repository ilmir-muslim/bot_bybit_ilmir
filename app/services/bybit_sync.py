from app.database.engine import SessionLocal
from app.database.models import TradeLog
from app.trader import translate_status
from app.config import BYBIT_API_KEY, BYBIT_API_SECRET, IS_TESTNET
from pybit.unified_trading import HTTP
from datetime import datetime


client = HTTP(testnet=IS_TESTNET, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)


def get_order_history(symbol: str, limit: int = 50):
    response = client.get_order_history(category="spot", symbol=symbol, limit=limit)
    return response["result"]["list"]


def sync_orders_to_db(symbol: str):
    db = SessionLocal()
    try:
        orders = get_order_history(symbol)
        for order in orders:
            if order["orderStatus"] != "Filled":
                continue

            order_id = order["orderId"]
            exists = db.query(TradeLog).filter_by(error=None).filter_by(
                symbol=order["symbol"],
                side=order["side"].upper(),
                qty=float(order["qty"]),
                avg_price=float(order["avgPrice"]),
            ).first()

            if exists:
                continue

            db.add(
                TradeLog(
                    symbol=order["symbol"],
                    side=order["side"].upper(),
                    qty=float(order["qty"]),
                    avg_price=float(order["avgPrice"]),
                    status=translate_status(order["orderStatus"]),
                    timestamp=datetime.fromtimestamp(int(order["createdTime"]) / 1000),
                    error=None,
                )
            )
        db.commit()
    finally:
        db.close()


def get_last_filled_order(symbol: str) -> dict | None:
    orders = get_order_history(symbol)
    for order in sorted(orders, key=lambda x: int(x["createdTime"]), reverse=True):
        if order["orderStatus"] == "Filled":
            return {
                "side": order["side"].upper(),  # "BUY" or "SELL"
                "qty": float(order["qty"]),
                "avg_price": float(order["avgPrice"]),
                "timestamp": int(order["createdTime"]),
            }
    return None


def init_strategy_state(strategy, symbol: str):
    last_order = get_last_filled_order(symbol)
    if last_order:
        strategy.last_action = last_order["side"]
        print(f"[INIT] Установлено last_action = {strategy.last_action}")
    else:
        print("[INIT] Нет истории для установки last_action")
