"""colorless × LangChain / LangGraph — gate + prove your tools.

`guard_tools` wraps a list of LangChain tools so every invocation is policy-gated and sealed.
It's duck-typed (no langchain import), so it survives LangChain's frequent API changes:

    from langchain_core.tools import tool
    from colorless import Colorless
    from colorless.integrations.langchain import guard_tools

    cl = Colorless("agent.jsonl"); cl.deny("delete_user")
    tools = guard_tools(cl, [search, delete_user])   # StructuredTool/Tool objects OR plain fns
    agent = create_react_agent(model, tools)

For a LangChain tool object it wraps the underlying callable(s) — `.func`, `.coroutine`,
`._run`, `._arun` — in place. For a plain callable it returns a guarded callable. A blocked tool
raises PolicyDenied / ApprovalRequired, which LangChain surfaces back to the model as a tool error.
"""

from __future__ import annotations

from typing import Iterable, List

from ..core import Colorless

# the callable attributes LangChain tool objects expose, across versions
_TOOL_CALLABLE_ATTRS = ("func", "coroutine", "_run", "_arun")


def _name_of(t) -> str:
    return getattr(t, "name", None) or getattr(t, "__name__", None) or "tool"


def guard_callable(colorless: Colorless, fn, name: str = None):
    """Return a gated + sealed version of a single callable."""
    return colorless.guard(fn, name=name or _name_of(fn))


def guard_tools(colorless: Colorless, tools: Iterable) -> List:
    """Gate + seal each tool. Returns a list aligned with `tools`: LangChain tool objects are
    wrapped in place where the object permits it; plain callables are replaced by guarded ones."""
    out = []
    for t in tools:
        name = _name_of(t)
        wrapped_any = False
        for attr in _TOOL_CALLABLE_ATTRS:
            fn = getattr(t, attr, None)
            if callable(fn):
                try:
                    setattr(t, attr, colorless.guard(fn, name=name))
                    wrapped_any = True
                except Exception:
                    # some tool objects are immutable (frozen pydantic) — fall through;
                    # the caller can instead guard the function before building the tool.
                    pass
        if wrapped_any:
            out.append(t)
        elif callable(t):
            out.append(colorless.guard(t, name=name))
        else:
            out.append(t)  # nothing we can wrap; return unchanged so the caller still gets a list
    return out
