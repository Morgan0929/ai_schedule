"""
DeepSeek LLM 客户端

通过 OpenAI 兼容 SDK 调用 DeepSeek API
"""
from openai import AsyncOpenAI
from common.config import settings


def get_llm_client() -> AsyncOpenAI:
    """
    获取 DeepSeek 异步客户端

    DeepSeek API 与 OpenAI SDK 完全兼容，
    只需修改 base_url 和 api_key
    """
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )


async def chat_completion(messages: list[dict], temperature: float = 0.7,
                          max_tokens: int = 4096, stream: bool = False) -> str:
    """
    调用 DeepSeek 聊天补全

    Args:
        messages: 消息列表 [{"role": "system/user/assistant", "content": "..."}]
        temperature: 温度参数 (0-1)，越低越确定
        max_tokens: 最大输出 token 数
        stream: 是否流式输出

    Returns:
        AI 回复文本
    """
    client = get_llm_client()

    if stream:
        # 流式输出
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
        # 非流式
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
