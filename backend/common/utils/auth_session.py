"""Redis-backed login session helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from common.config import settings
from common.schemas.user import UserDTO


SESSION_KEY_PREFIX = "auth:session:"


def _session_key(session_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}{session_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def store_login_session(session_id: str, user: UserDTO) -> dict:
    """Persist a signed-in user in Redis for the configured TTL."""
    from common.redis_client import get_redis

    payload = {
        "session_id": session_id,
        "user": user.model_dump(mode="json"),
        "created_at": _now_iso(),
        "last_active_at": _now_iso(),
    }
    redis = await get_redis()
    await redis.setex(_session_key(session_id), settings.session_ttl_seconds, json.dumps(payload, ensure_ascii=False))
    return payload


async def get_login_session(session_id: str) -> dict | None:
    """Load a login session from Redis."""
    from common.redis_client import get_redis

    redis = await get_redis()
    raw = await redis.get(_session_key(session_id))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


async def touch_login_session(session_id: str) -> bool:
    """Refresh the session timestamp without changing the TTL window."""
    session = await get_login_session(session_id)
    if not session:
        return False
    session["last_active_at"] = _now_iso()
    from common.redis_client import get_redis

    redis = await get_redis()
    await redis.setex(_session_key(session_id), settings.session_ttl_seconds, json.dumps(session, ensure_ascii=False))
    return True


async def delete_login_session(session_id: str) -> bool:
    """Remove a login session from Redis."""
    from common.redis_client import get_redis

    redis = await get_redis()
    deleted = await redis.delete(_session_key(session_id))
    return bool(deleted)


async def resolve_login_session(session_id: str) -> dict | None:
    """Return the current session payload, or None if it is gone."""
    return await get_login_session(session_id)
