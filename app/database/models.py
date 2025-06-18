from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.sql import func
from app.database.engine import Base

class TradeLog(Base):
    __tablename__ = "trade_logs"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    side = Column(String)  # BUY / SELL
    qty = Column(Float)
    avg_price = Column(Float)  # средняя цена исполнения
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    profit = Column(Float, nullable=True)
    profit_pct = Column(Float, nullable=True)
    commission = Column(Float, nullable=True)
    is_profitable = Column(Boolean, nullable=True)
    status = Column(String)
    error = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
