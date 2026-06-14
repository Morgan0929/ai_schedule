"""
工具定义 & 执行器 — Agent Function Calling

所有工具函数对接真实数据库和服务
"""
from typing import Any
from datetime import date, datetime, timedelta
from common.database import async_session_factory, Base, engine

# 确保所有 ORM 模型已注册到 Base.metadata
import timeline_service.models  # noqa: F401
import crawler_service.models  # noqa: F401
import app_service.models     # noqa: F401
from common.exceptions import NotFoundException


# ============ 工具执行器 ============

async def execute_tool(tool_name: str, params: dict[str, Any], user_id: int) -> dict[str, Any]:
    """
    通用工具执行入口
    """
    import inspect

    tool_func = TOOL_MAP.get(tool_name)
    if not tool_func:
        return {"success": False, "error": f"未知工具: {tool_name}"}

    # 过滤出函数真正接受的参数，避免 TypeError
    sig = inspect.signature(tool_func)
    valid_params = {"user_id": user_id}
    for k, v in params.items():
        if k in sig.parameters:
            valid_params[k] = v

    try:
        result = await tool_func(**valid_params)
        return {"success": True, "tool": tool_name, "result": result}
    except Exception as e:
        return {"success": False, "tool": tool_name, "error": str(e)}


# ============ 日历查询 ============

async def query_calendar(user_id: int, start: str = None, end: str = None,
                         start_date: str = None, end_date: str = None) -> list[dict]:
    """查询用户日历"""
    from timeline_service.repository.task_repo import TaskRepository

    # 兼容两种参数名
    s = start or start_date or date.today().isoformat()
    e = end or end_date or date.today().isoformat()

    try:
        start_dt = datetime.fromisoformat(s) if "T" not in s else datetime.fromisoformat(s)
        end_dt = datetime.fromisoformat(e) if "T" not in e else datetime.fromisoformat(e)
    except ValueError:
        start_dt = datetime.combine(date.today(), datetime.min.time())
        end_dt = datetime.combine(date.today(), datetime.max.time())

    async with async_session_factory() as db:
        repo = TaskRepository(db)
        tasks = await repo.find_by_user_time_range(user_id, start_dt, end_dt)
        return [
            {
                "id": t.id, "title": t.title, "start_time": t.start_time.isoformat(),
                "end_time": t.end_time.isoformat(), "priority": t.priority,
                "location": t.location, "category": t.category,
            }
            for t in tasks
        ]


# ============ 任务 CRUD ============

async def create_task_tool(user_id: int, title: str, start_time: str = None,
                           end_time: str = None, start: str = None, end: str = None,
                           priority: str = "MEDIUM", location: str = None,
                           category: str = "PERSONAL") -> dict:
    """创建任务（含冲突检测），兼容 start/end 和 start_time/end_time"""
    from common.schemas.task import TaskCreateDTO, PriorityEnum, TaskCategoryEnum
    from timeline_service.services.task_service import TaskService

    # 参数名兼容
    st = start_time or start
    et = end_time or end

    # 如果没有给时间，用默认值
    if not st:
        st = (datetime.now() + timedelta(hours=1)).isoformat()
    if not et:
        et = (datetime.now() + timedelta(hours=2)).isoformat()

    # 日期补全时间
    st = _normalize_datetime(st)
    et = _normalize_datetime(et, is_end=True, reference_start=st)

    dto = TaskCreateDTO(
        title=title,
        start_time=datetime.fromisoformat(st),
        end_time=datetime.fromisoformat(et),
        priority=PriorityEnum(priority),
        location=location,
        category=TaskCategoryEnum(category),
    )

    async with async_session_factory() as db:
        service = TaskService(db)
        try:
            task = await service.create_task(dto, user_id)
            await db.commit()
            return {"id": task.id, "title": task.title, "status": "created"}
        except Exception as e:
            await db.rollback()
            return {"error": str(e), "status": "conflict_or_error"}


def _normalize_datetime(dt_str: str, is_end: bool = False, reference_start: str = None) -> str:
    """规范化时间字符串：纯日期补上默认时间。end 自动设为 start+1h"""
    from datetime import timedelta
    from datetime import datetime as dt_cls
    if not dt_str:
        return (dt_cls.now() + timedelta(hours=1)).isoformat()
    # 如果只是日期（不含 T）
    if "T" not in dt_str:
        if is_end and reference_start and "T" in reference_start:
            # end 日期和 start 相同但没时间 → 设为 start+1h
            ref_dt = dt_cls.fromisoformat(reference_start)
            return (ref_dt + timedelta(hours=1)).isoformat()
        return f"{dt_str}T{'10:00:00' if is_end else '09:00:00'}"
    return dt_str


async def update_task_tool(user_id: int, task_id: int, **kwargs) -> dict:
    """更新任务"""
    from common.schemas.task import TaskUpdateDTO
    from timeline_service.services.task_service import TaskService

    # 转换枚举值
    if "priority" in kwargs and isinstance(kwargs["priority"], str):
        from common.schemas.task import PriorityEnum
        kwargs["priority"] = PriorityEnum(kwargs["priority"])

    dto = TaskUpdateDTO(**{k: v for k, v in kwargs.items() if v is not None})

    async with async_session_factory() as db:
        service = TaskService(db)
        task = await service.update_task(task_id, dto)
        await db.commit()
        return {"id": task.id, "title": task.title, "status": "updated"}


async def delete_task_tool(user_id: int, task_id: int) -> dict:
    """删除任务"""
    from timeline_service.services.task_service import TaskService

    async with async_session_factory() as db:
        service = TaskService(db)
        await service.delete_task(task_id)
        await db.commit()
        return {"task_id": task_id, "status": "deleted"}


# ============ 外部数据工具 ============

async def query_weather(user_id: int, city: str = "北京", target_date: str = None) -> dict:
    """查询天气（从爬虫数据获取）"""
    from crawler_service.services.crawl_service import CrawlService

    async with async_session_factory() as db:
        service = CrawlService(db)
        record = await service.get_latest("weather")
        if record and record.raw_data:
            return {"city": city, "source": "cached", "data": record.raw_data}
        return {"city": city, "source": "not_available", "message": "暂无天气数据，请先触发爬取"}


async def query_flight(user_id: int, origin: str, destination: str,
                       flight_date: str = None) -> list[dict]:
    """查询航班（预留）"""
    return [{"message": "航班查询功能开发中", "origin": origin, "destination": destination}]


# ============ 知识库工具 ============

async def search_knowledge(user_id: int, query: str, top_k: int = 3) -> list[dict]:
    """搜索知识库"""
    from rag_service.utils.retriever import retriever
    results = await retriever.search(query, top_k=top_k)
    return results


# ============ 工具注册表 ============

TOOL_MAP = {
    "query_calendar": query_calendar,
    "check_calendar": query_calendar,
    "create_task": create_task_tool,
    "create_task_tool": create_task_tool,
    "create_event": create_task_tool,  # LLM sometimes uses this name
    "update_task": update_task_tool,
    "update_task_tool": update_task_tool,
    "delete_task": delete_task_tool,
    "delete_task_tool": delete_task_tool,
    "delete_event": delete_task_tool,
    "query_weather": query_weather,
    "query_flight": query_flight,
    "search_knowledge": search_knowledge,
}
