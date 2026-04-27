"""
Paper Trader — simulated execution engine.
All the same risk checks as live, all the same logging,
but zero real money. Paper mode is the DEFAULT.
"""
import uuid
from datetime import datetime
from typing import Optional
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analysis.signals import Signal
from app.services.risk.manager import risk_manager, TradeParameters
from app.services.ai.explainer import trade_explainer
from app.models.trading import Trade, TradeStatus, Market, TradeDirection
from app.schemas.trading import TradeResponse


class PaperTrader:
    def __init__(self):
        self._balance: float = 1000.0  # default paper starting balance
        self._initial_balance: float = 1000.0
        self._open_trades: dict[str, Trade] = {}
        self._session_id: Optional[str] = None
        self._is_active: bool = False

    def start_session(self, initial_balance: float = 1000.0, session_id: Optional[str] = None) -> None:
        self._balance = initial_balance
        self._initial_balance = initial_balance
        self._session_id = session_id or str(uuid.uuid4())
        self._is_active = True
        self._open_trades = {}
        logger.info(f"Paper session started [{self._session_id}] — balance: ${initial_balance:.2f}")

    def stop_session(self) -> dict:
        self._is_active = False
        pnl = self._balance - self._initial_balance
        pnl_pct = (pnl / self._initial_balance) * 100
        logger.info(f"Paper session ended [{self._session_id}] — PnL: ${pnl:+.2f} ({pnl_pct:+.2f}%)")
        return {
            "session_id": self._session_id,
            "initial_balance": self._initial_balance,
            "final_balance": self._balance,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        }

    async def execute_signal(
        self,
        signal: Signal,
        strategy_id: str,
        db: AsyncSession,
    ) -> Optional[Trade]:
        if not self._is_active:
            logger.warning("Paper session not active — ignoring signal")
            return None

        # Full risk check — same as live
        risk_check = await risk_manager.check_trade(signal, is_paper=True)
        if not risk_check.passed:
            logger.warning(f"Risk check failed [{signal.instrument}]: {risk_check.reason}")
            return None

        # Size the trade
        params = risk_manager.size_trade(signal, self._balance)

        # Verify we have enough paper balance
        if params.risk_amount > self._balance:
            logger.warning("Insufficient paper balance for trade")
            return None

        # Generate AI explanation async (non-blocking)
        ai_explanation = None
        try:
            ai_explanation = await trade_explainer.explain_trade(signal, params)
        except Exception as e:
            logger.warning(f"AI explainer failed (non-critical): {e}")

        trade = Trade(
            id=str(uuid.uuid4()),
            strategy_id=strategy_id,
            instrument=signal.instrument,
            market=Market.SYNTHETIC if signal.instrument.startswith(("R_", "CRASH", "BOOM", "JD", "stp")) else Market.FOREX,
            direction=signal.direction,
            entry_price=signal.indicators.get("price", 0),
            quantity=params.quantity,
            stop_loss=params.stop_loss,
            take_profit=params.take_profit,
            risk_amount=params.risk_amount,
            risk_reward_ratio=params.risk_reward_ratio,
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

        self._open_trades[trade.id] = trade
        risk_manager.register_position_opened()

        logger.success(
            f"PAPER {signal.direction.value} {signal.instrument} | "
            f"Entry: {trade.entry_price:.5f} | SL: {params.stop_loss:.5f} | "
            f"TP: {params.take_profit:.5f if params.take_profit else 'none'} | "
            f"Risk: ${params.risk_amount:.2f} ({params.risk_pct}%)"
        )
        return trade

    async def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        db: AsyncSession,
        was_stop_loss: bool = False,
    ) -> Optional[Trade]:
        trade = self._open_trades.get(trade_id)
        if not trade:
            return None

        if trade.direction == TradeDirection.BUY:
            pnl = (exit_price - trade.entry_price) * trade.quantity
        else:
            pnl = (trade.entry_price - exit_price) * trade.quantity

        pnl_pct = (pnl / trade.risk_amount) * 100 if trade.risk_amount > 0 else 0

        trade.exit_price = exit_price
        trade.pnl = round(pnl, 2)
        trade.pnl_pct = round(pnl_pct, 2)
        trade.status = TradeStatus.CLOSED
        trade.closed_at = datetime.utcnow()

        self._balance += pnl
        del self._open_trades[trade_id]

        await risk_manager.register_position_closed(pnl, trade.instrument, was_stop_loss)
        await risk_manager.update_balance(self._balance)

        await db.merge(trade)

        logger.info(
            f"PAPER CLOSE {trade.instrument} | "
            f"Exit: {exit_price:.5f} | PnL: ${pnl:+.2f} ({pnl_pct:+.2f}%) | "
            f"{'STOP LOSS' if was_stop_loss else 'target/manual'}"
        )
        return trade

    async def check_stop_losses(self, current_prices: dict[str, float], db: AsyncSession) -> None:
        """Called by position monitor — checks if any open trade hit its SL."""
        for trade_id, trade in list(self._open_trades.items()):
            price = current_prices.get(trade.instrument)
            if price is None:
                continue

            hit_sl = False
            if trade.direction == TradeDirection.BUY and price <= trade.stop_loss:
                hit_sl = True
            elif trade.direction == TradeDirection.SELL and price >= trade.stop_loss:
                hit_sl = True

            hit_tp = False
            if trade.take_profit:
                if trade.direction == TradeDirection.BUY and price >= trade.take_profit:
                    hit_tp = True
                elif trade.direction == TradeDirection.SELL and price <= trade.take_profit:
                    hit_tp = True

            if hit_sl:
                await self.close_trade(trade_id, trade.stop_loss, db, was_stop_loss=True)
            elif hit_tp:
                await self.close_trade(trade_id, trade.take_profit, db, was_stop_loss=False)

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def open_positions(self) -> int:
        return len(self._open_trades)

    @property
    def is_active(self) -> bool:
        return self._is_active


paper_trader = PaperTrader()
