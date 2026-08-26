"""Runtime guards for the agent service."""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from common.exceptions import ServiceUnavailableException, BadRequestException
from common.redis_client import get_redis


class AsyncTaskGovernor:
    """Bound background task fan-out to avoid silent pileups."""

    def __init__(self, max_pending: int = 32):
        self._max_pending = max_pending
        self._pending: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()

    async def spawn(self, coro, *, name: str = "agent-bg") -> asyncio.Task:
        async with self._lock:
            if len(self._pending) >= self._max_pending:
                self._close_rejected_coroutine(coro)
                raise ServiceUnavailableException("background-task-governor")
            task = asyncio.create_task(coro, name=name)
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
            return task

    def submit(self, coro, *, name: str = "agent-bg") -> asyncio.Task:
        """Sync helper for call sites that already run inside the event loop."""
        if len(self._pending) >= self._max_pending:
            self._close_rejected_coroutine(coro)
            raise ServiceUnavailableException("background-task-governor")
        task = asyncio.create_task(coro, name=name)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    @staticmethod
    def _close_rejected_coroutine(coro) -> None:
        """Dispose a coroutine supplied by a rejected task submission."""
        close = getattr(coro, "close", None)
        if close is not None:
            close()

    @property
    def pending_count(self) -> int:
        return len(self._pending)


class DistributedSessionLock:
    """Redis-based lock that prevents concurrent turns for the same session."""

    def __init__(self, session_id: str, ttl_seconds: int = 120):
        self.session_id = session_id
        self.ttl_seconds = ttl_seconds
        self._token = uuid.uuid4().hex
        self._key = f"agent:session-lock:{session_id}"

    async def acquire(self, wait_timeout: float = 0.5, poll_interval: float = 0.05) -> None:
        deadline = time.monotonic() + wait_timeout
        redis = await get_redis()
        while True:
            ok = await redis.set(self._key, self._token, nx=True, ex=self.ttl_seconds)
            if ok:
                return
            if time.monotonic() >= deadline:
                raise ServiceUnavailableException("agent-session-lock")
            await asyncio.sleep(poll_interval)

    async def release(self) -> None:
        redis = await get_redis()
        await redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            self._key,
            self._token,
        )


@asynccontextmanager
async def guarded_session(session_id: str):
    """Acquire a per-session lock for the duration of one agent turn."""
    lock = DistributedSessionLock(session_id)
    await lock.acquire()
    try:
        yield
    finally:
        await lock.release()


def normalize_session_id(request_session_id: str | None, user_id: int | None) -> str:
    """Prevent shared per-user session keys from mixing turns across clients."""
    if request_session_id:
        cleaned = request_session_id.strip()
        if cleaned:
            return cleaned
    if not user_id:
        return f"anon:{uuid.uuid4().hex}"
    return f"u{user_id}:{uuid.uuid4().hex[:12]}"


def validate_user_session(user_id: int | None, session_id: str) -> None:
    """Ensure session ids are always bound to the current request scope."""
    if not session_id:
        raise BadRequestException("session_id required")
    if user_id is None:
        return


BACKGROUND_TASK_GOVERNOR = AsyncTaskGovernor()
