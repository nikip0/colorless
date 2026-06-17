"""Spin up the colorless dashboard with realistic data to look at.

Seeds a ledger with a few agent actions (allowed / denied / approved), drops one pending approval
into the queue, then launches the dashboard. Open the printed URL.

Run:  python3 examples/dashboard_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from colorless import Colorless
from colorless.dashboard import ApprovalQueue, serve

LEDGER = "demo_agent.jsonl"
QUEUE = "demo_approvals.json"


def seed():
    # fresh files each run
    for p in (LEDGER, QUEUE):
        if os.path.exists(p):
            os.remove(p)

    cl = Colorless(LEDGER)
    cl.deny("delete_database")
    cl.require_approval("send_money", when=lambda a: a["args"].get("amount", 0) > 100)

    @cl.guard
    def search_web(query): return f"results for {query}"

    @cl.guard
    def write_file(path, content): return "ok"

    @cl.guard
    def send_money(amount, to): return f"sent {amount}"

    @cl.guard
    def delete_database(name): return "dropped"

    # a normal working session
    search_web(query="stripe refund api")
    write_file(path="app.py", content="print('hi')")
    write_file(path="README.md", content="# hi")
    search_web(query="kalshi market data")
    try:
        send_money(amount=5000, to="acct_9")     # > 100, no approver here -> blocked + logged
    except Exception:
        pass
    try:
        delete_database(name="production")        # denied outright -> blocked + logged
    except Exception:
        pass

    # one LIVE pending approval to click in the UI
    q = ApprovalQueue(QUEUE)
    q.request({"name": "send_money", "args": {"amount": 250, "to": "vendor_acme"}})


if __name__ == "__main__":
    seed()
    print("Seeded demo_agent.jsonl + one pending approval. Open the dashboard:\n")
    serve(LEDGER, QUEUE, host="127.0.0.1", port=8787)
