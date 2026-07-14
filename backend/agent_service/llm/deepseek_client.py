"""
DeepSeek LLM 客户端 — 双模式

- 有 API Key：调用 DeepSeek API (OpenAI 兼容)
- 无 API Key：使用 mock 规则引擎回退

通过 is_llm_available() 检测当前模式
"""
from openai import AsyncOpenAI
from common.config import settings


def is_llm_available() -> bool:
    """检测 LLM API 是否可用"""
    return bool(settings.DEEPSEEK_API_KEY and
                settings.DEEPSEEK_API_KEY != "your-deepseek-api-key")


def get_llm_client() -> AsyncOpenAI | None:
    """获取 DeepSeek 客户端，不可用返回 None"""
    if not is_llm_available():
        return None
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )


async def chat_completion(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stream: bool = False,
) -> str:
    """
    调用 DeepSeek 聊天补全

    不可用时自动回退到 mock 引擎
    """
    if not is_llm_available():
        from agent_service.llm.mock_agent import mock_chat
        # 提取最后一条用户消息
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m["content"]
                break
        return await mock_chat(user_msg)

    client = get_llm_client()

    if stream:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        full_content = ""
        async for chunk in response:
            if chunk.choices[0].delta.content:
                full_content += chunk.choices[0].delta.content
        return full_content
    else:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


async def chat_completion_json(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> dict | None:
    """
    调用 LLM 并强制返回 JSON

    不可用时返回 None，由调用方使用 mock 逻辑
    """
    if not is_llm_available():
        return None

    import json
    client = get_llm_client()
    response = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        # DeepSeek may not support response_format; rely on prompt engineering instead
    )
    content = response.choices[0].message.content.strip()

    # Try direct JSON parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    for marker in ["```json", "```"]:
        if marker in content:
            try:
                start = content.index(marker) + len(marker)
                end = content.index("```", start)
                inner = content[start:end].strip()
                return json.loads(inner)
            except (ValueError, json.JSONDecodeError):
                continue

    # Try finding JSON object in text
    try:
        brace_start = content.index("{")
        brace_end = content.rindex("}") + 1
        return json.loads(content[brace_start:brace_end])
    except (ValueError, json.JSONDecodeError):
        pass

    return {"raw": content, "parse_error": True}


# ============ Streaming (流式输出) ============

async def astream_chat(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 2048,
):
    """
    流式对话 — 逐 token yield

    用法:
        async for chunk in astream_chat(messages):
            yield chunk  # str, 每个 token

    Mock 模式下模拟流式逐字输出。
    """
    if not is_llm_available():
        # Mock: 逐字输出
        from agent_service.llm.mock_agent import mock_chat
        text = await mock_chat(
            next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        )
        for char in text:
            yield char
            import asyncio
            await asyncio.sleep(0.02)  # 模拟打字效果
        return

    client = get_llm_client()
    response = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


# ============ Structured Output (Pydantic) ============

def get_structured_llm(output_schema: type):
    """
    返回一个支持结构化输出的 LLM 实例

    用法:
        llm = get_structured_llm(PlannerOutput)
        result = llm.invoke(messages)  # → PlannerOutput 实例

    原理:
        LangChain ChatOpenAI.with_structured_output()
        自动注入 JSON Schema 到 prompt + Pydantic 校验
    """
    from langchain_openai import ChatOpenAI
    from common.config import settings

    llm = ChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0.3,
        max_tokens=2048,
    )
    return llm.with_structured_output(output_schema, method="json_mode")
