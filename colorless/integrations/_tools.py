"""Shared duck-typed tool wrapping for the framework integrations.

Frameworks expose a tool's underlying callable under different attributes; we wrap whichever LEAF
callable exists so every invocation is gated + sealed — without importing the framework
(version-proof). We wrap at most ONE sync leaf and ONE async leaf per tool, preferring the explicit
function attribute over the `_run` method, so a tool whose public method delegates to its function
isn't gated twice (no double-logging).
"""

from __future__ import annotations

from typing import Iterable, List

from ..core import Colorless

# leaf callables, in priority order. The explicit function (func/fn) is preferred over the _run
# method (which usually delegates to it) so we never wrap both and double-count a single call.
_SYNC_ATTRS = ("func", "fn", "_run")
_ASYNC_ATTRS = ("coroutine", "async_fn", "_arun")


def _name_of(t) -> str:
    name = getattr(t, "name", None)
    if isinstance(name, str):
        return name
    md = getattr(t, "metadata", None)              # e.g. LlamaIndex FunctionTool.metadata.name
    if md is not None and isinstance(getattr(md, "name", None), str):
        return md.name
    return getattr(t, "__name__", None) or "tool"


def guard_callable(colorless: Colorless, fn, name: str = None):
    """Return a gated + sealed version of a single callable."""
    return colorless.guard(fn, name=name or _name_of(fn))


def guard_tools(colorless: Colorless, tools: Iterable) -> List:
    """Gate + seal each tool. Wraps the underlying callable in place for framework tool objects
    (LangChain / CrewAI / LlamaIndex / ...), or replaces a plain callable with a guarded one.
    Returns a list aligned with `tools`."""
    out = []
    for t in tools:
        name = _name_of(t)
        wrapped = False
        for group in (_SYNC_ATTRS, _ASYNC_ATTRS):
            for attr in group:
                fn = getattr(t, attr, None)
                if callable(fn):
                    try:
                        setattr(t, attr, colorless.guard(fn, name=name))
                        wrapped = True
                    except Exception:
                        pass            # immutable tool object — fall back to guarding the callable
                    break               # only the first (leaf) callable per group → no double-wrap
        if wrapped:
            out.append(t)
        elif callable(t):
            out.append(colorless.guard(t, name=name))
        else:
            out.append(t)
    return out
