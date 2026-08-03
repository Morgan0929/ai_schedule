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


async def _extract_and_save_memories(user_input: str, ai_reply: str, user_id: int):
    """Memory Manager: 对话结束后异步提取有价值信息"""
    try:
        from agent_service.memory.memories import MemoryManager
        from agent_service.memory.profile import ProfileManager

        memories = await MemoryManager.extract_from_conversation(user_input, ai_reply)
        for mem in memories:
            await MemoryManager.save(
                user_id=user_id, memory_type=mem["type"],
                content=mem["content"], importance=mem["importance"],
                confidence=mem["confidence"], source="agent",
            )

        if len(user_input) < 20:
            await ProfileManager.set(user_id, "reply_style", "short", confidence=0.6, source="agent")
        elif len(user_input) > 100:
            await ProfileManager.set(user_id, "reply_style", "detailed", confidence=0.6, source="agent")
    except Exception as e:
        logger.debug(f"Memory extraction skipped (non-critical): {e}")


class AgentService:
    """AI Agent 主服务"""

    @staticmethod
    async def chat_stream(request: AgentChatRequest):
        """流式对话 — 执行 LangGraph 工作流 + 流式 Reply"""
        session_id = request.session_id or str(uuid.uuid4())[:8]
        tracer = start_trace(session_id=session_id,
                             user_id=request.user_id or 0,
                             user_input=request.message)

        initial_state: AgentState = {
            "messages": AgentService._build_messages(request.history),
            "user_input": request.message,
            "user_id": request.user_id or 0, "session_id": session_id,
            "intent": "", "sub_tasks": [],
            "calendar_events": [], "external_data": {},
            "conflicts_found": [], "conflict_count": 0,
            "suggestions": [], "recommended_plan": "",
            "final_reply": "", "actions_taken": [], "tasks_created": [], "tasks_updated": [],
            "tool_calls_count": 0, "_tool_history": [], "_compressed_messages": False,
            "error": None,
        }

        try:
            graph = get_agent_graph()
            final_state = await graph.ainvoke(initial_state)

            tracer.add_step("planner",
                input_data={"user_input": request.message[:200]},
                output_data={"intent": final_state.get("intent"),
                             "sub_tasks": final_state.get("sub_tasks", [])[:5]})

            from agent_service.graph.graph import stream_reply
            full_reply = ""
            async for token in stream_reply(final_state):
                full_reply += token
                yield token

            tracer.add_step("reply", output_data={"reply": full_reply[:500]})
            tracer.finish(full_reply)

        except Exception as e:
            logger.exception(f"Agent stream error: {e}")
            yield f"sorry, error: {e}"

    @staticmethod
    def _build_messages(history: list[dict], max_rounds: int = 50) -> list:
        """从 history 构建 messages，保留最近 max_rounds 轮"""
        from langchain_core.messages import HumanMessage, AIMessage
        messages = []
        # 只取最近 100 条 (50 轮), 多的做摘要标记
        recent = history[-max_rounds * 2:] if len(history) > max_rounds * 2 else history
        if len(history) > max_rounds * 2:
            skipped = len(history) - len(recent)
            messages.append(HumanMessage(content=f"[更早的{skipped}条消息已省略]"))
        for m in recent:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role in ("user", "human"):
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))
        return messages

    @staticmethod
    async def chat(request: AgentChatRequest) -> AgentChatResponse:
        """非流式对话 — LangGraph 工作流 + Memory + Trace"""
        session_id = request.session_id or str(uuid.uuid4())[:8]
        tracer = start_trace(session_id=session_id,
                             user_id=request.user_id or 0,
                             user_input=request.message)

        initial_state: AgentState = {
            "messages": AgentService._build_messages(request.history),
            "user_input": request.message,
            "user_id": request.user_id or 0, "session_id": session_id,
            "intent": "", "sub_tasks": [],
            "calendar_events": [], "external_data": {},
            "conflicts_found": [], "conflict_count": 0,
            "suggestions": [], "recommended_plan": "",
            "final_reply": "", "actions_taken": [], "tasks_created": [], "tasks_updated": [],
            "tool_calls_count": 0, "_tool_history": [], "_compressed_messages": False,
            "error": None,
        }

        try:
            # Memory: Load + Summary Check + Prune
            from agent_service.memory.profile import ProfileManager
            from agent_service.memory.working import WorkingMemory
            from agent_service.memory.summarizer import SummaryNode, should_summarize
            from agent_service.memory.pruner import prune_messages

            user_id = request.user_id or 0

            profile_text = await ProfileManager.get_context_text(user_id)
            if profile_text:
                from langchain_core.messages import SystemMessage
                initial_state["messages"].append(SystemMessage(content=profile_text))

            recent_summary = await SummaryNode.load_recent(user_id, days=7)
            if recent_summary:
                from langchain_core.messages import SystemMessage
                initial_state["messages"].append(SystemMessage(content=recent_summary))

            working = await WorkingMemory.get(session_id)
            if working and working.get("intent"):
                initial_state["intent"] = working.get("intent", "")

            if should_summarize(initial_state["messages"]):
                logger.info("Token threshold exceeded, running Summary Node...")
                summary = await SummaryNode.summarize(initial_state["messages"], user_id)
                if summary:
                    await SummaryNode.save_to_db(user_id, summary)
                    initial_state["messages"] = prune_messages(initial_state["messages"])

            # LangGraph
            graph = get_agent_graph()
            final_state = await graph.ainvoke(initial_state)

            await WorkingMemory.save(session_id, "intent", final_state.get("intent"))
            await WorkingMemory.save(session_id, "actions", final_state.get("actions_taken", []))

            # Trace
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

            tracer.add_step("reply", output_data={"reply": reply[:500]})

            # Memory extraction (async, non-blocking)
            import asyncio as _asyncio
            _asyncio.create_task(_extract_and_save_memories(
                user_input=request.message, ai_reply=reply,
                user_id=request.user_id or 0,
            ))

            tracer.finish(reply)

            return AgentChatResponse(
                reply=reply, session_id=session_id,
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
                reply=f"sorry, error: {e}", session_id=session_id,
            )
