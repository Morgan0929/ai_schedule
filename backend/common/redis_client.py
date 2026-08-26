"""
Redis 客户端
"""
from __future__ import annotations

import redis.asyncio as aioredis
from common.config import settings
from common.utils.circuit_breaker import get_circuit_breaker

# 全局 Redis 连接池
redis_pool: "RedisFacade | None" = None
_redis_client: aioredis.Redis | None = None


class RedisFacade:
    """Redis proxy with a shared circuit breaker."""

    def __init__(self, client: aioredis.Redis):
        self._client = client
        self._breaker = get_circuit_breaker(
            "redis",
            service_label="Redis",
            failure_threshold=3,
            recovery_timeout=30.0,
        )

    async def get(self, *args, **kwargs):
        return await self._breaker.call(self._client.get, *args, **kwargs)

    async def setex(self, *args, **kwargs):
        return await self._breaker.call(self._client.setex, *args, **kwargs)

    async def set(self, *args, **kwargs):
        return await self._breaker.call(self._client.set, *args, **kwargs)

    async def delete(self, *args, **kwargs):
        return await self._breaker.call(self._client.delete, *args, **kwargs)

    async def incr(self, *args, **kwargs):
        return await self._breaker.call(self._client.incr, *args, **kwargs)

    async def expire(self, *args, **kwargs):
        return await self._breaker.call(self._client.expire, *args, **kwargs)

    async def eval(self, *args, **kwargs):
        return await self._breaker.call(self._client.eval, *args, **kwargs)

    async def ping(self, *args, **kwargs):
        return await self._breaker.call(self._client.ping, *args, **kwargs)

    async def close(self):
        await self.aclose()

    async def aclose(self):
        close = getattr(self._client, "aclose", None)
        if close is not None:
            await close()
            return
        close = getattr(self._client, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result

    def __getattr__(self, item):
        return getattr(self._client, item)


async def get_redis() -> aioredis.Redis:
    """获取 Redis 连接"""
    global redis_pool, _redis_client
    if redis_pool is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            protocol=2,  # RESP2, 兼容旧版 Redis
        )
        redis_pool = RedisFacade(_redis_client)
    return redis_pool


async def close_redis():
    """关闭 Redis 连接"""
    global redis_pool, _redis_client
    if redis_pool:
        await redis_pool.aclose()
        redis_pool = None
        _redis_client = None
