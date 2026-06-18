"""The CLI is what an auditor (or CI) runs to independently verify a ledger.
Run: python3 -m unittest tests.test_cli
"""

import contextlib
import io
import os
import tempfile
import unittest

from colorless import Colorless
from colorless.__main__ import main


def _run(argv):
    """Run the CLI, swallow its stdout, return the exit code."""
    with contextlib.redirect_stdout(io.StringIO()):
        return main(argv)


def _run_capture(argv):
    """Run the CLI, return (exit_code, stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "log.jsonl")
        w = Colorless(ledger=self.path)

        @w.guard
        def step(x):
            return x

        for i in range(3):
            step(x=i)

    def _lines(self):
        with open(self.path) as f:
            return f.readlines()

    def test_verify_clean_exits_zero(self):
        self.assertEqual(_run(["verify", self.path]), 0)

    def test_verify_broken_exits_one(self):
        lines = self._lines()
        lines[0] = lines[0].replace('"x":0', '"x":99')   # forge a past action
        with open(self.path, "w") as f:
            f.writelines(lines)
        self.assertEqual(_run(["verify", self.path]), 1)

    def test_head_and_tail_ok(self):
        self.assertEqual(_run(["head", self.path]), 0)
        self.assertEqual(_run(["tail", self.path, "-n", "2"]), 0)

    def test_tail_zero_prints_nothing(self):
        # `tail -n 0` must print 0 rows, not the whole ledger (the entries()[-0:] footgun)
        code, out = _run_capture(["tail", self.path, "-n", "0"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_verify_missing_ledger_exits_one(self):
        # a deleted / mis-pathed ledger must FAIL verify, not pass as "ok, length 0"
        gone = os.path.join(self.dir, "does_not_exist.jsonl")
        self.assertEqual(_run(["verify", gone]), 1)

    def test_anchor_then_verify_anchor(self):
        anchor = os.path.join(self.dir, "a.json")
        self.assertEqual(_run(["anchor", self.path, anchor]), 0)
        self.assertTrue(os.path.exists(anchor))
        self.assertEqual(_run(["verify-anchor", self.path, anchor]), 0)
        # truncate the tail -> the published anchor no longer matches -> exit 1
        with open(self.path, "w") as f:
            f.writelines(self._lines()[:1])
        self.assertEqual(_run(["verify-anchor", self.path, anchor]), 1)


if __name__ == "__main__":
    unittest.main()
