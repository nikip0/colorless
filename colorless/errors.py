"""Exceptions raised when the policy blocks an action."""

from __future__ import annotations


class ColorlessError(Exception):
    """Base class for all colorless errors."""


class PolicyDenied(ColorlessError):
    """The action is forbidden by policy and was NOT executed."""

    def __init__(self, action: dict, decision):
        self.action, self.decision = action, decision
        super().__init__(f"action {action.get('name')!r} denied by policy: {decision.reason}")


class ApprovalRequired(ColorlessError):
    """The action needs a human sign-off that was not granted; it was NOT executed."""

    def __init__(self, action: dict, decision):
        self.action, self.decision = action, decision
        super().__init__(
            f"action {action.get('name')!r} requires human approval: {decision.reason}")
