from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.trading import BacktestResult, Strategy
from app.schemas.trading import BacktestRunRequest, BacktestResultResponse
from app.services.backtester import run_backtest
from loguru import logger

router = APIRouter(prefix="/backtest", tags=["Backtesting"])


@router.post("/run")
async def start_backtest(
    payload: BacktestRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    strategy = await db.get(Strategy, payload.strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Create placeholder result
    result = BacktestResult(
        strategy_id=payload.strategy_id,
        instrument=payload.instrument,
        timeframe=payload.timeframe,
        date_from=payload.date_from,
        date_to=payload.date_to,
        initial_capital=payload.initial_capital,
        final_capital=payload.initial_capital,  # will be updated
    )
    db.add(result)
    await db.flush()
    result_id = result.id

    background_tasks.add_task(
        run_backtest,
        backtest_id=result_id,
        strategy=strategy,
        instrument=payload.instrument,
        timeframe=payload.timeframe,
        date_from=payload.date_from,
        date_to=payload.date_to,
        initial_capital=payload.initial_capital,
    )

    return {"backtest_id": result_id, "message": "Backtest started in background", "status": "running"}


@router.get("/{backtest_id}", response_model=BacktestResultResponse)
async def get_backtest_result(backtest_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.get(BacktestResult, backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return result


@router.get("/{backtest_id}/trades")
async def get_backtest_trades(backtest_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.get(BacktestResult, backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest not found")
    # Return equity curve as trade approximation (full trade log stored in equity_curve JSONB)
    return {"backtest_id": backtest_id, "trades": result.equity_curve}


@router.post("/{backtest_id}/monte-carlo")
async def run_monte_carlo(backtest_id: str, simulations: int = 1000, db: AsyncSession = Depends(get_db)):
    import numpy as np
    result = await db.get(BacktestResult, backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest not found")

    if not result.equity_curve:
        raise HTTPException(status_code=400, detail="No equity curve data for Monte Carlo")

    # Extract trade PnLs from equity curve
    equity = [point.get("equity", 0) for point in result.equity_curve if isinstance(point, dict)]
    if len(equity) < 2:
        raise HTTPException(status_code=400, detail="Insufficient equity data")

    returns = np.diff(equity)
    mc_finals = []

    for _ in range(simulations):
        shuffled = np.random.permutation(returns)
        final = result.initial_capital + float(np.sum(shuffled))
        mc_finals.append(final)

    mc_finals = sorted(mc_finals)
    return {
        "simulations": simulations,
        "initial_capital": result.initial_capital,
        "median_final": round(float(np.median(mc_finals)), 2),
        "p10_final": round(float(np.percentile(mc_finals, 10)), 2),
        "p25_final": round(float(np.percentile(mc_finals, 25)), 2),
        "p75_final": round(float(np.percentile(mc_finals, 75)), 2),
        "p90_final": round(float(np.percentile(mc_finals, 90)), 2),
        "worst_case": round(float(mc_finals[0]), 2),
        "best_case": round(float(mc_finals[-1]), 2),
        "prob_profit": round(sum(1 for f in mc_finals if f > result.initial_capital) / simulations, 4),
    }
