"""LLM guardrails: timeout, concurrency, and soft rate limiting."""

from __future__ import annotations

import asyncio
import time

from common.exceptions import ServiceUnavailableException, BadRequestException
from common.redis_client import get_redis
from common.utils.circuit_breaker import get_circuit_breaker


class LLMConcurrencyLimiter:
    """Bound concurrent in-flight LLM calls locally."""

    def __init__(self, max_concurrent: int = 4):
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def acquire(self, timeout: float = 1.0) -> None:
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise ServiceUnavailableException("llm-concurrency") from exc

    def release(self) -> None:
        self._semaphore.release()


class LLMRateLimiter:
    """Simple Redis-backed token bucket per user/session."""

    def __init__(self, key_prefix: str = "agent:llm-rate", capacity: int = 12, window_seconds: int = 60):
        self.key_prefix = key_prefix
        self.capacity = capacity
        self.window_seconds = window_seconds

    async def allow(self, scope: str) -> None:
        redis = await get_redis()
        now = int(time.time())
        window_slot = now // self.window_seconds
        key = f"{self.key_prefix}:{scope}:{window_slot}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, self.window_seconds + 1)
        if count > self.capacity:
            raise ServiceUnavailableException("llm-rate-limit")


LLM_LIMITER = LLMConcurrencyLimiter()
LLM_RATE_LIMITER = LLMRateLimiter()


async def guarded_llm_call(scope: str, call_fn, *, timeout: float = 20.0, fallback_fn=None):
    """Execute an LLM call with concurrency, timeout, rate limit, and breaker guards."""
    await LLM_RATE_LIMITER.allow(scope)
    acquired = False
    breaker = get_circuit_breaker(
        "llm:deepseek",
        service_label="DeepSeek",
        failure_threshold=3,
        recovery_timeout=30.0,
    )
    try:
        await LLM_LIMITER.acquire()
        acquired = True

        async def _invoke():
            return await asyncio.wait_for(call_fn(), timeout=timeout)

        return await breaker.call(_invoke)
    except (asyncio.TimeoutError, ServiceUnavailableException) as exc:
        if fallback_fn:
            return await fallback_fn()
        raise ServiceUnavailableException("DeepSeek") from exc
    finally:
        if acquired:
            LLM_LIMITER.release()
