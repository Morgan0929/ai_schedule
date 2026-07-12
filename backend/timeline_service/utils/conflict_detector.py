"""
冲突检测引擎

核心规则：
1. 时间重叠：task_a.end > task_b.start → 冲突
2. 优先级排序：HIGH > MEDIUM > LOW
3. 地点冲突：同一时间段不同地点 → 物理不可达
4. 缓冲时间：相邻任务至少 15 分钟
"""
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from timeline_service.models.task_model import TaskModel


class ConflictSeverity(str, Enum):
    CRITICAL = "CRITICAL"   # 高优先级任务被冲突
    WARNING = "WARNING"     # 普通冲突
    INFO = "INFO"           # 低优先级或缓冲冲突


class PriorityWeight:
    """优先级权重"""
    HIGH = 3
    MEDIUM = 2
    LOW = 1


@dataclass
class DetectedConflict:
    """检测到的冲突"""
    user_id: int
    task_a_id: int
    task_b_id: int
    task_a_title: str
    task_b_title: str
    overlap_start: datetime
    overlap_end: datetime
    severity: ConflictSeverity
    reason: str
    suggested_resolution: str = ""


@dataclass
class ConflictReport:
    """冲突检测报告"""
    user_id: int
    conflicts: list[DetectedConflict] = field(default_factory=list)
    total_conflicts: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0

    def add_conflict(self, conflict: DetectedConflict):
        self.conflicts.append(conflict)
        self.total_conflicts += 1
        if conflict.severity == ConflictSeverity.CRITICAL:
            self.critical_count += 1
        elif conflict.severity == ConflictSeverity.WARNING:
            self.warning_count += 1
        else:
            self.info_count += 1


class ConflictDetector:
    """冲突检测引擎"""

    def __init__(self, buffer_minutes: int = 15):
        self.buffer_minutes = buffer_minutes

    def detect(self, tasks: list[TaskModel]) -> ConflictReport:
        """
        检测任务列表中的所有冲突
        """
        report = ConflictReport(user_id=tasks[0].user_id if tasks else 0)

        if len(tasks) < 2:
            return report

        # 按开始时间排序
        sorted_tasks = sorted(tasks, key=lambda t: t.start_time)

        for i in range(len(sorted_tasks)):
            for j in range(i + 1, len(sorted_tasks)):
                conflict = self._check_pair(sorted_tasks[i], sorted_tasks[j])
                if conflict:
                    report.add_conflict(conflict)

        return report

    def _check_pair(self, task_a: TaskModel, task_b: TaskModel) -> DetectedConflict | None:
        """检查两个任务之间是否存在冲突"""
        # 规则 1：时间重叠检测
        if task_a.end_time <= task_b.start_time or task_b.end_time <= task_a.start_time:
            return None  # 无重叠

        # 计算重叠区间
        overlap_start = max(task_a.start_time, task_b.start_time)
        overlap_end = min(task_a.end_time, task_b.end_time)

        # 规则 2：根据优先级判定严重程度
        severity = self._calculate_severity(task_a, task_b)
        reason = self._build_reason(task_a, task_b, overlap_start, overlap_end)

        return DetectedConflict(
            user_id=task_a.user_id,
            task_a_id=task_a.id,
            task_b_id=task_b.id,
            task_a_title=task_a.title,
            task_b_title=task_b.title,
            overlap_start=overlap_start,
            overlap_end=overlap_end,
            severity=severity,
            reason=reason,
        )

    def _calculate_severity(self, task_a: TaskModel, task_b: TaskModel) -> ConflictSeverity:
        """计算冲突严重程度"""
        a_weight = getattr(PriorityWeight, task_a.priority, PriorityWeight.MEDIUM)
        b_weight = getattr(PriorityWeight, task_b.priority, PriorityWeight.MEDIUM)

        # 两个高优先级任务冲突 → CRITICAL
        if a_weight == PriorityWeight.HIGH and b_weight == PriorityWeight.HIGH:
            return ConflictSeverity.CRITICAL
        # 一个高优先级 → WARNING
        elif a_weight == PriorityWeight.HIGH or b_weight == PriorityWeight.HIGH:
            return ConflictSeverity.WARNING
        # 两个低优先级 → INFO
        else:
            return ConflictSeverity.INFO

    def _build_reason(self, task_a: TaskModel, task_b: TaskModel,
                      overlap_start: datetime, overlap_end: datetime) -> str:
        """构建冲突原因描述"""
        overlap_minutes = int((overlap_end - overlap_start).total_seconds() // 60)
        return (
            f"「{task_a.title}」({task_a.start_time.strftime('%H:%M')}-{task_a.end_time.strftime('%H:%M')})"
            f" 与 「{task_b.title}」({task_b.start_time.strftime('%H:%M')}-{task_b.end_time.strftime('%H:%M')})"
            f" 重叠 {overlap_minutes} 分钟"
        )

    def _check_location_conflict(self, task_a: TaskModel, task_b: TaskModel) -> bool:
        """检查地点冲突：同一时间段不同地点"""
        if not task_a.location or not task_b.location:
            return False
        if task_a.location == task_b.location:
            return False
        # 检查任务是否在时间上相近
        time_gap = abs((task_a.end_time - task_b.start_time).total_seconds())
        return time_gap < self.buffer_minutes * 60  # 缓冲时间内需要切换地点
