from typing import Optional
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, func, Index

class Base(DeclarativeBase):
    pass

class TradeLog(Base):
    __tablename__ = "trade_logs"
    __table_args__ = (
        Index('idx_symbol_side', 'symbol', 'side'),
        Index('idx_timestamp', 'timestamp'),
        Index('idx_order_id', 'order_id', unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    side: Mapped[str] = mapped_column(nullable=True)
    qty: Mapped[float] = mapped_column(nullable=True)
    avg_price: Mapped[float] = mapped_column(nullable=True)
    entry_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    profit: Mapped[Optional[float]] = mapped_column(nullable=True)
    profit_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    commission: Mapped[Optional[float]] = mapped_column(nullable=True)
    is_profitable: Mapped[Optional[bool]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(nullable=True)
    timestamp: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=func.now())

class UserTradeStats(Base):
    __tablename__ = "user_trade_stats"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    side: Mapped[str] = mapped_column(nullable=True)
    qty: Mapped[float] = mapped_column(nullable=True)
    price: Mapped[float] = mapped_column(nullable=True)
    profit: Mapped[Optional[float]] = mapped_column(nullable=True)
    profit_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    timestamp: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=func.now())