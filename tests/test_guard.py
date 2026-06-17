"""Guarding actions: allow runs+logs, deny/approval block and never execute, errors are
recorded, and the ledger stays verifiable throughout. Run: python3 -m unittest tests.test_guard
"""

import os
import tempfile
import unittest

from colorless import ApprovalRequired, PolicyDenied, Colorless


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "log.jsonl")

    def _w(self, **kw):
        return Colorless(ledger=self.path, **kw)

    def test_allowed_action_runs_and_logs(self):
        w = self._w()
        ran = []

        @w.guard
        def send(msg):
            ran.append(msg)
            return "sent"

        self.assertEqual(send(msg="hi"), "sent")
        self.assertEqual(ran, ["hi"])
        e = w.entries(ref="send")[0]
        self.assertEqual(e["decision"], "allow")
        self.assertTrue(e["executed"] and e["ok"])
        self.assertTrue(w.verify()["ok"])

    def test_denied_action_blocks_and_does_not_run(self):
        w = self._w().deny("drop_table")
        ran = []

        @w.guard
        def drop_table():
            ran.append(1)

        with self.assertRaises(PolicyDenied):
            drop_table()
        self.assertEqual(ran, [])                       # never executed
        e = w.entries(ref="drop_table")[0]
        self.assertEqual(e["decision"], "deny")
        self.assertFalse(e["executed"])
        self.assertTrue(w.verify()["ok"])               # the block itself is sealed in the chain

    def test_approval_required_blocks_without_handler(self):
        w = self._w()
        w.require_approval("refund")
        ran = []

        @w.guard
        def refund(amount):
            ran.append(amount)

        with self.assertRaises(ApprovalRequired):
            refund(amount=999)
        self.assertEqual(ran, [])
        self.assertFalse(w.entries(ref="refund")[0]["executed"])

    def test_approval_granted_runs(self):
        w = self._w(on_approval=lambda action, d: True)
        w.require_approval("refund")

        @w.guard
        def refund(amount):
            return f"ok {amount}"

        self.assertEqual(refund(amount=20), "ok 20")
        e = w.entries(ref="refund")[-1]
        self.assertTrue(e["executed"] and e["approved"])

    def test_error_in_action_is_recorded_and_reraised(self):
        w = self._w()

        @w.guard
        def boom():
            raise ValueError("kaboom")

        with self.assertRaises(ValueError):
            boom()
        e = w.entries(ref="boom")[0]
        self.assertTrue(e["executed"])
        self.assertFalse(e["ok"])
        self.assertIn("kaboom", e["error"])
        self.assertTrue(w.verify()["ok"])

    def test_context_manager_form(self):
        w = self._w().deny("wire_transfer")
        with self.assertRaises(PolicyDenied):
            with w.action("wire_transfer", amount=10000):
                self.fail("body must not run on a denied action")
        # an allowed one runs and logs
        done = []
        with w.action("notify", who="ops"):
            done.append(1)
        self.assertEqual(done, [1])
        self.assertTrue(w.verify()["ok"])

    def test_redaction_keeps_secrets_out_of_the_ledger(self):
        def redact(args):
            return {k: ("***" if k == "api_key" else v) for k, v in args.items()}

        w = self._w(redact=redact)

        @w.guard
        def call_api(api_key, endpoint):
            return "ok"

        call_api(api_key="sk-supersecret", endpoint="/v1/x")
        logged = w.entries(ref="call_api")[0]["action"]["args"]
        self.assertEqual(logged["api_key"], "***")
        self.assertEqual(logged["endpoint"], "/v1/x")

    def test_check_does_not_log(self):
        w = self._w().deny("x")
        d = w.check("x")
        self.assertTrue(d.denied)
        self.assertEqual(w.entries(), [])               # check is pure — nothing written


if __name__ == "__main__":
    unittest.main()
