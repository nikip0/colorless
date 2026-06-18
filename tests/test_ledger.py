"""The crown jewel: the tamper-evident ledger must catch every edit, delete, reorder, and
tail-truncation. Run: python3 -m unittest tests.test_ledger
"""

import json
import os
import tempfile
import unittest

from colorless.ledger import GENESIS, Ledger


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "log.jsonl")
        self.led = Ledger(self.path)

    def _seed(self, n=4):
        for i in range(n):
            self.led.append("action", ref=f"tool_{i}", action={"name": f"tool_{i}"}, ok=True)

    def _lines(self):
        with open(self.path) as f:
            return f.readlines()

    def _write(self, lines):
        with open(self.path, "w") as f:
            f.writelines(lines)

    def test_append_and_verify_clean(self):
        self._seed(5)
        res = self.led.verify()
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["length"], 5)
        self.assertEqual(self.led.head()["head"], res["head"])

    def test_genesis_links_first_entry(self):
        e = self.led.append("action", ref="x")
        self.assertEqual(e["prev_hash"], GENESIS)
        self.assertEqual(e["seq"], 0)

    def test_entries_filter_by_ref(self):
        self._seed(4)
        only = self.led.entries(ref="tool_2")
        self.assertEqual(len(only), 1)
        self.assertEqual(only[0]["ref"], "tool_2")

    def test_editing_a_payload_is_caught(self):
        self._seed(4)
        lines = self._lines()
        row = json.loads(lines[1])
        row["action"]["name"] = "EVIL"            # forge a past action
        lines[1] = json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
        self._write(lines)
        res = self.led.verify()
        self.assertFalse(res["ok"])
        self.assertEqual(res["broken_at"], 1)
        self.assertIn("altered", res["reason"])

    def test_deleting_a_middle_entry_is_caught(self):
        self._seed(4)
        lines = self._lines()
        del lines[2]
        self._write(lines)
        res = self.led.verify()
        self.assertFalse(res["ok"])
        self.assertEqual(res["broken_at"], 2)

    def test_reordering_is_caught(self):
        self._seed(4)
        lines = self._lines()
        lines[1], lines[2] = lines[2], lines[1]
        self._write(lines)
        res = self.led.verify()
        self.assertFalse(res["ok"])

    def test_tail_truncation_passes_verify_but_fails_anchor(self):
        self._seed(5)
        anchor_path = os.path.join(self.dir, "anchor.json")
        self.led.anchor(anchor_path)
        # erase the most recent two entries (e.g. the agent's last two risky actions)
        self._write(self._lines()[:3])
        # internal verify can't see a tail-truncation — the shorter chain is self-consistent
        self.assertTrue(self.led.verify()["ok"])
        # ...but the published anchor commits the longer prefix, so it's caught
        a = self.led.verify_against_anchor(anchor_path)
        self.assertTrue(a["anchored"])
        self.assertFalse(a["matches"])

    def test_anchor_matches_when_untouched(self):
        self._seed(3)
        anchor_path = os.path.join(self.dir, "anchor.json")
        self.led.anchor(anchor_path)
        self.led.append("action", ref="more")          # appending past the anchor is fine
        a = self.led.verify_against_anchor(anchor_path)
        self.assertTrue(a["matches"], a)

    def test_no_anchor_yet(self):
        self._seed(1)
        a = self.led.verify_against_anchor(os.path.join(self.dir, "nope.json"))
        self.assertFalse(a["anchored"])

    def test_malformed_anchor_without_head_is_not_a_match(self):
        # a corrupt/truncated anchor with no "head" commits nothing — it must NOT read as verified
        self._seed(3)
        bad = os.path.join(self.dir, "bad_anchor.json")
        with open(bad, "w") as f:
            json.dump({"length": 3}, f)              # no head field
        a = self.led.verify_against_anchor(bad)
        self.assertFalse(a["anchored"])
        self.assertNotEqual(a.get("matches"), True)

    def test_non_finite_floats_are_valid_json_and_verify(self):
        # a tool returning NaN/Infinity must not poison the chain with invalid JSON tokens
        self.led.append("action", ref="score", value=float("nan"), big=float("inf"))
        line = self._lines()[0]
        self.assertNotIn("NaN", line)
        self.assertNotIn("Infinity", line)
        parsed = json.loads(line)                    # strict parse succeeds (null, not NaN)
        self.assertIsNone(parsed["value"])
        self.assertIsNone(parsed["big"])
        self.assertTrue(self.led.verify()["ok"])

    def test_payload_cannot_overwrite_chain_fields(self):
        # a caller-supplied key named seq/ts must not clobber the structural field & corrupt the chain
        self.led.append("action", ref="x", seq=999, ts="2000-01-01T00:00:00", note="hi")
        row = json.loads(self._lines()[0])
        self.assertEqual(row["seq"], 0)              # real chain seq, not the payload's 999
        self.assertNotEqual(row["ts"], "2000-01-01T00:00:00")
        self.assertEqual(row["note"], "hi")          # ordinary payload still recorded
        self.assertTrue(self.led.verify()["ok"])


if __name__ == "__main__":
    unittest.main()
