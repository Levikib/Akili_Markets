import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Float, Boolean, Text, Integer, Enum as SAEnum,
    ForeignKey, DateTime, CheckConstraint, JSON, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
import enum
from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class StrategyType(str, enum.Enum):
    MOMENTUM       = "momentum"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT       = "breakout"
    SCALPER        = "scalper"


class TradeDirection(str, enum.Enum):
    BUY  = "BUY"
    SELL = "SELL"


class TradeStatus(str, enum.Enum):
    OPEN      = "OPEN"
    CLOSED    = "CLOSED"
    CANCELLED = "CANCELLED"
    PENDING   = "PENDING"


class RiskEventType(str, enum.Enum):
    DAILY_LIMIT_HIT    = "daily_limit_hit"
    DRAWDOWN_LIMIT     = "drawdown_limit"
    KILL_SWITCH        = "kill_switch"
    STOP_LOSS_COOLDOWN = "stop_loss_cooldown"
    POSITION_LIMIT     = "position_limit"
    RR_REJECTED        = "rr_rejected"


class Market(str, enum.Enum):
    SYNTHETIC = "synthetic"
    FOREX     = "forex"
    CRYPTO    = "crypto"


class Timeframe(str, enum.Enum):
    M1  = "M1"
    M5  = "M5"
    M15 = "M15"
    H1  = "H1"
    H4  = "H4"
    D1  = "D1"


class Strategy(Base):
    __tablename__ = "strategies"
    __table_args__ = (
        CheckConstraint("risk_per_trade_pct <= 2.0", name="ck_risk_per_trade_max"),
    )

    id:                 Mapped[str]            = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name:               Mapped[str]            = mapped_column(String(100), nullable=False)
    type:               Mapped[StrategyType]   = mapped_column(SAEnum(StrategyType), nullable=False)
    instrument:         Mapped[str]            = mapped_column(String(20), nullable=False)
    market:             Mapped[Market]         = mapped_column(SAEnum(Market), nullable=False, default=Market.CRYPTO)
    timeframe:          Mapped[Timeframe]      = mapped_column(SAEnum(Timeframe), nullable=False)
    parameters:         Mapped[dict]           = mapped_column(JSONB, nullable=False, default=dict)
    risk_per_trade_pct: Mapped[float]          = mapped_column(Float, nullable=False, default=1.5)
    is_active:          Mapped[bool]           = mapped_column(Boolean, default=False)
    is_paper:           Mapped[bool]           = mapped_column(Boolean, default=True)
    description:        Mapped[Optional[str]]  = mapped_column(Text)
    created_at:         Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:         Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    trades:          Mapped[list["Trade"]]         = relationship("Trade", back_populates="strategy")
    risk_events:     Mapped[list["RiskEvent"]]     = relationship("RiskEvent", back_populates="strategy")
    backtest_results:Mapped[list["BacktestResult"]]= relationship("BacktestResult", back_populates="strategy")
    paper_sessions:  Mapped[list["PaperSession"]]  = relationship("PaperSession", back_populates="strategy")


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("stop_loss IS NOT NULL", name="ck_stop_loss_required"),
    )

    id:               Mapped[str]             = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id:          Mapped[Optional[str]]   = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    strategy_id:      Mapped[str]             = mapped_column(String(36), ForeignKey("strategies.id"), nullable=False)
    instrument:       Mapped[str]             = mapped_column(String(20), nullable=False)
    market:           Mapped[Market]          = mapped_column(SAEnum(Market), nullable=False)
    direction:        Mapped[TradeDirection]  = mapped_column(SAEnum(TradeDirection), nullable=False)

    entry_price:      Mapped[float]           = mapped_column(Float, nullable=False)
    exit_price:       Mapped[Optional[float]] = mapped_column(Float)
    quantity:         Mapped[float]           = mapped_column(Float, nullable=False)

    stop_loss:        Mapped[float]           = mapped_column(Float, nullable=False)
    take_profit:      Mapped[Optional[float]] = mapped_column(Float)

    risk_amount:      Mapped[float]           = mapped_column(Float, nullable=False)
    risk_reward_ratio:Mapped[Optional[float]] = mapped_column(Float)
    pnl:              Mapped[Optional[float]] = mapped_column(Float)
    pnl_pct:          Mapped[Optional[float]] = mapped_column(Float)

    status:           Mapped[TradeStatus]     = mapped_column(SAEnum(TradeStatus), nullable=False, default=TradeStatus.PENDING)
    is_paper:         Mapped[bool]            = mapped_column(Boolean, nullable=False, default=True)
    binance_order_id: Mapped[Optional[str]]   = mapped_column(String(100))

    signal_reason:    Mapped[str]             = mapped_column(Text, nullable=False)
    ai_explanation:   Mapped[Optional[str]]   = mapped_column(Text)
    entry_indicators: Mapped[dict]            = mapped_column(JSONB, nullable=False, default=dict)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)

    opened_at:        Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at:        Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="trades")


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id:                      Mapped[str]           = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id:                 Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    event_type:              Mapped[RiskEventType] = mapped_column(SAEnum(RiskEventType), nullable=False)
    strategy_id:             Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("strategies.id"))
    description:             Mapped[str]           = mapped_column(Text, nullable=False)
    account_balance_at_event:Mapped[Optional[float]]= mapped_column(Float)
    created_at:              Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    strategy: Mapped[Optional["Strategy"]] = relationship("Strategy", back_populates="risk_events")


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id:               Mapped[str]      = mapped_column(String(36), primary_key=True, default=gen_uuid)
    strategy_id:      Mapped[str]      = mapped_column(String(36), ForeignKey("strategies.id"), nullable=False)
    instrument:       Mapped[str]      = mapped_column(String(20), nullable=False)
    timeframe:        Mapped[Timeframe]= mapped_column(SAEnum(Timeframe), nullable=False)
    date_from:        Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_to:          Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    initial_capital:  Mapped[float]    = mapped_column(Float, nullable=False)
    final_capital:    Mapped[float]    = mapped_column(Float, nullable=False)
    total_trades:     Mapped[int]      = mapped_column(Integer, nullable=False, default=0)
    winning_trades:   Mapped[int]      = mapped_column(Integer, nullable=False, default=0)
    win_rate:         Mapped[Optional[float]] = mapped_column(Float)
    profit_factor:    Mapped[Optional[float]] = mapped_column(Float)
    sharpe_ratio:     Mapped[Optional[float]] = mapped_column(Float)
    max_drawdown_pct: Mapped[Optional[float]] = mapped_column(Float)
    total_return_pct: Mapped[Optional[float]] = mapped_column(Float)
    expectancy:       Mapped[Optional[float]] = mapped_column(Float)
    equity_curve:     Mapped[list]     = mapped_column(JSONB, nullable=False, default=list)
    ran_at:           Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="backtest_results")


class PaperSession(Base):
    __tablename__ = "paper_sessions"

    id:                  Mapped[str]           = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id:             Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    strategy_id:         Mapped[str]           = mapped_column(String(36), ForeignKey("strategies.id"), nullable=False)
    started_at:          Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at:            Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    initial_balance:     Mapped[float]         = mapped_column(Float, nullable=False, default=1000.0)
    final_balance:       Mapped[Optional[float]] = mapped_column(Float)
    total_trades:        Mapped[int]           = mapped_column(Integer, default=0)
    win_rate:            Mapped[Optional[float]] = mapped_column(Float)
    profit_factor:       Mapped[Optional[float]] = mapped_column(Float)
    max_drawdown_pct:    Mapped[Optional[float]] = mapped_column(Float)
    days_active:         Mapped[int]           = mapped_column(Integer, default=0)
    is_qualified:        Mapped[bool]          = mapped_column(Boolean, default=False)
    qualification_reason:Mapped[Optional[str]] = mapped_column(Text)

    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="paper_sessions")


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id:                   Mapped[str]   = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id:              Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    balance:              Mapped[float] = mapped_column(Float, nullable=False)
    equity:               Mapped[float] = mapped_column(Float, nullable=False)
    margin_used:          Mapped[float] = mapped_column(Float, default=0.0)
    free_margin:          Mapped[float] = mapped_column(Float, default=0.0)
    open_positions_count: Mapped[int]   = mapped_column(Integer, default=0)
    daily_pnl:            Mapped[float] = mapped_column(Float, default=0.0)
    daily_pnl_pct:        Mapped[float] = mapped_column(Float, default=0.0)
    recorded_at:          Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
