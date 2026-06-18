"""Alerting: webhook/slack alerters fire on blocked or errored actions (not allowed ones), and the
approval-queue on_request fires when an action needs a human. Fake sender = no network in tests.
Run: python3 -m unittest tests.test_alerts
"""

import os
import tempfile
import unittest

from colorless import Colorless, PolicyDenied
from colorless.alerts import approval_alerter, post_json, slack_alerter, webhook_alerter
from colorless.dashboard import ApprovalQueue


class _Sink:
    def __init__(self):
        self.calls = []

    def __call__(self, url, payload):
        self.calls.append((url, payload))


class AlertsTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "log.jsonl")

    def test_webhook_alerts_on_block_not_on_allow(self):
        sink = _Sink()
        cl = Colorless(ledger=self.path).deny("danger")
        cl.subscribe(webhook_alerter("http://x", sender=sink, background=False))
        cl.run("ok", {"a": 1}, lambda: "y")             # allowed -> no alert
        self.assertEqual(len(sink.calls), 0)
        with self.assertRaises(PolicyDenied):
            cl.run("danger", {}, lambda: "boom")        # denied -> alert
        self.assertEqual(len(sink.calls), 1)
        url, payload = sink.calls[0]
        self.assertEqual(url, "http://x")
        self.assertEqual(payload["entry"]["action"]["name"], "danger")

    def test_alerts_on_error(self):
        sink = _Sink()
        cl = Colorless(ledger=self.path)
        cl.subscribe(webhook_alerter("http://x", sender=sink, background=False))

        def boom():
            raise ValueError("x")

        with self.assertRaises(ValueError):
            cl.run("boom", {}, boom)
        self.assertEqual(len(sink.calls), 1)
        self.assertFalse(sink.calls[0][1]["entry"]["ok"])

    def test_slack_alerter_formats_text(self):
        sink = _Sink()
        cl = Colorless(ledger=self.path).deny("wipe")
        cl.subscribe(slack_alerter("http://slack", sender=sink, background=False))
        with self.assertRaises(PolicyDenied):
            cl.run("wipe", {}, lambda: "x")
        self.assertEqual(len(sink.calls), 1)
        text = sink.calls[0][1]["text"]
        self.assertIn("blocked", text)
        self.assertIn("wipe", text)

    def test_approval_alerter_via_queue(self):
        sink = _Sink()
        q = ApprovalQueue(os.path.join(tempfile.mkdtemp(), "q.json"),
                          on_request=approval_alerter("http://x", slack=True, sender=sink, background=False))
        q.request({"name": "refund", "args": {"amount": 9000}})
        self.assertEqual(len(sink.calls), 1)
        text = sink.calls[0][1]["text"]
        self.assertIn("refund", text)
        self.assertIn("approval", text.lower())

    def test_post_json_swallows_failure(self):
        self.assertIsNone(post_json("http://127.0.0.1:1/", {"x": 1}, timeout=1))   # refused -> None, no raise

    def test_background_dispatch_delivers_via_shared_worker(self):
        # background=True now routes through ONE shared bounded-queue worker (not a thread per alert)
        import colorless.alerts as alerts_mod
        sink = _Sink()
        cl = Colorless(ledger=self.path).deny("danger")
        cl.subscribe(slack_alerter("http://x", sender=sink, background=True))
        with self.assertRaises(PolicyDenied):
            cl.run("danger", {}, lambda: "boom")
        self.assertIsNotNone(alerts_mod._alert_q)   # lazily started on first background alert
        alerts_mod._alert_q.join()                  # deterministic: wait for the worker to drain
        self.assertEqual(len(sink.calls), 1)
        self.assertIn("blocked", sink.calls[0][1]["text"])


if __name__ == "__main__":
    unittest.main()
