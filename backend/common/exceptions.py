"""
全局异常定义
"""
from typing import Any


class AppException(Exception):
    """应用基础异常"""

    def __init__(self, code: int, message: str, detail: Any = None):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


class NotFoundException(AppException):
    """资源未找到"""

    def __init__(self, resource: str, identifier: Any = None):
        super().__init__(
            code=404,
            message=f"{resource} 未找到" + (f": {identifier}" if identifier else ""),
        )


class BadRequestException(AppException):
    """请求参数错误"""

    def __init__(self, message: str = "请求参数错误", detail: Any = None):
        super().__init__(code=400, message=message, detail=detail)


class UnauthorizedException(AppException):
    """未认证"""

    def __init__(self, message: str = "未登录或登录已过期"):
        super().__init__(code=401, message=message)


class ForbiddenException(AppException):
    """无权限"""

    def __init__(self, message: str = "无访问权限"):
        super().__init__(code=403, message=message)


class ConflictException(AppException):
    """冲突异常 — 日程冲突时使用"""

    def __init__(self, message: str = "存在时间冲突", detail: Any = None):
        super().__init__(code=409, message=message, detail=detail)


class ServiceUnavailableException(AppException):
    """服务不可用"""

    def __init__(self, service: str):
        super().__init__(code=503, message=f"服务 {service} 暂时不可用")


class AIServiceException(AppException):
    """AI 服务异常"""

    def __init__(self, message: str = "AI 服务处理失败", detail: Any = None):
        super().__init__(code=502, message=message, detail=detail)
