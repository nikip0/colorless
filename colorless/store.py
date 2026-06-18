"""Pluggable ledger storage. The chain logic (hashing / verify / anchor) lives in `Ledger`; a
Store only persists and retrieves sealed rows. Two backends, both zero-dependency:

  - JsonlStore  : append-only JSONL file — the portable, cross-language default.
  - SqliteStore : stdlib `sqlite3` — indexed head()/entries()/tail(), no full-file rewrite or
                  full-file read on the hot path; scales to millions of rows.

Entries and hashing are identical in either backend, so verify() is backend-agnostic: the SAME
sealed entries produce the SAME head hash whether stored as JSONL or SQLite (see test_store).
"""

from __future__ import annotations

import json
import os
import sqlite3

from .ledger import GENESIS, canonical


class JsonlStore:
    """Append-only JSONL file (the default)."""

    def __init__(self, path: str):
        self.path = str(path)

    def iter_all(self):
        """Stream entries one at a time (constant memory — used by verify on large ledgers)."""
        if not os.path.exists(self.path):
            return
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def read_all(self) -> list:
        return list(self.iter_all())

    def append_row(self, entry: dict) -> None:
        with open(self.path, "a") as f:
            f.write(canonical(entry) + "\n")

    def head(self) -> dict:
        rows = self.read_all()
        if not rows:
            return {"head": GENESIS, "length": 0}
        return {"head": rows[-1]["row_hash"], "length": len(rows)}

    def entries(self, ref=None) -> list:
        return [r for r in self.read_all() if ref is None or r.get("ref") == ref]

    def tail(self, limit: int) -> list:
        return self.read_all()[-int(limit):]


class SqliteStore:
    """sqlite3-backed store — indexed reads, append without rewriting the whole file. Each call
    uses its own connection (cheap, and safe across threads/processes; SQLite file-locks writes)."""

    def __init__(self, path: str):
        self.path = str(path)
        self._exec(self._create)

    def _exec(self, fn):
        conn = sqlite3.connect(self.path)
        try:
            with conn:                      # commit on success / rollback on error
                return fn(conn)
        finally:
            conn.close()

    @staticmethod
    def _create(c):
        c.execute(
            "CREATE TABLE IF NOT EXISTS entries ("
            "seq INTEGER PRIMARY KEY, ref TEXT, row_hash TEXT UNIQUE, "
            "prev_hash TEXT, content_hash TEXT, data TEXT NOT NULL)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_entries_ref ON entries(ref)")

    def iter_all(self):
        """Stream rows from a server-side cursor (constant memory) — used by verify at scale."""
        conn = sqlite3.connect(self.path)
        try:
            for (d,) in conn.execute("SELECT data FROM entries ORDER BY seq"):
                yield json.loads(d)
        finally:
            conn.close()

    def read_all(self) -> list:
        return list(self.iter_all())

    def append_row(self, entry: dict) -> None:
        self._exec(lambda c: c.execute(
            "INSERT INTO entries (seq, ref, row_hash, prev_hash, content_hash, data) "
            "VALUES (?,?,?,?,?,?)",
            (entry["seq"], entry.get("ref", ""), entry["row_hash"], entry["prev_hash"],
             entry["content_hash"], canonical(entry))))

    def head(self) -> dict:
        def f(c):
            n = c.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            if not n:
                return {"head": GENESIS, "length": 0}
            h = c.execute("SELECT row_hash FROM entries ORDER BY seq DESC LIMIT 1").fetchone()[0]
            return {"head": h, "length": n}
        return self._exec(f)

    def entries(self, ref=None) -> list:
        def f(c):
            if ref is None:
                cur = c.execute("SELECT data FROM entries ORDER BY seq")
            else:
                cur = c.execute("SELECT data FROM entries WHERE ref=? ORDER BY seq", (ref,))
            return [json.loads(d) for (d,) in cur]
        return self._exec(f)

    def tail(self, limit: int) -> list:
        rows = self._exec(lambda c: c.execute(
            "SELECT data FROM entries ORDER BY seq DESC LIMIT ?", (int(limit),)).fetchall())
        return [json.loads(d) for (d,) in reversed(rows)]
