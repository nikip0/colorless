"""Integration adapters (MCP + LangChain) gate + seal correctly. Uses fakes, so it runs with
neither SDK installed. Run: python3 -m unittest tests.test_integrations
"""

import os
import tempfile
import unittest

from colorless import Colorless, PolicyDenied
from colorless.integrations.langchain import guard_callable, guard_tools
from colorless.integrations.mcp import tool_guard


class _FakeStructuredTool:
    """Mimics a LangChain StructuredTool: a `.name` and a settable `.func` callable."""

    def __init__(self, name, func):
        self.name = name
        self.func = func

    def invoke(self, kwargs):          # what LangChain calls at runtime
        return self.func(**kwargs)


class IntegrationsTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "l.jsonl")

    # --- MCP ---
    def test_mcp_tool_guard_gates_and_seals(self):
        cl = Colorless(self.path).deny("drop")
        tg = tool_guard(cl, {"q": lambda x: f"r:{x}", "drop": lambda: "boom"})
        self.assertEqual(tg.call("q", {"x": 1}), "r:1")
        with self.assertRaises(PolicyDenied):
            tg.call("drop", {})
        self.assertTrue(cl.verify()["ok"])

    # --- LangChain ---
    def test_guard_tools_wraps_tool_object_func(self):
        cl = Colorless(self.path).deny("delete_user")
        search = _FakeStructuredTool("search", lambda query: f"r:{query}")
        delete = _FakeStructuredTool("delete_user", lambda user_id: "gone")
        tools = guard_tools(cl, [search, delete])
        self.assertEqual(tools[0].invoke({"query": "x"}), "r:x")     # allowed runs
        with self.assertRaises(PolicyDenied):
            tools[1].invoke({"user_id": "u1"})                        # denied blocks
        self.assertEqual(len(cl.entries()), 2)                        # both attempts sealed
        self.assertTrue(cl.verify()["ok"])

    def test_guard_tools_wraps_plain_callable(self):
        cl = Colorless(self.path).deny("danger")

        def danger():
            return "boom"

        guarded = guard_tools(cl, [danger])[0]
        with self.assertRaises(PolicyDenied):
            guarded()

    def test_guard_callable_single(self):
        cl = Colorless(self.path)
        f = guard_callable(cl, lambda a: a * 2, name="double")
        self.assertEqual(f(a=3), 6)
        self.assertEqual(cl.entries(ref="double")[0]["decision"], "allow")


if __name__ == "__main__":
    unittest.main()
