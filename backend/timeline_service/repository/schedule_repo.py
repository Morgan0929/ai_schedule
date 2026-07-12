"""
课表数据访问层
"""
from datetime import date
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from timeline_service.models.schedule_model import ScheduleModel, get_current_semester


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
        """查询指定日期的课程（根据星期几匹配）"""
        week_day = target_date.isoweekday()  # 1=周一, 7=周日
        semester = get_current_semester()

        result = await self.db.execute(
            select(ScheduleModel)
            .where(
                ScheduleModel.user_id == user_id,
                ScheduleModel.semester == semester,
                ScheduleModel.week_day == week_day,
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
