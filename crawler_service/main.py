"""
crawler-service 入口 — 爬虫数据采集
端口 8001
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from common.config import settings
from common.exceptions import AppException
from common.models.response import Result


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # TODO: 启动 APScheduler 定时任务
    from crawler_service.scheduler import start_scheduler
    start_scheduler()
    yield
    # TODO: 关闭调度器
    from crawler_service.scheduler import stop_scheduler
    stop_scheduler()


app = FastAPI(
    title="AI Schedule Agent — Crawler Service",
    version="0.1.0",
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


@app.get("/health", response_model=Result)
async def health_check():
    return Result.success({"status": "ok", "service": "crawler-service"})


@app.post("/api/v1/crawl/trigger", response_model=Result)
async def trigger_crawl(source: str = ""):
    """手动触发爬取"""
    return Result.success({"message": f"爬取任务已触发: {source}"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.CRAWLER_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
