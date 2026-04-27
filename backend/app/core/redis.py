import json
from typing import Any, Optional
import redis.asyncio as aioredis
from app.core.config import settings
from loguru import logger


_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=5,   # Upstash free tier limit
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


class RedisCache:
    TICK_PREFIX = "tick:"
    CANDLE_PREFIX = "candle:"
    SIGNAL_PREFIX = "signal:"
    RISK_PREFIX = "risk:"
    POSITION_PREFIX = "position:"

    def __init__(self, redis: aioredis.Redis):
        self.r = redis

    async def set_tick(self, instrument: str, tick: dict) -> None:
        key = f"{self.TICK_PREFIX}{instrument}"
        await self.r.setex(key, 60, json.dumps(tick))

    async def get_tick(self, instrument: str) -> Optional[dict]:
        key = f"{self.TICK_PREFIX}{instrument}"
        data = await self.r.get(key)
        return json.loads(data) if data else None

    async def push_candle(self, instrument: str, timeframe: str, candle: dict) -> None:
        key = f"{self.CANDLE_PREFIX}{instrument}:{timeframe}"
        pipe = self.r.pipeline()
        pipe.lpush(key, json.dumps(candle))
        pipe.ltrim(key, 0, 499)  # keep last 500 candles
        pipe.expire(key, 86400)
        await pipe.execute()

    async def get_candles(self, instrument: str, timeframe: str, count: int = 200) -> list[dict]:
        key = f"{self.CANDLE_PREFIX}{instrument}:{timeframe}"
        raw = await self.r.lrange(key, 0, count - 1)
        return [json.loads(c) for c in raw]

    async def set_risk_state(self, state: dict) -> None:
        await self.r.setex(f"{self.RISK_PREFIX}state", 300, json.dumps(state))

    async def get_risk_state(self) -> Optional[dict]:
        data = await self.r.get(f"{self.RISK_PREFIX}state")
        return json.loads(data) if data else None

    async def set_cooldown(self, instrument: str, minutes: int) -> None:
        key = f"{self.RISK_PREFIX}cooldown:{instrument}"
        await self.r.setex(key, minutes * 60, "1")

    async def is_on_cooldown(self, instrument: str) -> bool:
        key = f"{self.RISK_PREFIX}cooldown:{instrument}"
        return await self.r.exists(key) == 1

    async def publish_signal(self, channel: str, signal: dict) -> None:
        await self.r.publish(channel, json.dumps(signal))

    async def set_json(self, key: str, value: Any, ttl: int = 300) -> None:
        await self.r.setex(key, ttl, json.dumps(value))

    async def get_json(self, key: str) -> Optional[Any]:
        data = await self.r.get(key)
        return json.loads(data) if data else None
