"""Gate + prove a LangChain agent's tools with colorless.

Requires LangChain:   pip install langchain-core
Run:                  python3 examples/langchain_agent.py

Every tool the agent calls is policy-checked before it runs and sealed into a tamper-evident
ledger (`colorless verify lc_agent.jsonl`). Your agent code is unchanged — you only wrap the
tool list once.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from colorless import Colorless
from colorless.integrations.langchain import guard_tools

try:
    from langchain_core.tools import tool
except ImportError:
    raise SystemExit("This example needs LangChain:  pip install langchain-core")


@tool
def search(query: str) -> str:
    """Search the web."""
    return f"results for {query!r}"


@tool
def delete_user(user_id: str) -> str:
    """Delete a user account (will be denied by policy)."""
    return f"deleted {user_id}"


cl = Colorless("lc_agent.jsonl")
cl.deny("delete_user")

# one line: gate + seal every tool. Hand these to your agent as usual.
tools = guard_tools(cl, [search, delete_user])

if __name__ == "__main__":
    # normally: agent = create_react_agent(model, tools); agent.invoke(...)
    # here we just invoke the guarded tools directly to show gating + the ledger:
    print(tools[0].invoke({"query": "colorless"}))
    try:
        tools[1].invoke({"user_id": "u_42"})
    except Exception as e:
        print("delete_user blocked:", type(e).__name__)
    print("verify ->", cl.verify())
