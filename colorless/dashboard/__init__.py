"""colorless dashboard — the product surface over the engine.

A zero-dependency (stdlib `http.server`) web app that reads the tamper-evident ledger and renders
the live action feed, pending approvals, and integrity/verify status. Launch it with:

    python -m colorless dashboard agent.jsonl

The core engine stays zero-dependency; so does this. `ApprovalQueue` + `queue_approval` make the
human-in-the-loop gate real: an agent blocks on a pending request, a human resolves it on screen.
"""

from .approvals import ApprovalQueue, queue_approval
from .server import DashboardData, serve

__all__ = ["ApprovalQueue", "queue_approval", "DashboardData", "serve"]
