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
from common.database import get_db, init_db
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.CRAWLER_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
