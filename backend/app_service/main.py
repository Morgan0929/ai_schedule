"""
app_service 入口 — API 网关 & 用户认证
端口 8000
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import settings
from common.database import get_db, init_db
from common.exceptions import AppException, UnauthorizedException
from common.schemas.response import Result, PageResult
from common.schemas.user import UserCreateDTO, UserLoginDTO

from app_service.services.user_service import UserService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表，关闭时释放资源"""
    await init_db()
    # 创建默认 admin 账号
    from app_service.models.user_model import UserModel
    from common.utils.password import hash_password
    from common.database import async_session_factory
    async with async_session_factory() as db:
        from app_service.repository.user_repo import UserRepository
        repo = UserRepository(db)
        existing = await repo.find_by_username("admin")
        if not existing:
            admin = UserModel(
                username="admin",
                email="admin@example.com",
                password_hash=hash_password("<CHANGE_ME>"),
                role="ADMIN",
            )
            db.add(admin)
            await db.commit()
            print("[Init] 默认 admin 账号已创建 (admin / <CHANGE_ME>)")
    yield


app = FastAPI(
    title="AI Schedule Agent — API Gateway",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.code,
        content=Result.error(exc.code, exc.message).model_dump(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content=Result.error(500, f"服务器内部错误: {str(exc)}").model_dump(),
    )


# ============ 健康检查 ============
@app.get("/health", response_model=Result)
async def health_check():
    return Result.success({"status": "ok", "service": "app-service"})


# ============ 用户 API ============
@app.post("/api/v1/auth/register", response_model=Result)
async def register(dto: UserCreateDTO, db: AsyncSession = Depends(get_db)):
    """用户注册"""
    service = UserService(db)
    user = await service.register(dto)
    return Result.created(user.model_dump())


@app.post("/api/v1/auth/login", response_model=Result)
async def login(dto: UserLoginDTO, db: AsyncSession = Depends(get_db)):
    """用户登录"""
    service = UserService(db)
    result = await service.login(dto)
    return Result.success(result.model_dump())


@app.get("/api/v1/users/me", response_model=Result)
async def get_current_user_info(
    user_id: int = Query(..., description="用户 ID（后续改为 JWT 解析）"),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户信息（临时用 user_id 参数，后续从 JWT 解析）"""
    service = UserService(db)
    user = await service.get_user(user_id)
    return Result.success(user.model_dump())


@app.get("/api/v1/users", response_model=Result)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """分页查询用户列表"""
    service = UserService(db)
    users, total = await service.list_users(page, page_size)
    return Result.success(PageResult.of(users, total, page, page_size).model_dump())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.APP_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
