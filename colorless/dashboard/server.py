"""The dashboard server — stdlib `http.server` only (zero dependencies).

`DashboardData` is the pure data layer (feed / stats / verify / pending) over the ledger + queue —
testable without a socket. The HTTP handler is a thin shell over it. Read-only on the ledger;
the only writes are approve/deny on the approval queue.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from ..ledger import Ledger
from .approvals import ApprovalQueue

_UI = os.path.join(os.path.dirname(__file__), "ui.html")


class DashboardData:
    def __init__(self, ledger_path: str, queue: "ApprovalQueue | None" = None):
        self.ledger = Ledger(ledger_path)
        self.queue = queue

    def feed(self, limit: int = 500) -> list:
        rows = self.ledger.entries()
        return list(reversed(rows[-limit:]))  # newest first, only the last `limit`

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

    def approve(self, rid: str, approver: "str | None" = None) -> bool:
        return bool(self.queue and self.queue.resolve(rid, True, approver))

    def deny(self, rid: str, approver: "str | None" = None) -> bool:
        return bool(self.queue and self.queue.resolve(rid, False, approver))


def make_handler(data: DashboardData, token: "str | None" = None, tokens: "dict | None" = None):
    # identity map (name -> secret). A single `token` is the "owner" identity; `tokens` adds named users.
    idmap = dict(tokens or {})
    if token:
        idmap.setdefault("owner", token)

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

        def _supplied_token(self):
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                return auth[7:]
            return (parse_qs(urlsplit(self.path).query).get("token") or [None])[0]

        def _identity(self):
            """The authenticated user's name, or None. Compares against every token constant-time and
            without early-exit, so timing doesn't reveal which token matched."""
            supplied = self._supplied_token()
            if supplied is None:
                return None
            matched = None
            for name, secret in idmap.items():
                if hmac.compare_digest(str(supplied), str(secret)):
                    matched = name
            return matched

        def _authed(self) -> bool:
            """No tokens configured -> open (loopback dev). Otherwise require a valid token."""
            return (not idmap) or (self._identity() is not None)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                try:
                    with open(_UI, "rb") as f:
                        self._send(200, f.read(), "text/html; charset=utf-8")  # shell is public; data is gated
                except OSError:
                    self._send(500, {"error": "ui not found"})
                return
            if not self._authed():
                self._send(401, {"error": "unauthorized"})
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
            if not self._authed():
                self._send(401, {"error": "unauthorized"})
                return
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
            approver = self._identity()  # authenticated identity (named token) — sealed as the approver
            if path == "/api/approve":
                self._send(200, {"ok": data.approve(rid, approver)})
            elif path == "/api/deny":
                self._send(200, {"ok": data.deny(rid, approver)})
            else:
                self._send(404, {"error": "not found"})

    return Handler


def serve(ledger_path: str, queue_path: "str | None" = None,
          host: str = "127.0.0.1", port: int = 8787, token: "str | None" = None,
          tokens: "dict | None" = None, token_name: str = "owner"):
    queue = ApprovalQueue(queue_path) if queue_path else ApprovalQueue()
    data = DashboardData(ledger_path, queue)
    # Build the identity map. Named `tokens` (name->secret) take precedence — each becomes an
    # authenticated approver identity. Otherwise a single token labeled `token_name`, generated by
    # default (secure), env-overridable; pass token="" to disable auth.
    if tokens:
        idmap = dict(tokens)
    else:
        if token is None:
            token = os.environ.get("COLORLESS_DASHBOARD_TOKEN") or secrets.token_urlsafe(32)
        idmap = {token_name: token} if token else {}
    httpd = ThreadingHTTPServer((host, port), make_handler(data, tokens=idmap or None))
    if host not in ("127.0.0.1", "localhost", "::1") and not idmap:
        print("WARNING: binding to a non-loopback host with NO token exposes the dashboard to anyone "
              "who can reach it — they can read the audit log and approve/deny actions.")
    if idmap:
        if tokens:  # multi-user: don't dump everyone's secrets to one console
            print(f"colorless dashboard → http://{host}:{port}   ({len(idmap)} named tokens loaded; "
                  "each user signs in with their own token)")
        else:       # single generated/explicit token: print the convenience URL
            print(f"colorless dashboard → http://{host}:{port}/?token={next(iter(idmap.values()))}")
        print("  (token required — open with ?token=… or send 'Authorization: Bearer <token>')")
    else:
        print(f"colorless dashboard → http://{host}:{port}   (no token — open access)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
