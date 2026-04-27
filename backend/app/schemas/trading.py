from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any
from datetime import datetime
from app.models.trading import StrategyType, TradeDirection, TradeStatus, RiskEventType, Market, Timeframe


# ─── Strategy Schemas ────────────────────────────────────────────────────────

class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: StrategyType
    instrument: str
    market: Market = Market.SYNTHETIC
    timeframe: Timeframe
    parameters: dict = {}
    risk_per_trade_pct: float = Field(default=1.5, gt=0, le=2.0)
    description: Optional[str] = None


class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    parameters: Optional[dict] = None
    risk_per_trade_pct: Optional[float] = Field(default=None, gt=0, le=2.0)
    is_active: Optional[bool] = None
    description: Optional[str] = None


class StrategyResponse(BaseModel):
    id: str
    name: str
    type: StrategyType
    instrument: str
    market: Market
    timeframe: Timeframe
    parameters: dict
    risk_per_trade_pct: float
    is_active: bool
    is_paper: bool
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Signal Schemas ───────────────────────────────────────────────────────────

class SignalResponse(BaseModel):
    strategy_id: str
    strategy_name: str
    instrument: str
    direction: TradeDirection
    confidence: float = Field(..., ge=0, le=100)
    reason: str
    indicators: dict
    timestamp: datetime


# ─── Trade Schemas ────────────────────────────────────────────────────────────

class TradeResponse(BaseModel):
    id: str
    strategy_id: str
    instrument: str
    market: Market
    direction: TradeDirection
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    stop_loss: float
    take_profit: Optional[float]
    risk_amount: float
    risk_reward_ratio: Optional[float]
    pnl: Optional[float]
    pnl_pct: Optional[float]
    status: TradeStatus
    is_paper: bool
    signal_reason: str
    ai_explanation: Optional[str]
    entry_indicators: dict
    confidence_score: Optional[float]
    opened_at: datetime
    closed_at: Optional[datetime]

    class Config:
        from_attributes = True


# ─── Risk Schemas ─────────────────────────────────────────────────────────────

class RiskStatus(BaseModel):
    is_paper_mode: bool
    daily_loss_pct: float
    daily_loss_limit_pct: float
    drawdown_pct: float
    drawdown_limit_pct: float
    open_positions: int
    max_positions: int
    all_strategies_paused: bool
    kill_switch_active: bool
    peak_balance: float
    current_balance: float


class RiskSettingsUpdate(BaseModel):
    max_risk_per_trade_pct: Optional[float] = Field(default=None, gt=0, le=2.0)
    max_daily_loss_pct: Optional[float] = Field(default=None, gt=0, le=10.0)
    max_drawdown_pct: Optional[float] = Field(default=None, gt=0, le=25.0)


# ─── Backtest Schemas ─────────────────────────────────────────────────────────

class BacktestRunRequest(BaseModel):
    strategy_id: str
    instrument: str
    timeframe: Timeframe
    date_from: datetime
    date_to: datetime
    initial_capital: float = Field(default=1000.0, gt=0)


class BacktestResultResponse(BaseModel):
    id: str
    strategy_id: str
    instrument: str
    timeframe: Timeframe
    date_from: datetime
    date_to: datetime
    initial_capital: float
    final_capital: float
    total_trades: int
    winning_trades: int
    win_rate: Optional[float]
    profit_factor: Optional[float]
    sharpe_ratio: Optional[float]
    sortino_ratio: Optional[float]
    max_drawdown_pct: Optional[float]
    total_return_pct: Optional[float]
    expectancy: Optional[float]
    equity_curve: list
    ran_at: datetime

    class Config:
        from_attributes = True


# ─── Paper Session Schemas ────────────────────────────────────────────────────

class PaperSessionResponse(BaseModel):
    id: str
    strategy_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    initial_balance: float
    final_balance: Optional[float]
    total_trades: int
    win_rate: Optional[float]
    profit_factor: Optional[float]
    max_drawdown_pct: Optional[float]
    days_active: int
    is_qualified: bool
    qualification_reason: Optional[str]

    class Config:
        from_attributes = True


# ─── System Status ────────────────────────────────────────────────────────────

class SystemStatus(BaseModel):
    mode: str  # "PAPER" | "LIVE"
    is_running: bool
    active_strategies: int
    open_positions: int
    daily_pnl: float
    daily_pnl_pct: float
    account_balance: float
    deriv_connected: bool
    uptime_seconds: float
