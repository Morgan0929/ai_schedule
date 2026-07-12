"""
Pydantic 模型 — 统一响应
"""
from typing import Any, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    """统一响应格式，对标 Java 项目的 Result 类"""

    code: int = 200
    message: str = "success"
    data: T | None = None

    @classmethod
    def success(cls, data: T = None, message: str = "success") -> "Result[T]":
        return cls(code=200, message=message, data=data)

    @classmethod
    def created(cls, data: T = None, message: str = "创建成功") -> "Result[T]":
        return cls(code=201, message=message, data=data)

    @classmethod
    def bad_request(cls, message: str = "请求参数错误") -> "Result[None]":
        return cls(code=400, message=message, data=None)

    @classmethod
    def not_found(cls, message: str = "资源不存在") -> "Result[None]":
        return cls(code=404, message=message, data=None)

    @classmethod
    def conflict(cls, message: str = "存在冲突") -> "Result[None]":
        return cls(code=409, message=message, data=None)

    @classmethod
    def error(cls, code: int = 500, message: str = "服务器内部错误") -> "Result[None]":
        return cls(code=code, message=message, data=None)

    def is_success(self) -> bool:
        return self.code in (200, 201)


class PageResult(BaseModel, Generic[T]):
    """分页响应"""

    items: list[T] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0

    @classmethod
    def of(cls, items: list[T], total: int, page: int, page_size: int) -> "PageResult[T]":
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(items=items, total=total, page=page, page_size=page_size, total_pages=total_pages)
