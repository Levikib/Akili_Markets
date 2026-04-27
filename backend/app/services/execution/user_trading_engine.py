"""
UserTradingEngine — per-user isolated trading execution.
Each user with active API keys gets their own BinanceClient, RiskManager,
PaperTrader, and position monitor. Completely isolated — one user's
trades, losses, and kill-switch never affect another user.
"""
import asyncio
import uuid
from datetime import datetime, date
from typing import Optional
from loguru import logger
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_api_key
from app.models.users import User, UserExchangeKey, UserSettings
from app.models.trading import Trade, TradeStatus, Market, TradeDirection
from app.services.analysis.signals import Signal
from app.services.ai.explainer import trade_explainer


class UserRiskManager:
    """Lightweight per-user risk manager — same hard rules, isolated state."""

    ABS_MAX_RISK  = 2.0
    ABS_MAX_DAILY = 10.0
    ABS_MAX_DD    = 25.0
    MAX_POSITIONS = 5

    def __init__(self, user_id: str, settings: UserSettings):
        self.user_id       = user_id
        self._max_risk_pct = min(settings.max_risk_per_trade_pct, self.ABS_MAX_RISK)
        self._max_daily_pct= min(settings.max_daily_loss_pct,     self.ABS_MAX_DAILY)
        self._max_dd_pct   = 15.0  # hard-coded drawdown kill

        self._balance      = settings.paper_balance
        self._peak_balance = settings.paper_balance
        self._daily_start  = settings.paper_balance
        self._daily_loss   = 0.0
        self._daily_date   = date.today()
        self._open_count   = 0
        self._paused       = False
        self._kill_active  = False

    def update_balance(self, new_balance: float) -> None:
        today = date.today()
        if self._daily_date != today:
            self._daily_start = self._balance
            self._daily_loss  = 0.0
            self._daily_date  = today
            self._paused      = False

        self._balance = new_balance
        if new_balance > self._peak_balance:
            self._peak_balance = new_balance
        if self._daily_start > 0:
            self._daily_loss = max(0.0, self._daily_start - new_balance)

        # Auto-pause on daily loss
        if self._daily_start > 0:
            daily_pct = self._daily_loss / self._daily_start * 100
            if daily_pct >= self._max_daily_pct and not self._paused:
                self._paused = True
                logger.warning(f"[User {self.user_id}] Daily loss limit hit {daily_pct:.1f}% — paused")

        # Auto kill-switch on drawdown
        if self._peak_balance > 0:
            dd_pct = (self._peak_balance - new_balance) / self._peak_balance * 100
            if dd_pct >= self._max_dd_pct and not self._kill_active:
                self._kill_active = True
                logger.critical(f"[User {self.user_id}] Drawdown kill switch fired {dd_pct:.1f}%")

    def check_trade(self, signal: Signal) -> tuple[bool, str]:
        if self._kill_active:
            return False, "Kill switch active"
        if self._paused:
            return False, "Daily loss limit reached — trading paused"
        if self._open_count >= self.MAX_POSITIONS:
            return False, f"Max {self.MAX_POSITIONS} concurrent positions reached"
        if signal.suggested_stop_loss is None:
            return False, "No stop-loss — rejected"
        return True, "ok"

    def size_trade(self, signal: Signal) -> dict:
        price = signal.indicators.get("price", 0)
        sl    = signal.suggested_stop_loss
        tp    = signal.suggested_take_profit

        risk_amount = self._balance * (self._max_risk_pct / 100)
        sl_dist     = abs(price - sl) if sl else 1.0
        quantity    = risk_amount / sl_dist if sl_dist > 0 else 1.0

        rr = 0.0
        if tp and sl_dist > 0:
            rr = abs(tp - price) / sl_dist

        return {
            "quantity":         round(quantity, 4),
            "risk_amount":      round(risk_amount, 2),
            "stop_loss":        round(sl, 5),
            "take_profit":      round(tp, 5) if tp else None,
            "risk_reward_ratio":round(rr, 2),
            "risk_pct":         self._max_risk_pct,
        }

    def register_open(self):
        self._open_count = min(self._open_count + 1, self.MAX_POSITIONS)

    def register_close(self, pnl: float):
        self._open_count = max(0, self._open_count - 1)
        self.update_balance(self._balance + pnl)

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def state(self) -> dict:
        daily_pct = (self._daily_loss / self._daily_start * 100) if self._daily_start > 0 else 0
        dd_pct    = ((self._peak_balance - self._balance) / self._peak_balance * 100) if self._peak_balance > 0 else 0
        return {
            "balance":        self._balance,
            "daily_loss_pct": round(daily_pct, 2),
            "drawdown_pct":   round(dd_pct, 2),
            "open_positions": self._open_count,
            "paused":         self._paused,
            "kill_active":    self._kill_active,
        }


class UserPaperTrader:
    """Isolated paper trader for one user."""

    def __init__(self, user_id: str, risk: UserRiskManager):
        self.user_id     = user_id
        self._risk       = risk
        self._open: dict[str, Trade] = {}

    async def execute_signal(self, signal: Signal, strategy_id: str, db) -> Optional[Trade]:
        ok, reason = self._risk.check_trade(signal)
        if not ok:
            logger.debug(f"[User {self.user_id}] Signal rejected: {reason}")
            return None

        params = self._risk.size_trade(signal)

        ai_explanation = None
        try:
            from app.services.risk.manager import TradeParameters
            tp = TradeParameters(
                quantity=params["quantity"],
                risk_amount=params["risk_amount"],
                stop_loss=params["stop_loss"],
                take_profit=params["take_profit"],
                risk_reward_ratio=params["risk_reward_ratio"],
                risk_pct=params["risk_pct"],
            )
            ai_explanation = await trade_explainer.explain_trade(signal, tp)
        except Exception:
            pass

        trade = Trade(
            id=str(uuid.uuid4()),
            user_id=self.user_id,
            strategy_id=strategy_id,
            instrument=signal.instrument,
            market=Market.CRYPTO,
            direction=signal.direction,
            entry_price=signal.indicators.get("price", 0),
            quantity=params["quantity"],
            stop_loss=params["stop_loss"],
            take_profit=params["take_profit"],
            risk_amount=params["risk_amount"],
            risk_reward_ratio=params["risk_reward_ratio"],
            status=TradeStatus.OPEN,
            is_paper=True,
            signal_reason=signal.reason,
            ai_explanation=ai_explanation,
            entry_indicators=signal.indicators,
            confidence_score=signal.confidence,
            opened_at=datetime.utcnow(),
        )
        db.add(trade)
        await db.flush()
        self._open[trade.id] = trade
        self._risk.register_open()

        logger.success(
            f"[User {self.user_id}] PAPER {signal.direction.value} {signal.instrument} "
            f"| Entry: {trade.entry_price:.2f} | SL: {params['stop_loss']:.2f} "
            f"| Risk: ${params['risk_amount']:.2f}"
        )
        return trade

    async def check_stops(self, prices: dict[str, float], db) -> None:
        for trade_id, trade in list(self._open.items()):
            price = prices.get(trade.instrument)
            if price is None:
                continue

            hit_sl = hit_tp = False
            if trade.direction == TradeDirection.BUY:
                hit_sl = price <= trade.stop_loss
                hit_tp = bool(trade.take_profit and price >= trade.take_profit)
            else:
                hit_sl = price >= trade.stop_loss
                hit_tp = bool(trade.take_profit and price <= trade.take_profit)

            if hit_sl:
                await self._close(trade_id, trade.stop_loss, db, sl=True)
            elif hit_tp:
                await self._close(trade_id, trade.take_profit, db, sl=False)  # type: ignore[arg-type]

    async def _close(self, trade_id: str, exit_price: float, db, sl: bool) -> None:
        trade = self._open.get(trade_id)
        if not trade:
            return

        if trade.direction == TradeDirection.BUY:
            pnl = (exit_price - trade.entry_price) * trade.quantity
        else:
            pnl = (trade.entry_price - exit_price) * trade.quantity

        trade.exit_price = exit_price
        trade.pnl        = round(pnl, 2)
        trade.pnl_pct    = round((pnl / trade.risk_amount) * 100, 2) if trade.risk_amount else 0
        trade.status     = TradeStatus.CLOSED
        trade.closed_at  = datetime.utcnow()

        del self._open[trade_id]
        self._risk.register_close(pnl)
        await db.merge(trade)

        logger.info(
            f"[User {self.user_id}] CLOSE {trade.instrument} "
            f"| PnL: ${pnl:+.2f} | {'SL' if sl else 'TP'}"
        )

    async def close_trade(self, trade_id: str, db) -> Optional[Trade]:
        trade = self._open.get(trade_id)
        if not trade:
            # Try DB
            t = await db.get(Trade, trade_id)
            if t and t.user_id == self.user_id:
                t.status    = TradeStatus.CLOSED
                t.closed_at = datetime.utcnow()
                t.pnl       = 0.0
                await db.merge(t)
                return t
            return None
        await self._close(trade_id, trade.entry_price, db, sl=False)
        return self._open.get(trade_id)

    @property
    def open_trades(self) -> list[Trade]:
        return list(self._open.values())


class UserTradingContext:
    """Everything needed to trade for one user."""

    def __init__(self, user: User, settings: UserSettings):
        self.user_id    = user.id
        self.user       = user
        self._risk      = UserRiskManager(user.id, settings)
        self._paper     = UserPaperTrader(user.id, self._risk)
        self._active    = True

    @property
    def risk(self) -> UserRiskManager:
        return self._risk

    @property
    def paper(self) -> UserPaperTrader:
        return self._paper

    @property
    def is_active(self) -> bool:
        return self._active

    def deactivate(self):
        self._active = False


class UserTradingEngine:
    """
    Central registry of per-user trading contexts.
    Loaded at startup and kept in sync as users add/remove keys.
    """

    def __init__(self):
        self._contexts: dict[str, UserTradingContext] = {}
        self._lock = asyncio.Lock()

    async def load_all_users(self) -> None:
        """Called at startup — load all active users with exchange keys."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.is_active == True)
            )
            users = result.scalars().all()

            for user in users:
                await self._load_user(user, db)

        logger.info(f"UserTradingEngine loaded {len(self._contexts)} user context(s)")

    async def _load_user(self, user: User, db) -> None:
        settings_result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        settings = settings_result.scalar_one_or_none()
        if not settings:
            settings = UserSettings(user_id=user.id)

        async with self._lock:
            self._contexts[user.id] = UserTradingContext(user, settings)

    async def reload_user(self, user_id: str) -> None:
        """Called when a user updates their settings or keys."""
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            if user and user.is_active:
                await self._load_user(user, db)

    def get_context(self, user_id: str) -> Optional[UserTradingContext]:
        return self._contexts.get(user_id)

    def all_contexts(self) -> list[UserTradingContext]:
        return [ctx for ctx in self._contexts.values() if ctx.is_active]

    async def execute_signal_for_all(self, signal: Signal, strategy_id: str) -> None:
        """Run a signal through every active user's paper trader independently."""
        if not self._contexts:
            return

        async with AsyncSessionLocal() as db:
            for ctx in self.all_contexts():
                try:
                    await ctx.paper.execute_signal(signal, strategy_id, db)
                except Exception as e:
                    logger.error(f"Signal execution error for user {ctx.user_id}: {e}")
            await db.commit()

    async def check_stops_for_all(self, prices: dict[str, float]) -> None:
        """Run stop/TP checks for all users against latest prices."""
        if not self._contexts:
            return

        async with AsyncSessionLocal() as db:
            for ctx in self.all_contexts():
                try:
                    await ctx.paper.check_stops(prices, db)
                except Exception as e:
                    logger.error(f"Stop check error for user {ctx.user_id}: {e}")
            await db.commit()

    def get_all_open_trades(self) -> dict[str, list[Trade]]:
        return {
            ctx.user_id: ctx.paper.open_trades
            for ctx in self.all_contexts()
        }


# Singleton
user_trading_engine = UserTradingEngine()
