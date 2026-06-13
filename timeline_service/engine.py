"""
时间线引擎核心

将零散任务按时间排序，生成可视化时间线结构
"""
from datetime import date, datetime, timedelta
from common.models.timeline import TimelineEvent
from timeline_service.models import TaskModel


class TimelineEngine:
    """时间线引擎"""

    @staticmethod
    def build_timeline(tasks: list[TaskModel], target_date: date) -> list[TimelineEvent]:
        """
        将任务列表转换为时间线事件列表

        Args:
            tasks: 当天或跨天的任务列表
            target_date: 目标日期

        Returns:
            按时间排序的事件列表
        """
        events: list[TimelineEvent] = []

        for task in tasks:
            # 确定任务在目标日期的时间范围
            task_date = task.start_time.date()

            if task_date == target_date:
                start_str = task.start_time.strftime("%H:%M")
                duration = int((task.end_time - task.start_time).total_seconds() // 60)
            elif task_date < target_date:
                # 跨天任务，从 00:00 开始
                start_str = "00:00"
                day_end = datetime.combine(target_date, datetime.max.time())
                duration = int((min(task.end_time, day_end) - datetime.combine(target_date, datetime.min.time())).total_seconds() // 60)
            else:
                continue  # 未来任务，不在目标日期范围内

            events.append(TimelineEvent(
                time=start_str,
                duration=max(duration, 0),
                event=task.title,
                task_id=task.id,
                category=task.category,
                location=task.location,
                priority=task.priority,
            ))

        # 按时间排序
        events.sort(key=lambda e: e.time)
        return events

    @staticmethod
    def add_buffer(events: list[TimelineEvent], buffer_minutes: int = 15) -> list[TimelineEvent]:
        """
        在事件之间插入缓冲时间块

        Args:
            events: 已排序的事件列表
            buffer_minutes: 缓冲时间（分钟）

        Returns:
            包含缓冲块的事件列表
        """
        if not events or len(events) < 2:
            return events

        result: list[TimelineEvent] = []
        for i, event in enumerate(events):
            result.append(event)
            if i < len(events) - 1:
                # 检查两个事件之间是否需要缓冲
                current_end = TimelineEngine._time_to_minutes(event.time) + event.duration
                next_start = TimelineEngine._time_to_minutes(events[i + 1].time)
                gap = next_start - current_end
                if 0 < gap < buffer_minutes:
                    result.append(TimelineEvent(
                        time=TimelineEngine._minutes_to_time(current_end),
                        duration=g gap,
                        event="[缓冲时间]",
                        category="PERSONAL",
                        priority="LOW",
                    ))

        return result

    @staticmethod
    def _time_to_minutes(time_str: str) -> int:
        """将 'HH:MM' 转为分钟数"""
        h, m = time_str.split(":")
        return int(h) * 60 + int(m)

    @staticmethod
    def _minutes_to_time(minutes: int) -> str:
        """将分钟数转为 'HH:MM'"""
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"
