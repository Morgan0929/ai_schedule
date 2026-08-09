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

async def query_calendar(user_id: int, start_time: str = None, end_time: str = None) -> list[dict]:
    """查询用户日历 — 只接受 start_time/end_time (Planner负责转成时间范围)"""
    if not start_time:
        return []  # 无时间参数 → 不查

    try:
        start_dt = datetime.fromisoformat(start_time)
        if end_time:
            end_dt = datetime.fromisoformat(end_time)
        elif "T" in start_time:
            end_dt = start_dt + timedelta(hours=2)
        else:
            end_dt = datetime.combine(start_dt.date(), datetime.max.time())
    except ValueError:
        return []

    try:
        import asyncpg
        from common.config import Settings; s_cfg = Settings()
        print(f"[TOOL] query_calendar {start_dt}~{end_dt}")
        conn = await asyncpg.connect(
            host=s_cfg.POSTGRES_HOST, port=s_cfg.POSTGRES_PORT,
            user=s_cfg.POSTGRES_USER, password=s_cfg.POSTGRES_PASSWORD,
            database=s_cfg.POSTGRES_DB, timeout=5)
        rows = await conn.fetch(
            "SELECT id,title,start_time,end_time,priority,location,category "
            "FROM task WHERE user_id=$1 AND start_time < $2 AND end_time > $3 "
            "ORDER BY start_time", user_id, end_dt, start_dt)
        await conn.close()
        return [{"id": r["id"], "title": r["title"],
                 "start_time": r["start_time"].isoformat(),
                 "end_time": r["end_time"].isoformat(),
                 "priority": r["priority"], "location": r["location"],
                 "category": r["category"]} for r in rows]
    except Exception:
        return []


# ============ PendingTask → Task (新流程) ============

async def create_pending_tool(user_id: int, title: str, start_time: str = "",
                               end_time: str = "") -> dict:
    """
    新流程: 用户新任务先存 Redis PendingTask, 检查冲突后再决定是否入库

    - 无冲突 → 直接 commit 到 PostgreSQL
    - 有冲突 → 返回冲突信息, PendingTask 留在 Redis 等用户决策
    """
    from agent_service.graph.pending_task import (
        create_pending, save_pending, check_pending_conflicts, commit_pending,
        pending_ref, task_ref,
    )

    pending = create_pending(title, start_time, end_time)
    await save_pending(pending)

    conflicts = await check_pending_conflicts(pending, user_id)

    if not conflicts:
        # 无冲突 → 直接入库
        result = await commit_pending(pending["ref_id"], user_id)
        return result

    # 有冲突 → 返回冲突 + pending 信息
    return {
        "status": "conflict",
        "conflict_level": conflicts[0].get("level", "HARD"),
        "pending_ref": pending["ref_id"],
        "pending_task": {
            "ref_id": pending["ref_id"],
            "title": pending["title"],
            "start_time": pending["start_time"],
            "end_time": pending["end_time"],
        },
        "conflicts": conflicts,
    }


# ============ 任务 CRUD (保留兼容) ============

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

    # 日期补全时间（先补再处理缺失）
    if st:
        st = _normalize_datetime(st)
    if et:
        et = _normalize_datetime(et)

    # 缺 start → 默认 now+1h; 缺 end → start+1h
    if not st:
        st = (datetime.now() + timedelta(hours=1)).isoformat()
        st = _normalize_datetime(st)
    if not et:
        from datetime import datetime as dt_cls
        st_dt = dt_cls.fromisoformat(st)
        et = (st_dt + timedelta(hours=1)).isoformat()

    dto = TaskCreateDTO(
        title=title,
        start_time=datetime.fromisoformat(st),
        end_time=datetime.fromisoformat(et),
        priority=PriorityEnum(priority),
        location=location,
        category=TaskCategoryEnum(category),
    )

    # Use asyncpg directly for remote PG (avoids SQLAlchemy greenlet on Windows)
    try:
        import asyncpg
        from common.config import Settings; s = Settings()
        conn = await asyncpg.connect(
            host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
            user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD,
            database=s.POSTGRES_DB, timeout=5)

        # Check conflict: HARD(重叠) / SOFT(±30min) / NONE
        hard = await conn.fetch(
            "SELECT id,title,start_time,end_time FROM task WHERE user_id=$1 AND start_time < $2 AND end_time > $3",
            user_id, dto.end_time, dto.start_time)
        soft = await conn.fetch(
            "SELECT id,title,start_time,end_time FROM task WHERE user_id=$1 AND start_time BETWEEN $2 AND $3 OR end_time BETWEEN $2 AND $3",
            user_id,
            dto.start_time - timedelta(minutes=30),
            dto.end_time + timedelta(minutes=30))

        if hard:
            from agent_service.graph.pending_task import create_pending_task, db_task_ref, pending_task_ref
            conflicts = [{
                "existing_task": db_task_ref(r["id"], r["title"], str(r["start_time"])[:16]),
                "new_task": pending_task_ref(
                    create_pending_task(dto.title, str(dto.start_time), str(dto.end_time))
                ),
                "level": "HARD",
            } for r in hard]
            await conn.close()
            return {"error": "与已有任务时间重叠", "status": "conflict",
                    "conflict_level": "HARD", "conflicts": conflicts}

        if soft:
            from agent_service.graph.pending_task import create_pending_task, db_task_ref, pending_task_ref
            near = [{
                "existing_task": db_task_ref(r["id"], r["title"], str(r["start_time"])[:16]),
                "new_task": pending_task_ref(
                    create_pending_task(dto.title, str(dto.start_time), str(dto.end_time))
                ),
                "level": "SOFT",
            } for r in soft if r not in hard]
            # SOFT conflict → 仍然创建, 附加警告
            tid = await conn.fetchval(
                "INSERT INTO task (user_id,title,start_time,end_time,priority,status,location,category,tags,task_metadata) "
                "VALUES ($1,$2,$3,$4,$5,'PENDING',$6,$7,'[]','{}') RETURNING id",
                user_id, dto.title, dto.start_time, dto.end_time, priority, location, category)
            # 回填: SOFT 下已成功创建, 升级为 database
            for n in near:
                n["new_task"]["id"] = tid
                n["new_task"]["source"] = "database"
            await conn.close()
            return {"id": tid, "title": dto.title, "status": "created",
                    "conflict_level": "SOFT", "conflicts": near,
                    "error": "与已有任务时间相近"}

        tid = await conn.fetchval(
            "INSERT INTO task (user_id,title,start_time,end_time,priority,status,location,category,tags,task_metadata) "
            "VALUES ($1,$2,$3,$4,$5,'PENDING',$6,$7,'[]','{}') RETURNING id",
            user_id, dto.title, dto.start_time, dto.end_time, priority, location, category)
        await conn.close()
        return {"id": tid, "title": dto.title, "status": "created"}
    except Exception as e:
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


async def update_task_tool(user_id: int, task_id: int = None, title: str = None,
                           new_time: str = None, start_time: str = None,
                           **kwargs) -> dict:
    """
    更新任务 — 支持 task_id 或 title 定位

    conflict_resolver 只知道 title (不知道 task_id),
    这里做 title → task_id 的查找
    """
    from common.schemas.task import TaskUpdateDTO
    from timeline_service.services.task_service import TaskService

    # ── task_id 不存在时, 用 title 查找 ──
    if task_id is None and title:
        try:
            import asyncpg
            from common.config import Settings; s = Settings()
            conn = await asyncpg.connect(
                host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
                user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD,
                database=s.POSTGRES_DB, timeout=5)
            row = await conn.fetchrow(
                "SELECT id FROM task WHERE user_id=$1 AND title=$2 "
                "ORDER BY start_time DESC LIMIT 1",
                user_id, title)
            await conn.close()
            if row:
                task_id = row["id"]
            else:
                return {"error": f"未找到任务「{title}」", "status": "not_found"}
        except Exception as e:
            return {"error": str(e), "status": "lookup_error"}

    if task_id is None:
        return {"error": "缺少 task_id 或 title", "status": "missing_param"}

    # 转换枚举值
    if "priority" in kwargs and isinstance(kwargs["priority"], str):
        from common.schemas.task import PriorityEnum
        kwargs["priority"] = PriorityEnum(kwargs["priority"])

    # 构建 update DTO
    update_fields = {k: v for k, v in kwargs.items() if v is not None}
    if new_time or start_time:
        try:
            from datetime import datetime as dt_cls
            t = new_time or start_time
            update_fields["start_time"] = dt_cls.fromisoformat(t)
        except (ValueError, TypeError):
            pass

    dto = TaskUpdateDTO(**update_fields)

    async with async_session_factory() as db:
        service = TaskService(db)
        try:
            task = await service.update_task(task_id, dto)
        except NotFoundException:
            if title:
                try:
                    import asyncpg
                    from common.config import Settings; s = Settings()
                    conn = await asyncpg.connect(
                        host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
                        user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD,
                        database=s.POSTGRES_DB, timeout=5)
                    row = await conn.fetchrow(
                        "SELECT id FROM task WHERE user_id=$1 AND title=$2 "
                        "ORDER BY start_time DESC LIMIT 1",
                        user_id, title)
                    await conn.close()
                    if row:
                        task_id = row["id"]
                        task = await service.update_task(task_id, dto)
                    else:
                        return {"error": f"未找到任务「{title}」", "status": "not_found"}
                except Exception as e:
                    return {"error": str(e), "status": "lookup_error"}
            else:
                return {"error": f"未找到任务 #{task_id}", "status": "not_found"}

        await db.commit()
        return {"id": task.id, "title": task.title,
                "new_time": (new_time or start_time or ""),
                "status": "updated"}


async def delete_task_tool(user_id: int, task_id: int) -> dict:
    """删除任务"""
    from timeline_service.services.task_service import TaskService

    async with async_session_factory() as db:
        service = TaskService(db)
        await service.delete_task(task_id)
        await db.commit()
        return {"task_id": task_id, "status": "deleted"}


# ============ 天气工具 ============

async def query_weather(user_id: int, city: str = "北京", date: str = None,
                        target_date: str = None) -> dict:
    """
    查询天气 — MCP Weather Server / wttr.in 实时

    统一返回格式:
      {
        "city": "英德",
        "query_date": "2026-08-09",
        "weather": {
          "temp_min": 27, "temp_max": 35,
          "desc": "Sunny", "humidity": 75
        }
      }

    Args:
        city: 城市名，默认北京
        date:  目标日期 ISO (优先)
        target_date: 兼容旧参数名
    """
    query_date = date or target_date or date.today().isoformat()

    # ── MCP Weather Server (优先) ──
    try:
        from agent_service.mcp.client import call_mcp_tool
        r = await call_mcp_tool("weather", "get_current_weather", {"city": city})
        if r.get("success") and r.get("data"):
            data = r["data"]
            return {
                "city": city,
                "query_date": query_date,
                "weather": {
                    "temp_min": data.get("temp_min", data.get("temp_c", "")),
                    "temp_max": data.get("temp_max", data.get("temp_c", "")),
                    "desc": data.get("desc", data.get("weatherDesc", "")),
                    "humidity": data.get("humidity", ""),
                },
            }
    except Exception:
        pass

    # ── Fallback: wttr.in ──
    try:
        import httpx
        url = f"https://wttr.in/{city}?format=j1"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            raw = resp.json()

        current = raw.get("current_condition", [{}])[0]
        forecasts = raw.get("weather", [])
        temp_min = ""
        temp_max = ""
        desc = current.get("weatherDesc", [{}])[0].get("value", "")
        humidity = current.get("humidity", "?")

        # 匹配目标日期的 forecast
        for f in forecasts:
            f_date = f.get("date", "")
            if f_date == query_date or (not temp_min):
                temp_min = f"{f.get('mintempC', '?')}"
                temp_max = f"{f.get('maxtempC', '?')}"
                if f_date == query_date:
                    hourly = f.get("hourly", [{}])
                    desc = hourly[4].get("weatherDesc", [{}])[0].get("value", desc) if len(hourly) > 4 else desc
                    break

        return {
            "city": city,
            "query_date": query_date,
            "weather": {
                "temp_min": temp_min,
                "temp_max": temp_max,
                "desc": desc,
                "humidity": humidity,
            },
        }
    except Exception as e:
        return {"city": city, "query_date": query_date, "weather": None,
                "error": str(e)}


# ============ 地图 & 定位工具 ============

CITY_COORDS = {
    "北京": (39.90, 116.40), "上海": (31.23, 121.47), "广州": (23.13, 113.26),
    "深圳": (22.54, 114.05), "杭州": (30.28, 120.15), "成都": (30.57, 104.06),
    "南京": (32.06, 118.79), "武汉": (30.58, 114.30), "重庆": (29.56, 106.55),
    "西安": (34.26, 108.94), "长沙": (28.22, 112.93), "郑州": (34.75, 113.62),
    "天津": (39.13, 117.20), "苏州": (31.30, 120.62), "东莞": (23.05, 113.75),
    "佛山": (23.02, 113.12), "珠海": (22.27, 113.58), "厦门": (24.48, 118.08),
    "青岛": (36.07, 120.38), "大连": (38.91, 121.61),
}


def _haversine(lat1, lon1, lat2, lon2) -> float:
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 1)


async def get_travel_time(user_id: int, origin: str, destination: str,
                          mode: str = "car") -> dict:
    """
    估算两地之间的出行时间和距离

    Args:
        origin: 出发地（城市名）
        destination: 目的地（城市名）
        mode: 出行方式 walk/bike/bus/car，默认 car
    """
    o = CITY_COORDS.get(origin)
    d = CITY_COORDS.get(destination)
    if not o: return {"error": f"未找到「{origin}」", "known": list(CITY_COORDS.keys())[:15]}
    if not d: return {"error": f"未找到「{destination}」", "known": list(CITY_COORDS.keys())[:15]}

    km = _haversine(*o, *d)
    road_km = round(km * 1.3, 1)
    speeds = {"walk": 5, "bike": 15, "bus": 30, "car": 60}
    hours = road_km / speeds.get(mode, 60)
    if hours >= 1:
        time_str = f"{int(hours)}h{int((hours % 1) * 60)}min"
    else:
        time_str = f"{int(hours * 60)}min"

    if road_km < 1: advice = "步行即可"
    elif road_km < 5: advice = "建议骑行或公交"
    elif road_km < 50: advice = "建议驾车或地铁"
    elif road_km < 500: advice = "建议高铁"
    else: advice = "建议飞机"

    return {
        "origin": origin, "destination": destination,
        "straight_km": km, "road_km": road_km,
        "mode": mode, "estimated_time": time_str, "advice": advice,
    }


async def search_location(user_id: int, query: str) -> dict:
    """
    搜索地点信息 (OpenStreetMap Nominatim, 免费 API)

    Args:
        query: 搜索关键词（地名/地址）
    """
    try:
        import httpx
        url = "https://nominatim.openstreetmap.org/search"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={
                "q": query, "format": "json", "limit": 5, "accept-language": "zh"
            }, headers={"User-Agent": "AIScheduleAgent-Lin/1.0"})
            resp.raise_for_status()
            data = resp.json()
        return {
            "query": query,
            "results": [{
                "name": p.get("display_name", ""),
                "lat": float(p.get("lat", 0)),
                "lon": float(p.get("lon", 0)),
                "type": p.get("type", ""),
            } for p in data[:5]],
        }
    except Exception as e:
        return {"query": query, "error": str(e)}


# ============ 航班（预留）============

async def query_flight(user_id: int, origin: str, destination: str,
                       flight_date: str = None) -> list[dict]:
    return [{"message": "航班查询开发中", "origin": origin, "destination": destination}]


# ============ 文档分析 (Document Analyzer) ============

async def analyze_document(user_id: int, image_base64: str,
                           doc_type: str = "generic", hint: str = "") -> dict:
    """
    分析文档图片 — 课表/作业/通知/票据等

    林收到用户上传的图片后，调用此工具识别内容，
    返回结构化数据，再由 Calendar/Task/Reminder 工具处理。

    Args:
        image_base64: 图片的 base64 编码
        doc_type:     文档类型 course_schedule/homework/exam_notice/ticket/generic
        hint:         用户的额外提示
    """
    from agent_service.tools.document_analyzer import DocumentAnalyzer
    return await DocumentAnalyzer.analyze(image_base64, doc_type, hint)


# ============ 知识库工具 ============

async def search_knowledge(user_id: int, query: str, top_k: int = 3) -> list[dict]:
    """搜索知识库 — pgvector 语义检索"""
    from rag_service.services.rag_service import RagService
    docs = await RagService.search_documents(user_id, query, top_k)
    mems = await RagService.search_semantic_memory(user_id, query, top_k=3)
    return {"documents": docs, "memories": mems}




# ============ Todo 工具 ============

async def create_todo_tool(user_id: int, title: str, note: str = "",
                           priority: str = "MEDIUM") -> dict:
    from agent_service.graph.todo_service import create_todo
    return await create_todo(user_id, title, note, priority)


async def list_todos_tool(user_id: int) -> list[dict]:
    from agent_service.graph.todo_service import list_todos
    return await list_todos(user_id)


async def save_pending_todo_tool(user_id: int, title: str,
                                  due_date: str = "") -> dict:
    """将待办写入 Redis (5min TTL), 无具体时间的事件先暂存"""
    from agent_service.graph.pending_task import (
        create_pending_todo, save_pending_todo, commit_todo_to_db, is_todo_committed,
    )
    todo = create_pending_todo(title, due_date)
    await save_pending_todo(todo)
    # 尝试立刻落库 (如有 due_date 且已明确)
    if due_date:
        result = await commit_todo_to_db(todo["ref_id"], user_id)
        if result.get("id"):
            return {"id": result["id"], "title": title, "status": "created",
                    "ref_id": todo["ref_id"], "committed": True}
    return {"ref_id": todo["ref_id"], "title": title,
            "status": "pending", "committed": False}


# ============ MCP 工具函数 (外部能力) ============

async def mcp_weather_current(user_id: int, city: str = "北京") -> dict:
    from agent_service.mcp.client import call_mcp_tool
    return await call_mcp_tool("weather", "get_current_weather", {"city": city})

async def mcp_weather_forecast(user_id: int, city: str = "北京", days: int = 2) -> dict:
    from agent_service.mcp.client import call_mcp_tool
    return await call_mcp_tool("weather", "get_forecast", {"city": city, "days": days})

async def mcp_web_search(user_id: int, query: str, max_results: int = 5) -> dict:
    from agent_service.mcp.client import call_mcp_tool
    return await call_mcp_tool("search", "web_search", {"query": query, "max_results": max_results})


# ============ 工具注册表 ============

async def reschedule_pending_tool(user_id: int, ref_id: str = "",
                                   start_time: str = "", new_time: str = "") -> dict:
    """更新 Redis PendingTask 的时间 (不写 DB)"""
    from agent_service.graph.pending_task import get_pending, save_pending
    pending = await get_pending(ref_id)
    if not pending:
        return {"error": f"PendingTask not found: {ref_id}", "status": "not_found"}
    t = new_time or start_time
    if t:
        try:
            old_start = datetime.fromisoformat(pending["start_time"])
            old_end = datetime.fromisoformat(pending.get("end_time", pending["start_time"]))
            duration = old_end - old_start
        except (TypeError, ValueError):
            duration = timedelta(hours=1)
        pending["start_time"] = t
        pending["end_time"] = (
            datetime.fromisoformat(t) + duration
        ).isoformat()
    pending["status"] = "rescheduled"
    await save_pending(pending)
    return {"ref_id": ref_id, "title": pending["title"],
            "start_time": pending["start_time"], "status": "rescheduled"}


async def commit_pending_tool(user_id: int, ref_id: str = "",
                              title: str = "", new_time: str = "",
                              start_time: str = "") -> dict:
    """PendingTask → PostgreSQL. 冲突解决后调用."""
    from agent_service.graph.pending_task import commit_pending
    overrides = {}
    t = new_time or start_time
    if t:
        overrides["start_time"] = t
    return await commit_pending(ref_id, user_id, overrides if overrides else None)


async def _query_calendar_shared(user_id: int, start_time: str = None,
                                 end_time: str = None) -> list[dict]:
    """Read tasks through the same SQLAlchemy engine used by timeline APIs."""
    if not start_time:
        return []
    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time) if end_time else start_dt + timedelta(hours=2)
    except (TypeError, ValueError):
        return []

    from timeline_service.services.task_service import TaskService

    async with async_session_factory() as db:
        tasks, _ = await TaskService(db).list_tasks(
            user_id, start=start_dt, end=end_dt, page=1, page_size=1000
        )
        return [task.model_dump(mode="json") for task in tasks]


async def _create_task_shared(user_id: int, title: str, start_time: str = None,
                              end_time: str = None, start: str = None,
                              end: str = None, priority: str = "MEDIUM",
                              location: str = None,
                              category: str = "PERSONAL") -> dict:
    """Create a task through the shared SQLAlchemy session."""
    from common.schemas.task import TaskCreateDTO, PriorityEnum, TaskCategoryEnum
    from common.exceptions import ConflictException
    from timeline_service.services.task_service import TaskService

    st = start_time or start or (datetime.now() + timedelta(hours=1)).isoformat()
    st = _normalize_datetime(st)
    et = _normalize_datetime(end_time or end) if (end_time or end) else (
        datetime.fromisoformat(st) + timedelta(hours=1)
    ).isoformat()
    dto = TaskCreateDTO(
        title=title,
        start_time=datetime.fromisoformat(st),
        end_time=datetime.fromisoformat(et),
        priority=PriorityEnum(priority),
        location=location,
        category=TaskCategoryEnum(category),
    )

    try:
        async with async_session_factory() as db:
            task = await TaskService(db).create_task(dto, user_id)
            await db.commit()
            return {"id": task.id, "title": task.title,
                    "start_time": task.start_time.isoformat(),
                    "end_time": task.end_time.isoformat(), "status": "created"}
    except ConflictException as exc:
        return {"error": exc.message, "status": "conflict",
                "conflict_level": "HARD", "conflicts": exc.detail or []}
    except Exception as exc:
        return {"error": str(exc), "status": "create_failed"}


async def _update_task_shared(user_id: int, task_id: int = None, title: str = None,
                              new_time: str = None, start_time: str = None,
                              **kwargs) -> dict:
    """Resolve and update a task from one user-scoped SQLAlchemy session."""
    from common.schemas.task import TaskUpdateDTO, PriorityEnum
    from common.exceptions import NotFoundException
    from timeline_service.services.task_service import TaskService

    if isinstance(kwargs.get("priority"), str):
        kwargs["priority"] = PriorityEnum(kwargs["priority"])
    update_fields = {key: value for key, value in kwargs.items() if value is not None}
    time_value = new_time or start_time
    if time_value:
        try:
            update_fields["start_time"] = datetime.fromisoformat(time_value)
        except (TypeError, ValueError):
            return {"error": "invalid start_time", "status": "invalid_param"}
    if not update_fields:
        return {"error": "no update fields", "status": "missing_param"}

    async with async_session_factory() as db:
        service = TaskService(db)
        if task_id is None and title:
            existing = await service.repo.find_latest_by_user_title(user_id, title)
            task_id = existing.id if existing else None
        if task_id is None:
            return {"error": "task_id or title is required", "status": "missing_param"}
        if time_value and "end_time" not in update_fields:
            existing = await service.repo.find_by_id(task_id)
            if existing:
                duration = existing.end_time - existing.start_time
                update_fields["end_time"] = datetime.fromisoformat(time_value) + duration
        try:
            task = await service.update_task_for_user(
                user_id, task_id, TaskUpdateDTO(**update_fields)
            )
        except NotFoundException:
            return {"error": f"task not found: {task_id}", "status": "not_found"}
        await db.commit()
        return {"id": task.id, "title": task.title,
                "new_time": time_value or "", "status": "updated"}


async def _delete_task_shared(user_id: int, task_id: int = None, title: str = "",
                              time_range: dict | None = None) -> dict:
    """Delete by id, or resolve one user-scoped task from an exact title and time range."""
    from timeline_service.services.task_service import TaskService

    async with async_session_factory() as db:
        repo = TaskService(db).repo
        task = None

        if task_id:
            task = await repo.find_by_id(task_id)
            if not task or task.user_id != user_id:
                return {"error": f"task not found: {task_id}", "status": "not_found"}
        elif title and time_range:
            try:
                start = datetime.fromisoformat(time_range["start"])
                end = datetime.fromisoformat(time_range["end"])
            except (KeyError, TypeError, ValueError):
                return {"error": "invalid task time range", "status": "invalid_request"}

            matches = [
                candidate for candidate in await repo.find_by_user_time_range(user_id, start, end)
                if candidate.title == title
            ]
            if not matches:
                return {"error": f"task not found: {title}", "status": "not_found"}
            if len(matches) > 1:
                return {
                    "error": f"multiple tasks matched: {title}",
                    "status": "ambiguous",
                    "matches": [
                        {"id": candidate.id, "title": candidate.title,
                         "start_time": candidate.start_time.isoformat()}
                        for candidate in matches
                    ],
                }
            task = matches[0]
        else:
            return {"error": "task_id or title with time_range is required", "status": "invalid_request"}

        await db.delete(task)
        await db.commit()
        return {"task_id": task.id, "title": task.title, "status": "deleted"}


# Keep direct imports (for example calendar_service) on the same code path as
# execute_tool and the public TOOL_MAP.
query_calendar = _query_calendar_shared
create_task_tool = _create_task_shared
update_task_tool = _update_task_shared
delete_task_tool = _delete_task_shared


TOOL_MAP = {
    # 日历 & 任务
    "query_calendar": _query_calendar_shared,
    "check_calendar": _query_calendar_shared,
    "create_pending": create_pending_tool,
    "reschedule_pending": reschedule_pending_tool,  # 更新 Redis PendingTask 时间
    "commit_pending": commit_pending_tool,          # PendingTask → DB
    "create_task": _create_task_shared,
    "create_task_tool": _create_task_shared,
    "create_event": _create_task_shared,
    "update_task": _update_task_shared,
    "update_task_tool": _update_task_shared,
    "delete_task": _delete_task_shared,
    "delete_task_tool": _delete_task_shared,
    "delete_event": _delete_task_shared,
    # 天气 & 出行
    "query_weather": query_weather,
    "get_travel_time": get_travel_time,
    "search_location": search_location,
    "query_flight": query_flight,
    # 文档分析
    "analyze_document": analyze_document,
    # 知识库
    "search_knowledge": search_knowledge,
    # === Todo ===
    "create_todo_tool": create_todo_tool,
    "create_todo": create_todo_tool,
    "save_pending_todo": save_pending_todo_tool,
    "list_todos": list_todos_tool,
    # === MCP 外部服务 ===
    "mcp_weather_current": mcp_weather_current,
    "mcp_weather_forecast": mcp_weather_forecast,
    "mcp_web_search": mcp_web_search,
}
