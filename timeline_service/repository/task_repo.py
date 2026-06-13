"""
任务数据访问层
"""
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from timeline_service.models import TaskModel


class TaskRepository:
    """任务 Repository"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_by_id(self, task_id: int) -> TaskModel | None:
        """按 ID 查询"""
        result = await self.db.execute(
            select(TaskModel).where(TaskModel.id == task_id)
        )
        return result.scalar_one_or_none()

    async def find_by_user_time_range(
        self, user_id: int, start: datetime, end: datetime
    ) -> list[TaskModel]:
        """查询用户在指定时间范围内的任务"""
        result = await self.db.execute(
            select(TaskModel)
            .where(
                and_(
                    TaskModel.user_id == user_id,
                    TaskModel.start_time < end,
                    TaskModel.end_time > start,
                )
            )
            .order_by(TaskModel.start_time.asc())
        )
        return list(result.scalars().all())

    async def create(self, task: TaskModel) -> TaskModel:
        """创建任务"""
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def update(self, task: TaskModel) -> TaskModel:
        """更新任务"""
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def delete(self, task_id: int) -> bool:
        """删除任务"""
        task = await self.find_by_id(task_id)
        if task:
            await self.db.delete(task)
            await self.db.flush()
            return True
        return False

    async def list_by_user(
        self, user_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[TaskModel], int]:
        """分页查询用户任务"""
        base_query = select(TaskModel).where(TaskModel.user_id == user_id)

        count_result = await self.db.execute(base_query)
        total = len(count_result.scalars().all())

        query = (
            base_query
            .offset((page - 1) * page_size)
            .limit(page_size)
            .order_by(TaskModel.start_time.desc())
        )
        result = await self.db.execute(query)
        tasks = list(result.scalars().all())

        return tasks, total
