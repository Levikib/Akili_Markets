"""
Binance Live Trader — real money execution via Binance Futures API.
Same qualification gate as before. Same risk rules. Same kill switch.
Leverage locked to 1x by default — no margin amplification.
"""
import uuid
from datetime import datetime
from typing import Optional
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analysis.signals import Signal
from app.services.risk.manager import risk_manager
from app.services.binance.client import binance_client, INSTRUMENT_MAP
from app.services.ai.explainer import trade_explainer
from app.models.trading import Trade, TradeStatus, Market, PaperSession, TradeDirection


class BinanceLiveTrader:
    def __init__(self):
        self._enabled: bool = False
        self._session_start: Optional[datetime] = None

    def can_go_live(self, session: PaperSession) -> tuple[bool, str]:
        checks = [
            (session.days_active >= 30,                                       "Need 30 days paper trading"),
            (session.win_rate is not None and session.win_rate >= 0.45,       "Need win rate >= 45%"),
            (session.profit_factor is not None and session.profit_factor >= 1.2, "Need profit factor >= 1.2"),
            (session.max_drawdown_pct is not None and session.max_drawdown_pct < 20, "Drawdown too high"),
            (session.total_trades >= 100,                                     "Need 100+ paper trades"),
        ]
        failed = [msg for passed, msg in checks if not passed]
        return (len(failed) == 0, "; ".join(failed))

    async def enable(self, session: PaperSession) -> tuple[bool, str]:
        if not binance_client.is_authorized:
            return False, "Binance API keys not configured"
        qualified, reason = self.can_go_live(session)
        if not qualified:
            return False, reason
        self._enabled = True
        self._session_start = datetime.utcnow()
        logger.critical("BINANCE LIVE TRADING ENABLED — REAL MONEY ACTIVE")
        return True, "Live trading enabled"

    def disable(self) -> None:
        self._enabled = False
        logger.info("Binance live trading disabled")

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
            return None
        if not binance_client.is_authorized:
            logger.error("Binance not authorized")
            return None

        risk_check = await risk_manager.check_trade(signal, is_paper=False)
        if not risk_check.passed:
            logger.warning(f"Risk check failed: {risk_check.reason}")
            return None

        params = risk_manager.size_trade(signal, binance_client.balance)
        symbol = INSTRUMENT_MAP.get(signal.instrument, signal.instrument)
        side = "BUY" if signal.direction == TradeDirection.BUY else "SELL"

        # Enforce minimum quantity
        min_qty = binance_client.get_min_quantity(symbol)
        quantity = max(params.quantity, min_qty)

        ai_explanation = None
        try:
            ai_explanation = await trade_explainer.explain_trade(signal, params)
        except Exception as e:
            logger.warning(f"AI explainer failed: {e}")

        try:
            order = await binance_client.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                stop_loss=params.stop_loss,
                take_profit=params.take_profit,
            )
            entry_price = float(order.get("avgPrice") or order.get("price") or 0)
            order_id = str(order.get("orderId", ""))
        except Exception as e:
            logger.error(f"Binance order failed: {e}")
            return None

        trade = Trade(
            id=str(uuid.uuid4()),
            strategy_id=strategy_id,
            instrument=symbol,
            market=Market.SYNTHETIC,
            direction=signal.direction,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=params.stop_loss,
            take_profit=params.take_profit,
            risk_amount=params.risk_amount,
            risk_reward_ratio=params.risk_reward_ratio,
            status=TradeStatus.OPEN,
            is_paper=False,
            deriv_contract_id=order_id,
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
            f"BINANCE LIVE {side} {symbol} | qty:{quantity} | "
            f"entry:{entry_price} | SL:{params.stop_loss} | TP:{params.take_profit}"
        )
        return trade

    async def kill_all(self, db: AsyncSession) -> dict:
        result = await binance_client.kill_all()
        await risk_manager.activate_kill_switch()
        self.disable()
        return {**result, "kill_switch_active": True}


binance_live_trader = BinanceLiveTrader()
