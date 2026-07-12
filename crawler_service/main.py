"""
crawler_service 入口 — 爬虫数据采集
端口 8001
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import settings
from common.database import get_db, init_db, async_session_factory
from common.exceptions import AppException
from common.schemas.response import Result, PageResult

from crawler_service.models.crawl_model import CrawlTriggerRequest
from crawler_service.services.crawl_service import CrawlService
from crawler_service.utils.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    await init_db()
    start_scheduler()
    logger.info("Crawler service started with scheduler")
    yield
    stop_scheduler()
    logger.info("Crawler service stopped")


app = FastAPI(
    title="AI Schedule Agent — Crawler Service",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.code,
        content=Result.error(exc.code, exc.message).model_dump(),
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content=Result.error(400, str(exc)).model_dump(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content=Result.error(500, f"服务器内部错误: {str(exc)}").model_dump(),
    )


# ============ 健康检查 ============
@app.get("/health", response_model=Result)
async def health_check():
    return Result.success({"status": "ok", "service": "crawler-service"})


# ============ 爬虫管理 API ============
@app.get("/api/v1/crawl/spiders", response_model=Result)
async def list_spiders():
    """列出所有可用爬虫"""
    spiders = CrawlService.get_available_spiders()
    return Result.success(spiders)


@app.post("/api/v1/crawl/trigger", response_model=Result)
async def trigger_crawl(
    request: CrawlTriggerRequest,
    db: AsyncSession = Depends(get_db),
):
    """手动触发一次爬取"""
    service = CrawlService(db)
    record = await service.trigger_crawl(request)
    return Result.success({
        "task_id": record.id,
        "source": record.source,
        "status": record.status,
        "extracted_info": record.extracted_info,
    })


@app.get("/api/v1/crawl/records", response_model=Result)
async def list_records(
    source: str = Query(None, description="按数据源过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """分页查询爬取记录"""
    service = CrawlService(db)
    records, total = await service.list_records(source, page, page_size)
    return Result.success(PageResult.of(records, total, page, page_size).model_dump())


@app.get("/api/v1/crawl/records/{record_id}", response_model=Result)
async def get_record(record_id: int, db: AsyncSession = Depends(get_db)):
    """获取单条爬取记录详情"""
    service = CrawlService(db)
    record = await service.get_record(record_id)
    return Result.success(record.model_dump())


@app.get("/api/v1/crawl/latest/{source}", response_model=Result)
async def get_latest(source: str, db: AsyncSession = Depends(get_db)):
    """获取指定数据源的最新数据"""
    service = CrawlService(db)
    record = await service.get_latest(source)
    if not record:
        return Result.success(None, f"暂无 {source} 数据")
    return Result.success(record.model_dump())


# ============ 课表刷新 API ============
from pydantic import BaseModel, Field


class ScheduleRefreshRequest(BaseModel):
    """课表刷新请求"""
    user_id: int = Field(..., description="用户 ID")
    courses: list[dict] = Field(..., description="课程列表")
    source: str = Field(default="gdut", description="数据来源")
    semester: str | None = Field(None, description="学期（为空则取当前学期）")


@app.post("/api/v1/crawl/schedule/refresh", response_model=Result)
async def refresh_schedule(
    request: ScheduleRefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    手动刷新课表 — 更新 Redis 缓存 + SQL 持久化

    使用场景:
    - 首次导入课表
    - 点击刷新按钮重新爬取
    - 学期初更新新课表
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from timeline_service.models.schedule_model import get_current_semester
    from timeline_service.repository.schedule_repo import ScheduleRepository
    from personal.schedule_storage import (
        save_schedule_to_sql, cache_daily_schedule,
        get_week_schedule_from_cache, invalidate_daily_cache,
    )
    from datetime import date, timedelta

    user_id = request.user_id
    semester = request.semester or get_current_semester()

    # === 1. 更新 SQL (删除旧数据 + 插入新数据) ===
    saved_count = await save_schedule_to_sql(
        user_id=user_id,
        courses=request.courses,
        source=request.source,
        semester=semester,
    )

    # === 2. 刷新 Redis 缓存 (清除本周旧缓存 + 重写) ===
    today = date.today()
    refreshed_days = 0
    for i in range(7):
        d = today + timedelta(days=i)
        await invalidate_daily_cache(user_id, d)

        # 查出该天的课程并写入 Redis
        from timeline_service.repository.schedule_repo import ScheduleRepository
        async with async_session_factory() as sdb:
            srepo = ScheduleRepository(sdb)
            day_courses = await srepo.find_by_date(user_id, d)
            if day_courses:
                course_list = [
                    {"name": c.course_name, "time": f"{c.start_section}-{c.end_section}节",
                     "location": c.location, "teacher": c.teacher}
                    for c in day_courses
                ]
                await cache_daily_schedule(user_id, d, course_list)
                refreshed_days += 1

    await db.commit()

    return Result.success({
        "sql_saved": saved_count,
        "redis_days_refreshed": refreshed_days,
        "semester": semester,
        "source": request.source,
    })


@app.get("/api/v1/crawl/schedule/status", response_model=Result)
async def schedule_status(
    user_id: int = Query(..., description="用户 ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    查询课表缓存状态 — 是否已爬取、缓存是否有效
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from datetime import date
    from timeline_service.repository.schedule_repo import ScheduleRepository
    from timeline_service.models.schedule_model import get_current_semester
    from personal.schedule_storage import get_daily_schedule_from_cache

    semester = get_current_semester()
    today = date.today()

    # SQL 状态
    async with async_session_factory() as sdb:
        srepo = ScheduleRepository(sdb)
        sql_courses = await srepo.find_by_user_semester(user_id, semester)

    # Redis 状态
    redis_cached = await get_daily_schedule_from_cache(user_id, today)

    return Result.success({
        "semester": semester,
        "sql_course_count": len(sql_courses),
        "sql_has_data": len(sql_courses) > 0,
        "redis_today_cached": redis_cached is not None,
        "needs_first_crawl": len(sql_courses) == 0,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.CRAWLER_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
