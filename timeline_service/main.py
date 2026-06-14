"""
timeline_service 入口 — 时间线引擎 & 冲突检测
端口 8003
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import settings
from common.database import get_db, init_db
from common.exceptions import AppException
from common.schemas.response import Result, PageResult
from common.schemas.task import TaskCreateDTO, TaskUpdateDTO

from timeline_service.services.task_service import TaskService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表"""
    await init_db()
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content=Result.error(500, f"服务器内部错误: {str(exc)}").model_dump(),
    )


@app.get("/health", response_model=Result)
async def health_check():
    return Result.success({"status": "ok", "service": "timeline-service"})


# ============ 任务 CRUD API ============
@app.post("/api/v1/tasks", response_model=Result)
async def create_task(
    dto: TaskCreateDTO,
    user_id: int = Query(..., description="用户 ID"),
    db: AsyncSession = Depends(get_db),
):
    """创建任务（自动冲突检测）"""
    service = TaskService(db)
    task = await service.create_task(dto, user_id)
    return Result.created(task.model_dump())


@app.get("/api/v1/tasks", response_model=Result)
async def list_tasks(
    user_id: int = Query(..., description="用户 ID"),
    start: str = Query(None, description="开始时间 YYYY-MM-DD"),
    end: str = Query(None, description="结束时间 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询任务列表"""
    from datetime import datetime
    service = TaskService(db)
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None
    tasks, total = await service.list_tasks(user_id, start_dt, end_dt, page, page_size)
    return Result.success(PageResult.of(tasks, total, page, page_size).model_dump())


@app.get("/api/v1/tasks/{task_id}", response_model=Result)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """获取任务详情"""
    service = TaskService(db)
    task = await service.get_task(task_id)
    return Result.success(task.model_dump())


@app.put("/api/v1/tasks/{task_id}", response_model=Result)
async def update_task(
    task_id: int,
    dto: TaskUpdateDTO,
    db: AsyncSession = Depends(get_db),
):
    """更新任务"""
    service = TaskService(db)
    task = await service.update_task(task_id, dto)
    return Result.success(task.model_dump())


@app.delete("/api/v1/tasks/{task_id}", response_model=Result)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """删除任务"""
    service = TaskService(db)
    await service.delete_task(task_id)
    return Result.success(None, "删除成功")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.TIMELINE_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
