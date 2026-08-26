"""HTTP helpers protected by circuit breakers."""

from __future__ import annotations

from typing import Any

import httpx

from common.utils.circuit_breaker import get_circuit_breaker


async def request(
    service_name: str,
    method: str,
    url: str,
    *,
    timeout: float = 10.0,
    response_type: str = "json",
    **kwargs: Any,
) -> Any:
    """Perform an HTTP request behind a breaker and return a parsed response."""
    breaker = get_circuit_breaker(
        f"http:{service_name}",
        service_label=service_name,
        failure_threshold=3,
        recovery_timeout=30.0,
    )

    async def _send() -> httpx.Response:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response

    response = await breaker.call(_send)
    if response_type == "response":
        return response
    if response_type == "text":
        return response.text
    if response_type == "content":
        return response.content
    return response.json()


async def get_json(service_name: str, url: str, **kwargs: Any) -> Any:
    return await request(service_name, "GET", url, response_type="json", **kwargs)


async def get_text(service_name: str, url: str, **kwargs: Any) -> str:
    return await request(service_name, "GET", url, response_type="text", **kwargs)


async def get_response(service_name: str, url: str, **kwargs: Any) -> httpx.Response:
    return await request(service_name, "GET", url, response_type="response", **kwargs)
