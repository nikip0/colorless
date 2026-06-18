"""OpenTelemetry export: attribute mapping + live instrument + batch export. Uses a fake tracer so
it runs without opentelemetry installed. Run: python3 -m unittest tests.test_otel
"""

import os
import tempfile
import unittest

from colorless import Colorless, PolicyDenied
from colorless.otel import export_ledger, genai_attributes, instrument


class _FakeSpan:
    def __init__(self, name):
        self.name = name
        self.attributes = {}
        self.ended = False

    def set_attribute(self, k, v):
        self.attributes[k] = v

    def end(self):
        self.ended = True


class _FakeTracer:
    def __init__(self):
        self.spans = []

    def start_span(self, name):
        s = _FakeSpan(name)
        self.spans.append(s)
        return s


class OtelTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "log.jsonl")

    def test_genai_attributes_mapping(self):
        entry = {"seq": 0, "ref": "refund", "decision": "allow", "executed": True, "ok": True,
                 "row_hash": "abc", "action": {"name": "refund", "args": {"amount": 80}}}
        a = genai_attributes(entry)
        self.assertEqual(a["gen_ai.operation.name"], "execute_tool")
        self.assertEqual(a["gen_ai.tool.name"], "refund")
        self.assertEqual(a["colorless.decision"], "allow")
        self.assertTrue(a["colorless.executed"] and a["colorless.ok"])
        self.assertIn("amount", a["gen_ai.tool.call.arguments"])
        self.assertEqual(a["colorless.row_hash"], "abc")

    def test_instrument_emits_span_per_action(self):
        cl = Colorless(ledger=self.path).deny("danger")
        tracer = _FakeTracer()
        instrument(cl, tracer)

        cl.run("search", {"q": "hi"}, lambda: "ok")          # allowed
        try:
            cl.run("danger", {}, lambda: "boom")             # denied
        except PolicyDenied:
            pass

        self.assertEqual(len(tracer.spans), 2)               # both the allow and the deny
        names = [s.name for s in tracer.spans]
        self.assertIn("execute_tool search", names)
        self.assertIn("execute_tool danger", names)
        deny_span = next(s for s in tracer.spans if s.name == "execute_tool danger")
        self.assertEqual(deny_span.attributes["colorless.decision"], "deny")
        self.assertFalse(deny_span.attributes["colorless.executed"])
        self.assertTrue(all(s.ended for s in tracer.spans))  # spans always closed

    def test_large_arguments_are_truncated(self):
        entry = {"seq": 0, "decision": "allow", "executed": True, "ok": True,
                 "action": {"name": "ingest", "args": {"blob": "x" * 50000}}}
        a = genai_attributes(entry)
        self.assertLessEqual(len(a["gen_ai.tool.call.arguments"]), 4096 + 20)
        self.assertIn("truncated", a["gen_ai.tool.call.arguments"])

    def test_export_ledger_batch(self):
        cl = Colorless(ledger=self.path)
        cl.run("a", {"x": 1}, lambda: "y")
        cl.run("b", {"x": 2}, lambda: "z")
        tracer = _FakeTracer()
        n = export_ledger(self.path, tracer)
        self.assertEqual(n, 2)
        self.assertEqual(len(tracer.spans), 2)

    def test_genai_attributes_tolerates_non_int_seq(self):
        # a foreign/corrupt row with a non-int seq must not crash the mapping (was int() -> ValueError)
        a = genai_attributes({"seq": "not-an-int", "action": {"name": "x"}})
        self.assertEqual(a["colorless.seq"], -1)

    def test_export_ledger_skips_a_bad_entry_without_aborting(self):
        # one row that makes the backend throw must not abort the whole batch export
        cl = Colorless(ledger=self.path)
        cl.run("a", {"x": 1}, lambda: "y")
        cl.run("b", {"x": 2}, lambda: "z")

        class _ThrowingSpan(_FakeSpan):
            def set_attribute(self, k, v):
                if k == "gen_ai.tool.name" and v == "b":
                    raise RuntimeError("backend rejected this attribute")
                super().set_attribute(k, v)

        class _ThrowingTracer(_FakeTracer):
            def start_span(self, name):
                s = _ThrowingSpan(name)
                self.spans.append(s)
                return s

        n = export_ledger(self.path, _ThrowingTracer())
        self.assertEqual(n, 1)              # the good row exported; the bad one skipped, not fatal

    def test_subscriber_failure_never_breaks_logging(self):
        cl = Colorless(ledger=self.path)
        cl.subscribe(lambda entry: (_ for _ in ()).throw(RuntimeError("boom")))  # bad subscriber
        cl.run("a", {}, lambda: "ok")                        # must not raise
        self.assertTrue(cl.verify()["ok"])
        self.assertEqual(len(cl.entries()), 1)


if __name__ == "__main__":
    unittest.main()
