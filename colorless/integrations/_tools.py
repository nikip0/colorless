"""Shared duck-typed tool wrapping for the framework integrations.

Frameworks expose a tool's underlying callable under different attributes; we wrap whichever LEAF
callable exists so every invocation is gated + sealed — without importing the framework
(version-proof). We wrap at most ONE sync leaf and ONE async leaf per tool, preferring the explicit
function attribute over the `_run` method, so a tool whose public method delegates to its function
isn't gated twice (no double-logging).
"""

from __future__ import annotations

from typing import Iterable, List

from ..core import GUARDED_MARK, Colorless

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
        leaf_found = False
        for group in (_SYNC_ATTRS, _ASYNC_ATTRS):
            for attr in group:
                fn = getattr(t, attr, None)
                if callable(fn):
                    leaf_found = True
                    if getattr(fn, GUARDED_MARK, False):
                        wrapped = True          # already guarded — idempotent, don't re-wrap
                    else:
                        try:
                            setattr(t, attr, colorless.guard(fn, name=name))
                            wrapped = True
                        except Exception:
                            pass                # immutable leaf — handled in the else below
                    break                       # only the first (leaf) callable per group → no double-wrap
        if wrapped:
            out.append(t)
        elif not leaf_found and callable(t):
            # a plain callable (or a tool that IS its own callable); guard it, unless already guarded
            out.append(t if getattr(t, GUARDED_MARK, False) else colorless.guard(t, name=name))
        else:
            # A leaf callable existed but couldn't be replaced (immutable tool), or nothing here is
            # gateable. Returning it UNGATED would silently defeat the gate — refuse loudly instead.
            raise TypeError(
                f"colorless.guard_tools: cannot gate tool {name!r} — its underlying callable could "
                f"not be wrapped (immutable tool object?) and the tool itself isn't callable. Wrap "
                f"the function before building the tool, or pass the raw callable.")
    return out
