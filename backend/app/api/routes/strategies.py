from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.core.database import get_db
from app.models.trading import Strategy, Trade
from app.schemas.trading import StrategyCreate, StrategyUpdate, StrategyResponse, SignalResponse
from loguru import logger

router = APIRouter(prefix="/strategies", tags=["Strategies"])


@router.get("", response_model=List[StrategyResponse])
async def list_strategies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Strategy).order_by(Strategy.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(payload: StrategyCreate, db: AsyncSession = Depends(get_db)):
    strategy = Strategy(**payload.model_dump())
    db.add(strategy)
    await db.flush()
    await db.refresh(strategy)
    logger.info(f"Strategy created: {strategy.name} [{strategy.type}]")
    return strategy


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: str, db: AsyncSession = Depends(get_db)):
    strategy = await db.get(Strategy, strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(strategy_id: str, payload: StrategyUpdate, db: AsyncSession = Depends(get_db)):
    strategy = await db.get(Strategy, strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(strategy, field, value)
    await db.flush()
    await db.refresh(strategy)
    return strategy


@router.post("/{strategy_id}/activate", response_model=StrategyResponse)
async def activate_strategy(strategy_id: str, db: AsyncSession = Depends(get_db)):
    strategy = await db.get(Strategy, strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if not strategy.is_paper:
        raise HTTPException(status_code=400, detail="Only paper strategies can be activated via API. Live requires qualification.")
    strategy.is_active = True
    await db.flush()
    await db.refresh(strategy)
    logger.info(f"Strategy activated: {strategy.name}")
    return strategy


@router.post("/{strategy_id}/deactivate", response_model=StrategyResponse)
async def deactivate_strategy(strategy_id: str, db: AsyncSession = Depends(get_db)):
    strategy = await db.get(Strategy, strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    strategy.is_active = False
    await db.flush()
    await db.refresh(strategy)
    return strategy


@router.get("/{strategy_id}/signals")
async def get_strategy_signals(strategy_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    strategy = await db.get(Strategy, strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    result = await db.execute(
        select(Trade)
        .where(Trade.strategy_id == strategy_id)
        .order_by(Trade.opened_at.desc())
        .limit(limit)
    )
    trades = result.scalars().all()
    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy.name,
        "signals": [
            {
                "id": t.id,
                "direction": t.direction,
                "confidence": t.confidence_score,
                "reason": t.signal_reason,
                "indicators": t.entry_indicators,
                "timestamp": t.opened_at,
                "outcome": t.status,
                "pnl": t.pnl,
            }
            for t in trades
        ],
    }
