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


# ============ 天气工具 ============

async def query_weather(user_id: int, city: str = "北京", target_date: str = None) -> dict:
    """
    查询天气 — 优先缓存，无缓存则实时请求 wttr.in (免费 API)

    Args:
        city: 城市名（中文或拼音），默认北京
        target_date: 日期 YYYY-MM-DD（1-3天预报）
    """
    # 1. 先查缓存
    from crawler_service.services.crawl_service import CrawlService
    async with async_session_factory() as db:
        service = CrawlService(db)
        record = await service.get_latest("weather")
        if record and record.raw_data:
            data = record.raw_data.get("data", {})
            if data.get("city") == city:
                return {"city": city, "source": "cached", **record.raw_data}

    # 2. 实时请求 wttr.in
    try:
        import httpx
        url = f"https://wttr.in/{city}?format=j1"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            raw = resp.json()

        current = raw.get("current_condition", [{}])[0]
        forecasts = raw.get("weather", [])[:3]

        return {
            "city": city, "source": "realtime",
            "current": {
                "temp": f"{current.get('temp_C', '?')}C",
                "desc": current.get("weatherDesc", [{}])[0].get("value", ""),
                "humidity": f"{current.get('humidity', '?')}%",
                "wind": f"{current.get('windspeedKmph', '?')} km/h",
            },
            "daily": [{
                "date": f.get("date", ""),
                "high": f"{f.get('maxtempC', '?')}C",
                "low": f"{f.get('mintempC', '?')}C",
                "desc": f.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", ""),
            } for f in forecasts],
        }
    except Exception as e:
        return {"city": city, "source": "unavailable", "error": str(e)}


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
    """搜索知识库"""
    from rag_service.utils.retriever import retriever
    results = await retriever.search(query, top_k=top_k)
    return results


# ============ 工具注册表 ============

TOOL_MAP = {
    # 日历 & 任务
    "query_calendar": query_calendar,
    "check_calendar": query_calendar,
    "create_task": create_task_tool,
    "create_task_tool": create_task_tool,
    "create_event": create_task_tool,
    "update_task": update_task_tool,
    "update_task_tool": update_task_tool,
    "delete_task": delete_task_tool,
    "delete_task_tool": delete_task_tool,
    "delete_event": delete_task_tool,
    # 天气 & 出行
    "query_weather": query_weather,
    "get_travel_time": get_travel_time,
    "search_location": search_location,
    "query_flight": query_flight,
    # 文档分析
    "analyze_document": analyze_document,
    # 知识库
    "search_knowledge": search_knowledge,
}
