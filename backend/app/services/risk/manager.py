"""
Risk Manager — enforces ALL hard rules BEFORE any trade reaches execution.
Every rule here is a hard gate. None can be bypassed at runtime.
Capital preservation is the primary strategy.
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional
from loguru import logger

from app.core.config import settings
from app.core.redis import RedisCache, get_redis
from app.services.analysis.signals import Signal
from app.models.trading import RiskEventType, TradeDirection


@dataclass
class RiskCheck:
    passed: bool
    reason: str
    event_type: Optional[RiskEventType] = None


@dataclass
class TradeParameters:
    """Computed trade parameters after risk sizing."""
    quantity: float
    risk_amount: float
    stop_loss: float
    take_profit: Optional[float]
    risk_reward_ratio: float
    risk_pct: float


class RiskManager:
    # Hard limits — these CANNOT be changed at runtime, only in config
    ABS_MAX_RISK_PER_TRADE = 2.0   # 2% absolute ceiling, hardcoded
    ABS_MAX_DAILY_LOSS = 10.0      # 10% absolute daily loss ceiling
    ABS_MAX_DRAWDOWN = 25.0        # 25% absolute drawdown ceiling

    def __init__(self):
        self._cache: Optional[RedisCache] = None
        self._account_balance: float = 0.0
        self._peak_balance: float = 0.0
        self._daily_start_balance: float = 0.0
        self._daily_loss: float = 0.0
        self._daily_loss_date: Optional[date] = None
        self._open_positions: int = 0
        self._strategies_paused: bool = False
        self._kill_switch_active: bool = False
        self._cooldown_instruments: dict[str, datetime] = {}

        # Effective limits (from config, capped at hard ceiling)
        self._max_risk_pct = min(settings.max_risk_per_trade_pct, self.ABS_MAX_RISK_PER_TRADE)
        self._max_daily_loss_pct = min(settings.max_daily_loss_pct, self.ABS_MAX_DAILY_LOSS)
        self._max_drawdown_pct = min(settings.max_drawdown_pct, self.ABS_MAX_DRAWDOWN)

        logger.info(
            f"Risk Manager initialized — "
            f"Max risk/trade: {self._max_risk_pct}% | "
            f"Max daily loss: {self._max_daily_loss_pct}% | "
            f"Max drawdown: {self._max_drawdown_pct}%"
        )

    async def init(self, account_balance: float) -> None:
        redis = await get_redis()
        self._cache = RedisCache(redis)
        await self.update_balance(account_balance)
        logger.info(f"Risk Manager ready. Balance: {account_balance}")

    # ─── Balance Management ───────────────────────────────────────────────

    async def update_balance(self, new_balance: float) -> None:
        today = date.today()

        # Reset daily tracking on new day
        if self._daily_loss_date != today:
            self._daily_start_balance = new_balance if self._account_balance == 0 else self._account_balance
            self._daily_loss = 0.0
            self._daily_loss_date = today
            self._strategies_paused = False
            logger.info(f"New trading day — daily loss reset. Start balance: {self._daily_start_balance}")

        self._account_balance = new_balance

        # Track peak balance for drawdown calculation
        if new_balance > self._peak_balance:
            self._peak_balance = new_balance

        # Compute daily loss
        if self._daily_start_balance > 0:
            self._daily_loss = self._daily_start_balance - new_balance

        await self._check_limits_after_update()

    async def record_pnl(self, pnl: float) -> None:
        if pnl < 0:
            await self.update_balance(self._account_balance + pnl)

    # ─── Pre-Trade Checks (ALL must pass for trade to execute) ───────────

    async def check_trade(self, signal: Signal, is_paper: bool = True) -> RiskCheck:
        """Run ALL risk checks against a signal. Returns first failure or pass."""

        # 1. Kill switch
        if self._kill_switch_active:
            return RiskCheck(False, "Kill switch is active — all trading halted", RiskEventType.KILL_SWITCH)

        # 2. Strategies paused (daily limit hit)
        if self._strategies_paused and not is_paper:
            return RiskCheck(False, "All strategies paused — daily loss limit reached", RiskEventType.DAILY_LIMIT_HIT)

        # 3. Max concurrent positions
        if self._open_positions >= settings.max_concurrent_positions:
            return RiskCheck(
                False,
                f"Max concurrent positions reached ({self._open_positions}/{settings.max_concurrent_positions})",
                RiskEventType.POSITION_LIMIT
            )

        # 4. Instrument cooldown
        cooldown_check = await self._check_cooldown(signal.instrument)
        if not cooldown_check.passed:
            return cooldown_check

        # 5. Stop-loss required
        if signal.suggested_stop_loss is None:
            return RiskCheck(False, "No stop-loss provided — trade rejected. Every trade MUST have a stop-loss.")

        # 6. R:R ratio check
        rr_check = self._check_rr_ratio(signal)
        if not rr_check.passed:
            return rr_check

        # 7. Daily loss limit
        daily_loss_pct = (self._daily_loss / self._daily_start_balance * 100) if self._daily_start_balance > 0 else 0
        if daily_loss_pct >= self._max_daily_loss_pct:
            return RiskCheck(
                False,
                f"Daily loss limit reached: {daily_loss_pct:.2f}% of {self._max_daily_loss_pct}% limit",
                RiskEventType.DAILY_LIMIT_HIT
            )

        # 8. Drawdown check
        drawdown_check = self._check_drawdown()
        if not drawdown_check.passed:
            return drawdown_check

        return RiskCheck(True, "All risk checks passed")

    def _check_rr_ratio(self, signal: Signal) -> RiskCheck:
        if signal.suggested_stop_loss is None or signal.suggested_take_profit is None:
            return RiskCheck(True, "No TP provided — R:R check skipped")

        price = signal.indicators.get("price", 0)
        sl = signal.suggested_stop_loss
        tp = signal.suggested_take_profit

        if signal.direction == TradeDirection.BUY:
            risk = abs(price - sl)
            reward = abs(tp - price)
        else:
            risk = abs(sl - price)
            reward = abs(price - tp)

        if risk == 0:
            return RiskCheck(False, "Stop loss equals entry price — zero risk distance", RiskEventType.RR_REJECTED)

        rr = reward / risk

        if rr < settings.min_rr_ratio:
            return RiskCheck(
                False,
                f"R:R ratio {rr:.2f}:1 is below minimum {settings.min_rr_ratio}:1 — trade rejected",
                RiskEventType.RR_REJECTED
            )

        if rr < settings.warn_rr_ratio:
            logger.warning(f"R:R {rr:.2f}:1 is below ideal {settings.warn_rr_ratio}:1 — trade allowed but flagged")

        return RiskCheck(True, f"R:R ratio {rr:.2f}:1 accepted")

    def _check_drawdown(self) -> RiskCheck:
        if self._peak_balance == 0:
            return RiskCheck(True, "No peak balance recorded yet")
        drawdown_pct = (self._peak_balance - self._account_balance) / self._peak_balance * 100
        if drawdown_pct >= self._max_drawdown_pct:
            return RiskCheck(
                False,
                f"Max drawdown exceeded: {drawdown_pct:.2f}% from peak (limit: {self._max_drawdown_pct}%)",
                RiskEventType.DRAWDOWN_LIMIT
            )
        return RiskCheck(True, f"Drawdown {drawdown_pct:.2f}% within limits")

    async def _check_cooldown(self, instrument: str) -> RiskCheck:
        if self._cache and await self._cache.is_on_cooldown(instrument):
            return RiskCheck(
                False,
                f"{instrument} is on {settings.stop_loss_cooldown_minutes}-minute cooldown after stop-loss",
                RiskEventType.STOP_LOSS_COOLDOWN
            )
        return RiskCheck(True, f"No cooldown on {instrument}")

    # ─── Position Sizing ──────────────────────────────────────────────────

    def size_trade(self, signal: Signal, account_balance: float) -> TradeParameters:
        """
        Calculate position size from risk parameters.
        Risk amount = max_risk_pct% of account balance.
        Quantity = risk_amount / distance_to_stop_loss
        """
        price = signal.indicators.get("price", 0) or list(signal.indicators.values())[0]
        sl = signal.suggested_stop_loss
        tp = signal.suggested_take_profit

        risk_pct = min(self._max_risk_pct, self.ABS_MAX_RISK_PER_TRADE)
        risk_amount = account_balance * (risk_pct / 100)

        sl_distance = abs(price - sl)
        quantity = risk_amount / sl_distance if sl_distance > 0 else 1.0

        if tp:
            if signal.direction == TradeDirection.BUY:
                rr = (tp - price) / sl_distance
            else:
                rr = (price - tp) / sl_distance
        else:
            rr = 0.0

        return TradeParameters(
            quantity=round(quantity, 4),
            risk_amount=round(risk_amount, 2),
            stop_loss=round(sl, 5),
            take_profit=round(tp, 5) if tp else None,
            risk_reward_ratio=round(rr, 2),
            risk_pct=risk_pct,
        )

    # ─── Post-Trade Actions ───────────────────────────────────────────────

    def register_position_opened(self) -> None:
        self._open_positions = min(self._open_positions + 1, settings.max_concurrent_positions)
        logger.debug(f"Position opened. Open positions: {self._open_positions}")

    async def register_position_closed(self, pnl: float, instrument: str, was_stop_loss: bool) -> None:
        self._open_positions = max(0, self._open_positions - 1)
        if pnl < 0:
            await self.record_pnl(pnl)
        if was_stop_loss and self._cache:
            await self._cache.set_cooldown(instrument, settings.stop_loss_cooldown_minutes)
            logger.info(f"Stop-loss hit on {instrument} — {settings.stop_loss_cooldown_minutes}min cooldown set")
        logger.debug(f"Position closed. PnL: {pnl:+.2f}. Open positions: {self._open_positions}")

    # ─── Kill Switch ──────────────────────────────────────────────────────

    async def activate_kill_switch(self) -> str:
        self._kill_switch_active = True
        self._strategies_paused = True
        msg = f"KILL SWITCH ACTIVATED at {datetime.utcnow().isoformat()}Z — all trading halted"
        logger.critical(msg)
        if self._cache:
            await self._cache.set_json("risk:kill_switch", {"active": True, "at": datetime.utcnow().isoformat()}, ttl=86400)
        return msg

    async def deactivate_kill_switch(self) -> str:
        self._kill_switch_active = False
        msg = "Kill switch deactivated. Strategies remain paused until manually resumed."
        logger.info(msg)
        return msg

    # ─── Internal Limit Checks ────────────────────────────────────────────

    async def _check_limits_after_update(self) -> None:
        # Daily loss auto-pause
        if self._daily_start_balance > 0:
            daily_loss_pct = self._daily_loss / self._daily_start_balance * 100
            if daily_loss_pct >= self._max_daily_loss_pct and not self._strategies_paused:
                self._strategies_paused = True
                logger.warning(f"DAILY LOSS LIMIT HIT: {daily_loss_pct:.2f}% — all strategies auto-paused")

        # Drawdown kill switch
        if self._peak_balance > 0:
            drawdown_pct = (self._peak_balance - self._account_balance) / self._peak_balance * 100
            if drawdown_pct >= self._max_drawdown_pct and not self._kill_switch_active:
                await self.activate_kill_switch()
                logger.critical(f"MAX DRAWDOWN EXCEEDED: {drawdown_pct:.2f}% — kill switch fired automatically")

    # ─── State ────────────────────────────────────────────────────────────

    @property
    def state(self) -> dict:
        daily_loss_pct = 0.0
        if self._daily_start_balance > 0:
            daily_loss_pct = self._daily_loss / self._daily_start_balance * 100
        drawdown_pct = 0.0
        if self._peak_balance > 0:
            drawdown_pct = (self._peak_balance - self._account_balance) / self._peak_balance * 100
        return {
            "account_balance": self._account_balance,
            "peak_balance": self._peak_balance,
            "daily_start_balance": self._daily_start_balance,
            "daily_loss": self._daily_loss,
            "daily_loss_pct": daily_loss_pct,
            "daily_loss_limit_pct": self._max_daily_loss_pct,
            "drawdown_pct": drawdown_pct,
            "drawdown_limit_pct": self._max_drawdown_pct,
            "open_positions": self._open_positions,
            "max_positions": settings.max_concurrent_positions,
            "strategies_paused": self._strategies_paused,
            "kill_switch_active": self._kill_switch_active,
        }

    async def resume_strategies(self) -> None:
        if not self._kill_switch_active:
            self._strategies_paused = False
            logger.info("Strategies manually resumed")

    def can_go_live(self, session) -> tuple[bool, str]:
        """Gate check before enabling live trading."""
        checks = [
            (session.days_active >= 30, "Need 30 days paper trading"),
            (session.win_rate is not None and session.win_rate >= 0.45, "Need win rate >= 45%"),
            (session.profit_factor is not None and session.profit_factor >= 1.2, "Need profit factor >= 1.2"),
            (session.max_drawdown_pct is not None and session.max_drawdown_pct < 20, "Drawdown too high"),
            (session.total_trades >= 100, "Need 100+ paper trades"),
        ]
        failed = [msg for passed, msg in checks if not passed]
        return (len(failed) == 0, "; ".join(failed))


# Singleton
risk_manager = RiskManager()
