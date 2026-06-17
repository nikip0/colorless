"""warrant — authorize, gate, and prove every action your AI agent takes.

    from warrant import Warrant

    w = Warrant("agent.jsonl")
    w.deny("delete_database")
    w.require_approval("refund", when=lambda a: a["args"].get("amount", 0) > 100)

    @w.guard
    def refund(amount, to): ...

    w.verify()   # -> {"ok": True, ...}  tamper-evident proof of everything it did
"""

from .core import Warrant
from .errors import ApprovalRequired, PolicyDenied, WarrantError
from .ledger import GENESIS, Ledger
from .policy import ALLOW, APPROVE, DENY, Decision, Policy

__version__ = "0.1.0"
__all__ = [
    "Warrant", "Policy", "Decision", "Ledger",
    "WarrantError", "PolicyDenied", "ApprovalRequired",
    "ALLOW", "DENY", "APPROVE", "GENESIS", "__version__",
]
