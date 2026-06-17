"""Policy engine: ordered rules, first match wins, configurable default.
Run: python3 -m unittest tests.test_policy
"""

import unittest

from colorless.policy import Policy


def act(name, **args):
    return {"name": name, "args": args}


class PolicyTest(unittest.TestCase):
    def test_default_allow(self):
        self.assertTrue(Policy().decide(act("anything")).allowed)

    def test_default_deny(self):
        self.assertTrue(Policy(default="deny").decide(act("anything")).denied)

    def test_deny_by_name(self):
        p = Policy().deny("delete_db")
        self.assertTrue(p.decide(act("delete_db")).denied)
        self.assertTrue(p.decide(act("read")).allowed)

    def test_require_approval_with_predicate(self):
        p = Policy().require_approval("refund", when=lambda a: a["args"]["amount"] > 100)
        self.assertTrue(p.decide(act("refund", amount=500)).needs_approval)
        self.assertTrue(p.decide(act("refund", amount=50)).allowed)

    def test_first_match_wins(self):
        # a specific allow placed BEFORE a broad deny should win for the specific case
        p = Policy().allow("refund", when=lambda a: a["args"]["amount"] < 10).deny("refund")
        self.assertTrue(p.decide(act("refund", amount=5)).allowed)
        self.assertTrue(p.decide(act("refund", amount=999)).denied)

    def test_reason_is_surfaced(self):
        p = Policy().deny("wipe", reason="destructive and irreversible")
        d = p.decide(act("wipe"))
        self.assertEqual(d.reason, "destructive and irreversible")

    def test_chaining_returns_policy(self):
        p = Policy()
        self.assertIs(p.deny("a"), p)
        self.assertIs(p.allow("b"), p)

    def test_invalid_default_rejected(self):
        with self.assertRaises(ValueError):
            Policy(default="maybe")


if __name__ == "__main__":
    unittest.main()
