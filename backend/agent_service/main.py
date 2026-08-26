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
from fastapi import Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.config import settings
from common.database import init_db
from common.exceptions import AppException
from common.schemas.response import Result
from common.schemas.agent import AgentChatRequest, AgentChatResponse

# 确保所有 ORM 模型在 init_db() 前导入
import timeline_service.models.task_model  # noqa: F401
import timeline_service.models.schedule_model  # noqa: F401
import crawler_service.models.crawl_model  # noqa: F401
import app_service.models.user_model     # noqa: F401

from agent_service.services.agent_service import AgentService
from agent_service.llm.deepseek_client import is_llm_available

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    await init_db()
    from agent_service.mcp.client import init_mcp_servers, list_all_mcp_tools
    mcp_servers = init_mcp_servers()
    mcp_tools = list_all_mcp_tools()
    mode = "LLM (DeepSeek)" if is_llm_available() else "Mock (规则引擎)"
    logger.info(f"Agent started — Mode: {mode} | MCP: {mcp_servers} ({len(mcp_tools)} tools)")
    yield


app = FastAPI(
    title="AI Schedule Agent — Agent Service",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
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
    import json
    from fastapi.responses import StreamingResponse

    async def generate():
        async for event in AgentService.chat_stream(request):
            event_type = event.get("type", "token")
            payload = json.dumps(event, ensure_ascii=True, default=str)
            yield f"event: {event_type}\ndata: {payload}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream; charset=utf-8",
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


@app.get("/api/v1/agent/history", response_model=Result)
async def get_agent_history(
    user_id: int = Query(..., description="用户 ID"),
    session_id: str | None = Query(None, description="会话 ID（可选）"),
):
    from sqlalchemy import text
    from common.database import async_session_factory
    from agent_service.utils.tracer import _stable_session_uuid

    async with async_session_factory() as db:
        if session_id:
            session_key = _stable_session_uuid(session_id)
            result = await db.execute(text(
                "SELECT messages FROM agent_session WHERE id = :id AND user_id = :user_id"
            ), {"id": session_key, "user_id": user_id})
        else:
            result = await db.execute(text(
                "SELECT messages FROM agent_session WHERE user_id = :user_id ORDER BY updated_at DESC LIMIT 1"
            ), {"user_id": user_id})
        row = result.first()
    messages = row[0] if row else []
    return Result.success(messages[-100:] if isinstance(messages, list) else [])


@app.delete("/api/v1/agent/history", response_model=Result)
async def clear_agent_history(
    user_id: int = Query(..., description="用户 ID"),
    session_id: str | None = Query(None, description="会话 ID（可选）"),
):
    from sqlalchemy import text
    from common.database import async_session_factory
    from agent_service.utils.tracer import _stable_session_uuid

    async with async_session_factory() as db:
        if session_id:
            session_key = _stable_session_uuid(session_id)
            await db.execute(text(
                "DELETE FROM agent_session WHERE id = :id AND user_id = :user_id"
            ), {"id": session_key, "user_id": user_id})
        else:
            await db.execute(text(
                "DELETE FROM agent_session WHERE user_id = :user_id"
            ), {"user_id": user_id})
        await db.commit()
    return Result.success(None, "对话历史已清空")


@app.get("/api/v1/todos", response_model=Result)
async def list_todos(user_id: int = Query(..., description="用户 ID")):
    from agent_service.graph.todo_service import list_todos as list_active_todos

    todos = await list_active_todos(user_id, status="ACTIVE")
    return Result.success(todos)


@app.get("/api/v1/todos/history", response_model=Result)
async def list_todo_history(
    user_id: int = Query(..., description="用户 ID"),
    limit: int = Query(50, ge=1, le=100, description="返回数量"),
):
    from agent_service.graph.todo_service import list_todo_history as list_history

    return Result.success(await list_history(user_id, limit=limit))


@app.put("/api/v1/todos/{todo_id}/done", response_model=Result)
async def complete_todo(todo_id: int, user_id: int = Query(..., description="用户 ID")):
    from agent_service.graph.todo_service import complete_todo as mark_done

    return Result.success(await mark_done(user_id, todo_id=todo_id))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.AGENT_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
