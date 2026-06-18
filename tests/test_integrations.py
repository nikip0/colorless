"""Integration adapters (MCP + LangChain) gate + seal correctly. Uses fakes, so it runs with
neither SDK installed. Run: python3 -m unittest tests.test_integrations
"""

import os
import tempfile
import unittest

from colorless import Colorless, PolicyDenied
from colorless.integrations import crewai, llamaindex, openai_agents
from colorless.integrations._tools import guard_tools as shared_guard_tools
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


# --- fakes mimicking each framework's tool shape ---
class _FakeBaseTool:
    """CrewAI/LangChain BaseTool: name + a leaf ._run; the public run() delegates to it."""
    def __init__(self, name, run):
        self.name = name
        self._run = run

    def run(self, **kwargs):
        return self._run(**kwargs)


class _FakeFunctionTool:
    """LlamaIndex FunctionTool: metadata.name + a leaf .fn."""
    class _Md:
        def __init__(self, name):
            self.name = name

    def __init__(self, name, fn):
        self.metadata = self._Md(name)
        self.fn = fn

    def call(self, **kwargs):
        return self.fn(**kwargs)


class _FakeStructuredToolWithRun:
    """StructuredTool-like: BOTH .func (leaf) and ._run (delegates to func) — the double-wrap trap."""
    def __init__(self, name, func):
        self.name = name
        self.func = func

    def _run(self, **kwargs):
        return self.func(**kwargs)

    def invoke(self, kwargs):
        return self._run(**kwargs)


class FrameworkAdapterTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "l.jsonl")

    def test_crewai_basetool(self):
        cl = Colorless(self.path).deny("danger")
        (g,) = crewai.guard_tools(cl, [_FakeBaseTool("danger", lambda **k: "boom")])
        with self.assertRaises(PolicyDenied):
            g.run()                                   # public run -> guarded leaf _run -> blocked
        self.assertEqual(cl.entries("danger")[0]["decision"], "deny")

    def test_llamaindex_functiontool(self):
        cl = Colorless(self.path)
        (g,) = llamaindex.guard_tools(cl, [_FakeFunctionTool("search", lambda q: f"r:{q}")])
        self.assertEqual(g.call(q="x"), "r:x")        # name resolved from metadata.name
        self.assertEqual(cl.entries("search")[0]["decision"], "allow")

    def test_openai_agents_guard_decorator(self):
        cl = Colorless(self.path).deny("wipe")

        @openai_agents.guard(cl, name="wipe")
        def wipe():
            return "gone"

        with self.assertRaises(PolicyDenied):
            wipe()
        self.assertEqual(cl.entries("wipe")[0]["decision"], "deny")

    def test_no_double_wrap_when_run_delegates_to_func(self):
        cl = Colorless(self.path)
        (g,) = shared_guard_tools(cl, [_FakeStructuredToolWithRun("act", lambda x: x * 2)])
        self.assertEqual(g.invoke({"x": 3}), 6)       # invoke -> _run(original) -> func(guarded)
        self.assertEqual(len(cl.entries("act")), 1)   # exactly ONE log entry, not two

    def test_adapters_share_one_implementation(self):
        self.assertIs(crewai.guard_tools, llamaindex.guard_tools)
        self.assertIs(crewai.guard_tools, guard_tools)   # langchain re-exports the same


if __name__ == "__main__":
    unittest.main()
