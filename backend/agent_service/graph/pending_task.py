"""
PendingTask & Stage — Agent 工作记忆中的实体生命周期

══════════════════════════════════
实体分层
══════════════════════════════════

  UserIntent
       │
       ▼
  PendingTask (Redis: pending:task:{ref_id})
       │  status: conflict_blocked → waiting_confirm
       │
       ▼
  Task (PostgreSQL, id=22)

══════════════════════════════════
Conflict 引用格式
══════════════════════════════════

  "keep": "task:21"           → 数据库已有任务
  "move": "pending:abc123"    → Redis PendingTask
  "cancel": "pending:abc123"  → 取消 PendingTask

══════════════════════════════════
Stage 状态机
══════════════════════════════════

  WAITING_CHOICE  ──(A/B/C)──► WAITING_CONFIRM
       │                            │
       └──(取消)──► CANCELLED       └──(确认)──► COMMITTED → clear
"""
import json
import uuid
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ═══════════════════ Stage 常量 ═══════════════════

STAGE_WAITING_CHOICE = "waiting_choice"
STAGE_WAITING_CONFIRM = "waiting_confirm"
STAGE_COMMITTED = "committed"
STAGE_CANCELLED = "cancelled"

# ═══════════════════ 引用格式 ═══════════════════

REF_TASK = "task"        # "task:21"
REF_PENDING = "pending"  # "pending:abc123"

def task_ref(task_id: int) -> str:
    return f"{REF_TASK}:{task_id}"

def pending_ref(ref_id: str) -> str:
    return f"{REF_PENDING}:{ref_id}"

def parse_ref(ref: str) -> tuple[str, str | int]:
    """ "task:21" → ("task", 21); "pending:abc" → ("pending", "abc") """
    kind, val = ref.split(":", 1)
    return kind, (int(val) if kind == REF_TASK else val)

# ═══════════════════ PendingTask CRUD (Redis) ═══════════════════

PENDING_TTL = 1800  # 30 min


async def _redis():
    from common.redis_client import get_redis
    return await get_redis()


def _rkey(ref_id: str) -> str:
    return f"pending:task:{ref_id}"


def create_pending(title: str, start_time: str, end_time: str = "",
                   source: str = "user_request") -> dict:
    """创建 PendingTask dict (未写入 Redis)"""
    return {
        "ref_id": f"pending_{uuid.uuid4().hex[:8]}",
        "title": title,
        "start_time": start_time,
        "end_time": end_time or start_time,
        "source": source,
        "status": "conflict_blocked",
    }


async def save_pending(pending: dict) -> None:
    """写入 Redis"""
    try:
        r = await _redis()
        await r.setex(_rkey(pending["ref_id"]), PENDING_TTL,
                      json.dumps(pending, ensure_ascii=False))
    except Exception as e:
        logger.debug(f"save_pending failed: {e}")


async def get_pending(ref_id: str) -> dict | None:
    """从 Redis 读取"""
    try:
        r = await _redis()
        data = await r.get(_rkey(ref_id))
        return json.loads(data) if data else None
    except Exception:
        return None


async def delete_pending(ref_id: str) -> None:
    """从 Redis 删除"""
    try:
        r = await _redis()
        await r.delete(_rkey(ref_id))
    except Exception:
        pass


async def commit_pending(ref_id: str, user_id: int,
                         overrides: dict = None) -> dict:
    """
    PendingTask → PostgreSQL Task

    从 Redis 读取 PendingTask, INSERT 到 PostgreSQL, 删除 Redis
    """
    pending = await get_pending(ref_id)
    if not pending:
        return {"error": f"PendingTask not found: {ref_id}"}

    title = pending["title"]
    start_time = (overrides or {}).get("start_time", pending["start_time"])
    end_time = (overrides or {}).get("end_time")
    if not end_time:
        end_time = pending.get("end_time", start_time)
        if start_time != pending.get("start_time"):
            try:
                old_start = datetime.fromisoformat(pending["start_time"])
                old_end = datetime.fromisoformat(end_time)
                duration = old_end - old_start
                if duration.total_seconds() > 0:
                    end_time = (datetime.fromisoformat(start_time) + duration).isoformat()
            except (TypeError, ValueError):
                pass

    # 先删 Redis (防重复 commit), 再 INSERT
    await delete_pending(ref_id)

    try:
        import asyncpg
        from common.config import Settings; s = Settings()
        conn = await asyncpg.connect(
            host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
            user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD,
            database=s.POSTGRES_DB, timeout=5)

        # 幂等检查: 同用户同标题同时段 5 分钟内视为重复
        existing = await conn.fetchval(
            "SELECT id FROM task WHERE user_id=$1 AND title=$2 "
            "AND start_time BETWEEN $3 AND $4 LIMIT 1",
            user_id, title,
            datetime.fromisoformat(start_time) - timedelta(minutes=5),
            datetime.fromisoformat(start_time) + timedelta(minutes=5))
        if existing:
            await conn.close()
            return {"id": existing, "title": title,
                    "status": "already_exists", "ref_id": ref_id}

        tid = await conn.fetchval(
            "INSERT INTO task (user_id,title,start_time,end_time,priority,status,location,category,tags,task_metadata) "
            "VALUES ($1,$2,$3,$4,'MEDIUM','PENDING','','PERSONAL','[]','{}') RETURNING id",
            user_id, title,
            datetime.fromisoformat(start_time),
            datetime.fromisoformat(end_time))

        await conn.close()
        return {"id": tid, "title": title, "start_time": start_time,
                "status": "created", "ref_id": ref_id}
    except Exception as e:
        return {"error": str(e), "status": "commit_failed"}


# ═══════════════════ 冲突检测 (PendingTask vs DB) ═══════════════════

async def check_pending_conflicts(pending: dict, user_id: int) -> list[dict]:
    """
    检查 PendingTask 是否与已有任务冲突

    Returns:
        [] 无冲突 → 可直接 commit
        [{existing_task, pending_task, level}] → 有冲突
    """
    try:
        import asyncpg
        from common.config import Settings; s = Settings()
        st = datetime.fromisoformat(pending["start_time"])
        et = datetime.fromisoformat(pending.get("end_time", pending["start_time"]))

        conn = await asyncpg.connect(
            host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
            user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD,
            database=s.POSTGRES_DB, timeout=5)

        hard = await conn.fetch(
            "SELECT id,title,start_time,end_time FROM task "
            "WHERE user_id=$1 AND start_time < $2 AND end_time > $3",
            user_id, et, st)

        conflicts = []
        for r in hard:
            conflicts.append({
                "existing_task": {
                    "id": r["id"], "title": r["title"],
                    "time": str(r["start_time"])[:16],
                    "source": "database",
                },
                "pending_ref": pending["ref_id"],
                "pending_task": {
                    "ref_id": pending["ref_id"],
                    "title": pending["title"],
                    "start_time": pending["start_time"],
                    "end_time": pending["end_time"],
                },
                "level": "HARD",
            })

        await conn.close()
        return conflicts
    except Exception:
        return []


# ═══════════════════ TaskRef (兼容旧格式) ═══════════════════

def db_task_ref(task_id: int, title: str, time: str) -> dict:
    return {"id": task_id, "title": title, "time": time, "source": "database"}


def pending_task_ref(pending: dict) -> dict:
    start_time = pending.get("start_time", "")
    return {
        "id": None, "title": pending["title"],
        "time": start_time,
        "start_time": start_time,
        "end_time": pending.get("end_time", ""),
        "source": "pending", "ref_id": pending.get("ref_id", ""),
    }


async def _check_pending_conflicts_shared(pending: dict, user_id: int) -> list[dict]:
    """Check conflicts through the configured SQLAlchemy database."""
    try:
        from common.database import async_session_factory
        from timeline_service.repository.task_repo import TaskRepository

        start = datetime.fromisoformat(pending["start_time"])
        end = datetime.fromisoformat(pending.get("end_time", pending["start_time"]))
        async with async_session_factory() as db:
            tasks = await TaskRepository(db).find_by_user_time_range(user_id, start, end)
            return [{
                "existing_task": db_task_ref(
                    task.id, task.title, task.start_time.isoformat()[:16]
                ),
                "pending_ref": pending["ref_id"],
                "pending_task": pending_task_ref(pending),
                "level": "HARD",
            } for task in tasks]
    except (TypeError, ValueError):
        return []


async def _commit_pending_shared(ref_id: str, user_id: int,
                                 overrides: dict = None) -> dict:
    """Commit a pending task through the configured SQLAlchemy database."""
    pending = await get_pending(ref_id)
    if not pending:
        return {"error": f"PendingTask not found: {ref_id}"}

    title = pending["title"]
    start_time = (overrides or {}).get("start_time", pending["start_time"])
    end_time = (overrides or {}).get("end_time") or pending.get("end_time", start_time)
    try:
        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time)
    except (TypeError, ValueError) as exc:
        return {"error": str(exc), "status": "commit_failed"}

    await delete_pending(ref_id)
    try:
        from common.database import async_session_factory
        from timeline_service.models.task_model import TaskModel
        from timeline_service.repository.task_repo import TaskRepository

        async with async_session_factory() as db:
            repo = TaskRepository(db)
            existing = await repo.find_by_user_time_range(
                user_id, start - timedelta(minutes=5), start + timedelta(minutes=5)
            )
            existing = [task for task in existing if task.title == title]
            if existing:
                await db.rollback()
                return {"id": existing[0].id, "title": title,
                        "status": "already_exists", "ref_id": ref_id}

            task = await repo.create(TaskModel(
                user_id=user_id,
                title=title,
                start_time=start,
                end_time=end,
                priority="MEDIUM",
                status="PENDING",
                location="",
                category="PERSONAL",
                tags=[],
                extra_data={},
            ))
            await db.commit()
            return {"id": task.id, "title": title, "start_time": start_time,
                    "status": "created", "ref_id": ref_id}
    except Exception as exc:
        return {"error": str(exc), "status": "commit_failed"}


# Keep pending-task flows on the same database as the regular task tools.
check_pending_conflicts = _check_pending_conflicts_shared
commit_pending = _commit_pending_shared


# ═══════════════════ Pending Todo CRUD (Redis → PostgreSQL) ═══════════════════

TODO_TTL = 300  # 5 min — 超时自动落 PG

_PENDING_TODO_PREFIX = "todo:pending"


def _todo_key(ref_id: str) -> str:
    return f"{_PENDING_TODO_PREFIX}:{ref_id}"


def create_pending_todo(title: str, due_date: str = "",
                        source: str = "user_request") -> dict:
    """创建 PendingTodo dict (未写入 Redis)"""
    return {
        "ref_id": f"todo_{uuid.uuid4().hex[:8]}",
        "title": title,
        "due_date": due_date,
        "created_at": datetime.now().isoformat(),
        "source": source,
    }


async def save_pending_todo(todo: dict) -> None:
    """写入 Redis, TTL=300s"""
    try:
        r = await _redis()
        await r.setex(_todo_key(todo["ref_id"]), TODO_TTL,
                      json.dumps(todo, ensure_ascii=False))
    except Exception as e:
        logger.debug(f"save_pending_todo failed: {e}")


async def get_pending_todo(ref_id: str) -> dict | None:
    """从 Redis 读取 PendingTodo"""
    try:
        r = await _redis()
        data = await r.get(_todo_key(ref_id))
        return json.loads(data) if data else None
    except Exception:
        return None


async def delete_pending_todo(ref_id: str) -> None:
    """从 Redis 删除 PendingTodo"""
    try:
        r = await _redis()
        await r.delete(_todo_key(ref_id))
    except Exception:
        pass


async def commit_todo_to_db(ref_id: str, user_id: int) -> dict:
    """Redis PendingTodo → PostgreSQL todo_queue (不删除 Redis, 由 TTL 自然过期)"""
    todo = await get_pending_todo(ref_id)
    if not todo:
        return {"error": f"PendingTodo not found: {ref_id}"}

    try:
        from agent_service.graph.todo_service import create_todo
        result = await create_todo(user_id, todo["title"], "",
                                    todo.get("priority", "MEDIUM"))
        # 标记已落库, 防重复
        r_set = await _redis()
        await r_set.setex(f"{_todo_key(ref_id)}:committed", 3600, "1")
        return {"id": result.get("id"), "title": todo["title"],
                "status": result.get("status", "created"),
                "ref_id": ref_id, "committed": True}
    except Exception as e:
        return {"error": str(e), "status": "commit_failed"}


async def is_todo_committed(ref_id: str) -> bool:
    """检查是否已落过库"""
    try:
        r = await _redis()
        return await r.exists(f"{_todo_key(ref_id)}:committed") > 0
    except Exception:
        return False


async def flush_expired_todos(user_id: int) -> list[dict]:
    """
    扫描 Redis 中 todo:pending:* 键, 将到期的 PendingTodo 写入 PG.
    在每次对话前调用.
    """
    try:
        r = await _redis()
        results = []
        cursor = 0
        while True:
            cursor, keys = await r.scan(cursor, match=f"{_PENDING_TODO_PREFIX}:*", count=20)
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                # 跳过 committed 标记键
                if key_str.endswith(":committed"):
                    continue
                ref_id = key_str.replace(f"{_PENDING_TODO_PREFIX}:", "")
                # 跳过已落库的
                if await is_todo_committed(ref_id):
                    continue
                data = await r.get(key_str)
                if data:
                    todo = json.loads(data)
                    try:
                        created_at = datetime.fromisoformat(todo.get("created_at", "2000-01-01T00:00:00"))
                    except (ValueError, TypeError):
                        created_at = datetime(2000, 1, 1)
                    if (datetime.now() - created_at).total_seconds() > TODO_TTL:
                        result = await commit_todo_to_db(ref_id, user_id)
                        if result.get("id"):
                            results.append(result)
            if cursor == 0:
                break
        if results:
            logger.info(f"flush_expired_todos: committed {len(results)} to PG")
        return results
    except Exception as e:
        logger.debug(f"flush_expired_todos failed: {e}")
        return []
