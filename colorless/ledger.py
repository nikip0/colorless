"""Tamper-evident, append-only ledger for AI-agent actions.

Every entry is sealed into a hash chain:

    content_hash = sha256(canonical(entry payload))
    row_hash     = sha256(prev_hash + content_hash)

Editing, reordering, deleting, or backdating any past entry changes its content hash, which breaks
the row hash, which breaks every link after it — `verify()` catches all of it. `anchor()` snapshots
the head hash so even truncation of the recent tail is provable against an externally published value.

The chain logic lives here; persistence is a pluggable Store (see `store.py`). The default is a
zero-dependency JSONL file (portable, cross-language). Point the ledger at a `.db` / `.sqlite` path
(or pass `backend="sqlite"`) to use the indexed, scalable stdlib-sqlite3 backend — same entries,
same hashes, so verify (and cross-language verify) are backend-agnostic.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from datetime import datetime, timezone

GENESIS = "0" * 64
# the linking fields are NOT part of the signed content (they're derived from it)
_CHAIN_FIELDS = ("content_hash", "prev_hash", "row_hash")


def _json_default(o):
    return o.isoformat() if isinstance(o, datetime) else str(o)


def _sanitize(o):
    """Normalise non-finite floats (NaN / Infinity) to None. json.dumps would otherwise emit the
    bare tokens `NaN`/`Infinity` — invalid JSON that a strict parser (every non-Python verifier)
    rejects — so this keeps the chain valid JSON and matches JS's JSON.stringify(NaN) === null,
    preserving cross-language verify."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_sanitize(v) for v in o]
    return o


def canonical(payload: dict) -> str:
    """Deterministic JSON — sorted keys, no whitespace, non-finite floats normalised to null — so
    the same entry always hashes identically and verify can reproduce the write-time hash."""
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"), default=_json_default)


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def content_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k not in _CHAIN_FIELDS}
    return _sha(canonical(body))


def _detect_backend(path: str) -> str:
    return "sqlite" if path.lower().endswith((".db", ".sqlite", ".sqlite3")) else "jsonl"


class Ledger:
    """An append-only, hash-chained ledger over a pluggable Store."""

    def __init__(self, path: str = "colorless.jsonl", backend: "str | None" = None, store=None):
        self.path = str(path)
        self._lock = threading.Lock()  # serialise read-head -> append within this process
        if store is not None:
            self.store = store
            self.backend = getattr(store, "backend", "custom")
        else:
            from .store import JsonlStore, SqliteStore  # lazy import avoids a circular dependency
            self.backend = backend or _detect_backend(self.path)
            self.store = SqliteStore(self.path) if self.backend == "sqlite" else JsonlStore(self.path)

    # --- internal -------------------------------------------------------------
    def _read(self) -> list:
        return self.store.read_all()

    # --- writing --------------------------------------------------------------
    def append(self, kind: str, ref: str = "", **payload) -> dict:
        """Seal one entry to the end of the chain. Returns the full entry (incl. row_hash).

        The read-head -> write is serialised by an in-process lock, so concurrent agent threads
        can't fork the chain by computing `prev_hash` off the same head. (Single-writer per ledger
        is the supported model; concurrent threads in one process are safe.)"""
        with self._lock:
            h = self.store.head()
            prev = h["head"]
            # payload first, then the chain/meta fields — so a caller-supplied payload key named
            # seq/ts/kind/ref can never silently overwrite a structural field and corrupt the chain
            # (key order is irrelevant to the hash: canonical() sorts keys).
            entry = {
                **payload,
                "seq": h["length"],
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                "ref": str(ref or ""),
            }
            ch = content_hash(entry)
            entry["content_hash"] = ch
            entry["prev_hash"] = prev
            entry["row_hash"] = _sha(prev + ch)
            self.store.append_row(entry)
            return entry

    # --- reading --------------------------------------------------------------
    def head(self) -> dict:
        """Head hash + length — the compact fingerprint of the entire history."""
        return self.store.head()

    def entries(self, ref=None) -> list:
        """All entries, or just those for one ref (e.g. a single tool / request id)."""
        return self.store.entries(ref)

    def tail(self, limit: int = 500) -> list:
        """The last `limit` entries (oldest-first). Indexed on the sqlite backend — the dashboard
        feed uses this so it never reads the whole ledger."""
        return self.store.tail(limit)

    # --- verification ---------------------------------------------------------
    def verify(self) -> dict:
        """Re-walk the chain and re-hash every entry, STREAMING it — constant memory even on a
        million-row ledger. Catches edits, deletes, reorders, and forks. Read-only — what an
        auditor runs."""
        prev = GENESIS
        count = 0
        for i, r in enumerate(self.store.iter_all()):
            count = i + 1
            if r.get("seq") != i:
                return self._broken(count, i, "seq out of order (entry inserted, deleted, or reordered)")
            if content_hash(r) != r.get("content_hash"):
                return self._broken(count, i, "entry payload altered")
            if r.get("prev_hash") != prev:
                return self._broken(count, i, "prev_hash discontinuity (broken or forked link)")
            if r.get("row_hash") != _sha(prev + r["content_hash"]):
                return self._broken(count, i, "row_hash mismatch")
            prev = r["row_hash"]
        return {"ok": True, "length": count, "head": prev, "broken_at": None}

    @staticmethod
    def _broken(length, i, reason) -> dict:
        return {"ok": False, "length": length, "broken_at": i, "reason": reason}

    # --- anchoring (defends against tail-truncation) --------------------------
    def anchor(self, path: str) -> dict:
        """Snapshot the head hash to `path` (atomically). Publish that file EXTERNALLY
        (git commit / OpenTimestamps / a public chain) and the head is provably fixed in time:
        nothing at or before it can later be removed or rewritten undetected."""
        h = self.head()
        h["anchored_at"] = datetime.now(timezone.utc).isoformat()
        tmp = str(path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(h, f, indent=2)
        os.replace(tmp, str(path))  # atomic — never leaves a truncated anchor on crash
        return h

    def verify_against_anchor(self, path: str) -> dict:
        """Internal verify proves the chain is self-consistent, but a tail-truncation leaves a valid
        shorter chain. The anchored head commits the whole prefix up to it — if that exact head is
        still present, nothing at/below it was removed or rewritten."""
        try:
            with open(path) as f:
                a = json.load(f)
        except (OSError, ValueError):
            return {"anchored": False, "reason": "no anchor published yet"}
        head = a.get("head")
        if not head:
            # a truncated/corrupt anchor with no head commits nothing — don't report it as a match
            return {"anchored": False, "reason": "anchor missing head — malformed or truncated"}
        present = any(r.get("row_hash") == head for r in self.store.iter_all())
        if head and head != GENESIS and not present:
            return {"anchored": True, "matches": False, "anchored_head": head,
                    "anchored_length": a.get("length"),
                    "reason": "anchored head not in ledger — truncated or replayed below the anchor"}
        return {"anchored": True, "matches": True, "anchored_head": head,
                "anchored_length": a.get("length"), "anchored_at": a.get("anchored_at")}
