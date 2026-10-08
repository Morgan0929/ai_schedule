"""Shared identity checks for user-owned API resources."""

import re

from fastapi import Depends, Header, Request

from common.exceptions import ForbiddenException, UnauthorizedException
from common.schemas.user import UserDTO
from common.utils.auth_session import get_login_session
from common.utils.jwt import decode_access_token


async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> UserDTO:
    if not authorization:
        raise UnauthorizedException("请先登录")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedException("请先登录")
    payload = decode_access_token(token.strip())
    if not payload or not payload.get("sid") or not payload.get("sub"):
        raise UnauthorizedException("登录已过期")
    session = await get_login_session(payload["sid"])
    if not session:
        raise UnauthorizedException("登录已过期")
    user = session.get("user") or {}
    if session.get("session_id") != payload["sid"] or str(user.get("id")) != str(payload["sub"]):
        raise UnauthorizedException("登录已失效")
    if not user.get("is_active", False):
        raise UnauthorizedException("账号已被禁用")
    return UserDTO.model_validate(user)


def check_requested_user_id(requested_user_id: int | None, user_id: int) -> None:
    """Legacy clients can send their own ID, but cannot select another user."""
    if requested_user_id is not None and requested_user_id != user_id:
        raise ForbiddenException("不能访问其他用户的数据")


async def get_authenticated_user_id(
    request: Request, user: UserDTO = Depends(get_current_user),
) -> int:
    # Check every occurrence, including duplicate query parameters.
    for value in request.query_params.getlist("user_id"):
        try:
            requested_user_id = int(value)
        except ValueError:
            raise ForbiddenException("用户 ID 与登录身份不匹配")
        check_requested_user_id(requested_user_id, user.id)
    return user.id


def scope_agent_session(session_id: str | None, user_id: int) -> str | None:
    """Bind client-selected conversation keys to the authenticated user."""
    if not session_id or not session_id.strip():
        return None
    cleaned = session_id.strip()
    prefix = f"u{user_id}:"
    if cleaned.startswith(prefix):
        return cleaned
    if re.match(r"^u\d+:", cleaned):
        raise ForbiddenException("不能访问其他用户的会话")
    return prefix + cleaned
