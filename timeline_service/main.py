"""
timeline-service 入口 — 时间线引擎 & 冲突检测
端口 8003
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from common.config import settings
from common.exceptions import AppException
from common.models.response import Result
from common.models.timeline import TimelineDTO, TimelineGenerateDTO
from common.models.conflict import ConflictDTO


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="AI Schedule Agent — Timeline Service",
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
    return Result.success({"status": "ok", "service": "timeline-service"})


# ============ 时间线 API ============
@app.get("/api/v1/timeline")
async def get_timeline(date: str = Query(..., description="日期 YYYY-MM-DD")):
    """获取指定日期时间线"""
    return Result.success({"date": date, "events": []})


@app.post("/api/v1/timeline/generate")
async def generate_timeline(dto: TimelineGenerateDTO):
    """AI 自动生成时间线"""
    return Result.success({"message": "时间线生成功能待实现"})


# ============ 冲突检测 API ============
@app.get("/api/v1/conflicts")
async def detect_conflicts(
    user_id: int = Query(...),
    start: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end: str = Query(..., description="结束日期 YYYY-MM-DD"),
):
    """检测时间范围内的冲突"""
    # TODO: 调用 conflict_detector 检测
    return Result.success({"user_id": user_id, "conflicts": []})


@app.post("/api/v1/conflicts/resolve/{conflict_id}")
async def resolve_conflict(conflict_id: int):
    """AI 协调解决冲突"""
    return Result.success({"conflict_id": conflict_id, "resolution": "待实现"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.TIMELINE_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
