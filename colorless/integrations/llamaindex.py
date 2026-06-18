"""colorless × LlamaIndex — gate + prove your agents' tools.

`guard_tools` wraps LlamaIndex tools (e.g. `FunctionTool`) so every call is policy-gated and sealed.
Duck-typed (no llama_index import); wraps the tool's underlying `fn` / `async_fn`.

    from llama_index.core.tools import FunctionTool
    from colorless import Colorless
    from colorless.integrations.llamaindex import guard_tools

    cl = Colorless("agent.jsonl"); cl.deny("delete_index")
    tools = guard_tools(cl, [FunctionTool.from_defaults(fn=search), delete_tool])
    agent = ReActAgent.from_tools(tools, llm=llm)

A blocked tool raises PolicyDenied / ApprovalRequired — surface it back to the agent as a tool error.
"""

from ._tools import guard_callable, guard_tools

__all__ = ["guard_tools", "guard_callable"]
