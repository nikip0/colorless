"""Dashboard: approval queue (incl. the block-until-human flow), the data layer, and the HTTP API.
Run: python3 -m unittest tests.test_dashboard
"""

import json
import os
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

from colorless import Colorless
from colorless.dashboard import ApprovalQueue, queue_approval
from colorless.dashboard.server import DashboardData, make_handler


class ApprovalQueueTest(unittest.TestCase):
    def setUp(self):
        self.q = ApprovalQueue(os.path.join(tempfile.mkdtemp(), "q.json"))

    def test_request_pending_resolve(self):
        rid = self.q.request({"name": "wire", "args": {"amount": 9000}})
        self.assertEqual(len(self.q.pending()), 1)
        self.assertTrue(self.q.resolve(rid, True))
        self.assertEqual(len(self.q.pending()), 0)
        self.assertEqual(self.q.get(rid)["status"], "approved")

    def test_resolve_unknown_or_twice_returns_false(self):
        rid = self.q.request({"name": "x", "args": {}})
        self.assertFalse(self.q.resolve("nope", True))
        self.assertTrue(self.q.resolve(rid, False))
        self.assertFalse(self.q.resolve(rid, True))     # already decided

    def test_queue_approval_blocks_until_human_approves(self):
        on_approval = queue_approval(self.q, poll=0.02, timeout=3.0)

        def approver():
            for _ in range(300):
                p = self.q.pending()
                if p:
                    self.q.resolve(p[0]["id"], True)
                    return
                time.sleep(0.01)

        t = threading.Thread(target=approver)
        t.start()
        result = on_approval({"name": "send_money", "args": {"amount": 250}}, None)
        t.join()
        self.assertTrue(result)

    def test_queue_approval_times_out_to_deny(self):
        on_approval = queue_approval(self.q, poll=0.02, timeout=0.1)
        self.assertFalse(on_approval({"name": "x", "args": {}}, None))   # silence -> deny


class DashboardDataTest(unittest.TestCase):
    def _seed(self):
        d = tempfile.mkdtemp()
        lpath = os.path.join(d, "log.jsonl")
        qpath = os.path.join(d, "q.json")
        cl = Colorless(lpath).deny("danger")

        @cl.guard
        def ok():
            return "y"

        @cl.guard
        def danger():
            return "boom"

        ok()
        try:
            danger()
        except Exception:
            pass
        q = ApprovalQueue(qpath)
        q.request({"name": "send", "args": {"amount": 9}})
        return DashboardData(lpath, q), q

    def test_feed_newest_first(self):
        data, _ = self._seed()
        feed = data.feed()
        self.assertEqual(len(feed), 2)
        self.assertEqual(feed[0]["action"]["name"], "danger")   # most recent first

    def test_stats(self):
        data, _ = self._seed()
        s = data.stats()
        self.assertEqual(s["total"], 2)
        self.assertEqual(s["blocked"], 1)
        self.assertEqual(s["pending"], 1)
        self.assertTrue(s["integrity_ok"])

    def test_approve_via_data_layer(self):
        data, q = self._seed()
        rid = q.pending()[0]["id"]
        self.assertTrue(data.approve(rid))
        self.assertEqual(len(q.pending()), 0)


class HttpApiTest(unittest.TestCase):
    def test_endpoints_over_http(self):
        d = tempfile.mkdtemp()
        lpath = os.path.join(d, "log.jsonl")
        qpath = os.path.join(d, "q.json")
        cl = Colorless(lpath)

        @cl.guard
        def ok():
            return "y"

        ok()
        q = ApprovalQueue(qpath)
        rid = q.request({"name": "send", "args": {"amount": 9}})

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(DashboardData(lpath, q)))
        port = httpd.server_address[1]
        th = threading.Thread(target=httpd.serve_forever, daemon=True)
        th.start()
        try:
            base = f"http://127.0.0.1:{port}"
            stats = json.loads(urlopen(base + "/api/stats", timeout=5).read())
            self.assertEqual(stats["total"], 1)
            self.assertEqual(stats["pending"], 1)
            self.assertTrue(stats["integrity_ok"])

            feed = json.loads(urlopen(base + "/api/feed", timeout=5).read())["feed"]
            self.assertEqual(len(feed), 1)

            req = Request(base + "/api/approve", data=json.dumps({"id": rid}).encode(),
                          headers={"Content-Type": "application/json"})
            res = json.loads(urlopen(req, timeout=5).read())
            self.assertTrue(res["ok"])
            self.assertEqual(len(q.pending()), 0)

            # the dashboard HTML is served at /
            html = urlopen(base + "/", timeout=5).read().decode()
            self.assertIn("control room", html)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
