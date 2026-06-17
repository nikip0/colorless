"""Async agents are first-class: @guard and ToolGuard.acall gate + seal coroutine tools.
Run: python3 -m unittest tests.test_async
"""

import asyncio
import os
import tempfile
import unittest

from colorless import Colorless, PolicyDenied, ToolGuard


class AsyncTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "log.jsonl")

    def test_async_guard_runs_and_logs(self):
        w = Colorless(ledger=self.path)

        @w.guard
        async def fetch(url):
            await asyncio.sleep(0)
            return f"got {url}"

        self.assertEqual(asyncio.run(fetch(url="http://x")), "got http://x")
        e = w.entries(ref="fetch")[0]
        self.assertTrue(e["executed"] and e["ok"])
        self.assertTrue(w.verify()["ok"])

    def test_async_guard_denied_does_not_run(self):
        w = Colorless(ledger=self.path).deny("nuke")
        ran = []

        @w.guard
        async def nuke():
            ran.append(1)

        with self.assertRaises(PolicyDenied):
            asyncio.run(nuke())
        self.assertEqual(ran, [])
        self.assertFalse(w.entries(ref="nuke")[0]["executed"])

    def test_async_error_is_recorded(self):
        w = Colorless(ledger=self.path)

        @w.guard
        async def boom():
            raise ValueError("x")

        with self.assertRaises(ValueError):
            asyncio.run(boom())
        self.assertFalse(w.entries(ref="boom")[0]["ok"])

    def test_toolguard_acall(self):
        w = Colorless(ledger=self.path).deny("danger")
        tg = ToolGuard(w)

        async def search(q):
            await asyncio.sleep(0)
            return f"r:{q}"

        tg.add("search", search).add("danger", lambda: "x")

        self.assertEqual(asyncio.run(tg.acall("search", {"q": "z"})), "r:z")

        async def _denied():
            await tg.acall("danger", {})

        with self.assertRaises(PolicyDenied):
            asyncio.run(_denied())
        self.assertTrue(w.verify()["ok"])


if __name__ == "__main__":
    unittest.main()
