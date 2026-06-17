"""ToolGuard: gate + log tool calls in the universal (name, args) shape that OpenAI / Anthropic /
MCP all use. Run: python3 -m unittest tests.test_adapters
"""

import os
import tempfile
import unittest

from colorless import ApprovalRequired, PolicyDenied, ToolGuard, UnknownTool, Colorless


class ToolGuardTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "log.jsonl")

    def _tg(self, **kw):
        return Colorless(ledger=self.path, **kw)

    def test_call_allowed_tool_runs_and_logs(self):
        w = self._tg()
        tg = ToolGuard(w)
        tg.add("get_weather", lambda city: f"{city}: sunny")
        out = tg.call("get_weather", {"city": "NYC"})       # the LLM tool_call shape
        self.assertEqual(out, "NYC: sunny")
        e = w.entries(ref="get_weather")[0]
        self.assertEqual(e["decision"], "allow")
        self.assertTrue(e["ok"])
        self.assertTrue(w.verify()["ok"])

    def test_denied_tool_is_blocked_and_not_run(self):
        w = self._tg().deny("wire_money")
        tg = ToolGuard(w)
        ran = []
        tg.add("wire_money", lambda **k: ran.append(k))
        with self.assertRaises(PolicyDenied):
            tg.call("wire_money", {"amount": 9000})
        self.assertEqual(ran, [])
        self.assertFalse(w.entries(ref="wire_money")[0]["executed"])

    def test_approval_required_tool_blocks_without_handler(self):
        w = self._tg()
        w.require_approval("delete_file")
        tg = ToolGuard(w)
        tg.add("delete_file", lambda path: "gone")
        with self.assertRaises(ApprovalRequired):
            tg.call("delete_file", {"path": "/etc/hosts"})

    def test_register_decorator(self):
        w = self._tg()
        tg = ToolGuard(w)

        @tg.register()
        def search(q):
            return f"results for {q}"

        self.assertEqual(tg.call("search", {"q": "colorless"}), "results for colorless")

    def test_unknown_tool_raises(self):
        tg = ToolGuard(self._tg())
        with self.assertRaises(UnknownTool):
            tg.call("nonexistent", {})

    def test_guarded_returns_wrapped_callables(self):
        w = self._tg().deny("danger")
        tg = ToolGuard(w)
        tg.add("safe", lambda: "ok").add("danger", lambda: "boom")
        fns = tg.guarded()
        self.assertEqual(fns["safe"](), "ok")
        with self.assertRaises(PolicyDenied):
            fns["danger"]()

    def test_simulated_agent_loop_is_fully_verifiable(self):
        # mimic a model emitting a sequence of tool_calls; colorless gates + logs each
        w = self._tg().deny("drop_table")
        tg = ToolGuard(w)
        tg.add("query", lambda sql: "rows").add("drop_table", lambda name: "dropped")
        tool_calls = [("query", {"sql": "select 1"}),
                      ("drop_table", {"name": "users"}),
                      ("query", {"sql": "select 2"})]
        results = []
        for name, args in tool_calls:
            try:
                results.append(tg.call(name, args))
            except PolicyDenied:
                results.append("BLOCKED")
        self.assertEqual(results, ["rows", "BLOCKED", "rows"])
        self.assertEqual(len(w.entries()), 3)               # all three attempts sealed
        self.assertTrue(w.verify()["ok"])


if __name__ == "__main__":
    unittest.main()
