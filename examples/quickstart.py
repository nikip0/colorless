"""Quickstart: a refund agent that can't quietly do something catastrophic — and proves it.

Run:  python3 examples/quickstart.py
"""

import os
import sys
import tempfile

# run straight from a clone without installing (after `pip install -e .` this is unnecessary)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from warrant import ApprovalRequired, PolicyDenied, Warrant

# A human approval handler. In real life this pings Slack / a dashboard / a teammate.
# Here we auto-approve refunds <= $500 and reject anything bigger, to show both paths.
def human_approval(action, decision):
    amount = action["args"].get("amount", 0)
    print(f"   [approval needed] {action['name']} {action['args']}  ->  ", end="")
    ok = amount <= 500
    print("APPROVED" if ok else "REJECTED")
    return ok


def main():
    ledger_path = os.path.join(tempfile.mkdtemp(), "agent.jsonl")
    w = Warrant(ledger=ledger_path, on_approval=human_approval)

    # ---- policy: what is this agent allowed to do? --------------------------
    w.deny("delete_account")                                            # never, full stop
    w.require_approval("refund", when=lambda a: a["args"]["amount"] > 100)  # big refunds need a human
    # everything else is allowed by default

    @w.guard
    def lookup_order(order_id):
        return {"order_id": order_id, "total": 240}

    @w.guard
    def refund(amount, to):
        return f"refunded ${amount} to {to}"

    @w.guard
    def delete_account(user_id):
        return "deleted"  # ...this should never run

    print("Agent is working a support ticket:\n")

    # 1) allowed
    print(" - lookup_order ->", lookup_order(order_id="ord_991"))

    # 2) small refund: under the threshold, runs without approval
    print(" - refund $80   ->", refund(amount=80, to="cust_12"))

    # 3) big refund: needs approval (auto-approved here at $400)
    print(" - refund $400  ->", refund(amount=400, to="cust_12"))

    # 4) huge refund: approval rejected -> blocked
    try:
        refund(amount=5000, to="cust_12")
    except ApprovalRequired as e:
        print(" - refund $5000 -> BLOCKED:", e)

    # 5) forbidden action: denied outright, never executes
    try:
        delete_account(user_id="cust_12")
    except PolicyDenied as e:
        print(" - delete_acct  -> BLOCKED:", e)

    # ---- the payoff: a verifiable record of everything that happened --------
    print("\nLedger (every action, sealed in a hash chain):")
    for e in w.entries():
        line = f"   #{e['seq']} {e['action']['name']:<14} decision={e['decision']:<8} executed={e['executed']}"
        if not e["executed"]:
            line += "  (blocked)"
        print(line)

    print("\nverify() ->", w.verify())

    # ---- now prove it's tamper-evident: secretly rewrite a denied action ----
    with open(ledger_path) as f:
        lines = f.readlines()
    lines[-1] = lines[-1].replace('"executed":false', '"executed":true')  # forge the cover-up
    with open(ledger_path, "w") as f:
        f.writelines(lines)

    print("verify() after tampering with the log ->", w.verify())


if __name__ == "__main__":
    main()
