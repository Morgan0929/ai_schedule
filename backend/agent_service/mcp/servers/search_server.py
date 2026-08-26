"""
MCP Search Server — 网页搜索

外部能力, 通过 MCP 协议暴露给 Agent
"""
import json
import logging

from common.utils.http_client import get_json

logger = logging.getLogger(__name__)


class SearchMCPServer:
    """
    Search MCP Server

    暴露工具:
      - web_search: 搜索网页
    """

    name = "search"
    description = "网页搜索服务"

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        if tool_name == "web_search":
            return await self._web_search(arguments)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "web_search",
                "description": "搜索网页获取信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "max_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        ]

    async def _web_search(self, args: dict) -> str:
        query = args.get("query", "")
        max_results = args.get("max_results", 5)

        if not query:
            return json.dumps({"error": "query is required"})

        try:
            # DuckDuckGo Instant Answer API (免费, 无需 API Key)
            url = "https://api.duckduckgo.com/"
            params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
            data = await get_json("search", url, timeout=10.0, params=params)

            results = []
            # Abstract
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("AbstractSource", "DuckDuckGo"),
                    "snippet": data["AbstractText"][:300],
                    "url": data.get("AbstractURL", ""),
                })
            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                        "snippet": topic["Text"][:300],
                        "url": topic.get("FirstURL", ""),
                    })

            return json.dumps({
                "query": query,
                "results": results[:max_results],
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})
