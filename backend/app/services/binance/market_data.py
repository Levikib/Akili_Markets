"""
Binance market data service — manages tick/candle streams,
caches to Redis, provides same interface as Deriv market data.
Drop-in replacement — strategies consume identical CandleData format.
"""
import asyncio
from typing import Callable, Optional
from loguru import logger

from app.services.binance.client import binance_client, BINANCE_INSTRUMENTS, TIMEFRAME_MAP
from app.core.redis import RedisCache, get_redis


class BinanceMarketData:
    def __init__(self):
        self._cache: Optional[RedisCache] = None
        self._tick_subs: set[str] = set()
        self._candle_subs: set[str] = set()

    async def init(self) -> None:
        redis = await get_redis()
        self._cache = RedisCache(redis)
        logger.info("Binance market data service initialized")

    async def subscribe_ticks(self, symbol: str, callback: Callable) -> None:
        async def on_tick(tick: dict) -> None:
            if self._cache:
                await self._cache.set_tick(symbol, tick)
            result = callback(tick)
            if asyncio.iscoroutine(result):
                await result

        if symbol not in self._tick_subs:
            self._tick_subs.add(symbol)
            await binance_client.subscribe_ticks(symbol, on_tick)

    async def subscribe_candles(self, symbol: str, timeframe: str, callback: Callable) -> None:
        async def on_candle(candle: dict) -> None:
            if self._cache:
                await self._cache.push_candle(symbol, timeframe, candle)
            result = callback(candle)
            if asyncio.iscoroutine(result):
                await result

        key = f"{symbol}:{timeframe}"
        if key not in self._candle_subs:
            self._candle_subs.add(key)
            await binance_client.subscribe_candles(symbol, timeframe, on_candle)

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
                return list(reversed(cached))
        return await binance_client.get_candle_history(symbol, timeframe, count)

    async def get_latest_tick(self, symbol: str) -> Optional[dict]:
        if self._cache:
            tick = await self._cache.get_tick(symbol)
            if tick:
                return tick
        ticker = await binance_client.get_ticker(symbol)
        return {"quote": ticker["price"], "symbol": symbol, "epoch": ticker["epoch"]}


binance_market_data = BinanceMarketData()
