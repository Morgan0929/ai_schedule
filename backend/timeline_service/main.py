"""
timeline_service 入口 — 时间线引擎 & 冲突检测
端口 8003
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Query, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.authentication import get_authenticated_user_id
from common.config import settings
from common.database import get_db, init_db
from common.exceptions import AppException, NotFoundException
from common.schemas.response import Result, PageResult
from common.schemas.task import TaskCreateDTO, TaskUpdateDTO
from common.schemas.schedule import ScheduleCreateDTO, ScheduleUpdateDTO

from timeline_service.services.task_service import TaskService
from timeline_service.services.schedule_service import ScheduleService

# Ensure schedule attachment metadata is registered before init_db().
import timeline_service.models.schedule_model  # noqa: F401


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
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
@app.get("/media/{kind}/{filename}")
async def get_attachment(
    kind: str, filename: str,
    user_id: int = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Serve an attachment only to its owning user."""
    import re

    match = re.fullmatch(r"(task|schedule)-(\d+)-[0-9a-f]{16}\.(jpg|png|webp|gif)", filename)
    if not match or match.group(1) != kind:
        raise NotFoundException("附件")
    record_id = int(match.group(2))
    if kind == "task":
        item = await TaskService(db).get_task_for_user(user_id, record_id)
        attachments = item.attachments
    else:
        attachments = await ScheduleService(db).list_attachments(user_id, record_id)
    attachment = next((item for item in attachments if item.file_name == filename), None)
    path = (UPLOAD_DIR / kind / filename).resolve()
    if not attachment or not path.is_relative_to(UPLOAD_DIR.resolve()) or not path.is_file():
        raise NotFoundException("附件")
    return FileResponse(
        path, media_type=attachment.content_type,
        headers={"Cache-Control": "private, no-store"},
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
    user_id: int = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """创建任务（自动冲突检测）"""
    service = TaskService(db)
    task = await service.create_task(dto, user_id)
    return Result.created(task.model_dump(mode="json"))


@app.get("/api/v1/tasks", response_model=Result)
async def list_tasks(
    user_id: int = Depends(get_authenticated_user_id),
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
    return Result.success(PageResult.of(
        [task.model_dump(mode="json") for task in tasks],
        total,
        page,
        page_size,
    ).model_dump())


@app.get("/api/v1/tasks/{task_id}", response_model=Result)
async def get_task(
    task_id: int,
    user_id: int = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取任务详情"""
    service = TaskService(db)
    task = await service.get_task_for_user(user_id, task_id)
    return Result.success(task.model_dump(mode="json"))


@app.put("/api/v1/tasks/{task_id}", response_model=Result)
async def update_task(
    task_id: int,
    dto: TaskUpdateDTO,
    user_id: int = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """更新任务"""
    service = TaskService(db)
    task = await service.update_task_for_user(user_id, task_id, dto)
    return Result.success(task.model_dump(mode="json"))


@app.delete("/api/v1/tasks/{task_id}", response_model=Result)
async def delete_task(
    task_id: int,
    user_id: int = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除任务"""
    service = TaskService(db)
    await service.delete_task_for_user(user_id, task_id)
    return Result.success(None, "删除成功")


@app.post("/api/v1/tasks/{task_id}/images", response_model=Result)
async def upload_task_image(
    task_id: int,
    user_id: int = Depends(get_authenticated_user_id),
    file: UploadFile = File(..., description="图片文件"),
    db: AsyncSession = Depends(get_db),
):
    """给任务日程上传一张图片。"""
    image = await TaskService(db).add_attachment(user_id, task_id, file)
    return Result.created(image.model_dump(mode="json"), "上传成功")


@app.get("/api/v1/schedules", response_model=Result)
async def list_schedules(
    user_id: int = Depends(get_authenticated_user_id),
    target_date: str | None = Query(None, alias="date", description="日期 YYYY-MM-DD"),
    semester: str | None = Query(None, description="学期标识，不传则当前学期"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询课表。传 date 时按日期查；不传 date 时按学期分页查。"""
    from datetime import date

    service = ScheduleService(db)
    if target_date:
        try:
            parsed_date = date.fromisoformat(target_date)
        except ValueError as exc:
            raise AppException(400, "日期格式应为 YYYY-MM-DD") from exc
        return Result.success([item.model_dump(mode="json") for item in await service.list_by_date(user_id, parsed_date)])

    schedules, total = await service.list_schedules(user_id, semester, page, page_size)
    return Result.success(PageResult.of(
        [item.model_dump(mode="json") for item in schedules],
        total,
        page,
        page_size,
    ).model_dump())


@app.post("/api/v1/schedules", response_model=Result)
async def create_schedule(
    dto: ScheduleCreateDTO,
    user_id: int = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """手动新增一条课表日程。"""
    schedule = await ScheduleService(db).create_schedule(user_id, dto)
    return Result.created(schedule.model_dump(mode="json"))


@app.get("/api/v1/schedules/{schedule_id}", response_model=Result)
async def get_schedule(
    schedule_id: int,
    user_id: int = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取课表记录详情。"""
    schedule = await ScheduleService(db).get_schedule(user_id, schedule_id)
    return Result.success(schedule.model_dump(mode="json"))


@app.put("/api/v1/schedules/{schedule_id}", response_model=Result)
async def update_schedule(
    schedule_id: int,
    dto: ScheduleUpdateDTO,
    user_id: int = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """修改已有课表日程。"""
    schedule = await ScheduleService(db).update_schedule(user_id, schedule_id, dto)
    return Result.success(schedule.model_dump(mode="json"))


@app.delete("/api/v1/schedules/{schedule_id}", response_model=Result)
async def delete_schedule(
    schedule_id: int,
    user_id: int = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除已有课表日程。"""
    await ScheduleService(db).delete_schedule(user_id, schedule_id)
    return Result.success(None, "删除成功")


@app.get("/api/v1/schedules/{schedule_id}/images", response_model=Result)
async def list_schedule_images(
    schedule_id: int,
    user_id: int = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询课表日程图片。"""
    images = await ScheduleService(db).list_attachments(user_id, schedule_id)
    return Result.success([item.model_dump(mode="json") for item in images])


@app.post("/api/v1/schedules/{schedule_id}/images", response_model=Result)
async def upload_schedule_image(
    schedule_id: int,
    user_id: int = Depends(get_authenticated_user_id),
    file: UploadFile = File(..., description="图片文件"),
    db: AsyncSession = Depends(get_db),
):
    """给课表日程上传一张图片。"""
    image = await ScheduleService(db).add_attachment(user_id, schedule_id, file)
    return Result.created(image.model_dump(mode="json"), "上传成功")


@app.delete("/api/v1/schedules/{schedule_id}/images/{image_id}", response_model=Result)
async def delete_schedule_image(
    schedule_id: int,
    image_id: int,
    user_id: int = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除课表日程图片。"""
    await ScheduleService(db).delete_attachment(user_id, schedule_id, image_id)
    return Result.success(None, "删除成功")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.TIMELINE_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
