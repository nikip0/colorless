"""colorless CLI — independently verify and inspect an agent action ledger.

    python -m colorless verify        agent.jsonl
    python -m colorless head          agent.jsonl
    python -m colorless tail          agent.jsonl -n 10
    python -m colorless anchor        agent.jsonl agent.anchor.json
    python -m colorless verify-anchor agent.jsonl agent.anchor.json

`verify` exits non-zero if the chain is broken, so it drops straight into CI.
"""

from __future__ import annotations

import argparse
import json
import sys

from .ledger import Ledger


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="colorless",
                                description="Verify and inspect a colorless agent ledger.")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("verify", help="re-walk + re-hash the chain; exit 1 if broken")
    v.add_argument("ledger")

    h = sub.add_parser("head", help="print the head hash + length")
    h.add_argument("ledger")

    t = sub.add_parser("tail", help="print the last N entries")
    t.add_argument("ledger")
    t.add_argument("-n", type=int, default=10)

    a = sub.add_parser("anchor", help="snapshot the head hash to a file you publish externally")
    a.add_argument("ledger")
    a.add_argument("out")

    va = sub.add_parser("verify-anchor", help="check the ledger against a published anchor")
    va.add_argument("ledger")
    va.add_argument("anchor")

    d = sub.add_parser("dashboard", help="launch the web dashboard (feed, approvals, verify)")
    d.add_argument("ledger")
    d.add_argument("--queue", default="colorless_approvals.json", help="approval queue file")
    d.add_argument("--host", default="127.0.0.1")
    d.add_argument("--port", type=int, default=8787)
    d.add_argument("--token", default=None,
                   help="access token (default: generated; env COLORLESS_DASHBOARD_TOKEN; '' disables)")
    d.add_argument("--token-name", default="owner",
                   help="label for --token, recorded as the approver identity (default: owner)")
    d.add_argument("--tokens-file", default=None,
                   help="JSON {name: token} for multi-user access (approver = the authenticated name)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    led = Ledger(args.ledger)

    if args.cmd == "verify":
        res = led.verify()
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 1

    if args.cmd == "head":
        print(json.dumps(led.head(), indent=2))
        return 0

    if args.cmd == "tail":
        for e in led.entries()[-args.n:]:
            name = (e.get("action") or {}).get("name", "")
            print(f"#{e.get('seq'):<4} {e.get('kind',''):<8} {str(e.get('ref',''))[:24]:<24} "
                  f"{name:<16} {e.get('decision','')}"
                  f"{'' if e.get('executed', True) else '  (blocked)'}")
        return 0

    if args.cmd == "anchor":
        print(json.dumps(led.anchor(args.out), indent=2))
        return 0

    if args.cmd == "verify-anchor":
        res = led.verify_against_anchor(args.anchor)
        print(json.dumps(res, indent=2))
        return 0 if res.get("matches") else 1

    if args.cmd == "dashboard":
        from .dashboard.server import serve
        tokens = None
        if args.tokens_file:
            with open(args.tokens_file) as f:
                tokens = json.load(f)
        serve(args.ledger, args.queue, args.host, args.port,
              token=args.token, tokens=tokens, token_name=args.token_name)
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
