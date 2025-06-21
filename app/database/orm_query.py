from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc, func
from app.database.models import TradeLog, UserTradeStats
from app.utils.log_helper import log_maker

def orm_add_data_to_tables(
    session: Session, 
    data_trade_log: dict = None, 
    data_user_trade_stats: dict = None
):
    objects_to_add = []
    
    if data_trade_log:
        # Автоматическое заполнение цен входа/выхода
        if data_trade_log.get("side") == "BUY":
            data_trade_log.setdefault("entry_price", data_trade_log.get("avg_price"))
        elif data_trade_log.get("side") == "SELL":
            data_trade_log.setdefault("exit_price", data_trade_log.get("avg_price"))
        
        trade_log = TradeLog(**data_trade_log)
        objects_to_add.append(trade_log)
    
    if data_user_trade_stats:
        user_stats = UserTradeStats(**data_user_trade_stats)
        objects_to_add.append(user_stats)
    
    if not objects_to_add:
        return
    
    try:
        session.add_all(objects_to_add)
        session.commit()
    except IntegrityError as e:
        session.rollback()
        log_maker(f"⚠️ Integrity error (duplicate?): {e}")
    except Exception as e:
        session.rollback()
        log_maker(f"❌ Database error: {type(e).__name__} - {e}")

def get_last_trade(session: Session, symbol: str) -> TradeLog:
    """Возвращает последнюю сделку для указанного символа"""
    return session.query(TradeLog).filter(
        TradeLog.symbol == symbol
    ).order_by(desc(TradeLog.timestamp)).first()