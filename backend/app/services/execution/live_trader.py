"""
Live Trader — real money execution via Deriv API.
ONLY accessible after paper qualification gate passes.
Qualification check runs on EVERY session start — not just once.
"""
import uuid
from datetime import datetime
from typing import Optional
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analysis.signals import Signal
from app.services.risk.manager import risk_manager
from app.services.deriv.client import deriv_client
from app.services.ai.explainer import trade_explainer
from app.models.trading import Trade, TradeStatus, Market, PaperSession, TradeDirection


class LiveTrader:
    def __init__(self):
        self._enabled: bool = False  # requires explicit unlock per session
        self._session_start: Optional[datetime] = None

    def can_go_live(self, session: PaperSession) -> tuple[bool, str]:
        checks = [
            (session.days_active >= 30, "Need 30 days paper trading"),
            (session.win_rate is not None and session.win_rate >= 0.45, "Need win rate >= 45%"),
            (session.profit_factor is not None and session.profit_factor >= 1.2, "Need profit factor >= 1.2"),
            (session.max_drawdown_pct is not None and session.max_drawdown_pct < 20, "Drawdown too high"),
            (session.total_trades >= 100, "Need 100+ paper trades"),
        ]
        failed = [msg for passed, msg in checks if not passed]
        return (len(failed) == 0, "; ".join(failed))

    async def enable(self, session: PaperSession) -> tuple[bool, str]:
        qualified, reason = self.can_go_live(session)
        if not qualified:
            logger.warning(f"Live trading enable rejected: {reason}")
            return False, reason
        self._enabled = True
        self._session_start = datetime.utcnow()
        logger.critical("LIVE TRADING ENABLED — REAL MONEY MODE ACTIVE")
        return True, "Live trading enabled"

    def disable(self) -> None:
        self._enabled = False
        self._session_start = None
        logger.info("Live trading disabled")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def execute_signal(
        self,
        signal: Signal,
        strategy_id: str,
        db: AsyncSession,
    ) -> Optional[Trade]:
        if not self._enabled:
            logger.error("Live trading is not enabled — trade rejected")
            return None

        if not deriv_client.is_authorized:
            logger.error("Deriv client not authorized — trade rejected")
            return None

        risk_check = await risk_manager.check_trade(signal, is_paper=False)
        if not risk_check.passed:
            logger.warning(f"Risk check failed (live): {risk_check.reason}")
            return None

        params = risk_manager.size_trade(signal, deriv_client.balance)

        # Map direction to Deriv contract type
        contract_type = "CALL" if signal.direction == TradeDirection.BUY else "PUT"

        ai_explanation = None
        try:
            ai_explanation = await trade_explainer.explain_trade(signal, params)
        except Exception as e:
            logger.warning(f"AI explainer failed (non-critical): {e}")

        try:
            contract = await deriv_client.buy_contract(
                contract_type=contract_type,
                symbol=signal.instrument,
                duration=5,
                duration_unit="m",
                amount=params.risk_amount,
                basis="stake",
            )
            deriv_contract_id = str(contract.get("contract_id", ""))
        except Exception as e:
            logger.error(f"Deriv buy failed: {e}")
            return None

        trade = Trade(
            id=str(uuid.uuid4()),
            strategy_id=strategy_id,
            instrument=signal.instrument,
            market=Market.SYNTHETIC,
            direction=signal.direction,
            entry_price=float(contract.get("buy_price", signal.indicators.get("price", 0))),
            quantity=params.quantity,
            stop_loss=params.stop_loss,
            take_profit=params.take_profit,
            risk_amount=params.risk_amount,
            risk_reward_ratio=params.risk_reward_ratio,
            status=TradeStatus.OPEN,
            is_paper=False,
            deriv_contract_id=deriv_contract_id,
            signal_reason=signal.reason,
            ai_explanation=ai_explanation,
            entry_indicators=signal.indicators,
            confidence_score=signal.confidence,
            opened_at=datetime.utcnow(),
        )

        db.add(trade)
        await db.flush()

        risk_manager.register_position_opened()
        logger.critical(
            f"LIVE {signal.direction.value} {signal.instrument} | "
            f"Contract: {deriv_contract_id} | Entry: {trade.entry_price:.5f} | "
            f"SL: {params.stop_loss:.5f} | Risk: ${params.risk_amount:.2f}"
        )
        return trade

    async def close_trade(
        self,
        trade: Trade,
        db: AsyncSession,
        was_stop_loss: bool = False,
    ) -> Optional[Trade]:
        if not trade.deriv_contract_id:
            return None
        try:
            result = await deriv_client.sell_contract(int(trade.deriv_contract_id))
            exit_price = float(result.get("sold_for", 0))
            pnl = exit_price - trade.risk_amount

            trade.exit_price = exit_price
            trade.pnl = round(pnl, 2)
            trade.pnl_pct = round((pnl / trade.risk_amount) * 100, 2)
            trade.status = TradeStatus.CLOSED
            trade.closed_at = datetime.utcnow()

            await risk_manager.register_position_closed(pnl, trade.instrument, was_stop_loss)
            await db.merge(trade)
            logger.critical(
                f"LIVE CLOSE {trade.instrument} | PnL: ${pnl:+.2f} | "
                f"{'STOP LOSS' if was_stop_loss else 'target/manual'}"
            )
            return trade
        except Exception as e:
            logger.error(f"Failed to close live trade {trade.id}: {e}")
            return None

    async def kill_all(self, db: AsyncSession) -> dict:
        """Emergency: close all live positions and cancel pending contracts."""
        contracts = await deriv_client.get_open_contracts()
        closed = 0
        errors = 0
        for contract in contracts:
            try:
                await deriv_client.sell_contract(int(contract["contract_id"]))
                closed += 1
            except Exception as e:
                logger.error(f"Kill failed for contract {contract.get('contract_id')}: {e}")
                errors += 1
        await risk_manager.activate_kill_switch()
        self.disable()
        return {"closed": closed, "errors": errors, "kill_switch_active": True}


live_trader = LiveTrader()
