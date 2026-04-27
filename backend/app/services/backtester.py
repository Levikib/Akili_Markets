"""
Event-driven backtester — replays historical candle data and executes
strategy logic as if it were live, recording every trade.
"""
import numpy as np
from datetime import datetime
from typing import Optional
from loguru import logger

from app.services.deriv.client import deriv_client
from app.services.analysis.signals import generate_signal
from app.services.analysis.indicators import CandleData
from app.models.trading import Strategy, BacktestResult, Timeframe
from app.core.database import AsyncSessionLocal


TIMEFRAME_GRANULARITY = {
    "M1": 60, "M5": 300, "M15": 900,
    "H1": 3600, "H4": 14400, "D1": 86400,
}


async def run_backtest(
    backtest_id: str,
    strategy: Strategy,
    instrument: str,
    timeframe: str,
    date_from: datetime,
    date_to: datetime,
    initial_capital: float,
) -> None:
    logger.info(f"Backtest [{backtest_id}] starting: {strategy.type} on {instrument} {timeframe}")
    async with AsyncSessionLocal() as db:
        try:
            result = await db.get(BacktestResult, backtest_id)
            if not result:
                return

            granularity = TIMEFRAME_GRANULARITY.get(timeframe, 300)
            candles = await deriv_client.get_candle_history(
                symbol=instrument,
                granularity=granularity,
                count=5000,
            )

            if len(candles) < 50:
                logger.warning(f"Backtest [{backtest_id}]: insufficient candles ({len(candles)})")
                return

            metrics = _run_simulation(
                candles=candles,
                strategy_type=strategy.type.value,
                instrument=instrument,
                timeframe=timeframe,
                initial_capital=initial_capital,
                confidence_threshold=float(strategy.parameters.get("confidence_threshold", 60.0)),
            )

            result.final_capital = metrics["final_capital"]
            result.total_trades = metrics["total_trades"]
            result.winning_trades = metrics["winning_trades"]
            result.win_rate = metrics["win_rate"]
            result.profit_factor = metrics["profit_factor"]
            result.sharpe_ratio = metrics["sharpe_ratio"]
            result.sortino_ratio = metrics["sortino_ratio"]
            result.max_drawdown_pct = metrics["max_drawdown_pct"]
            result.total_return_pct = metrics["total_return_pct"]
            result.expectancy = metrics["expectancy"]
            result.equity_curve = metrics["equity_curve"]

            await db.merge(result)
            await db.commit()
            logger.success(f"Backtest [{backtest_id}] complete — Return: {metrics['total_return_pct']:.2f}% | Win rate: {metrics['win_rate']*100:.1f}%")
        except Exception as e:
            logger.error(f"Backtest [{backtest_id}] failed: {e}")
            await db.rollback()


def _run_simulation(
    candles: list[dict],
    strategy_type: str,
    instrument: str,
    timeframe: str,
    initial_capital: float,
    confidence_threshold: float,
) -> dict:
    capital = initial_capital
    peak = initial_capital
    max_dd = 0.0
    trades = []
    equity_curve = [{"i": 0, "equity": capital, "timestamp": candles[0].get("epoch", 0)}]

    open_trade = None
    warmup = 50  # need enough bars for indicators

    for i in range(warmup, len(candles)):
        window = candles[:i + 1]
        data = CandleData.from_candles(window)

        current_candle = candles[i]
        current_price = float(current_candle["close"])

        # Check open trade first
        if open_trade:
            sl = open_trade["sl"]
            tp = open_trade["tp"]
            direction = open_trade["direction"]
            entry = open_trade["entry"]
            risk = open_trade["risk"]

            hit_sl = (direction == "BUY" and current_price <= sl) or \
                     (direction == "SELL" and current_price >= sl)
            hit_tp = tp and ((direction == "BUY" and current_price >= tp) or
                             (direction == "SELL" and current_price <= tp))

            if hit_sl or hit_tp:
                exit_price = sl if hit_sl else tp
                if direction == "BUY":
                    pnl = (exit_price - entry) / entry * risk * (capital / initial_capital)
                else:
                    pnl = (entry - exit_price) / entry * risk * (capital / initial_capital)

                capital += pnl
                if capital > peak:
                    peak = capital
                dd = (peak - capital) / peak * 100
                if dd > max_dd:
                    max_dd = dd

                trades.append({
                    "entry": entry,
                    "exit": exit_price,
                    "direction": direction,
                    "pnl": round(pnl, 4),
                    "was_sl": hit_sl,
                    "bar": i,
                    "equity": round(capital, 4),
                    "timestamp": current_candle.get("epoch", 0),
                })
                equity_curve.append({"i": i, "equity": round(capital, 4), "timestamp": current_candle.get("epoch", 0)})
                open_trade = None

        # Generate new signal if no open trade
        if not open_trade:
            signal = generate_signal(strategy_type, data, instrument, timeframe, confidence_threshold)
            if signal and signal.suggested_stop_loss and signal.suggested_take_profit:
                open_trade = {
                    "direction": signal.direction.value,
                    "entry": current_price,
                    "sl": signal.suggested_stop_loss,
                    "tp": signal.suggested_take_profit,
                    "risk": capital * 0.015,  # 1.5% risk
                }

    # Compute metrics
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_rate = len(wins) / len(pnls) if pnls else 0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    expectancy = sum(pnls) / len(pnls) if pnls else 0
    total_return_pct = (capital - initial_capital) / initial_capital * 100

    # Sharpe ratio (simplified, using daily-equivalent returns)
    if len(pnls) > 1:
        returns_arr = np.array(pnls)
        sharpe = float(np.mean(returns_arr) / np.std(returns_arr)) * np.sqrt(252) if np.std(returns_arr) > 0 else 0
        neg_returns = returns_arr[returns_arr < 0]
        sortino_denom = np.std(neg_returns) if len(neg_returns) > 0 else 1
        sortino = float(np.mean(returns_arr) / sortino_denom) * np.sqrt(252)
    else:
        sharpe = 0
        sortino = 0

    return {
        "final_capital": round(capital, 2),
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 3),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "max_drawdown_pct": round(max_dd, 2),
        "total_return_pct": round(total_return_pct, 2),
        "expectancy": round(expectancy, 4),
        "equity_curve": equity_curve,
    }
