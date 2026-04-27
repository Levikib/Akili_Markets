from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.core.database import get_db
from app.models.trading import RiskEvent
from app.schemas.trading import RiskStatus, RiskSettingsUpdate
from app.services.risk.manager import risk_manager
from app.core.config import settings

router = APIRouter(prefix="/risk", tags=["Risk"])


@router.get("/status", response_model=RiskStatus)
async def get_risk_status():
    state = risk_manager.state
    return RiskStatus(
        is_paper_mode=True,  # from live_trader state
        daily_loss_pct=state["daily_loss_pct"],
        daily_loss_limit_pct=state["daily_loss_limit_pct"],
        drawdown_pct=state["drawdown_pct"],
        drawdown_limit_pct=state["drawdown_limit_pct"],
        open_positions=state["open_positions"],
        max_positions=state["max_positions"],
        all_strategies_paused=state["strategies_paused"],
        kill_switch_active=state["kill_switch_active"],
        peak_balance=state["peak_balance"],
        current_balance=state["account_balance"],
    )


@router.get("/events")
async def get_risk_events(limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RiskEvent).order_by(desc(RiskEvent.created_at)).limit(limit)
    )
    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "description": e.description,
            "account_balance_at_event": e.account_balance_at_event,
            "created_at": e.created_at,
        }
        for e in events
    ]


@router.put("/settings")
async def update_risk_settings(payload: RiskSettingsUpdate):
    updated = {}
    if payload.max_risk_per_trade_pct is not None:
        if payload.max_risk_per_trade_pct > risk_manager.ABS_MAX_RISK_PER_TRADE:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot exceed absolute ceiling of {risk_manager.ABS_MAX_RISK_PER_TRADE}%"
            )
        risk_manager._max_risk_pct = payload.max_risk_per_trade_pct
        updated["max_risk_per_trade_pct"] = payload.max_risk_per_trade_pct
    if payload.max_daily_loss_pct is not None:
        if payload.max_daily_loss_pct > risk_manager.ABS_MAX_DAILY_LOSS:
            raise HTTPException(status_code=400, detail=f"Cannot exceed {risk_manager.ABS_MAX_DAILY_LOSS}%")
        risk_manager._max_daily_loss_pct = payload.max_daily_loss_pct
        updated["max_daily_loss_pct"] = payload.max_daily_loss_pct
    if payload.max_drawdown_pct is not None:
        if payload.max_drawdown_pct > risk_manager.ABS_MAX_DRAWDOWN:
            raise HTTPException(status_code=400, detail=f"Cannot exceed {risk_manager.ABS_MAX_DRAWDOWN}%")
        risk_manager._max_drawdown_pct = payload.max_drawdown_pct
        updated["max_drawdown_pct"] = payload.max_drawdown_pct
    return {"updated": updated, "message": "Risk settings updated"}


@router.post("/resume")
async def resume_strategies():
    await risk_manager.resume_strategies()
    return {"message": "Strategies resumed (if kill switch is not active)"}
