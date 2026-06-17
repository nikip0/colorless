"""The dashboard server — stdlib `http.server` only (zero dependencies).

`DashboardData` is the pure data layer (feed / stats / verify / pending) over the ledger + queue —
testable without a socket. The HTTP handler is a thin shell over it. Read-only on the ledger;
the only writes are approve/deny on the approval queue.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..ledger import Ledger
from .approvals import ApprovalQueue

_UI = os.path.join(os.path.dirname(__file__), "ui.html")


class DashboardData:
    def __init__(self, ledger_path: str, queue: "ApprovalQueue | None" = None):
        self.ledger = Ledger(ledger_path)
        self.queue = queue

    def feed(self, limit: int = 500) -> list:
        rows = self.ledger.entries()
        return list(reversed(rows))[:limit]  # newest first

    def verify(self) -> dict:
        return self.ledger.verify()

    def stats(self) -> dict:
        rows = self.ledger.entries()
        by_decision: dict = {}
        tools: dict = {}
        blocked = 0
        for r in rows:
            d = r.get("decision", "?")
            by_decision[d] = by_decision.get(d, 0) + 1
            name = (r.get("action") or {}).get("name", "?")
            tools[name] = tools.get(name, 0) + 1
            if not r.get("executed", True):
                blocked += 1
        v = self.ledger.verify()
        return {
            "total": len(rows),
            "blocked": blocked,                 # catastrophes prevented
            "by_decision": by_decision,
            "tools": tools,
            "pending": len(self.queue.pending()) if self.queue else 0,
            "integrity_ok": v["ok"],
            "head": v.get("head"),
        }

    def pending(self) -> list:
        return self.queue.pending() if self.queue else []

    def approve(self, rid: str) -> bool:
        return bool(self.queue and self.queue.resolve(rid, True))

    def deny(self, rid: str) -> bool:
        return bool(self.queue and self.queue.resolve(rid, False))


def make_handler(data: DashboardData):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # quiet by default

        def _send(self, code: int, body, ctype: str = "application/json"):
            b = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                try:
                    with open(_UI, "rb") as f:
                        self._send(200, f.read(), "text/html; charset=utf-8")
                except OSError:
                    self._send(500, {"error": "ui not found"})
                return
            if path == "/api/feed":
                self._send(200, {"feed": data.feed()})
            elif path == "/api/verify":
                self._send(200, data.verify())
            elif path == "/api/stats":
                self._send(200, data.stats())
            elif path == "/api/pending":
                self._send(200, {"pending": data.pending()})
            elif path == "/api/export":
                self._send(200, {"entries": data.feed(limit=1_000_000)})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            path = self.path.split("?")[0]
            try:
                length = int(self.headers.get("Content-Length", 0) or 0)
            except ValueError:
                length = 0
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except ValueError:
                payload = {}
            rid = payload.get("id")
            if path == "/api/approve":
                self._send(200, {"ok": data.approve(rid)})
            elif path == "/api/deny":
                self._send(200, {"ok": data.deny(rid)})
            else:
                self._send(404, {"error": "not found"})

    return Handler


def serve(ledger_path: str, queue_path: "str | None" = None,
          host: str = "127.0.0.1", port: int = 8787):
    queue = ApprovalQueue(queue_path) if queue_path else ApprovalQueue()
    data = DashboardData(ledger_path, queue)
    httpd = ThreadingHTTPServer((host, port), make_handler(data))
    print(f"colorless dashboard → http://{host}:{port}   (ledger: {ledger_path})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
