from app.database.engine import SessionLocal
from app.database.models import TradeLog
from app.database.orm_query import orm_add_data_to_tables
from app.trader import translate_status
from app.config import BYBIT_API_KEY, BYBIT_API_SECRET, IS_TESTNET
from pybit.unified_trading import HTTP
from datetime import datetime
from app.utils.log_helper import log_maker

client = HTTP(
    testnet=IS_TESTNET,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET,
    recv_window=15000,
)

def get_order_history(symbol: str, limit: int = 50):
    response = client.get_order_history(category="spot", symbol=symbol, limit=limit)
    return response["result"]["list"]

def sync_orders_to_db(symbol: str):
    db = SessionLocal()
    try:
        orders = get_order_history(symbol)
        # Сортируем ордера по времени создания (от старых к новым)
        sorted_orders = sorted(orders, key=lambda x: int(x["createdTime"]))
        
        # Список открытых покупок (FIFO)
        open_buys = []
        
        for order in sorted_orders:
            if order["orderStatus"] != "Filled":
                continue
                
            order_id = order["orderId"]
            # Проверяем, есть ли уже такой ордер в базе
            if db.query(TradeLog).filter_by(order_id=order_id).first():
                continue
                
            trade_data = {
                "symbol": order["symbol"],
                "side": order["side"].upper(),
                "qty": float(order["qty"]),
                "avg_price": float(order["avgPrice"]),
                "status": translate_status(order["orderStatus"]),
                "timestamp": datetime.fromtimestamp(int(order["createdTime"]) / 1000),
                "commission": float(order.get("execFee", 0)),
                "order_id": order_id,
            }
            
            stats_data = {
                "symbol": trade_data["symbol"],
                "side": trade_data["side"],
                "qty": trade_data["qty"],
                "price": trade_data["avg_price"],
            }
            
            # Обработка BUY ордера
            if trade_data["side"] == "BUY":
                open_buys.append({
                    "order_id": order_id,
                    "qty": trade_data["qty"],
                    "price": trade_data["avg_price"],
                })
            
            # Обработка SELL ордера
            elif trade_data["side"] == "SELL":
                sell_qty = trade_data["qty"]
                total_profit = 0
                total_qty = 0
                
                # Алгоритм FIFO: итерируемся по открытым покупкам
                for buy in open_buys[:]:
                    if sell_qty <= 0:
                        break
                    
                    # Сколько из этой покупки можем продать
                    match_qty = min(buy["qty"], sell_qty)
                    # Прибыль с этой части
                    profit = (trade_data["avg_price"] - buy["price"]) * match_qty
                    total_profit += profit
                    total_qty += match_qty
                    
                    # Уменьшаем количество в открытой покупке и в ордере на продажу
                    buy["qty"] -= match_qty
                    sell_qty -= match_qty
                    
                    # Если покупка полностью закрыта, удаляем из списка
                    if buy["qty"] <= 0:
                        open_buys.remove(buy)
                
                # Рассчитываем процент прибыли
                if total_qty > 0:
                    profit_pct = total_profit / (total_qty * trade_data["avg_price"]) * 100
                    trade_data["profit"] = total_profit
                    trade_data["profit_pct"] = profit_pct
                    trade_data["is_profitable"] = total_profit > 0
                    stats_data["profit"] = total_profit
                    stats_data["profit_pct"] = profit_pct
            
            # Добавляем данные в базу
            orm_add_data_to_tables(
                session=db,
                data_trade_log=trade_data,
                data_user_trade_stats=stats_data
            )
        
        # Логируем оставшиеся открытые позиции
        if open_buys:
            log_maker(f"⚠️ Осталось открытых позиций: {len(open_buys)}")
            
    except Exception as e:
        db.rollback()
        log_maker(f"❌ Ошибка синхронизации: {e}")
    finally:
        db.close()

def get_last_filled_order(self, symbol: str) -> dict | None:
    """Возвращает последний заполненный ордер для символа"""
    try:
        response = self.client.get_order_history(
            category="spot",
            symbol=symbol,
            limit=50,
            orderStatus="Filled"
        )
        orders = response["result"]["list"]
        
        # Фильтруем только заполненные ордера
        filled_orders = [o for o in orders if o["orderStatus"] == "Filled"]
        
        if not filled_orders:
            return None
            
        # Сортируем по времени (последние сначала)
        sorted_orders = sorted(filled_orders, key=lambda x: int(x["createdTime"]), reverse=True)
        
        return {
            "side": sorted_orders[0]["side"].upper(),
            "qty": float(sorted_orders[0]["qty"]),
            "avg_price": float(sorted_orders[0]["avgPrice"]),
            "timestamp": int(sorted_orders[0]["createdTime"]),
        }
    except Exception as e:
        log_maker(f"❌ Ошибка получения последнего ордера: {e}")
        return None