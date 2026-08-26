"""
JWT 认证
"""
import uuid
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from common.config import settings


def create_session_id() -> str:
    """Generate a Redis-backed login session id."""
    return uuid.uuid4().hex


def create_access_token(user_id: int, username: str, role: str, session_id: str) -> str:
    """生成 JWT access token"""
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "sid": session_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """解析 JWT token"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None
