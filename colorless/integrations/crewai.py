"""colorless × CrewAI — gate + prove your agents' tools.

`guard_tools` wraps CrewAI tools so every call is policy-gated and sealed into the tamper-evident
ledger. Duck-typed (no crewai import), so it tracks CrewAI's API across versions.

    from crewai.tools import tool
    from colorless import Colorless
    from colorless.integrations.crewai import guard_tools

    cl = Colorless("agent.jsonl"); cl.deny("delete_repo")
    tools = guard_tools(cl, [search, delete_repo])   # BaseTool objects OR plain @tool fns
    agent = Agent(role="...", tools=tools, ...)

A blocked tool raises PolicyDenied / ApprovalRequired — surface it back to the crew as a tool error.
"""

from ._tools import guard_callable, guard_tools

__all__ = ["guard_tools", "guard_callable"]
