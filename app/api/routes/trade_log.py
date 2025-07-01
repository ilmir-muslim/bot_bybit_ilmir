from app.notifier import send_telegram_message
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.engine import create_db
from app.database.models import TradeLog


router = APIRouter()

@router.get("/trade")
def get_trade_log(limit: int = 20, db: Session = Depends(create_db)):
    try:
        logs = db.query(TradeLog).order_by(TradeLog.timestamp.desc()).limit(limit).all()
        return [
            {
                "symbol": log.symbol,
                "side": log.side,
                "qty": log.qty,
                "price": log.avg_price,
                "status": log.status,
                "time": log.timestamp.isoformat()
            }
            for log in logs
        ]
    except Exception as e:
        import traceback
        traceback.print_exc()
        send_telegram_message("error in get_trade_log: " + str(e))
        return {"error": str(e)}
