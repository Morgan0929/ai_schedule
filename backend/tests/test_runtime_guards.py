import asyncio
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_service.utils import runtime
from common.exceptions import ServiceUnavailableException
from common.utils import circuit_breaker, llm_guard


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expirations = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = time.time() + ex
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        existed = key in self.values
        self.values.pop(key, None)
        self.expirations.pop(key, None)
        return 1 if existed else 0

    async def incr(self, key):
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = value
        return value

    async def expire(self, key, seconds):
        self.expirations[key] = time.time() + seconds
        return True

    async def eval(self, script, numkeys, key, token):
        if self.values.get(key) == token:
            await self.delete(key)
            return 1
        return 0


class RuntimeGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_lock_rejects_concurrent_turns_and_releases(self):
        redis = FakeRedis()

        async def fake_get_redis():
            return redis

        with patch.object(runtime, "get_redis", fake_get_redis):
            first = runtime.DistributedSessionLock("session-a", ttl_seconds=5)
            second = runtime.DistributedSessionLock("session-a", ttl_seconds=5)

            await first.acquire(wait_timeout=0.01, poll_interval=0.001)
            with self.assertRaises(ServiceUnavailableException) as ctx:
                await second.acquire(wait_timeout=0.01, poll_interval=0.001)
            self.assertEqual(ctx.exception.code, 503)

            await first.release()
            await second.acquire(wait_timeout=0.01, poll_interval=0.001)
            await second.release()

    async def test_session_lock_release_is_token_scoped(self):
        redis = FakeRedis()

        async def fake_get_redis():
            return redis

        with patch.object(runtime, "get_redis", fake_get_redis):
            owner = runtime.DistributedSessionLock("session-b", ttl_seconds=5)
            intruder = runtime.DistributedSessionLock("session-b", ttl_seconds=5)

            await owner.acquire(wait_timeout=0.01, poll_interval=0.001)
            await intruder.release()

            blocked = runtime.DistributedSessionLock("session-b", ttl_seconds=5)
            with self.assertRaises(ServiceUnavailableException):
                await blocked.acquire(wait_timeout=0.01, poll_interval=0.001)

            await owner.release()

    async def test_session_lock_burst_has_single_active_owner(self):
        redis = FakeRedis()
        active = 0
        max_active = 0
        completed = 0
        state_lock = asyncio.Lock()

        async def fake_get_redis():
            return redis

        async def worker():
            nonlocal active, max_active, completed
            lock = runtime.DistributedSessionLock("burst-session", ttl_seconds=5)
            await lock.acquire(wait_timeout=10.0, poll_interval=0.001)
            try:
                async with state_lock:
                    active += 1
                    max_active = max(max_active, active)
                await asyncio.sleep(0.002)
                async with state_lock:
                    active -= 1
                    completed += 1
            finally:
                await lock.release()

        with patch.object(runtime, "get_redis", fake_get_redis):
            await asyncio.gather(*(worker() for _ in range(20)))

        self.assertEqual(completed, 20)
        self.assertEqual(max_active, 1)

    async def test_background_governor_caps_pending_tasks(self):
        governor = runtime.AsyncTaskGovernor(max_pending=1)
        gate = asyncio.Event()

        async def wait_forever():
            await gate.wait()

        first = await governor.spawn(wait_forever(), name="first")
        self.assertEqual(governor.pending_count, 1)

        with self.assertRaises(ServiceUnavailableException) as ctx:
            await governor.spawn(wait_forever(), name="second")
        self.assertEqual(ctx.exception.code, 503)

        gate.set()
        await first

    async def test_llm_rate_limiter_enforces_window_capacity(self):
        redis = FakeRedis()

        async def fake_get_redis():
            return redis

        limiter = llm_guard.LLMRateLimiter(capacity=2, window_seconds=60)
        with patch.object(llm_guard, "get_redis", fake_get_redis):
            await limiter.allow("user-1")
            await limiter.allow("user-1")
            with self.assertRaises(ServiceUnavailableException) as ctx:
                await limiter.allow("user-1")
            self.assertEqual(ctx.exception.code, 503)

    async def test_llm_rate_limiter_burst_only_allows_capacity(self):
        redis = FakeRedis()

        async def fake_get_redis():
            return redis

        limiter = llm_guard.LLMRateLimiter(capacity=5, window_seconds=60)

        async def attempt():
            try:
                await limiter.allow("burst-user")
                return True
            except ServiceUnavailableException:
                return False

        with patch.object(llm_guard, "get_redis", fake_get_redis):
            results = await asyncio.gather(*(attempt() for _ in range(20)))

        self.assertEqual(sum(results), 5)

    async def test_guarded_llm_call_uses_fallback_on_timeout(self):
        redis = FakeRedis()

        async def fake_get_redis():
            return redis

        async def slow_call():
            await asyncio.sleep(0.05)
            return "slow"

        async def fallback():
            return "fallback"

        circuit_breaker._BREAKERS.pop("llm:deepseek", None)
        with patch.object(llm_guard, "get_redis", fake_get_redis), patch.object(
            llm_guard, "LLM_LIMITER", llm_guard.LLMConcurrencyLimiter(max_concurrent=1)
        ):
            result = await llm_guard.guarded_llm_call(
                "timeout-scope",
                slow_call,
                timeout=0.001,
                fallback_fn=fallback,
            )

        self.assertEqual(result, "fallback")

    async def test_guarded_llm_call_propagates_rate_limit(self):
        redis = FakeRedis()

        async def fake_get_redis():
            return redis

        async def fast_call():
            return "ok"

        rate_limiter = llm_guard.LLMRateLimiter(capacity=1, window_seconds=60)
        circuit_breaker._BREAKERS.pop("llm:deepseek", None)
        with patch.object(llm_guard, "get_redis", fake_get_redis), patch.object(
            llm_guard, "LLM_RATE_LIMITER", rate_limiter
        ), patch.object(llm_guard, "LLM_LIMITER", llm_guard.LLMConcurrencyLimiter(max_concurrent=1)):
            self.assertEqual(await llm_guard.guarded_llm_call("limited", fast_call), "ok")
            with self.assertRaises(ServiceUnavailableException) as ctx:
                await llm_guard.guarded_llm_call("limited", fast_call)
            self.assertEqual(ctx.exception.code, 503)


class SessionIdTests(unittest.TestCase):
    def test_normalize_session_id_uses_request_session(self):
        self.assertEqual(runtime.normalize_session_id("  client-session  ", 7), "client-session")

    def test_normalize_session_id_does_not_reuse_user_active_key(self):
        first = runtime.normalize_session_id(None, 7)
        second = runtime.normalize_session_id(None, 7)

        self.assertTrue(first.startswith("u7:"))
        self.assertTrue(second.startswith("u7:"))
        self.assertNotEqual(first, "u7:active")
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
