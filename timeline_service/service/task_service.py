"""
任务业务逻辑层
"""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from timeline_service.models import TaskModel
from timeline_service.repository.task_repo import TaskRepository
from timeline_service.conflict_detector import ConflictDetector
from common.exceptions import NotFoundException, BadRequestException, ConflictException
from common.models.task import TaskDTO, TaskCreateDTO, TaskUpdateDTO


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
        return TaskDTO.model_validate(task)

    async def get_task(self, task_id: int) -> TaskDTO:
        """获取任务详情"""
        task = await self.repo.find_by_id(task_id)
        if not task:
            raise NotFoundException("任务", task_id)
        return TaskDTO.model_validate(task)

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
        return TaskDTO.model_validate(task)

    async def delete_task(self, task_id: int) -> bool:
        """删除任务"""
        success = await self.repo.delete(task_id)
        if not success:
            raise NotFoundException("任务", task_id)
        return True

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

        return [TaskDTO.model_validate(t) for t in tasks], total
