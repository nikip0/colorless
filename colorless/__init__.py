"""colorless — authorize, gate, and prove every action your AI agent takes.

    from colorless import Colorless

    w = Colorless("agent.jsonl")
    w.deny("delete_database")
    w.require_approval("refund", when=lambda a: a["args"].get("amount", 0) > 100)

    @w.guard
    def refund(amount, to): ...

    w.verify()   # -> {"ok": True, ...}  tamper-evident proof of everything it did
"""

from .adapters import ToolGuard, UnknownTool
from .core import Colorless
from .errors import ApprovalRequired, PolicyDenied, ColorlessError
from .ledger import GENESIS, Ledger
from .policy import ALLOW, APPROVE, DENY, Decision, Policy
from .redaction import redact_secrets

__version__ = "0.2.0"
__all__ = [
    "Colorless", "Policy", "Decision", "Ledger", "ToolGuard", "UnknownTool",
    "ColorlessError", "PolicyDenied", "ApprovalRequired", "redact_secrets",
    "ALLOW", "DENY", "APPROVE", "GENESIS", "__version__",
]
