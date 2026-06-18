"""Pluggable storage: JSONL (default) + SQLite. Same hashing/verify in both, so the SAME sealed
entries produce the SAME head hash regardless of backend. Run: python3 -m unittest tests.test_store
"""

import json
import os
import sqlite3
import tempfile
import unittest

from colorless import Colorless, Ledger
from colorless.store import SqliteStore


def _tmp(ext):
    return os.path.join(tempfile.mkdtemp(), "ledger" + ext)


class StoreTest(unittest.TestCase):
    def test_backend_autodetect(self):
        self.assertEqual(Ledger(_tmp(".jsonl")).backend, "jsonl")
        self.assertEqual(Ledger(_tmp(".db")).backend, "sqlite")
        self.assertEqual(Ledger(_tmp(".sqlite")).backend, "sqlite")
        self.assertEqual(Ledger(_tmp(".jsonl"), backend="sqlite").backend, "sqlite")  # explicit override
        self.assertEqual(Ledger(store=SqliteStore(_tmp(".db"))).backend, "sqlite")    # injected store reports its backend

    def _exercise(self, path):
        led = Ledger(path)
        led.append("action", "a", x=1)
        led.append("action", "b", x=2)
        led.append("action", "a", x=3)
        self.assertEqual(led.head()["length"], 3)
        self.assertTrue(led.verify()["ok"])
        self.assertEqual(len(led.entries("a")), 2)                 # filter by ref
        self.assertEqual(len(led.entries()), 3)
        self.assertEqual([e["ref"] for e in led.tail(2)], ["b", "a"])   # last 2, oldest-first
        return led

    def test_jsonl_backend(self):
        self._exercise(_tmp(".jsonl"))

    def test_sqlite_backend(self):
        self._exercise(_tmp(".db"))

    def test_sqlite_tamper_is_caught(self):
        path = _tmp(".db")
        led = Ledger(path)
        led.append("action", "a", x=1)
        led.append("action", "b", x=2)
        con = sqlite3.connect(path)                                # forge a past entry in the DB
        forged = json.loads(con.execute("SELECT data FROM entries WHERE seq=0").fetchone()[0])
        forged["action"] = "EVIL"
        con.execute("UPDATE entries SET data=? WHERE seq=0", (json.dumps(forged),))
        con.commit()
        con.close()
        res = led.verify()
        self.assertFalse(res["ok"])
        self.assertEqual(res["broken_at"], 0)

    def test_cross_backend_same_entries_verify_identically(self):
        jl = Ledger(_tmp(".jsonl"))
        jl.append("action", "a", x=1)
        jl.append("action", "b", x=2)
        spath = _tmp(".db")
        store = SqliteStore(spath)
        for e in jl.entries():                                     # replay the SAME sealed entries
            store.append_row(e)
        sl = Ledger(spath)
        self.assertTrue(sl.verify()["ok"])
        self.assertEqual(sl.head()["head"], jl.head()["head"])     # identical chain, different backend

    def test_sqlite_verify_many_rows_streams(self):
        path = _tmp(".db")
        led = Ledger(path)
        for i in range(200):
            led.append("action", "t", i=i)
        res = led.verify()                                         # streamed walk, constant memory
        self.assertTrue(res["ok"])
        self.assertEqual(res["length"], 200)
        self.assertEqual(led.head()["length"], 200)

    def test_colorless_with_sqlite(self):
        path = _tmp(".db")
        cl = Colorless(ledger=path).deny("danger")

        @cl.guard
        def ok():
            return "y"

        @cl.guard
        def danger():
            return "boom"

        ok()
        try:
            danger()
        except Exception:
            pass
        self.assertTrue(cl.verify()["ok"])
        self.assertEqual(len(cl.entries()), 2)
        self.assertTrue(os.path.exists(path))                      # sqlite file created


if __name__ == "__main__":
    unittest.main()
