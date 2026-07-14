"""
agent_service 入口 — AI Agent 核心 (LangGraph + DeepSeek)
端口 8002
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.config import settings
from common.database import init_db
from common.exceptions import AppException
from common.schemas.response import Result
from common.schemas.agent import AgentChatRequest, AgentChatResponse

# 确保所有 ORM 模型在 init_db() 前导入
import timeline_service.models.task_model  # noqa: F401
import crawler_service.models.crawl_model  # noqa: F401
import app_service.models.user_model     # noqa: F401

from agent_service.services.agent_service import AgentService
from agent_service.llm.deepseek_client import is_llm_available

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    await init_db()
    mode = "LLM (DeepSeek)" if is_llm_available() else "Mock (规则引擎)"
    logger.info(f"Agent service started — 模式: {mode}")
    yield


app = FastAPI(
    title="AI Schedule Agent — Agent Service",
    version="0.2.0",
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content=Result.error(500, str(exc)).model_dump(),
    )


# ============ 健康检查 ============
@app.get("/health", response_model=Result)
async def health_check():
    return Result.success({
        "status": "ok",
        "service": "agent-service",
        "mode": "llm" if is_llm_available() else "mock",
    })


# ============ Agent 对话 API（核心） ============
@app.post("/api/v1/agent/chat", response_model=Result)
async def agent_chat(request: AgentChatRequest):
    """
    非流式对话 — 返回完整 JSON 响应
    """
    response = await AgentService.chat(request)
    return Result.success(response.model_dump())


@app.post("/api/v1/agent/chat/stream")
async def agent_chat_stream(request: AgentChatRequest):
    """
    流式对话 — SSE (Server-Sent Events) 逐 token 输出

    前端调用:
        const eventSource = new EventSource('/api/v1/agent/chat/stream');
        eventSource.onmessage = (e) => { appendText(e.data); };
    """
    from fastapi.responses import StreamingResponse

    async def generate():
        async for token in AgentService.chat_stream(request):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/v1/agent/mode", response_model=Result)
async def get_mode():
    """获取当前 Agent 运行模式"""
    return Result.success({
        "mode": "llm" if is_llm_available() else "mock",
        "model": settings.DEEPSEEK_MODEL if is_llm_available() else "rule-engine",
        "features": {
            "intent_recognition": True,
            "task_crud": True,
            "conflict_detection": True,
            "coordination": "llm" if is_llm_available() else "template",
            "weather_query": True,
            "natural_language_understanding": is_llm_available(),
        },
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.AGENT_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
