"""Live human-in-the-loop approvals — the "approve from a screen" half of the dashboard.

An agent's `on_approval` enqueues a pending request and blocks until a human resolves it in the
dashboard (or a timeout elapses → denied, fail-safe). File-backed JSON so the queue survives a
restart and can be shared between the agent process and the dashboard process.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApprovalQueue:
    def __init__(self, path: str = "colorless_approvals.json"):
        self.path = str(path)
        self._lock = threading.Lock()

    def _read(self) -> list:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def _write(self, rows: list) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(rows, f, indent=2)
        os.replace(tmp, self.path)  # atomic — never leaves a half-written queue

    def request(self, action: dict) -> str:
        """Enqueue a pending approval; returns its id."""
        with self._lock:
            rows = self._read()
            rid = uuid.uuid4().hex[:12]
            rows.append({"id": rid, "action": action, "status": "pending",
                         "requested_at": _now(), "decided_at": None})
            self._write(rows)
            return rid

    def pending(self) -> list:
        return [r for r in self._read() if r.get("status") == "pending"]

    def all(self) -> list:
        return self._read()

    def get(self, rid: str):
        for r in self._read():
            if r.get("id") == rid:
                return r
        return None

    def resolve(self, rid: str, approved: bool) -> bool:
        """Approve/deny a pending request. Returns False if it's unknown or already decided."""
        with self._lock:
            rows = self._read()
            for r in rows:
                if r.get("id") == rid and r.get("status") == "pending":
                    r["status"] = "approved" if approved else "denied"
                    r["decided_at"] = _now()
                    self._write(rows)
                    return True
            return False


def queue_approval(queue: ApprovalQueue, poll: float = 0.5, timeout: float = 300.0):
    """Return an `on_approval(action, decision) -> bool` that enqueues the action and blocks until a
    human resolves it in the dashboard, or `timeout` seconds pass (→ denied, fail-safe).

        cl = Colorless("agent.jsonl", on_approval=queue_approval(ApprovalQueue()))
    """
    def on_approval(action, decision) -> bool:
        rid = queue.request(action)
        waited = 0.0
        while waited < timeout:
            rec = queue.get(rid)
            if rec and rec.get("status") != "pending":
                return rec["status"] == "approved"
            time.sleep(poll)
            waited += poll
        return False  # timed out → deny (never auto-approve on silence)

    return on_approval
