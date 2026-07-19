"""
MCP Weather Server — 天气查询

外部能力, 通过 MCP 协议暴露给 Agent
底层: wttr.in 免费 API
"""
import json
import logging

logger = logging.getLogger(__name__)


class WeatherMCPServer:
    """
    Weather MCP Server

    暴露工具:
      - get_current_weather: 获取当前天气
      - get_forecast: 获取天气预报 (1-3天)
    """

    name = "weather"
    description = "天气查询服务 (wttr.in)"

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """MCP 协议: 调用工具"""
        if tool_name == "get_current_weather":
            return await self._get_current(arguments)
        elif tool_name == "get_forecast":
            return await self._get_forecast(arguments)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    def list_tools(self) -> list[dict]:
        """MCP 协议: 列出可用工具"""
        return [
            {
                "name": "get_current_weather",
                "description": "获取指定城市的当前天气",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "城市名 (中文或拼音)"},
                    },
                    "required": ["city"],
                },
            },
            {
                "name": "get_forecast",
                "description": "获取指定城市1-3天天气预报",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "days": {"type": "integer", "default": 2},
                    },
                    "required": ["city"],
                },
            },
        ]

    async def _get_current(self, args: dict) -> str:
        city = args.get("city", "Beijing")
        try:
            import httpx
            url = f"https://wttr.in/{city}?format=j1"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                raw = resp.json()
            current = raw.get("current_condition", [{}])[0]
            return json.dumps({
                "city": city,
                "temp_c": current.get("temp_C", "?"),
                "desc": current.get("weatherDesc", [{}])[0].get("value", ""),
                "humidity": current.get("humidity", "?"),
                "wind_kmph": current.get("windspeedKmph", "?"),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _get_forecast(self, args: dict) -> str:
        city = args.get("city", "Beijing")
        days = min(args.get("days", 2), 3)
        try:
            import httpx
            url = f"https://wttr.in/{city}?format=j1"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                raw = resp.json()
            forecasts = raw.get("weather", [])[:days]
            daily = []
            for f in forecasts:
                daily.append({
                    "date": f.get("date", ""),
                    "high_c": f.get("maxtempC", "?"),
                    "low_c": f.get("mintempC", "?"),
                    "desc": f.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", ""),
                })
            return json.dumps({"city": city, "daily": daily}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})
