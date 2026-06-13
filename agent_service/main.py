"""
agent-service 入口 — AI Agent 核心 (LangGraph + DeepSeek)
端口 8002
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
from common.models.agent import AgentChatRequest, AgentChatResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="AI Schedule Agent — Agent Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.code,
        content=Result.error(exc.code, exc.message).model_dump(),
    )


@app.get("/health", response_model=Result)
async def health_check():
    return Result.success({"status": "ok", "service": "agent-service"})


# ============ Agent 对话 API（核心） ============
@app.post("/api/v1/agent/chat", response_model=Result)
async def agent_chat(request: AgentChatRequest):
    """
    Agent 对话入口

    工作流：
    1. Planner — 分析意图，拆解子任务
    2. Tools — 查询日历/客户安排/天气/航班
    3. ConflictDetector — 检查时间冲突
    4. Coordinator — AI 协调生成多方案
    5. Reply — 格式化回复
    """
    # TODO: 接入 LangGraph 编排
    return Result.success(AgentChatResponse(
        reply=f"收到您的消息：{request.message}\n\nAgent 核心功能正在开发中...",
        session_id=request.session_id or "new-session",
    ).model_dump())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.AGENT_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
