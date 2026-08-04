"""
Calendar Service — 统一日程查询层

Planner 输出 → ScheduleQuery(标准化) → query_calendar → 结果
"""
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field


class ScheduleQuery(BaseModel):
    """统一日程查询 Schema — 所有查询经过这里标准化"""
    start_time: datetime = Field(description="查询开始时间")
    end_time: datetime = Field(description="查询结束时间")
    user_id: int = Field(default=0)
    query_type: str = Field(default="range", description="range / point / free_slot")

    @classmethod
    def from_params(cls, params: dict, user_id: int = 0) -> "ScheduleQuery | None":
        """从 Planner 输出构建标准查询"""
        if not params:
            return None

        # date → 全天
        if "date" in params and "start_time" not in params:
            d = params["date"]
            start = datetime.fromisoformat(f"{d}T00:00:00" if "T" not in str(d) else str(d))
            end = datetime.fromisoformat(f"{d}T23:59:59" if "T" not in str(d) else str(d))
            return cls(start_time=start, end_time=end, user_id=user_id, query_type="range")

        # start_time only → point ±2h
        if "start_time" in params:
            st = str(params["start_time"])
            start = datetime.fromisoformat(st)
            if "end_time" in params:
                end = datetime.fromisoformat(str(params["end_time"]))
            elif "T" in st:
                end = start + timedelta(hours=2)
            else:
                end = datetime.combine(start.date(), datetime.max.time())
            return cls(start_time=start, end_time=end, user_id=user_id,
                       query_type="point" if "T" in st else "range")

        return None

    def to_iso(self) -> tuple[str, str]:
        return self.start_time.isoformat(), self.end_time.isoformat()


async def calendar_query(params: dict, user_id: int) -> list[dict]:
    """Calendar Service 入口 — 标准查询"""
    query = ScheduleQuery.from_params(params, user_id)
    if not query:
        return []

    from agent_service.graph.tools import query_calendar
    start_str, end_str = query.to_iso()
    return await query_calendar(user_id, start_time=start_str, end_time=end_str)
