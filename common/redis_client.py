"""
Redis 客户端
"""
import redis.asyncio as aioredis
from common.config import settings

# 全局 Redis 连接池
redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """获取 Redis 连接"""
    global redis_pool
    if redis_pool is None:
        redis_pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_pool


async def close_redis():
    """关闭 Redis 连接"""
    global redis_pool
    if redis_pool:
        await redis_pool.close()
        redis_pool = None
