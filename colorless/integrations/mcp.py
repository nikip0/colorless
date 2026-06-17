"""colorless × MCP — gate + prove tool calls inside a Model Context Protocol server.

MCP tools are plain functions the server dispatches by (name, arguments) — exactly the shape
colorless expects. No special SDK binding is needed; two patterns work:

    # Pattern 1 — decorate each tool (works with FastMCP's @mcp.tool()):
    from colorless import Colorless
    cl = Colorless("agent.jsonl"); cl.deny("delete_database")

    @mcp.tool()
    @cl.guard                      # gate + seal every call (put @cl.guard INNER, @mcp.tool() outer)
    def refund(amount: float, to: str) -> str: ...

    # Pattern 2 — route the server's call_tool handler through a ToolGuard:
    from colorless.integrations.mcp import tool_guard
    tg = tool_guard(cl, {"refund": refund})
    result = tg.call(name, arguments)     # inside your call_tool handler

This module imports NO MCP SDK, so colorless stays zero-dependency. See examples/mcp_server.py
for a runnable FastMCP server (`pip install mcp`).
"""

from __future__ import annotations

from typing import Optional

from ..adapters import ToolGuard
from ..core import Colorless


def tool_guard(colorless: Colorless, tools: "Optional[dict]" = None) -> ToolGuard:
    """A ToolGuard for your MCP tool registry. Use `tg.call(name, arguments)` (or `acall`) inside
    your server's call_tool handler; it raises PolicyDenied / ApprovalRequired when blocked, which
    you can return to the model as a clean refusal."""
    return ToolGuard(colorless, tools)
