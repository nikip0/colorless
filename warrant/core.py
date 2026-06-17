"""Warrant — gate every action your AI agent takes, and seal it into a verifiable ledger.

Two guarantees, in ~5 lines of your code:

  1. BEFORE an action runs, it is checked against a policy → allow / deny / needs-approval.
     A denied or unapproved action never executes.
  2. AFTER (and around) every action, a tamper-evident record is appended to a hash chain —
     so you can later PROVE exactly what your agent did and that each action was authorized.

This is decision SUPPORT and accountability, never an auto-approver: an action that needs
approval is blocked until your `on_approval` handler returns True.
"""

from __future__ import annotations

import functools
import json
from contextlib import contextmanager
from typing import Callable, Optional

from .errors import ApprovalRequired, PolicyDenied
from .ledger import Ledger
from .policy import APPROVE, DENY, Policy


def _safe(v):
    """Best-effort JSON-serialisable value for the ledger."""
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return repr(v)


class Warrant:
    def __init__(self, ledger="warrant.jsonl", policy: Optional[Policy] = None,
                 on_approval: Optional[Callable[[dict, object], bool]] = None,
                 redact: Optional[Callable[[dict], dict]] = None):
        self.ledger = ledger if isinstance(ledger, Ledger) else Ledger(ledger)
        self.policy = policy or Policy()
        # on_approval(action, decision) -> bool. None => an approval-required action always blocks.
        self.on_approval = on_approval
        # redact(args) -> args, to strip secrets before they're written to the ledger.
        self.redact = redact

    # --- policy authoring (chainable) ----------------------------------------
    def allow(self, *a, **k) -> "Warrant":
        self.policy.allow(*a, **k)
        return self

    def deny(self, *a, **k) -> "Warrant":
        self.policy.deny(*a, **k)
        return self

    def require_approval(self, *a, **k) -> "Warrant":
        self.policy.require_approval(*a, **k)
        return self

    def check(self, name: str, **args):
        """Evaluate policy for an action WITHOUT running or logging it."""
        return self.policy.decide({"name": name, "args": args})

    # --- gating internals -----------------------------------------------------
    def _logged_args(self, args: dict) -> dict:
        return self.redact(dict(args)) if self.redact else args

    def _gate(self, action: dict):
        """Evaluate policy; record + raise on deny / unapproved; else return (decision, log_action)."""
        decision = self.policy.decide(action)
        log_action = {"name": action["name"], "args": self._logged_args(action.get("args", {}))}
        if decision.denied:
            self.ledger.append("action", ref=action["name"], action=log_action,
                               decision=DENY, reason=decision.reason, executed=False)
            raise PolicyDenied(action, decision)
        if decision.needs_approval:
            approved = bool(self.on_approval(action, decision)) if self.on_approval else False
            if not approved:
                self.ledger.append("action", ref=action["name"], action=log_action,
                                   decision=APPROVE, approved=False, reason=decision.reason,
                                   executed=False)
                raise ApprovalRequired(action, decision)
        return decision, log_action

    def _record(self, name, log_action, decision, ok, result=None, error=None) -> dict:
        payload = {"action": log_action, "decision": decision.verdict, "executed": True, "ok": ok}
        if decision.needs_approval:
            payload["approved"] = True
        if ok and result is not None:
            payload["result"] = _safe(result)
        if not ok:
            payload["error"] = error
        return self.ledger.append("action", ref=name, **payload)

    def run(self, name: str, arguments: dict, fn: Callable[[], object]):
        """Gate an action (name, arguments), execute the zero-arg `fn` if allowed, record the
        outcome, and return its result. Raises PolicyDenied / ApprovalRequired if blocked. This is
        the shared gated path used by `@guard` and the tool adapters — call it directly when you
        already have a tool name + an args dict (e.g. from an LLM tool_call)."""
        decision, log_action = self._gate({"name": name, "args": arguments})
        try:
            result = fn()
        except Exception as e:
            self._record(name, log_action, decision, ok=False, error=f"{type(e).__name__}: {e}")
            raise
        self._record(name, log_action, decision, ok=True, result=result)
        return result

    # --- the two ways to gate an action --------------------------------------
    def guard(self, fn=None, *, name=None):
        """Decorator: wrap a tool/function so every call is policy-checked and logged.

            @w.guard
            def transfer_funds(amount, to): ...
        """
        def wrap(func):
            action_name = name or func.__name__

            @functools.wraps(func)
            def inner(*args, **kwargs):
                # named args log cleanly; positionals are captured best-effort as _0, _1, ...
                logged = dict(kwargs)
                if args:
                    logged = {**{f"_{i}": a for i, a in enumerate(args)}, **kwargs}
                return self.run(action_name, logged, lambda: func(*args, **kwargs))

            return inner

        return wrap(fn) if fn else wrap

    @contextmanager
    def action(self, name: str, **args):
        """Context manager for inline actions:

            with w.action("transfer_funds", amount=5000, to="acct_2"):
                bank.transfer(...)
        """
        act = {"name": name, "args": args}
        decision, log_action = self._gate(act)
        try:
            yield decision
        except Exception as e:
            self._record(name, log_action, decision, ok=False, error=f"{type(e).__name__}: {e}")
            raise
        self._record(name, log_action, decision, ok=True)

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
