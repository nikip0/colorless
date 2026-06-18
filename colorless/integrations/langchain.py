"""colorless × LangChain / LangGraph — gate + prove your tools.

`guard_tools` wraps a list of LangChain tools so every invocation is policy-gated and sealed. It's
duck-typed (no langchain import), so it survives LangChain's frequent API changes:

    from langchain_core.tools import tool
    from colorless import Colorless
    from colorless.integrations.langchain import guard_tools

    cl = Colorless("agent.jsonl"); cl.deny("delete_user")
    tools = guard_tools(cl, [search, delete_user])   # StructuredTool/Tool objects OR plain fns
    agent = create_react_agent(model, tools)

A blocked tool raises PolicyDenied / ApprovalRequired, which LangChain surfaces back to the model
as a tool error.
"""

from ._tools import guard_callable, guard_tools

__all__ = ["guard_tools", "guard_callable"]
