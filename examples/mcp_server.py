"""A tiny MCP server whose every tool is gated + sealed by colorless.

Requires the MCP SDK:            pip install mcp
Run as an MCP stdio server:      python3 examples/mcp_server.py

Point any MCP client (Claude Desktop, Cursor, your own loop) at it. Every tool call the model
makes is policy-checked BEFORE it runs and written to a tamper-evident ledger you can audit with
`colorless verify mcp_agent.jsonl`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from colorless import Colorless

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    raise SystemExit("This example needs the MCP SDK:  pip install mcp")


cl = Colorless("mcp_agent.jsonl")
cl.deny("delete_database")
cl.require_approval("send_money", when=lambda a: a["args"].get("amount", 0) > 100)

mcp = FastMCP("colorless-demo")


# NOTE: @mcp.tool() is the OUTER decorator, @cl.guard the INNER one — colorless gates the call,
# FastMCP still sees the original signature (guard preserves it via functools.wraps).
@mcp.tool()
@cl.guard
def search_docs(query: str) -> str:
    """Search the documentation."""
    return f"top result for {query!r}"


@mcp.tool()
@cl.guard
def send_money(amount: float, to: str) -> str:
    """Send money to a recipient (over $100 requires human approval)."""
    return f"sent ${amount} to {to}"


@mcp.tool()
@cl.guard
def delete_database(name: str) -> str:
    """Drop a database (denied by policy — will never execute)."""
    return f"dropped {name}"


if __name__ == "__main__":
    mcp.run()
