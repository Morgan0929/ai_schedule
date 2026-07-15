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


async def _extract_and_save_memories(user_input: str, ai_reply: str, user_id: int):
    """Memory Manager: 对话结束后异步提取有价值信息"""
    try:
        from agent_service.memory.memories import MemoryManager
        from agent_service.memory.profile import ProfileManager

        # 提取值得保存的记忆
        memories = await MemoryManager.extract_from_conversation(user_input, ai_reply)
        for mem in memories:
            await MemoryManager.save(
                user_id=user_id,
                memory_type=mem["type"],
                content=mem["content"],
                importance=mem["importance"],
                confidence=mem["confidence"],
                source="agent",
            )

        # 提取用户画像 (communication style)
        if len(user_input) < 20:
            await ProfileManager.set(user_id, "reply_style", "short",
                                     confidence=0.6, source="agent")
        elif len(user_input) > 100:
            await ProfileManager.set(user_id, "reply_style", "detailed",
                                     confidence=0.6, source="agent")

    except Exception as e:
        logger.debug(f"Memory extraction skipped (non-critical): {e}")


class AgentService:
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
            "actions_taken": [], "tasks_created": [], "tasks_updated": [],
            "tool_calls_count": 0, "_tool_history": [], "_compressed_messages": False,
            "error": None,
        }

        try:
            # === Memory: Load + Summary Check + Prune ===
            from agent_service.memory.profile import ProfileManager
            from agent_service.memory.working import WorkingMemory
            from agent_service.memory.summarizer import SummaryNode, should_summarize
            from agent_service.memory.pruner import prune_messages, filter_tool_messages

            user_id = request.user_id or 0

            # 注入用户画像
            profile_text = await ProfileManager.get_context_text(user_id)
            if profile_text:
                from langchain_core.messages import SystemMessage
                initial_state["messages"].append(SystemMessage(content=profile_text))

            # 注入近期摘要
            recent_summary = await SummaryNode.load_recent(user_id, days=7)
            if recent_summary:
                from langchain_core.messages import SystemMessage
                initial_state["messages"].append(SystemMessage(content=recent_summary))

            # 恢复工作记忆
            working = await WorkingMemory.get(session_id)
            if working and working.get("intent"):
                initial_state["intent"] = working.get("intent", "")

            # Token 检查: 超过阈值则触发摘要
            if should_summarize(initial_state["messages"]):
                logger.info("Token threshold exceeded, running Summary Node...")
                summary = await SummaryNode.summarize(initial_state["messages"], user_id)
                if summary:
                    # 保存摘要
                    await SummaryNode.save_to_db(user_id, summary)
                    # 裁剪消息
                    initial_state["messages"] = prune_messages(initial_state["messages"])

            # 执行 LangGraph 工作流
            graph = get_agent_graph()
            final_state = await graph.ainvoke(initial_state)

            # === Save Working Memory ===
            await WorkingMemory.save(session_id, "intent", final_state.get("intent"))
            await WorkingMemory.save(session_id, "actions", final_state.get("actions_taken", []))

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

            # === Memory Extraction (对话结束后异步提取) ===
            import asyncio as _asyncio
            _asyncio.create_task(_extract_and_save_memories(user_input=request.message,
                                                            ai_reply=reply,
                                                            user_id=request.user_id or 0))

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
