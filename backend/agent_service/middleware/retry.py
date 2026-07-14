"""
Model Retry + Tool Retry — 指数退避 + Fallback

类似 Java Spring Retry:
  @Retryable(maxAttempts=3, backoff=@Backoff(delay=1000, multiplier=2))
"""
import asyncio
import logging
import functools
from typing import Any, Callable

logger = logging.getLogger(__name__)

RETRY_MAX = 3
RETRY_BASE_DELAY = 1.0  # 秒
RETRY_BACKOFF = 2.0      # 指数因子


# ============ Tool Retry ============

def with_retry(max_attempts: int = RETRY_MAX, base_delay: float = RETRY_BASE_DELAY):
    """
    工具函数重试装饰器 — 指数退避

    用法:
        @with_retry(max_attempts=3)
        async def query_weather(...): ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"Tool '{func.__name__}' attempt {attempt}/{max_attempts} "
                            f"failed: {e}. Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)
                        delay *= RETRY_BACKOFF
            logger.error(
                f"Tool '{func.__name__}' failed after {max_attempts} attempts: {last_error}"
            )
            return {"error": str(last_error), "retries_exhausted": True}
        return wrapper
    return decorator


# ============ Model Retry ============

async def model_retry(
    call_fn: Callable,
    max_attempts: int = RETRY_MAX,
    fallback_fn: Callable = None,
):
    """
    LLM 调用重试 — 超时/限流/JSON解析失败自动重试

    用法:
        result = await model_retry(
            lambda: llm.ainvoke(prompt),
            fallback_fn=lambda: mock_plan(user_input)
        )

    失败顺序: DeepSeek → 重试3次 → Fallback → Mock
    """
    delay = RETRY_BASE_DELAY
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await call_fn()
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # 可重试的错误类型
            retryable = any(kw in error_str for kw in [
                "timeout", "rate_limit", "too many requests",
                "server error", "service unavailable", "connection",
                "jsondecodeerror", "parse_error",
            ])
            if not retryable and attempt >= max_attempts:
                break
            if attempt < max_attempts:
                logger.warning(
                    f"LLM attempt {attempt}/{max_attempts} failed: {e}. Retry in {delay}s"
                )
                await asyncio.sleep(delay)
                delay *= RETRY_BACKOFF

    logger.error(f"LLM failed after {max_attempts} attempts: {last_error}")

    # Fallback
    if fallback_fn:
        logger.info("Using fallback model/mock")
        try:
            return await fallback_fn()
        except Exception as fe:
            logger.error(f"Fallback also failed: {fe}")

    return None
