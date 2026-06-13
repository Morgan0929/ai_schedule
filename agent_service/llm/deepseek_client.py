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
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # 尝试从 markdown code block 中提取
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            content = content[start:end].strip()
            try:
                return json.loads(content)
            except Exception:
                pass
        return {"raw": content, "parse_error": True}
