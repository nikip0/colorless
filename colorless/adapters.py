"""Drop colorless into the agent loops people actually run.

LLM agents ultimately call a tool by `(name, arguments_dict)` — that's the shape OpenAI
function-calling, Anthropic tool use, and MCP servers all hand you. `ToolGuard` wraps a
registry of those tools so every call is policy-gated and sealed into the ledger, with a
single `.call(name, arguments)` you drop into your dispatch loop.

Zero dependencies — works with any framework because it only assumes the universal
(name, args) tool-call shape.
"""

from __future__ import annotations

from typing import Callable, Optional

from .core import Colorless


class UnknownTool(KeyError):
    """A tool name was dispatched that isn't registered."""


class ToolGuard:
    def __init__(self, colorless: Colorless, tools: Optional[dict] = None):
        self.w = colorless
        self.tools: dict = dict(tools or {})

    def add(self, name: str, fn: Callable) -> "ToolGuard":
        self.tools[name] = fn
        return self

    def register(self, name: Optional[str] = None):
        """Decorator: register (and thereby guard) a tool by name.

            tg = ToolGuard(w)

            @tg.register()
            def send_email(to, body): ...
        """
        def deco(fn):
            self.tools[name or fn.__name__] = fn
            return fn
        return deco

    def call(self, name: str, arguments: Optional[dict] = None):
        """Dispatch ONE tool call through the policy gate + ledger. This is the line you put in
        your agent loop / MCP `call_tool` handler. Raises PolicyDenied / ApprovalRequired when
        blocked (so the model sees a clean, loggable refusal), UnknownTool for a bad name."""
        arguments = arguments or {}
        if name not in self.tools:
            raise UnknownTool(name)
        fn = self.tools[name]
        return self.w.run(name, arguments, lambda: fn(**arguments))

    async def acall(self, name: str, arguments: Optional[dict] = None):
        """Async dispatch — for coroutine tools or an asyncio agent loop. Same gating + sealing."""
        arguments = arguments or {}
        if name not in self.tools:
            raise UnknownTool(name)
        fn = self.tools[name]
        return await self.w.arun(name, arguments, lambda: fn(**arguments))

    def guarded(self) -> dict:
        """Return `{name: wrapped_fn}` where each wrapped fn is gated+logged — handy when a
        framework wants callables it can invoke directly rather than a dispatcher."""
        return {name: self.w.guard(fn, name=name) for name, fn in self.tools.items()}
