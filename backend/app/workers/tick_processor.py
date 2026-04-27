"""
Tick processor — receives live ticks, builds candle windows,
runs all active strategies, and emits signals.
"""
import asyncio
from typing import Optional
from loguru import logger
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.trading import Strategy
from app.services.analysis.signals import generate_signal
from app.services.analysis.indicators import CandleData
from app.services.binance.market_data import binance_market_data
from app.services.execution.user_trading_engine import user_trading_engine
from app.core.redis import RedisCache, get_redis


class TickProcessor:
    def __init__(self):
        self._running = False
        self._cache: Optional[RedisCache] = None

    async def start(self) -> None:
        self._running = True
        try:
            redis = await get_redis()
            self._cache = RedisCache(redis)
        except Exception as e:
            logger.warning(f"Redis unavailable at startup — signals won't be cached: {e}")
        logger.info("Tick processor started")

    async def stop(self) -> None:
        self._running = False

    async def process_strategies(self) -> None:
        """Called on a schedule — runs all active strategies against latest candles."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.is_active == True)
            )
            strategies = result.scalars().all()

            for strategy in strategies:
                try:
                    await self._process_strategy(strategy, db)
                except Exception as e:
                    logger.error(f"Strategy processing error [{strategy.name}]: {e}")

    async def _process_strategy(self, strategy: Strategy, db) -> None:
        try:
            candles = await binance_market_data.get_candles(
                symbol=strategy.instrument,
                timeframe=strategy.timeframe.value,
                count=200,
            )
        except Exception as e:
            logger.debug(f"Could not fetch candles for {strategy.instrument}: {e}")
            return

        if len(candles) < 50:
            return

        data = CandleData.from_candles(candles)
        confidence_threshold = float(strategy.parameters.get("confidence_threshold", 60.0))

        signal = generate_signal(
            strategy_type=strategy.type.value,
            data=data,
            instrument=strategy.instrument,
            timeframe=strategy.timeframe.value,
            confidence_threshold=confidence_threshold,
        )

        if signal:
            logger.info(
                f"Signal [{strategy.name}]: {signal.direction.value} {signal.instrument} "
                f"| Confidence: {signal.confidence:.0f} | {signal.reason[:80]}..."
            )

            if self._cache:
                try:
                    await self._cache.publish_signal(
                        "signals",
                        {
                            "strategy_id": strategy.id,
                            "strategy_name": strategy.name,
                            "direction": signal.direction.value,
                            "instrument": signal.instrument,
                            "confidence": signal.confidence,
                            "reason": signal.reason,
                            "indicators": {k: round(v, 5) if isinstance(v, float) else v
                                           for k, v in signal.indicators.items()},
                        }
                    )
                except Exception as e:
                    logger.debug(f"Redis publish skipped: {e}")

            # Run signal through every active user's paper trader
            try:
                await user_trading_engine.execute_signal_for_all(signal, strategy.id)
            except Exception as e:
                logger.error(f"User engine signal error: {e}")


tick_processor = TickProcessor()
