"""
任务业务逻辑层
"""
from datetime import datetime
import hashlib
from pathlib import Path
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from timeline_service.models.task_model import TaskModel
from timeline_service.repository.task_repo import TaskRepository
from timeline_service.utils.conflict_detector import ConflictDetector
from common.exceptions import NotFoundException, BadRequestException, ConflictException
from common.schemas.task import TaskDTO, TaskCreateDTO, TaskUpdateDTO, TaskAttachmentDTO


ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
IMAGE_EXTENSIONS = {ext: content_type for content_type, ext in ALLOWED_IMAGE_TYPES.items()}
MAX_IMAGE_SIZE = 10 * 1024 * 1024


class TaskService:
    """任务服务"""

    def __init__(self, db: AsyncSession):
        self.repo = TaskRepository(db)
        self.conflict_detector = ConflictDetector()

    async def create_task(self, dto: TaskCreateDTO, user_id: int) -> TaskDTO:
        """创建任务（含冲突检测）"""
        # 参数校验
        if not dto.validate_time_range():
            raise BadRequestException("结束时间必须晚于开始时间")

        # 冲突检测
        overlapping = await self.repo.find_by_user_time_range(
            user_id, dto.start_time, dto.end_time
        )
        if overlapping:
            # 构建临时 TaskModel 用于冲突检测
            new_task = TaskModel(
                user_id=user_id,
                title=dto.title,
                start_time=dto.start_time,
                end_time=dto.end_time,
                priority=dto.priority.value if dto.priority else "MEDIUM",
                location=dto.location,
                category=dto.category.value if dto.category else "PERSONAL",
            )
            report = self.conflict_detector.detect(overlapping + [new_task])
            if report.total_conflicts > 0:
                raise ConflictException(
                    f"与 {report.total_conflicts} 个已有任务时间重叠",
                    detail=[c.__dict__ for c in report.conflicts],
                )

        # 创建
        task = TaskModel(
            user_id=user_id,
            title=dto.title,
            description=dto.description,
            start_time=dto.start_time,
            end_time=dto.end_time,
            priority=dto.priority.value if dto.priority else "MEDIUM",
            location=dto.location,
            category=dto.category.value if dto.category else "PERSONAL",
            tags=dto.tags or [],
        )
        task = await self.repo.create(task)
        return self._to_dto(task)

    async def get_task(self, task_id: int) -> TaskDTO:
        """获取任务详情"""
        task = await self.repo.find_by_id(task_id)
        if not task:
            raise NotFoundException("任务", task_id)
        return self._to_dto(task)

    async def update_task(self, task_id: int, dto: TaskUpdateDTO) -> TaskDTO:
        """更新任务"""
        task = await self.repo.find_by_id(task_id)
        if not task:
            raise NotFoundException("任务", task_id)

        # 只更新传入的字段
        update_data = dto.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                # 处理枚举值
                if hasattr(value, 'value'):
                    value = value.value
                setattr(task, key, value)

        task = await self.repo.update(task)
        return self._to_dto(task)

    async def update_task_for_user(
        self, user_id: int, task_id: int, dto: TaskUpdateDTO
    ) -> TaskDTO:
        """Update a task only when it belongs to the requesting user."""
        task = await self.repo.find_by_id(task_id)
        if not task or task.user_id != user_id:
            raise NotFoundException("task", task_id)
        return await self.update_task(task_id, dto)

    async def get_task_for_user(self, user_id: int, task_id: int) -> TaskDTO:
        """Fetch a task only when it belongs to the requesting user."""
        task = await self.repo.find_by_id(task_id)
        if not task or task.user_id != user_id:
            raise NotFoundException("task", task_id)
        return self._to_dto(task)

    async def delete_task(self, task_id: int) -> bool:
        """删除任务"""
        success = await self.repo.delete(task_id)
        if not success:
            raise NotFoundException("任务", task_id)
        return True

    async def delete_task_for_user(self, user_id: int, task_id: int) -> bool:
        task = await self.repo.find_by_id(task_id)
        if not task or task.user_id != user_id:
            raise NotFoundException("task", task_id)
        for attachment in self._attachments(task):
            try:
                Path(self._storage_path(attachment["file_url"])).unlink(missing_ok=True)
            except OSError:
                pass
        return await self.delete_task(task_id)

    async def list_tasks(
        self, user_id: int, start: datetime = None, end: datetime = None,
        page: int = 1, page_size: int = 20
    ) -> tuple[list[TaskDTO], int]:
        """查询任务列表（支持时间范围过滤）"""
        if start and end:
            tasks = await self.repo.find_by_user_time_range(user_id, start, end)
            total = len(tasks)
            # 简单分页
            offset = (page - 1) * page_size
            tasks = tasks[offset:offset + page_size]
        else:
            tasks, total = await self.repo.list_by_user(user_id, page, page_size)

        return [self._to_dto(t) for t in tasks], total

    async def add_attachment(
        self, user_id: int, task_id: int, file: UploadFile,
    ) -> TaskAttachmentDTO:
        task = await self.repo.find_by_id(task_id)
        if not task or task.user_id != user_id:
            raise NotFoundException("task", task_id)
        content_type = self._resolve_content_type(file)
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise BadRequestException("仅支持 JPEG / PNG / WebP / GIF 图片")
        data = await file.read()
        if len(data) > MAX_IMAGE_SIZE:
            raise BadRequestException("图片大小不能超过 10MB")

        digest = hashlib.sha256(data).hexdigest()[:16]
        ext = ALLOWED_IMAGE_TYPES[content_type]
        safe_name = f"task-{task.id}-{digest}{ext}"
        storage_dir = Path(__file__).resolve().parents[2] / "uploads" / "task"
        storage_dir.mkdir(parents=True, exist_ok=True)
        path = storage_dir / safe_name
        path.write_bytes(data)

        attachment = {
            "id": digest,
            "task_id": task.id,
            "file_name": safe_name,
            "original_name": file.filename or safe_name,
            "content_type": content_type,
            "file_size": len(data),
            "file_url": f"/media/task/{safe_name}",
            "created_at": datetime.now().isoformat(),
        }
        metadata = dict(task.extra_data or {})
        metadata["attachments"] = [*self._attachments(task), attachment]
        task.extra_data = metadata
        await self.repo.update(task)
        return TaskAttachmentDTO.model_validate(attachment)

    @staticmethod
    def _attachments(task: TaskModel) -> list[dict]:
        metadata = task.extra_data or {}
        items = metadata.get("attachments", []) if isinstance(metadata, dict) else []
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _storage_path(file_url: str) -> str:
        relative = file_url.removeprefix("/media/")
        return str(Path(__file__).resolve().parents[2] / "uploads" / relative)

    @staticmethod
    def _resolve_content_type(file: UploadFile) -> str:
        if file.content_type in ALLOWED_IMAGE_TYPES:
            return file.content_type
        ext = Path(file.filename or "").suffix.lower()
        return IMAGE_EXTENSIONS.get(ext, file.content_type or "")

    @classmethod
    def _to_dto(cls, task: TaskModel) -> TaskDTO:
        dto = TaskDTO.model_validate(task)
        dto.attachments = [
            TaskAttachmentDTO.model_validate(item)
            for item in cls._attachments(task)
        ]
        return dto
