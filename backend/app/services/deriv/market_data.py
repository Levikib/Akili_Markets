"""
Market data service — manages tick/candle streams, caches to Redis,
and provides a clean interface for strategies to consume market data.
"""
import asyncio
from typing import Callable, Optional
from loguru import logger

from app.services.deriv.client import deriv_client
from app.core.redis import RedisCache, get_redis


TIMEFRAME_GRANULARITY = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}

INSTRUMENTS = {
    # Synthetic Indices
    "R_75": "Volatility 75 Index",
    "R_25": "Volatility 25 Index",
    "R_50": "Volatility 50 Index",
    "R_100": "Volatility 100 Index",
    "CRASH300N": "Crash 300 Index",
    "CRASH500": "Crash 500 Index",
    "CRASH1000": "Crash 1000 Index",
    "BOOM300N": "Boom 300 Index",
    "BOOM500": "Boom 500 Index",
    "BOOM1000": "Boom 1000 Index",
    "stpRNG": "Step Index",
    "JD25": "Jump 25 Index",
    "JD50": "Jump 50 Index",
    "JD75": "Jump 75 Index",
    # Forex
    "frxEURUSD": "EUR/USD",
    "frxGBPUSD": "GBP/USD",
    "frxUSDJPY": "USD/JPY",
    "frxAUDUSD": "AUD/USD",
    "frxUSDCHF": "USD/CHF",
}


class MarketDataService:
    def __init__(self):
        self._tick_subscribers: dict[str, list[Callable]] = {}
        self._candle_subscribers: dict[str, list[Callable]] = {}
        self._active_tick_subs: set[str] = set()
        self._active_candle_subs: set[str] = set()
        self._cache: Optional[RedisCache] = None

    async def init(self) -> None:
        redis = await get_redis()
        self._cache = RedisCache(redis)

    async def subscribe_ticks(self, symbol: str, callback: Callable) -> None:
        if symbol not in self._tick_subscribers:
            self._tick_subscribers[symbol] = []
        self._tick_subscribers[symbol].append(callback)

        if symbol not in self._active_tick_subs:
            self._active_tick_subs.add(symbol)
            await deriv_client.subscribe_ticks(symbol, self._on_tick(symbol))
            logger.info(f"Tick subscription active: {symbol}")

    async def subscribe_candles(self, symbol: str, timeframe: str, callback: Callable) -> None:
        key = f"{symbol}:{timeframe}"
        if key not in self._candle_subscribers:
            self._candle_subscribers[key] = []
        self._candle_subscribers[key].append(callback)

        if key not in self._active_candle_subs:
            self._active_candle_subs.add(key)
            granularity = TIMEFRAME_GRANULARITY[timeframe]
            await deriv_client.subscribe_candles(symbol, granularity, self._on_candle(symbol, timeframe))
            logger.info(f"Candle subscription active: {symbol} {timeframe}")

    def _on_tick(self, symbol: str) -> Callable:
        async def handler(tick: dict) -> None:
            if self._cache:
                await self._cache.set_tick(symbol, tick)
            for cb in self._tick_subscribers.get(symbol, []):
                asyncio.create_task(cb(tick))
        return handler

    def _on_candle(self, symbol: str, timeframe: str) -> Callable:
        async def handler(candle: dict) -> None:
            if self._cache:
                await self._cache.push_candle(symbol, timeframe, candle)
            key = f"{symbol}:{timeframe}"
            for cb in self._candle_subscribers.get(key, []):
                asyncio.create_task(cb(candle))
        return handler

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
        from_cache: bool = True,
    ) -> list[dict]:
        if from_cache and self._cache:
            cached = await self._cache.get_candles(symbol, timeframe, count)
            if len(cached) >= count:
                return list(reversed(cached))  # oldest first

        granularity = TIMEFRAME_GRANULARITY[timeframe]
        return await deriv_client.get_candle_history(symbol, granularity, count)

    async def get_latest_tick(self, symbol: str) -> Optional[dict]:
        if self._cache:
            return await self._cache.get_tick(symbol)
        return None


market_data = MarketDataService()
