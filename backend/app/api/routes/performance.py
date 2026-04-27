from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.database import get_db
from app.models.trading import Trade, TradeStatus, AccountSnapshot
from app.models.users import User
from app.api.routes.auth import get_current_user

router = APIRouter(prefix="/performance", tags=["Performance"])


@router.get("/summary")
async def get_performance_summary(
    is_paper: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Trade).where(
            and_(
                Trade.status == TradeStatus.CLOSED,
                Trade.is_paper == is_paper,
                Trade.user_id == current_user.id,
            )
        )
    )
    trades = result.scalars().all()
    if not trades:
        return {"message": "No closed trades yet", "total_trades": 0}

    pnls = [t.pnl for t in trades if t.pnl is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_rate = len(wins) / len(pnls) if pnls else 0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    expectancy = sum(pnls) / len(pnls) if pnls else 0
    total_return = sum(pnls)

    return {
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(win_rate, 4),
        "win_rate_pct": round(win_rate * 100, 2),
        "profit_factor": round(profit_factor, 3),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_pnl": round(total_return, 2),
        "expectancy": round(expectancy, 2),
        "best_trade": round(max(pnls), 2) if pnls else 0,
        "worst_trade": round(min(pnls), 2) if pnls else 0,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "is_paper": is_paper,
    }


@router.get("/daily")
async def get_daily_pnl(
    is_paper: bool = True,
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Trade).where(
            and_(
                Trade.status == TradeStatus.CLOSED,
                Trade.is_paper == is_paper,
                Trade.user_id == current_user.id,
            )
        ).order_by(Trade.closed_at)
    )
    trades = result.scalars().all()

    daily: dict = {}
    for t in trades:
        if t.closed_at and t.pnl is not None:
            day = t.closed_at.date().isoformat()
            if day not in daily:
                daily[day] = {"date": day, "pnl": 0, "trades": 0, "wins": 0}
            daily[day]["pnl"] += t.pnl
            daily[day]["trades"] += 1
            if t.pnl > 0:
                daily[day]["wins"] += 1

    return sorted(daily.values(), key=lambda x: x["date"])


@router.get("/by-strategy")
async def get_performance_by_strategy(
    is_paper: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Trade).where(
            and_(
                Trade.status == TradeStatus.CLOSED,
                Trade.is_paper == is_paper,
                Trade.user_id == current_user.id,
            )
        )
    )
    trades = result.scalars().all()

    by_strategy: dict = {}
    for t in trades:
        sid = t.strategy_id
        if sid not in by_strategy:
            by_strategy[sid] = {"strategy_id": sid, "trades": 0, "pnl": 0.0, "wins": 0}
        by_strategy[sid]["trades"] += 1
        if t.pnl:
            by_strategy[sid]["pnl"] += t.pnl
            if t.pnl > 0:
                by_strategy[sid]["wins"] += 1

    for s in by_strategy.values():
        if s["trades"] > 0:
            s["win_rate"] = round(s["wins"] / s["trades"], 4)
    return list(by_strategy.values())


@router.get("/by-instrument")
async def get_performance_by_instrument(
    is_paper: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Trade).where(
            and_(
                Trade.status == TradeStatus.CLOSED,
                Trade.is_paper == is_paper,
                Trade.user_id == current_user.id,
            )
        )
    )
    trades = result.scalars().all()
    by_instrument: dict = {}
    for t in trades:
        inst = t.instrument
        if inst not in by_instrument:
            by_instrument[inst] = {"instrument": inst, "trades": 0, "pnl": 0.0, "wins": 0}
        by_instrument[inst]["trades"] += 1
        if t.pnl:
            by_instrument[inst]["pnl"] += t.pnl
            if t.pnl > 0:
                by_instrument[inst]["wins"] += 1
    return sorted(by_instrument.values(), key=lambda x: x["pnl"], reverse=True)


@router.get("/drawdown")
async def get_drawdown_analysis(
    is_paper: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AccountSnapshot)
        .where(AccountSnapshot.user_id == current_user.id)
        .order_by(AccountSnapshot.recorded_at)
    )
    snapshots = result.scalars().all()
    if not snapshots:
        return {"message": "No snapshots yet"}

    equity = [s.equity for s in snapshots]
    peak = equity[0]
    max_dd = 0.0
    dd_series = []
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd:
            max_dd = dd
        dd_series.append(dd)

    return {
        "max_drawdown_pct": round(max_dd, 2),
        "current_drawdown_pct": round(dd_series[-1], 2) if dd_series else 0,
        "drawdown_series": [round(d, 2) for d in dd_series],
        "snapshot_count": len(snapshots),
    }
