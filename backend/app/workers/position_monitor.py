"""
Position monitor — runs every 5 seconds, checks all open positions
against current prices, triggers SL/TP closes.
"""
import asyncio
from loguru import logger

from app.services.binance.market_data import binance_market_data
from app.services.execution.user_trading_engine import user_trading_engine


class PositionMonitor:
    def __init__(self):
        self._running = False

    async def start(self) -> None:
        self._running = True
        asyncio.create_task(self._monitor_loop())
        logger.info("Position monitor started")

    async def stop(self) -> None:
        self._running = False

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                await self._check_positions()
            except Exception as e:
                logger.error(f"Position monitor error: {e}")
            await asyncio.sleep(5)

    async def _check_positions(self) -> None:
        all_trades = user_trading_engine.get_all_open_trades()
        if not all_trades:
            return

        # Collect all instruments across all users
        instruments = {
            trade.instrument
            for trades in all_trades.values()
            for trade in trades
        }
        if not instruments:
            return

        current_prices: dict[str, float] = {}
        for inst in instruments:
            try:
                tick = await binance_market_data.get_latest_tick(inst)
                if tick:
                    current_prices[inst] = float(tick.get("price", tick.get("quote", 0)))
            except Exception as e:
                logger.debug(f"Price fetch failed for {inst}: {e}")

        if current_prices:
            try:
                await user_trading_engine.check_stops_for_all(current_prices)
            except Exception as e:
                logger.error(f"Stop check error: {e}")


position_monitor = PositionMonitor()
