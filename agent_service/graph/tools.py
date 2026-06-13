"""
工具定义 — Agent 可调用的 Function Calling 工具

Agent 通过调用这些工具来操作日历、查询数据、创建任务等
"""
from typing import Any
from datetime import datetime, date
from common.exceptions import NotFoundException


# ============ 日历工具 ============

async def query_calendar(user_id: int, start_date: date, end_date: date) -> list[dict[str, Any]]:
    """
    查询用户日历

    Args:
        user_id: 用户 ID
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        日历事件列表
    """
    # TODO: 从数据库查询
    return []


async def create_task_tool(user_id: int, title: str, start_time: datetime,
                           end_time: datetime, priority: str = "MEDIUM",
                           location: str = None, category: str = "PERSONAL") -> dict[str, Any]:
    """
    创建新任务

    Args:
        user_id: 用户 ID
        title: 任务标题
        start_time: 开始时间
        end_time: 结束时间
        priority: 优先级 HIGH/MEDIUM/LOW
        location: 地点
        category: 分类 MEETING/TRIP/PERSONAL/WORK

    Returns:
        创建的任务
    """
    # TODO: 写入数据库
    task = {
        "id": 0,
        "user_id": user_id,
        "title": title,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "priority": priority,
        "location": location,
        "category": category,
    }
    return task


async def update_task_tool(task_id: int, **kwargs) -> dict[str, Any]:
    """
    更新任务

    Args:
        task_id: 任务 ID
        **kwargs: 要更新的字段

    Returns:
        更新后的任务
    """
    # TODO: 更新数据库
    return {"id": task_id, **kwargs}


async def delete_task_tool(task_id: int) -> bool:
    """删除任务"""
    # TODO: 删除数据库记录
    return True


# ============ 外部数据工具 ============

async def query_weather(city: str, target_date: date = None) -> dict[str, Any]:
    """
    查询天气

    Args:
        city: 城市名
        target_date: 目标日期

    Returns:
        天气信息
    """
    # TODO: 接入天气 API 或爬虫数据
    return {"city": city, "date": str(target_date), "weather": "待实现"}


async def query_flight(origin: str, destination: str, date: date) -> list[dict[str, Any]]:
    """
    查询航班

    Args:
        origin: 出发城市
        destination: 到达城市
        date: 日期

    Returns:
        航班列表
    """
    # TODO: 接入航班 API 或爬虫数据
    return []


# ============ 工具注册表 ============

# 工具定义（用于 LangChain/LangGraph Function Calling）
TOOL_DEFINITIONS = [
    {
        "name": "query_calendar",
        "description": "查询用户指定时间范围内的日程安排",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "用户 ID"},
                "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
            },
            "required": ["user_id", "start_date", "end_date"],
        },
    },
    {
        "name": "create_task_tool",
        "description": "创建一个新的任务/行程",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "title": {"type": "string", "description": "任务标题"},
                "start_time": {"type": "string", "description": "开始时间 ISO 格式"},
                "end_time": {"type": "string", "description": "结束时间 ISO 格式"},
                "priority": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "location": {"type": "string"},
                "category": {"type": "string", "enum": ["MEETING", "TRIP", "PERSONAL", "WORK"]},
            },
            "required": ["user_id", "title", "start_time", "end_time"],
        },
    },
    {
        "name": "update_task_tool",
        "description": "更新已有任务",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "title": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "priority": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "query_weather",
        "description": "查询指定城市的天气",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名"},
                "target_date": {"type": "string", "description": "日期 YYYY-MM-DD"},
            },
            "required": ["city"],
        },
    },
]

# 工具名称到函数的映射
TOOL_MAP = {
    "query_calendar": query_calendar,
    "create_task_tool": create_task_tool,
    "update_task_tool": update_task_tool,
    "delete_task_tool": delete_task_tool,
    "query_weather": query_weather,
    "query_flight": query_flight,
}
