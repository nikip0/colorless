"""Tamper-evident, append-only ledger for AI-agent actions.

Every entry is sealed into a hash chain:

    content_hash = sha256(canonical(entry payload))
    row_hash     = sha256(prev_hash + content_hash)

Editing, reordering, deleting, or backdating any past entry changes its content
hash, which breaks the row hash, which breaks every link after it — `verify()`
catches all of it. `anchor()` snapshots the head hash so that even truncation of
the recent tail is provable against an externally published value.

Zero dependencies. The ledger is a plain JSONL file you can read, grep, and ship.
(Generalized from a hash chain originally built for a financial audit trail.)
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone

GENESIS = "0" * 64
# the linking fields are NOT part of the signed content (they're derived from it)
_CHAIN_FIELDS = ("content_hash", "prev_hash", "row_hash")


def _json_default(o):
    return o.isoformat() if isinstance(o, datetime) else str(o)


def canonical(payload: dict) -> str:
    """Deterministic JSON — sorted keys, no whitespace — so the same entry always
    hashes identically and verify can reproduce the write-time hash."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def content_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k not in _CHAIN_FIELDS}
    return _sha(canonical(body))


class Ledger:
    """An append-only, hash-chained JSONL file of agent actions."""

    def __init__(self, path: str = "colorless.jsonl"):
        self.path = str(path)
        self._lock = threading.Lock()  # serialise read-head -> append within this process

    # --- internal -------------------------------------------------------------
    def _read(self) -> list:
        rows = []
        if os.path.exists(self.path):
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
        return rows

    # --- writing --------------------------------------------------------------
    def append(self, kind: str, ref: str = "", **payload) -> dict:
        """Seal one entry to the end of the chain. Returns the full entry (incl. row_hash).

        The read-head -> write is serialised by an in-process lock, so concurrent agent
        threads can't fork the chain by computing `prev_hash` off the same head. (Cross-process
        writers to one ledger file would still need external locking — single-writer per file
        is the supported model; concurrent threads in one process are safe.)"""
        with self._lock:
            rows = self._read()
            prev = rows[-1]["row_hash"] if rows else GENESIS
            entry = {
                "seq": len(rows),
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                "ref": str(ref or ""),
                **payload,
            }
            ch = content_hash(entry)
            entry["content_hash"] = ch
            entry["prev_hash"] = prev
            entry["row_hash"] = _sha(prev + ch)
            with open(self.path, "a") as f:
                f.write(canonical(entry) + "\n")
            return entry

    # --- reading --------------------------------------------------------------
    def head(self) -> dict:
        """Head hash + length — the compact fingerprint of the entire history."""
        rows = self._read()
        if not rows:
            return {"head": GENESIS, "length": 0}
        return {"head": rows[-1]["row_hash"], "length": len(rows)}

    def entries(self, ref=None) -> list:
        """All entries, or just those for one ref (e.g. a single tool / request id)."""
        return [r for r in self._read() if ref is None or r.get("ref") == ref]

    # --- verification ---------------------------------------------------------
    def verify(self) -> dict:
        """Re-walk the chain and re-hash every entry. Catches edits, deletes, reorders,
        and forks. O(n), read-only — this is what an auditor runs."""
        rows = self._read()
        prev = GENESIS
        for i, r in enumerate(rows):
            if r.get("seq") != i:
                return self._broken(rows, i, "seq out of order (entry inserted, deleted, or reordered)")
            if content_hash(r) != r.get("content_hash"):
                return self._broken(rows, i, "entry payload altered")
            if r.get("prev_hash") != prev:
                return self._broken(rows, i, "prev_hash discontinuity (broken or forked link)")
            if r.get("row_hash") != _sha(prev + r["content_hash"]):
                return self._broken(rows, i, "row_hash mismatch")
            prev = r["row_hash"]
        return {"ok": True, "length": len(rows), "head": prev, "broken_at": None}

    @staticmethod
    def _broken(rows, i, reason) -> dict:
        return {"ok": False, "length": len(rows), "broken_at": i, "reason": reason}

    # --- anchoring (defends against tail-truncation) --------------------------
    def anchor(self, path: str) -> dict:
        """Snapshot the head hash to `path` (atomically). Publish that file EXTERNALLY
        (git commit / OpenTimestamps / a public chain) and the head is provably fixed in
        time: nothing at or before it can later be removed or rewritten undetected."""
        h = self.head()
        h["anchored_at"] = datetime.now(timezone.utc).isoformat()
        tmp = str(path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(h, f, indent=2)
        os.replace(tmp, str(path))  # atomic — never leaves a truncated anchor on crash
        return h

    def verify_against_anchor(self, path: str) -> dict:
        """Internal verify proves the chain is self-consistent, but a tail-truncation
        leaves a valid shorter chain. The anchored head commits the whole prefix up to it —
        if that exact head is still present, nothing at/below it was removed or rewritten."""
        try:
            with open(path) as f:
                a = json.load(f)
        except (OSError, ValueError):
            return {"anchored": False, "reason": "no anchor published yet"}
        head = a.get("head")
        present = any(r.get("row_hash") == head for r in self._read())
        if head and head != GENESIS and not present:
            return {"anchored": True, "matches": False, "anchored_head": head,
                    "anchored_length": a.get("length"),
                    "reason": "anchored head not in ledger — truncated or replayed below the anchor"}
        return {"anchored": True, "matches": True, "anchored_head": head,
                "anchored_length": a.get("length"), "anchored_at": a.get("anchored_at")}
