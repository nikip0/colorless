"""How warrant sits inside a real agent loop.

An LLM (OpenAI/Anthropic) returns tool_calls as (name, arguments). You normally dispatch
them straight to your functions. With warrant you dispatch them through `ToolGuard.call`,
which gates each one against policy and seals it into a verifiable ledger — without changing
your tools or your loop.

Here the "model" is a hardcoded list of tool_calls so the demo runs with no API key.
Run:  python3 examples/agent_loop.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from warrant import PolicyDenied, ToolGuard, Warrant


# --- your tools (unchanged) --------------------------------------------------
def search_web(query):
    return f"top result for {query!r}"

def write_file(path, content):
    return f"wrote {len(content)} bytes to {path}"

def send_invoice(customer, amount):
    return f"invoiced {customer} ${amount}"


def main():
    ledger = os.path.join(tempfile.mkdtemp(), "agent.jsonl")
    w = Warrant(ledger=ledger)                       # no on_approval -> approval-required = blocked
    w.deny("delete_repo")
    w.require_approval("send_invoice", when=lambda a: a["args"]["amount"] > 1000)

    tg = ToolGuard(w)
    tg.add("search_web", search_web)
    tg.add("write_file", write_file)
    tg.add("send_invoice", send_invoice)
    tg.add("delete_repo", lambda name: "deleted")

    # what the LLM "decided" to do this turn:
    tool_calls = [
        ("search_web",  {"query": "stripe refund api"}),
        ("write_file",  {"path": "app.py", "content": "print('hi')"}),
        ("send_invoice", {"customer": "Acme", "amount": 50000}),   # > 1000 -> needs approval
        ("delete_repo", {"name": "production"}),                   # denied outright
    ]

    print("Agent loop (each tool_call passes through warrant):\n")
    for name, args in tool_calls:
        try:
            result = tg.call(name, args)
            print(f"  ✓ {name}({args}) -> {result}")
        except PolicyDenied as e:
            print(f"  ✗ {name}({args}) -> DENIED")
        except Exception as e:
            print(f"  ✗ {name}({args}) -> {type(e).__name__}: {e}")

    print("\nVerifiable record of the whole turn:")
    for e in w.entries():
        flag = "" if e["executed"] else "  (blocked)"
        print(f"  #{e['seq']} {e['action']['name']:<13} {e['decision']:<8}{flag}")
    print("\nverify() ->", w.verify())


if __name__ == "__main__":
    main()
