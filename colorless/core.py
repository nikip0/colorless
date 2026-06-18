"""Colorless — gate every action your AI agent takes, and seal it into a verifiable ledger.

Two guarantees, in ~5 lines of your code:

  1. BEFORE an action runs, it is checked against a policy → allow / deny / needs-approval.
     A denied or unapproved action never executes.
  2. AFTER (and around) every action, a tamper-evident record is appended to a hash chain —
     so you can later PROVE exactly what your agent did and that each action was authorized.

This is decision SUPPORT and accountability, never an auto-approver: an action that needs
approval is blocked until your `on_approval` handler returns True.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
from contextlib import contextmanager
from typing import Callable, Optional

from .errors import ApprovalRequired, PolicyDenied
from .ledger import Ledger
from .policy import APPROVE, DENY, Policy
from .redaction import redact_secrets

# marks a callable that guard() already wrapped, so the integration layer never double-wraps it
GUARDED_MARK = "_colorless_guarded"


def _safe(v):
    """Best-effort JSON-serialisable value for the ledger."""
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return repr(v)


def _approval_result(raw):
    """on_approval may return a bool, or a dict {'approved': bool, 'approver': str} so the human
    who authorized (or rejected) the action can be sealed into the ledger. Returns (approved, approver)."""
    if isinstance(raw, dict):
        return bool(raw.get("approved")), raw.get("approver")
    return bool(raw), None


class Colorless:
    def __init__(self, ledger="colorless.jsonl", policy: Optional[Policy] = None,
                 on_approval: Optional[Callable[[dict, object], bool]] = None,
                 redact="auto"):
        self.ledger = ledger if isinstance(ledger, Ledger) else Ledger(ledger)
        self.policy = policy or Policy()
        # on_approval(action, decision) -> bool. None => an approval-required action always blocks.
        self.on_approval = on_approval
        # redact(args) -> args, to strip secrets before they're written to the ledger.
        # "auto" => the built-in secret redactor (secure by default); None => no redaction.
        self.redact = redact_secrets if redact == "auto" else redact
        self._subscribers = []  # cb(entry) fired after every ledger append (OTel, alerting, ...)

    def subscribe(self, callback: "Callable[[dict], None]") -> "Callable":
        """Register a callback fired with each sealed ledger entry (after it's written). Used by the
        OTel exporter and alerting; a failing callback never breaks logging. Returns the callback."""
        self._subscribers.append(callback)
        return callback

    def _emit_event(self, entry: dict) -> None:
        for cb in self._subscribers:
            try:
                cb(entry)
            except Exception:
                pass  # a subscriber must never break the audit write

    def _write(self, ref: str, **payload) -> dict:
        entry = self.ledger.append("action", ref=ref, **payload)
        self._emit_event(entry)
        return entry

    # --- policy authoring (chainable) ----------------------------------------
    def allow(self, *a, **k) -> "Colorless":
        self.policy.allow(*a, **k)
        return self

    def deny(self, *a, **k) -> "Colorless":
        self.policy.deny(*a, **k)
        return self

    def require_approval(self, *a, **k) -> "Colorless":
        self.policy.require_approval(*a, **k)
        return self

    def check(self, name: str, **args):
        """Evaluate policy for an action WITHOUT running or logging it."""
        return self.policy.decide({"name": name, "args": args})

    # --- gating internals -----------------------------------------------------
    def _logged_args(self, args: dict) -> dict:
        # Redaction / dict-coercion must NEVER crash the gate before the action is sealed — otherwise
        # a blocked action neither runs nor leaves an audit trace. Fail safe to a marker and still
        # log (no raw args, in case the redactor failed mid-way over something sensitive).
        try:
            return self.redact(dict(args)) if self.redact else args
        except Exception as e:
            return {"_redaction_error": type(e).__name__}

    def _logged_value(self, v):
        """Run a single logged value (a tool RESULT or an ERROR message) through the same redactor
        as the args, so secrets/PII that a tool returns or that surface in an exception don't leak
        into the tamper-evident ledger (where they can never be scrubbed). Falls back to the raw
        value if the redactor can't handle a wrapped scalar."""
        if self.redact is None or v is None:
            return v
        try:
            return self.redact({"_": v}).get("_", v)
        except Exception:
            return v

    def _gate(self, action: dict):
        """Evaluate policy; record + raise on deny / unapproved; else return (decision, log_action,
        approver). `approver` is who authorized an approval-gated action (or None)."""
        decision = self.policy.decide(action)
        log_action = {"name": action["name"], "args": self._logged_args(action.get("args", {}))}
        if decision.denied:
            self._write(action["name"], action=log_action,
                        decision=DENY, reason=decision.reason, executed=False)
            raise PolicyDenied(action, decision)
        approver = None
        if decision.needs_approval:
            raw = self.on_approval(action, decision) if self.on_approval else False
            approved, approver = _approval_result(raw)
            if not approved:
                blocked = {"action": log_action, "decision": APPROVE, "approved": False,
                           "reason": decision.reason, "executed": False}
                if approver:
                    blocked["approver"] = approver   # who rejected it
                self._write(action["name"], **blocked)
                raise ApprovalRequired(action, decision)
        return decision, log_action, approver

    def _record(self, name, log_action, decision, ok, result=None, error=None, approver=None) -> dict:
        payload = {"action": log_action, "decision": decision.verdict, "executed": True, "ok": ok}
        if decision.needs_approval:
            payload["approved"] = True
            if approver:
                payload["approver"] = approver   # who authorized it — sealed in the chain
        if ok and result is not None:
            payload["result"] = _safe(self._logged_value(result))
        if not ok:
            payload["error"] = self._logged_value(error)
        return self._write(name, **payload)

    def run(self, name: str, arguments: dict, fn: Callable[[], object]):
        """Gate an action (name, arguments), execute the zero-arg `fn` if allowed, record the
        outcome, and return its result. Raises PolicyDenied / ApprovalRequired if blocked. This is
        the shared gated path used by `@guard` and the tool adapters — call it directly when you
        already have a tool name + an args dict (e.g. from an LLM tool_call)."""
        decision, log_action, approver = self._gate({"name": name, "args": arguments})
        try:
            result = fn()
        except Exception as e:
            self._record(name, log_action, decision, ok=False, error=f"{type(e).__name__}: {e}", approver=approver)
            raise
        self._record(name, log_action, decision, ok=True, result=result, approver=approver)
        return result

    async def arun(self, name: str, arguments: dict, fn: Callable[[], object]):
        """Async sibling of `run`: gate, then await `fn()` (sync or coroutine-returning) if allowed,
        record the outcome, and return its result. For agent frameworks that run on asyncio."""
        decision, log_action, approver = self._gate({"name": name, "args": arguments})
        try:
            result = fn()
            if inspect.isawaitable(result):
                result = await result
        except Exception as e:
            self._record(name, log_action, decision, ok=False, error=f"{type(e).__name__}: {e}", approver=approver)
            raise
        self._record(name, log_action, decision, ok=True, result=result, approver=approver)
        return result

    # --- the two ways to gate an action --------------------------------------
    def guard(self, fn=None, *, name=None):
        """Decorator: wrap a tool/function so every call is policy-checked and logged.

            @w.guard
            def transfer_funds(amount, to): ...
        """
        def _logged(args, kwargs):
            # named args log cleanly; positionals are captured best-effort as _0, _1, ...
            return {**{f"_{i}": a for i, a in enumerate(args)}, **kwargs} if args else dict(kwargs)

        def wrap(func):
            action_name = name or func.__name__

            if asyncio.iscoroutinefunction(func):
                @functools.wraps(func)
                async def ainner(*args, **kwargs):
                    return await self.arun(action_name, _logged(args, kwargs),
                                           lambda: func(*args, **kwargs))
                setattr(ainner, GUARDED_MARK, True)
                return ainner

            @functools.wraps(func)
            def inner(*args, **kwargs):
                return self.run(action_name, _logged(args, kwargs),
                                lambda: func(*args, **kwargs))
            setattr(inner, GUARDED_MARK, True)
            return inner

        return wrap(fn) if fn else wrap

    @contextmanager
    def action(self, name: str, **args):
        """Context manager for inline actions:

            with w.action("transfer_funds", amount=5000, to="acct_2"):
                bank.transfer(...)
        """
        act = {"name": name, "args": args}
        decision, log_action, approver = self._gate(act)
        try:
            yield decision
        except Exception as e:
            self._record(name, log_action, decision, ok=False, error=f"{type(e).__name__}: {e}", approver=approver)
            raise
        self._record(name, log_action, decision, ok=True, approver=approver)

    # --- verification passthrough --------------------------------------------
    def verify(self) -> dict:
        return self.ledger.verify()

    def head(self) -> dict:
        return self.ledger.head()

    def entries(self, ref=None) -> list:
        return self.ledger.entries(ref)

    def anchor(self, path: str) -> dict:
        return self.ledger.anchor(path)

    def verify_against_anchor(self, path: str) -> dict:
        return self.ledger.verify_against_anchor(path)
