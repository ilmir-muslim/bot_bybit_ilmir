from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from pybit.unified_trading import HTTP
from app.database.engine import SessionLocal
from app.database.models import TradeLog
from app.services.bybit_service import BybitService
from app.utils.place_order import safe_place_order
from app.config import BYBIT_API_KEY, BYBIT_API_SECRET, IS_TESTNET

client = HTTP(testnet=IS_TESTNET, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
bybit = BybitService()

def round_qty(qty: float, precision: int) -> float:
    quantize_str = "1" if precision == 0 else "1." + "0" * precision
    return float(Decimal(str(qty)).quantize(Decimal(quantize_str), rounding=ROUND_DOWN))


def place_market_order(symbol: str, side: str, qty: float):
    db = SessionLocal()
    try:
        qty_precision = bybit.get_qty_precision(symbol)
        rounded_qty = round_qty(qty, qty_precision)

        response = safe_place_order(bybit.client, symbol, side, str(rounded_qty))
        if not response:
            raise Exception("Ордер не исполнен")

        result = response["result"]
        status = result.get("order_status", "UNKNOWN")
        avg_price = float(result.get("avg_price", 0))

        if avg_price == 0:
            print("[WARN] avg_price == 0, пробуем повторно получить ордер...")
            order_id = result.get("orderId")
            if not order_id:
                raise Exception("Нет orderId для повторной проверки avg_price")

            order_info = bybit.client.get_order(category="spot", orderId=order_id)
            order_data = order_info["result"]["list"][0]
            avg_price = float(order_data.get("avgPrice", 0))
            status = order_data.get("orderStatus", status)

            if avg_price == 0:
                raise Exception("avg_price всё ещё равен 0 после повторной проверки")

        log_trade(
            db=db,
            symbol=symbol,
            side=side,
            qty=rounded_qty,
            price=avg_price,
            status=translate_status(status),
            error=None,
        )

        db.commit()
        return result

    except Exception as e:
        db.add(
            TradeLog(
                symbol=symbol,
                side=side,
                qty=qty,
                avg_price=0,
                status="ошибка",
                error=str(e),
            )
        )
        db.commit()
        print(f"[ОШИБКА] Ордер не прошёл: {e}")
        return None

    finally:
        db.close()

def translate_status(status):
    return {
        "Filled": "исполнено",
        "Cancelled": "отменено",
        "Rejected": "отклонено",
        "New": "новый",
        "PartiallyFilled": "частично исполнено",
    }.get(status, status)

def log_trade(db, symbol, side, qty, price, status, error=None):
    trade = TradeLog(
        symbol=symbol,
        side=side,
        qty=qty,
        avg_price=price,
        status=status,
        error=error,
    )

    if side == "SELL":
        last_buy = (
            db.query(TradeLog)
            .filter(TradeLog.symbol == symbol, TradeLog.side == "BUY")
            .order_by(TradeLog.timestamp.desc())
            .first()
        )

        if last_buy:
            entry_price = last_buy.avg_price
            exit_price = price
            commission = 0.001 * (entry_price + exit_price) * qty
            profit = (exit_price - entry_price) * qty - commission
            profit_pct = ((exit_price - entry_price) / entry_price) * 100

            trade.entry_price = entry_price
            trade.exit_price = exit_price
            trade.commission = round(commission, 6)
            trade.profit = round(profit, 6)
            trade.profit_pct = round(profit_pct, 4)
            trade.is_profitable = profit > 0

    db.add(trade)

def get_price_history(symbol: str, limit: int = 50):
    try:
        response = client.get_kline(
            category="spot",
            symbol=symbol,
            interval="1",
            limit=limit,
        )
        return [
            {
                "time": datetime.fromtimestamp(int(item[0]) / 1000),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
            for item in response["result"]["list"]
        ]
    except Exception as e:
        print(f"[ERROR] Ошибка получения истории цен: {e}")
        return []

def get_last_buy_price(symbol: str) -> float | None:
    with SessionLocal() as db:
        trade = (
            db.query(TradeLog)
            .filter(TradeLog.symbol == symbol, TradeLog.side == "BUY")
            .order_by(TradeLog.timestamp.desc())
            .first()
        )
        return trade.avg_price if trade else None
