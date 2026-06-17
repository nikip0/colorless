"""Secrets must never land in the ledger. Redaction is on by default. Run:
python3 -m unittest tests.test_redaction
"""

import os
import tempfile
import unittest

from colorless import Colorless, redact_secrets


class RedactionTest(unittest.TestCase):
    def test_redacts_by_key_name(self):
        out = redact_secrets({"api_key": "abc", "password": "p", "city": "NYC"})
        self.assertEqual(out["api_key"], "***")
        self.assertEqual(out["password"], "***")
        self.assertEqual(out["city"], "NYC")            # ordinary fields untouched

    def test_redacts_by_value_pattern(self):
        out = redact_secrets({"blob": "sk-ABCDEFGH12345678", "note": "hello"})
        self.assertEqual(out["blob"], "***")
        self.assertEqual(out["note"], "hello")

    def test_redacts_bearer_github_aws_slack(self):
        out = redact_secrets({
            "a": "Bearer xyz.123",
            "b": "ghp_" + "A" * 22,
            "c": "AKIA" + "B" * 16,
            "d": "xoxb-" + "1" * 12,
        })
        self.assertTrue(all(out[k] == "***" for k in "abcd"), out)

    def test_redacts_nested_dicts_and_lists(self):
        out = redact_secrets({
            "config": {"api_key": "abc", "host": "x"},
            "items": [{"token": "t"}, "sk-ABCDEFGH12345678", "plain"],
            "ok": "fine",
        })
        self.assertEqual(out["config"]["api_key"], "***")   # nested secret key masked
        self.assertEqual(out["config"]["host"], "x")
        self.assertEqual(out["items"][0]["token"], "***")   # secret key inside a list item
        self.assertEqual(out["items"][1], "***")            # secret-pattern string in a list
        self.assertEqual(out["items"][2], "plain")
        self.assertEqual(out["ok"], "fine")

    def test_default_colorless_redacts_secrets(self):
        path = os.path.join(tempfile.mkdtemp(), "log.jsonl")
        w = Colorless(ledger=path)                      # auto-redaction ON by default

        @w.guard
        def call_api(api_key, endpoint):
            return "ok"

        call_api(api_key="sk-supersecret123456", endpoint="/v1/x")
        args = w.entries(ref="call_api")[0]["action"]["args"]
        self.assertEqual(args["api_key"], "***")
        self.assertEqual(args["endpoint"], "/v1/x")

    def test_redaction_can_be_disabled(self):
        path = os.path.join(tempfile.mkdtemp(), "log.jsonl")
        w = Colorless(ledger=path, redact=None)

        @w.guard
        def call_api(api_key):
            return "ok"

        call_api(api_key="plaintext-on-purpose")
        self.assertEqual(w.entries(ref="call_api")[0]["action"]["args"]["api_key"],
                         "plaintext-on-purpose")


if __name__ == "__main__":
    unittest.main()
