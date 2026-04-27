from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional
from app.core.database import get_db
from app.models.trading import Trade, TradeStatus, PaperSession, Strategy
from app.models.users import User
from app.schemas.trading import TradeResponse, SystemStatus, PaperSessionResponse
from app.services.execution.paper_trader import paper_trader
from app.services.execution.live_trader import live_trader
from app.services.execution.user_trading_engine import user_trading_engine
from app.services.risk.manager import risk_manager
from app.services.binance.client import binance_client
from app.api.routes.auth import get_current_user
from loguru import logger
import time

router = APIRouter(prefix="/trading", tags=["Trading"])
security = HTTPBearer()

_start_time = time.time()


@router.get("/status")
async def get_system_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ctx = user_trading_engine.get_context(current_user.id)
    risk_state = ctx.risk.state if ctx else {}

    result = await db.execute(
        select(Trade)
        .where(Trade.status == TradeStatus.OPEN)
        .where(Trade.user_id == current_user.id)
    )
    open_trades = result.scalars().all()
    active_strats = await db.execute(
        select(Strategy).where(Strategy.is_active == True)
    )
    active_count = len(active_strats.scalars().all())

    return {
        "mode": "PAPER",
        "is_running": True,
        "active_strategies": active_count,
        "open_positions": len(open_trades),
        "daily_pnl": risk_state.get("daily_loss_pct", 0) * -1,
        "daily_pnl_pct": risk_state.get("daily_loss_pct", 0) * -1,
        "account_balance": risk_state.get("balance", 0),
        "binance_connected": binance_client.is_connected,
        "uptime_seconds": time.time() - _start_time,
    }


@router.post("/paper/start")
async def start_paper_session(
    strategy_id: str,
    initial_balance: float = 1000.0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    strategy = await db.get(Strategy, strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    session = PaperSession(
        strategy_id=strategy_id,
        initial_balance=initial_balance,
    )
    db.add(session)
    await db.flush()
    paper_trader.start_session(initial_balance, session.id)
    logger.info(f"Paper session started for strategy {strategy.name}")
    return {"session_id": session.id, "message": "Paper session started", "balance": initial_balance}


@router.post("/paper/stop")
async def stop_paper_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(PaperSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    result = paper_trader.stop_session()
    session.ended_at = result.get("ended_at")
    session.final_balance = result.get("final_balance")
    await db.flush()
    return result


@router.get("/paper/status")
async def get_paper_status(current_user: User = Depends(get_current_user)):
    ctx = user_trading_engine.get_context(current_user.id)
    if ctx:
        return {
            "is_active": ctx.is_active,
            "balance": ctx.risk.balance,
            "open_positions": ctx.risk.state["open_positions"],
            "mode": "PAPER",
            "risk": ctx.risk.state,
        }
    return {"is_active": False, "balance": 0, "open_positions": 0, "mode": "PAPER"}


@router.get("/trades", response_model=list[TradeResponse])
async def get_trades(
    is_paper: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Trade)
        .where(Trade.user_id == current_user.id)
        .order_by(desc(Trade.opened_at))
        .offset(offset)
        .limit(limit)
    )
    if is_paper is not None:
        query = query.where(Trade.is_paper == is_paper)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/positions")
async def get_open_positions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Trade)
        .where(Trade.status == TradeStatus.OPEN)
        .where(Trade.user_id == current_user.id)
    )
    trades = result.scalars().all()
    return [
        {
            "id": t.id,
            "instrument": t.instrument,
            "direction": t.direction.value if hasattr(t.direction, "value") else t.direction,
            "entry_price": t.entry_price,
            "stop_loss": t.stop_loss,
            "take_profit": t.take_profit,
            "quantity": t.quantity,
            "risk_amount": t.risk_amount,
            "is_paper": t.is_paper,
            "opened_at": t.opened_at,
        }
        for t in trades
    ]


@router.post("/trades/{trade_id}/close")
async def close_trade(
    trade_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ctx = user_trading_engine.get_context(current_user.id)
    if not ctx:
        raise HTTPException(status_code=404, detail="No trading context for user")
    trade = await ctx.paper.close_trade(trade_id, db)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    await db.commit()
    return {"message": "Trade closed", "trade_id": trade_id}


@router.post("/killswitch")
async def activate_kill_switch(
    current_user: User = Depends(get_current_user),
):
    """EMERGENCY: Halt trading for this user."""
    ctx = user_trading_engine.get_context(current_user.id)
    if ctx:
        ctx.deactivate()
    logger.critical(f"KILL SWITCH triggered by user {current_user.id}")
    return {"message": "Kill switch activated — trading halted", "kill_switch_active": True}
