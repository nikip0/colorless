"""Live human-in-the-loop approvals — the "approve from a screen" half of the dashboard.

An agent's `on_approval` enqueues a pending request and blocks until a human resolves it in the
dashboard (or a timeout elapses → denied, fail-safe). File-backed JSON so the queue survives a
restart and can be shared between the agent process and the dashboard process.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone

try:
    import fcntl  # POSIX advisory file locking — serialises the queue ACROSS processes
except ImportError:  # pragma: no cover - Windows
    fcntl = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApprovalQueue:
    def __init__(self, path: str = "colorless_approvals.json", on_request=None):
        self.path = str(path)
        self._lock = threading.Lock()
        self.on_request = on_request   # cb(record) fired when a pending approval is created (alerts)

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

    @contextlib.contextmanager
    def _file_lock(self):
        """Exclusive advisory lock around a read-modify-write, so a SEPARATE process (the agent
        enqueuing vs. the dashboard resolving) can't clobber the file and lose an update. Locks a
        dedicated sidecar file (never os.replace'd, so the inode stays stable). No-op without fcntl."""
        if fcntl is None:  # pragma: no cover - Windows
            yield
            return
        lock_f = open(self.path + ".lock", "w")
        try:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)
            lock_f.close()

    def request(self, action: dict) -> str:
        """Enqueue a pending approval; returns its id. Fires `on_request` best-effort AFTER the lock
        is released, so a slow alert (network POST) never blocks other enqueues."""
        rec = {"id": uuid.uuid4().hex[:12], "action": action, "status": "pending",
               "requested_at": _now(), "decided_at": None}
        with self._lock, self._file_lock():
            rows = self._read()
            rows.append(rec)
            self._write(rows)
        if self.on_request:
            try:
                self.on_request(rec)
            except Exception:
                pass  # an alert must never break the enqueue
        return rec["id"]

    def pending(self) -> list:
        return [r for r in self._read() if r.get("status") == "pending"]

    def all(self) -> list:
        return self._read()

    def get(self, rid: str):
        for r in self._read():
            if r.get("id") == rid:
                return r
        return None

    def resolve(self, rid: str, approved: bool, approver: "str | None" = None) -> bool:
        """Approve/deny a pending request, recording who resolved it. Returns False if it's unknown
        or already decided."""
        with self._lock, self._file_lock():
            rows = self._read()
            for r in rows:
                if r.get("id") == rid and r.get("status") == "pending":
                    r["status"] = "approved" if approved else "denied"
                    r["decided_at"] = _now()
                    if approver:
                        r["approver"] = approver
                    self._write(rows)
                    return True
            return False


def queue_approval(queue: ApprovalQueue, poll: float = 0.5, timeout: float = 300.0):
    """Return an `on_approval(action, decision)` that enqueues the action and blocks until a human
    resolves it in the dashboard, or `timeout` seconds pass (→ denied, fail-safe). Returns
    `{"approved": bool, "approver": str | None}` so the resolver's identity reaches the ledger.

        cl = Colorless("agent.jsonl", on_approval=queue_approval(ApprovalQueue()))
    """
    def on_approval(action, decision):
        rid = queue.request(action)
        deadline = time.monotonic() + timeout   # wall-clock: each get() also costs real time
        while time.monotonic() < deadline:
            rec = queue.get(rid)
            if rec and rec.get("status") != "pending":
                # dict carries the approver through to the ledger (who authorized it)
                return {"approved": rec["status"] == "approved", "approver": rec.get("approver")}
            time.sleep(poll)
        return {"approved": False, "approver": None}  # timed out → deny (never auto-approve on silence)

    return on_approval
