"""Async circuit breaker utilities."""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from common.exceptions import ServiceUnavailableException


@dataclass
class AsyncCircuitBreaker:
    """A small async circuit breaker with closed/open/half-open states."""

    name: str
    service_label: str | None = None
    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    _state: str = field(default="closed", init=False)
    _failure_count: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _probe_in_flight: bool = field(default=False, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def label(self) -> str:
        return self.service_label or self.name

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        await self._before_call()
        try:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            await self._after_failure()
            raise
        else:
            await self._after_success()
            return result

    async def _before_call(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._state == "open":
                if now - self._opened_at < self.recovery_timeout:
                    raise ServiceUnavailableException(self.label)
                self._state = "half_open"
                self._probe_in_flight = False

            if self._state == "half_open":
                if self._probe_in_flight:
                    raise ServiceUnavailableException(self.label)
                self._probe_in_flight = True

    async def _after_success(self) -> None:
        async with self._lock:
            self._state = "closed"
            self._failure_count = 0
            self._opened_at = 0.0
            self._probe_in_flight = False

    async def _after_failure(self) -> None:
        async with self._lock:
            self._probe_in_flight = False
            self._failure_count += 1
            if self._state == "half_open" or self._failure_count >= self.failure_threshold:
                self._state = "open"
                self._opened_at = time.monotonic()
                self._failure_count = self.failure_threshold


_BREAKERS: dict[str, AsyncCircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    *,
    service_label: str | None = None,
    failure_threshold: int = 3,
    recovery_timeout: float = 30.0,
) -> AsyncCircuitBreaker:
    """Return a shared breaker instance for the given name."""
    breaker = _BREAKERS.get(name)
    if breaker is None:
        breaker = AsyncCircuitBreaker(
            name=name,
            service_label=service_label,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        _BREAKERS[name] = breaker
    return breaker
