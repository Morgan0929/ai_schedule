"""
课表数据访问层
"""
from datetime import date
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from timeline_service.models.schedule_model import (
    ScheduleModel,
    ScheduleAttachmentModel,
    get_current_semester,
    get_semester_for_date,
    get_semester_week,
)


class ScheduleRepository:
    """课表 Repository"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_batch(self, schedules: list[ScheduleModel]) -> list[ScheduleModel]:
        """批量保存课表（先删旧数据再插入新数据）"""
        if not schedules:
            return []

        user_id = schedules[0].user_id
        semester = schedules[0].semester

        # 删除同一用户同一学期的旧数据
        await self.db.execute(
            delete(ScheduleModel).where(
                ScheduleModel.user_id == user_id,
                ScheduleModel.semester == semester,
            )
        )

        # 批量插入
        for s in schedules:
            self.db.add(s)

        await self.db.flush()
        return schedules

    async def create(self, schedule: ScheduleModel) -> ScheduleModel:
        self.db.add(schedule)
        await self.db.flush()
        await self.db.refresh(schedule)
        return schedule

    async def find_by_id(self, schedule_id: int) -> ScheduleModel | None:
        result = await self.db.execute(
            select(ScheduleModel).where(ScheduleModel.id == schedule_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: int,
        semester: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ScheduleModel], int]:
        if not semester:
            semester = get_current_semester()

        base_query = select(ScheduleModel).where(
            ScheduleModel.user_id == user_id,
            ScheduleModel.semester == semester,
        )
        count_result = await self.db.execute(base_query)
        total = len(count_result.scalars().all())

        query = (
            base_query
            .order_by(ScheduleModel.week_day, ScheduleModel.start_section, ScheduleModel.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def update(self, schedule: ScheduleModel) -> ScheduleModel:
        await self.db.flush()
        await self.db.refresh(schedule)
        return schedule

    async def delete(self, schedule: ScheduleModel) -> bool:
        await self.db.delete(schedule)
        await self.db.flush()
        return True

    async def add_attachments(
        self,
        schedule_id: int,
        user_id: int,
        attachments: list[ScheduleAttachmentModel],
    ) -> list[ScheduleAttachmentModel]:
        for attachment in attachments:
            self.db.add(attachment)
        await self.db.flush()
        for attachment in attachments:
            await self.db.refresh(attachment)
        return attachments

    async def list_attachments(
        self, schedule_id: int, user_id: int
    ) -> list[ScheduleAttachmentModel]:
        result = await self.db.execute(
            select(ScheduleAttachmentModel)
            .where(
                ScheduleAttachmentModel.schedule_id == schedule_id,
                ScheduleAttachmentModel.user_id == user_id,
            )
            .order_by(ScheduleAttachmentModel.created_at.asc())
        )
        return list(result.scalars().all())

    async def delete_attachments(self, schedule_id: int, user_id: int) -> int:
        result = await self.db.execute(
            delete(ScheduleAttachmentModel).where(
                ScheduleAttachmentModel.schedule_id == schedule_id,
                ScheduleAttachmentModel.user_id == user_id,
            )
        )
        await self.db.flush()
        return result.rowcount or 0

    async def find_by_user_semester(
        self, user_id: int, semester: str = None
    ) -> list[ScheduleModel]:
        """查询用户指定学期的课表"""
        if not semester:
            semester = get_current_semester()

        result = await self.db.execute(
            select(ScheduleModel)
            .where(
                ScheduleModel.user_id == user_id,
                ScheduleModel.semester == semester,
                ScheduleModel.is_active == True,
            )
            .order_by(ScheduleModel.week_day, ScheduleModel.start_section)
        )
        return list(result.scalars().all())

    async def find_by_date(
        self, user_id: int, target_date: date
    ) -> list[ScheduleModel]:
        """查询指定日期的课程（根据学期周次和星期几匹配）"""
        week_day = target_date.isoweekday()  # 1=周一, 7=周日
        semester = get_semester_for_date(target_date)
        semester_week = get_semester_week(target_date, semester)
        if semester_week is None:
            return []

        result = await self.db.execute(
            select(ScheduleModel)
            .where(
                ScheduleModel.user_id == user_id,
                ScheduleModel.semester == semester,
                ScheduleModel.week_day == week_day,
                ScheduleModel.start_week <= semester_week,
                ScheduleModel.end_week >= semester_week,
                ScheduleModel.is_active == True,
            )
            .order_by(ScheduleModel.start_section)
        )
        return list(result.scalars().all())

    async def cleanup_past_semesters(self, user_id: int) -> int:
        """清理已过期学期的课表，返回删除数量"""
        from timeline_service.models.schedule_model import get_past_semesters
        past = get_past_semesters()

        result = await self.db.execute(
            delete(ScheduleModel).where(
                ScheduleModel.user_id == user_id,
                ScheduleModel.semester.in_(past),
            )
        )
        await self.db.flush()
        return result.rowcount or 0
