"""colorless × OpenAI Agents SDK — gate + prove your function tools.

The cleanest wiring is to gate the function BEFORE `@function_tool` wraps it (the SDK closes over
your function, so decorate the leaf):

    from agents import function_tool
    from colorless import Colorless
    from colorless.integrations.openai_agents import guard

    cl = Colorless("agent.jsonl"); cl.deny("delete_account")

    @function_tool
    @guard(cl)                       # gate + seal every call (put @guard INNER, @function_tool outer)
    def refund(amount: float, to: str) -> str: ...

`guard_tools` is also re-exported for tool objects that expose a leaf callable. A blocked tool
raises PolicyDenied / ApprovalRequired.
"""

from ._tools import guard_callable, guard_tools


def guard(colorless, fn=None, *, name=None):
    """Decorator: `@guard(cl)` (or `@guard(cl, name="...")`) on a function before `@function_tool`."""
    if fn is not None:
        return colorless.guard(fn, name=name)
    return lambda f: colorless.guard(f, name=name)


__all__ = ["guard", "guard_tools", "guard_callable"]
