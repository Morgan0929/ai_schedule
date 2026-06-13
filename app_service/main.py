"""
app-service 入口 — API 网关 & 用户认证
端口 8000
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from common.config import settings
from common.exceptions import AppException
from common.models.response import Result


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
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
    return JSONResponse(
        status_code=500,
        content=Result.error(500, f"服务器内部错误: {str(exc)}").model_dump(),
    )


# ============ 健康检查 ============
@app.get("/health", response_model=Result)
async def health_check():
    return Result.success({"status": "ok", "service": "app-service"})


# ============ 用户 API ============
@app.post("/api/v1/auth/login", response_model=Result)
async def login():
    """用户登录（待实现）"""
    return Result.success({"message": "登录功能待实现"})


@app.post("/api/v1/auth/register", response_model=Result)
async def register():
    """用户注册（待实现）"""
    return Result.success({"message": "注册功能待实现"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.APP_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
