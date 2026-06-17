"""A tiny, ordered policy engine: decide allow / deny / approve for an action before it runs.

Rules are evaluated in the order they were added; the FIRST match wins. If nothing
matches, the policy's `default` applies. Default is `allow` (frictionless for dev); set
`Policy(default="deny")` for a deny-by-default production posture.
"""

from __future__ import annotations

from typing import Callable, Optional

ALLOW, DENY, APPROVE = "allow", "deny", "approve"


class Decision:
    def __init__(self, verdict: str, reason: str = "", rule: "Optional[_Rule]" = None):
        self.verdict = verdict
        self.reason = reason
        self.rule = rule

    @property
    def allowed(self) -> bool:
        return self.verdict == ALLOW

    @property
    def denied(self) -> bool:
        return self.verdict == DENY

    @property
    def needs_approval(self) -> bool:
        return self.verdict == APPROVE

    def __repr__(self) -> str:
        return f"Decision({self.verdict!r}, reason={self.reason!r})"


class _Rule:
    def __init__(self, verdict: str, name: Optional[str],
                 when: Optional[Callable[[dict], bool]], reason: str):
        self.verdict, self.name, self.when, self.reason = verdict, name, when, reason

    def matches(self, action: dict) -> bool:
        if self.name is not None and action.get("name") != self.name:
            return False
        if self.when is not None and not self.when(action):
            return False
        return True


class Policy:
    def __init__(self, default: str = ALLOW):
        if default not in (ALLOW, DENY, APPROVE):
            raise ValueError(f"default must be one of allow/deny/approve, got {default!r}")
        self.default = default
        self.rules: list = []

    def _add(self, verdict, name, when, reason) -> "Policy":
        self.rules.append(_Rule(verdict, name, when, reason or f"matched {verdict} rule"))
        return self  # chainable

    def allow(self, name=None, when=None, reason="") -> "Policy":
        return self._add(ALLOW, name, when, reason)

    def deny(self, name=None, when=None, reason="") -> "Policy":
        return self._add(DENY, name, when, reason)

    def require_approval(self, name=None, when=None, reason="") -> "Policy":
        return self._add(APPROVE, name, when, reason)

    def decide(self, action: dict) -> Decision:
        for rule in self.rules:
            if rule.matches(action):
                return Decision(rule.verdict, rule.reason, rule)
        return Decision(self.default, f"default:{self.default}")
