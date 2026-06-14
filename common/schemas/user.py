"""
用户模型
"""
from datetime import datetime
from pydantic import BaseModel, Field


class UserDTO(BaseModel):
    """用户响应"""
    id: int
    username: str
    email: str | None = None
    role: str = "USER"
    avatar_url: str | None = None
    is_active: bool = True
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserCreateDTO(BaseModel):
    """创建用户请求"""
    username: str = Field(..., min_length=2, max_length=64, description="用户名")
    email: str | None = Field(None, max_length=128, description="邮箱")
    password: str = Field(..., min_length=6, description="密码")
    role: str = Field(default="USER", pattern=r"^(ADMIN|USER)$")


class UserLoginDTO(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResultDTO(BaseModel):
    """登录响应"""
    token: str
    token_type: str = "Bearer"
    user: UserDTO
