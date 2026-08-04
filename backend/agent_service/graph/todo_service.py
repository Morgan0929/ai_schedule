"""
Todo Service — 待办队列

规则:
  - 最多5个ACTIVE, 超出→最旧的ARCHIVED
  - 提醒一次后 remind_count+=1, 不再主动提醒
  - 用户主动查看才显示
"""
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

MAX_ACTIVE = 5


async def _get_conn():
    import asyncpg
    from common.config import Settings
    s = Settings()
    return await asyncpg.connect(
        host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
        user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD,
        database=s.POSTGRES_DB, timeout=5,
    )


async def create_todo(user_id: int, title: str, note: str = "",
                      priority: str = "MEDIUM") -> dict:
    """创建待办, 超出5个则归档最旧的"""
    conn = await _get_conn()
    try:
        # FIFO: 超5个时归档最旧的
        active_count = await conn.fetchval(
            "SELECT count(*) FROM todo_queue WHERE user_id=$1 AND status='ACTIVE'", user_id)
        if active_count >= MAX_ACTIVE:
            oldest = await conn.fetchval(
                "UPDATE todo_queue SET status='ARCHIVED' WHERE id = ("
                "SELECT id FROM todo_queue WHERE user_id=$1 AND status='ACTIVE' "
                "ORDER BY created_at ASC LIMIT 1) RETURNING title", user_id)
            logger.info(f"Todo FIFO: archived '{oldest}'")

        row = await conn.fetchrow(
            "INSERT INTO todo_queue (user_id, title, note, priority) "
            "VALUES ($1,$2,$3,$4) RETURNING id, title, status",
            user_id, title, note, priority)
        return {"id": row["id"], "title": row["title"], "status": row["status"]}
    finally:
        await conn.close()


async def list_todos(user_id: int, status: str = "ACTIVE") -> list[dict]:
    """查看待办"""
    conn = await _get_conn()
    try:
        rows = await conn.fetch(
            "SELECT id, title, note, priority, status, remind_count, created_at "
            "FROM todo_queue WHERE user_id=$1 AND status=$2 "
            "ORDER BY created_at DESC LIMIT 10",
            user_id, status)
        return [{"id": r["id"], "title": r["title"], "note": r["note"],
                 "priority": r["priority"], "status": r["status"],
                 "remind_count": r["remind_count"],
                 "created_at": str(r["created_at"])[:10]}
                for r in rows]
    finally:
        await conn.close()


async def complete_todo(user_id: int, todo_id: int = None, title: str = None) -> dict:
    """完成待办"""
    conn = await _get_conn()
    try:
        if todo_id:
            await conn.execute(
                "UPDATE todo_queue SET status='DONE', updated_at=NOW() WHERE id=$1 AND user_id=$2",
                todo_id, user_id)
        elif title:
            await conn.execute(
                "UPDATE todo_queue SET status='DONE', updated_at=NOW() "
                "WHERE title ILIKE $1 AND user_id=$2 AND status='ACTIVE'",
                f"%{title}%", user_id)
        return {"status": "done"}
    finally:
        await conn.close()


async def remind_once(user_id: int) -> list[dict]:
    """返回需要提醒一次且未超过上限的待办"""
    conn = await _get_conn()
    try:
        rows = await conn.fetch(
            "SELECT id, title FROM todo_queue "
            "WHERE user_id=$1 AND status='ACTIVE' AND remind_count < max_remind",
            user_id)
        # 标记已提醒
        for r in rows:
            await conn.execute(
                "UPDATE todo_queue SET remind_count=remind_count+1 WHERE id=$1", r["id"])
        return [{"id": r["id"], "title": r["title"]} for r in rows]
    finally:
        await conn.close()
