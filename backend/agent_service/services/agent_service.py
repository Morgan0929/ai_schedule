"""
Agent 编排服务 — 核心对话入口

接收用户自然语言 → LangGraph 工作流 → 返回结构化响应
每次对话全程 Trace 记录
"""
import asyncio
import uuid
import logging
import time
from typing import Any
from common.schemas.agent import AgentChatRequest, AgentChatResponse, AgentSuggestion
from agent_service.graph.graph import get_agent_graph
from agent_service.graph.state import AgentState
from agent_service.llm.deepseek_client import is_llm_available
from agent_service.utils.tracer import start_trace
from agent_service.utils.runtime import (
    BACKGROUND_TASK_GOVERNOR,
    guarded_session,
    normalize_session_id,
)

logger = logging.getLogger(__name__)


async def _load_valid_pending_tasks(working: dict) -> list[dict]:
    """过滤已提交/已过期的 PendingTask, 清理旧版本遗留的工作记忆。"""
    pending_tasks = working.get("pending_tasks", []) or []
    if not pending_tasks:
        return []

    try:
        from agent_service.graph.pending_task import get_pending
        valid = []
        for task in pending_tasks:
            ref_id = task.get("ref_id", "")
            if not ref_id or await get_pending(ref_id):
                valid.append(task)
        return valid
    except Exception as e:
        logger.debug(f"Pending task validation skipped: {e}")
        return pending_tasks


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


def _confirmation_stage(final_state: dict) -> str:
    """Return the structured stage used by clients for confirmation controls."""
    pending = final_state.get("pending_action") or {}
    if pending.get("type") == "conflict_resolution":
        return pending.get("stage", "") or ""
    if final_state.get("needs_confirmation"):
        return "clarification"
    return ""


def _needs_confirm_button(final_state: dict) -> bool:
    """Only waiting_confirm should show Agree/Cancel shortcut buttons."""
    return _confirmation_stage(final_state) == "waiting_confirm"


class AgentService:
    """AI Agent 主服务"""

    @staticmethod
    async def chat_stream(request: AgentChatRequest):
        """流式对话 — 执行 LangGraph 工作流 + SSE 事件"""
        session_id = normalize_session_id(request.session_id, request.user_id)
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
            async with guarded_session(session_id):
                # Load working memory
                try:
                    from agent_service.memory.working import WorkingMemory
                    working = await WorkingMemory.get(session_id)
                    if working:
                        initial_state["active_flow"] = working.get("active_flow")
                        initial_state["pending_tasks"] = await _load_valid_pending_tasks(working)
                        conflict = working.get("conflict")
                        if conflict:
                            initial_state["pending_action"] = conflict
                            initial_state["active_flow"] = "conflict_resolution"
                except Exception as e:
                    logger.debug(f"Redis load failed: {e}")

                # Flush expired pending todos → PostgreSQL
                try:
                    from agent_service.graph.pending_task import flush_expired_todos
                    await BACKGROUND_TASK_GOVERNOR.spawn(
                        flush_expired_todos(request.user_id or 0),
                        name="flush-expired-todos",
                    )
                except Exception as e:
                    logger.debug(f"Todo flush skipped: {e}")

                graph = get_agent_graph()
                final_state = await asyncio.wait_for(graph.ainvoke(initial_state), timeout=45.0)

                # Sync working memory before releasing the session lock.
                try:
                    from agent_service.memory.working import WorkingMemory
                    flow = final_state.get("active_flow")
                    if flow == "conflict_resolution":
                        await WorkingMemory.save(session_id, "active_flow", flow)
                        conflict = final_state.get("pending_action")
                        if conflict and conflict.get("type") == "conflict_resolution":
                            await WorkingMemory.save(session_id, "conflict", conflict)
                    else:
                        await WorkingMemory.delete_key(session_id, "active_flow")
                        await WorkingMemory.delete_key(session_id, "conflict")
                    ptasks = final_state.get("pending_tasks", [])
                    if ptasks:
                        await WorkingMemory.save(session_id, "pending_tasks", ptasks)
                    else:
                        await WorkingMemory.delete_key(session_id, "pending_tasks")
                except Exception as e:
                    logger.debug(f"Redis save failed: {e}")

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

            from agent_service.graph.graph import stream_reply
            full_reply = ""
            async for token in stream_reply(final_state):
                full_reply += token
                yield {"type": "token", "content": token}

            tracer.add_step("reply", output_data={"reply": full_reply[:500]})

            BACKGROUND_TASK_GOVERNOR.submit(
                _extract_and_save_memories(
                    user_input=request.message, ai_reply=full_reply,
                    user_id=request.user_id or 0,
                ),
                name="extract-memories",
            )
            tracer.finish(full_reply)

            response = AgentService._response_from_state(
                session_id=session_id,
                final_state=final_state,
                reply=full_reply,
            )
            yield {"type": "done", "data": response.model_dump()}

        except Exception as e:
            logger.exception(f"Agent stream error: {e}")
            tracer.add_step("error", success=False, error=str(e))
            tracer.finish(f"Error: {e}")
            yield {"type": "error", "message": f"sorry, error: {e}"}

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
        session_id = normalize_session_id(request.session_id, request.user_id)
        print(f"SESSION ID: {session_id} (from_request={'YES' if request.session_id else 'AUTO'})")
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

        t_start = time.perf_counter()

        try:
            from agent_service.memory.working import WorkingMemory
            from agent_service.memory.summarizer import SummaryNode, should_summarize
            from agent_service.memory.pruner import prune_messages

            user_id = request.user_id or 0

            async with guarded_session(session_id):
                print(f"[TIMING] setup={(time.perf_counter() - t_start) * 1000:.0f}ms")

                # Load working memory (三层: active_flow / pending_tasks / conflict)
                t_working = time.perf_counter()
                working = await WorkingMemory.get(session_id)
                print(f"[TIMING] working_memory={(time.perf_counter() - t_working) * 1000:.0f}ms")
                if working:
                    print(f"[REDIS] load flow={working.get('active_flow')} ptasks={len(working.get('pending_tasks',[]))} conflict={'yes' if working.get('conflict') else 'no'}")
                if working:
                    initial_state["active_flow"] = working.get("active_flow")
                    initial_state["pending_tasks"] = await _load_valid_pending_tasks(working)
                    conflict = working.get("conflict")
                    if conflict:
                        initial_state["pending_action"] = conflict
                        initial_state["active_flow"] = "conflict_resolution"
                else:
                    print("No working memory (new session)")

                # Flush expired pending todos → PostgreSQL
                try:
                    from agent_service.graph.pending_task import flush_expired_todos
                    await BACKGROUND_TASK_GOVERNOR.spawn(
                        flush_expired_todos(user_id),
                        name="flush-expired-todos",
                    )
                except Exception as e:
                    logger.debug(f"Todo flush skipped: {e}")

                if should_summarize(initial_state["messages"]):
                    logger.info("Token threshold exceeded, running Summary Node...")
                    summary = await SummaryNode.summarize(initial_state["messages"], user_id)
                    if summary:
                        await SummaryNode.save_to_db(user_id, summary)
                        initial_state["messages"] = prune_messages(initial_state["messages"])

                # LangGraph
                graph = get_agent_graph()
                t_graph = time.perf_counter()
                final_state = await asyncio.wait_for(graph.ainvoke(initial_state), timeout=45.0)
                print(f"[TIMING] graph={(time.perf_counter() - t_graph) * 1000:.0f}ms")

                # Sync working memory (pause/resume 支持) before releasing the lock.
                flow = final_state.get("active_flow")
                flow_paused = final_state.get("_flow_paused")

                if flow_paused:
                    # Interrupt: 保留暂停的 conflict, 等下次恢复
                    paused = final_state.get("_paused_pending")
                    if paused:
                        await WorkingMemory.save(session_id, "active_flow", "conflict_resolution")
                        await WorkingMemory.save(session_id, "conflict", paused)
                    # 追加 interrupt 完成提示
                    reply = final_state.get("final_reply", "")
                    if paused and paused.get("summary"):
                        reply += f"\n\n💡 刚才还有一个冲突需要你选择：\n{paused.get('summary', '')}"
                        final_state["final_reply"] = reply
                elif flow == "conflict_resolution":
                    await WorkingMemory.save(session_id, "active_flow", flow)
                    conflict = final_state.get("pending_action")
                    if conflict and conflict.get("type") == "conflict_resolution":
                        await WorkingMemory.save(session_id, "conflict", conflict)
                else:
                    await WorkingMemory.delete_key(session_id, "active_flow")
                    await WorkingMemory.delete_key(session_id, "conflict")
                ptasks = final_state.get("pending_tasks", [])
                if ptasks:
                    await WorkingMemory.save(session_id, "pending_tasks", ptasks)
                else:
                    await WorkingMemory.delete_key(session_id, "pending_tasks")
                pa = final_state.get("pending_action", {})
                print(f"[REDIS] save flow={flow} stage={pa.get('stage','')}")

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

            reply = final_state.get("final_reply", "")

            tracer.add_step("reply", output_data={"reply": reply[:500]})

            # Memory extraction (async, non-blocking, bounded)
            BACKGROUND_TASK_GOVERNOR.submit(
                _extract_and_save_memories(
                    user_input=request.message, ai_reply=reply,
                    user_id=request.user_id or 0,
                ),
                name="extract-memories",
            )

            tracer.finish(reply)

            return AgentService._response_from_state(
                session_id=session_id,
                final_state=final_state,
                reply=reply,
            )

        except Exception as e:
            logger.exception(f"Agent chat error: {e}")
            tracer.add_step("error", success=False, error=str(e))
            tracer.finish(f"Error: {e}")
            return AgentChatResponse(
                reply=f"sorry, error: {e}", session_id=session_id,
            )

    @staticmethod
    def _response_from_state(
        session_id: str,
        final_state: dict,
        reply: str,
    ) -> AgentChatResponse:
        suggestions = []
        for s in final_state.get("suggestions", []):
            suggestions.append(AgentSuggestion(
                plan_id=s.get("plan_id", "?"),
                title=s.get("title", ""),
                description=s.get("description", ""),
                impact=s.get("impact", ""),
                is_recommended=s.get("is_recommended", False),
            ))

        return AgentChatResponse(
            reply=reply,
            session_id=session_id,
            needs_confirmation=_needs_confirm_button(final_state),
            confirmation_stage=_confirmation_stage(final_state),
            conflicts=final_state.get("conflicts_found", []),
            suggestions=suggestions,
            tasks_created=final_state.get("tasks_created", []),
            tasks_updated=final_state.get("tasks_updated", []),
            actions_taken=final_state.get("actions_taken", []),
        )
