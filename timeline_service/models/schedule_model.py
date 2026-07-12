"""
课表数据模型 — 持久化存储

与 TaskModel 不同:
- Task 是用户手动创建的自由日程
- Schedule 是从外部系统爬取的固定课程安排

学期结束后自动清理
"""
from datetime import datetime, date
from sqlalchemy import String, Integer, Date, Time, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from common.database import Base


class ScheduleModel(Base):
    """课程表"""
    __tablename__ = "schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), default="gdut")  # 数据来源: gdut / manual

    # 课程基本信息
    course_name: Mapped[str] = mapped_column(String(256), nullable=False, comment="课程名称")
    teacher: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="教师")
    location: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="上课地点")

    # 时间信息
    week_day: Mapped[int] = mapped_column(Integer, nullable=False, comment="星期几 1-7")
    start_week: Mapped[int] = mapped_column(Integer, default=1, comment="起始周")
    end_week: Mapped[int] = mapped_column(Integer, default=16, comment="结束周")
    start_time: Mapped[datetime | None] = mapped_column(Time, nullable=True, comment="开始时间")
    end_time: Mapped[datetime | None] = mapped_column(Time, nullable=True, comment="结束时间")
    start_section: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="开始节次")
    end_section: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="结束节次")

    # 学期信息（用于过期清理）
    semester: Mapped[str] = mapped_column(String(32), nullable=False, index=True,
                                          comment="学期标识, 如 2026-SPRING")

    # 原始数据
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True, comment="原始爬取数据JSON")

    # 标记
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return (f"<Schedule({self.course_name} "
                f"周{self.week_day} {self.start_section}-{self.end_section}节 "
                f"[{self.semester}])>")


def get_current_semester() -> str:
    """获取当前学期标识"""
    today = date.today()
    year = today.year
    # 2-7月为春季，8-1月为秋季
    if 2 <= today.month <= 7:
        return f"{year}-SPRING"
    else:
        return f"{year}-FALL"


def get_past_semesters() -> list[str]:
    """获取已过期的学期列表（用于清理）"""
    current = get_current_semester()
    parts = current.split("-")
    year, term = int(parts[0]), parts[1]

    past = []
    # 返回之前两个学期的标识
    if term == "SPRING":
        past.append(f"{year-1}-FALL")
        past.append(f"{year-1}-SPRING")
    else:
        past.append(f"{year}-SPRING")
        past.append(f"{year-1}-FALL")

    # 排除当前学期
    return [p for p in past if p != current]
