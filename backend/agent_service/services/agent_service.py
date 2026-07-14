"""
Agent 编排服务 — 核心对话入口

接收用户自然语言 → LangGraph 工作流 → 返回结构化响应
每次对话全程 Trace 记录
"""
import uuid
import logging
from typing import Any
from common.schemas.agent import AgentChatRequest, AgentChatResponse, AgentSuggestion
from agent_service.graph.graph import get_agent_graph
from agent_service.graph.state import AgentState
from agent_service.llm.deepseek_client import is_llm_available
from agent_service.utils.tracer import start_trace

logger = logging.getLogger(__name__)


class AgentService:
    """AI Agent 主服务"""

    @staticmethod
    async def chat_stream(request: AgentChatRequest):
        """
        流式对话 — 执行 LangGraph 工作流 + 流式 Reply

        Yields: str (逐 token, 用于 SSE)
        """
        session_id = request.session_id or str(uuid.uuid4())[:8]
        tracer = start_trace(session_id=session_id,
                             user_id=request.user_id or 0,
                             user_input=request.message)

        initial_state: AgentState = {
            "messages": [], "user_input": request.message,
            "user_id": request.user_id or 0, "session_id": session_id,
            "intent": "", "sub_tasks": [],
            "calendar_events": [], "external_data": {},
            "conflicts_found": [], "conflict_count": 0,
            "suggestions": [], "recommended_plan": "",
            "final_reply": "", "actions_taken": [], "tasks_created": [], "tasks_updated": [],
            "error": None,
        }

        try:
            graph = get_agent_graph()
            final_state = await graph.ainvoke(initial_state)

            tracer.add_step("planner",
                input_data={"user_input": request.message[:200]},
                output_data={"intent": final_state.get("intent"),
                             "sub_tasks": final_state.get("sub_tasks", [])[:5]})

            # 流式输出 Reply
            from agent_service.graph.graph import stream_reply
            full_reply = ""
            async for token in stream_reply(final_state):
                full_reply += token
                yield token

            tracer.add_step("reply", output_data={"reply": full_reply[:500]})
            tracer.finish(full_reply)

        except Exception as e:
            logger.exception(f"Agent stream error: {e}")
            yield f"抱歉，处理时遇到问题：{e}"


    @staticmethod
    async def chat(request: AgentChatRequest) -> AgentChatResponse:
        """
        处理一次 Agent 对话（非流式）

        完整工作流 + Trace:
        1. Planner 解析意图   → trace
        2. Tools 执行操作      → trace
        3. Conflict 冲突检测   → trace
        4. Coordinator 协调    → trace
        5. Reply 生成回复      → trace
        """
        session_id = request.session_id or str(uuid.uuid4())[:8]

        tracer = start_trace(
            session_id=session_id,
            user_id=request.user_id or 0,
            user_input=request.message,
        )

        initial_state: AgentState = {
            "messages": [],
            "user_input": request.message,
            "user_id": request.user_id or 0,
            "session_id": session_id,
            "intent": "",
            "sub_tasks": [],
            "calendar_events": [],
            "external_data": {},
            "conflicts_found": [],
            "conflict_count": 0,
            "suggestions": [],
            "recommended_plan": "",
            "final_reply": "",
            "actions_taken": [],
            "tasks_created": [],
            "tasks_updated": [],
            "error": None,
        }

        try:
            # 执行 LangGraph 工作流
            graph = get_agent_graph()
            final_state = await graph.ainvoke(initial_state)

            # === Trace 各步骤 ===
            tracer.add_step("planner",
                input_data={"user_input": request.message[:200]},
                output_data={"intent": final_state.get("intent"),
                             "sub_tasks": final_state.get("sub_tasks", [])[:5]})

            if final_state.get("actions_taken"):
                tracer.add_step("tools",
                    input_data={"sub_tasks": final_state.get("sub_tasks", [])[:5]},
                    output_data={"actions": final_state.get("actions_taken"),
                                 "tasks_created": final_state.get("tasks_created")})

            if final_state.get("conflicts_found"):
                tracer.add_step("conflict",
                    output_data={"conflicts": final_state.get("conflicts_found"),
                                 "count": final_state.get("conflict_count")})

            if final_state.get("suggestions"):
                tracer.add_step("coordinator",
                    output_data={"suggestions": final_state.get("suggestions"),
                                 "recommended": final_state.get("recommended_plan")})

            # 构建响应
            suggestions = []
            for s in final_state.get("suggestions", []):
                suggestions.append(AgentSuggestion(
                    plan_id=s.get("plan_id", "?"),
                    title=s.get("title", ""),
                    description=s.get("description", ""),
                    impact=s.get("impact", ""),
                    is_recommended=s.get("is_recommended", False),
                ))

            reply = final_state.get("final_reply", "")
            if not is_llm_available() and "mock" not in reply.lower():
                reply += "\n\n💡 提示：配置 DeepSeek API Key 后可使用完整 AI 能力。"

            tracer.add_step("reply",
                output_data={"reply": reply[:500]})

            # === 结束 Trace ===
            tracer.finish(reply)

            return AgentChatResponse(
                reply=reply,
                session_id=session_id,
                conflicts=final_state.get("conflicts_found", []),
                suggestions=suggestions,
                tasks_created=final_state.get("tasks_created", []),
                tasks_updated=final_state.get("tasks_updated", []),
                actions_taken=final_state.get("actions_taken", []),
            )

        except Exception as e:
            logger.exception(f"Agent chat error: {e}")
            tracer.add_step("error", success=False, error=str(e))
            tracer.finish(f"Error: {e}")
            return AgentChatResponse(
                reply=f"抱歉，处理您的请求时遇到了问题：{e}\n\n请稍后重试或换一种方式描述。",
                session_id=session_id,
            )
