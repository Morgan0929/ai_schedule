"""
爬虫基类 — 所有爬虫继承此类
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SpiderResult:
    """爬虫返回的标准化结果"""
    source: str
    title: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)
    crawled_at: str = field(default_factory=lambda: datetime.now().isoformat())
    success: bool = True
    error: str = ""


class BaseSpider(ABC):
    """爬虫抽象基类"""

    # 子类必须定义
    name: str = "base"
    description: str = "基础爬虫"
    version: str = "1.0.0"

    @abstractmethod
    async def crawl(self, **params) -> SpiderResult:
        """
        执行爬取，返回标准化结果

        Args:
            **params: 爬虫特定参数（如城市名、日期等）

        Returns:
            SpiderResult: 标准化爬取结果
        """
        pass

    def get_info(self) -> dict[str, str]:
        """返回爬虫元信息"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
        }

    @staticmethod
    def error_result(source: str, error: str) -> SpiderResult:
        """快速创建错误结果"""
        return SpiderResult(
            source=source,
            title=f"Error: {error[:50]}",
            success=False,
            error=error,
        )
