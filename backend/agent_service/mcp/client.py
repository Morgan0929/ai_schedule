"""
MCP Client — Agent 与外部 MCP Server 的桥梁

架构:
  林 Agent → MCP Client → [Weather MCP | Search MCP | File MCP]
  内部服务 (Memory/Conflict/Calendar/RAG) 不经过 MCP — 直接调用

MCP Client 负责:
  1. 注册所有 MCP Server
  2. 统一调用接口: call_mcp_tool(server, tool, params)
  3. 返回结构化结果给 Agent Tool
"""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# MCP Server 注册表 — 外部能力
MCP_SERVERS: dict[str, Any] = {}


def register_mcp_server(name: str, server):
    """注册 MCP Server"""
    MCP_SERVERS[name] = server
    logger.info(f"MCP Server registered: {name}")


def get_mcp_server(name: str):
    return MCP_SERVERS.get(name)


async def call_mcp_tool(server_name: str, tool_name: str, params: dict) -> dict:
    """
    统一 MCP 工具调用接口

    Args:
        server_name: MCP Server 名称 (weather/search/filesystem)
        tool_name:   工具名称
        params:      参数

    Returns:
        {"success": True, "data": {...}} | {"success": False, "error": "..."}
    """
    server = MCP_SERVERS.get(server_name)
    if not server:
        return {"success": False, "error": f"MCP Server not found: {server_name}"}

    try:
        raw = await server.call_tool(tool_name, params)
        data = json.loads(raw) if isinstance(raw, str) else raw
        return {"success": True, "data": data}
    except Exception as e:
        logger.error(f"MCP call failed [{server_name}.{tool_name}]: {e}")
        return {"success": False, "error": str(e)}


def list_all_mcp_tools() -> list[dict]:
    """列出所有已注册的 MCP 工具"""
    tools = []
    for name, server in MCP_SERVERS.items():
        if hasattr(server, "list_tools"):
            for tool in server.list_tools():
                tools.append({
                    "server": name,
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                })
    return tools


# ============ 启动时注册 ============

def init_mcp_servers():
    """在 Agent 启动时调用, 注册所有 MCP Server"""
    from agent_service.mcp.servers.weather_server import WeatherMCPServer
    from agent_service.mcp.servers.search_server import SearchMCPServer

    register_mcp_server("weather", WeatherMCPServer())
    register_mcp_server("search", SearchMCPServer())

    logger.info(f"MCP initialized: {list(MCP_SERVERS.keys())}")
    return list(MCP_SERVERS.keys())
