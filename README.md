# warrant

**Authorize, gate, and prove every action your AI agent takes.**
Tamper-evident. Zero dependencies. ~5 lines of code.

> ⚠️ v0.1 — early but real. The core (policy gating + verifiable ledger) works and is tested.
> The hosted dashboard, framework adapters, and team features are on the roadmap below.

---

## The problem

AI agents have graduated from *answering questions* to *taking actions* — sending emails,
moving money, writing to your database, calling other tools. The moment an agent can act,
two questions decide whether you can actually ship it:

1. **Can you stop the catastrophic action before it happens?** (refund $1M, drop a table, email every customer)
2. **Can you prove, later, exactly what it did — and that every action was authorized?**

Today most teams have neither. They have *traces* and *eval scores from development* — not a
**runtime gate** and not a **tamper-evident record** of what the agent did in production.

`warrant` is that missing layer.

## Install

```bash
pip install warrant-agents   # zero dependencies
```

## Quickstart

```python
from warrant import Warrant

w = Warrant("agent.jsonl", on_approval=ping_slack)   # on_approval(action, decision) -> bool

w.deny("delete_account")                                       # never, full stop
w.require_approval("refund", when=lambda a: a["args"]["amount"] > 100)   # big ones need a human

@w.guard
def refund(amount, to):
    return payments.refund(amount, to)

refund(amount=80, to="cust_12")     # runs — logged, sealed in the chain
refund(amount=5000, to="cust_12")   # raises ApprovalRequired until a human says yes
```

Then, at any time:

```python
w.verify()
# {"ok": True, "length": 412, "head": "9f3c…"}   <- cryptographic proof nothing was altered
```

Tamper with a single past entry — edit it, delete it, reorder it — and `verify()` tells you
exactly where the chain broke. `anchor()` publishes the head hash externally so even silently
deleting the most recent entries is provable.

Run the full demo:

```bash
python3 examples/quickstart.py
```

## Why it's different

| | dev-time eval / tracing<br/>(LangSmith, Braintrust, Arize) | prompt guardrails<br/>(Guardrails AI, NeMo) | **warrant** |
|---|---|---|---|
| Stops a forbidden **action** before it runs | ✗ | partial (text only) | ✅ |
| Human-in-the-loop approval gate | ✗ | ✗ | ✅ |
| **Tamper-evident** record of what the agent did | ✗ | ✗ | ✅ |
| Independently verifiable / anchorable proof | ✗ | ✗ | ✅ |
| Built for **production runtime**, not just dev | partial | ✅ | ✅ |
| Dependencies | many | several | **zero** |

The leaders watch your agent *while you build it*. `warrant` governs and proves what it does
*once it's live and touching the real world* — the part you actually get fired (or sued) over.

## Core concepts

- **Policy** — ordered rules (`allow` / `deny` / `require_approval`), first match wins, default configurable. Deny-by-default for production: `Warrant(policy=Policy(default="deny"))`.
- **Guard** — `@w.guard` on a function, or `with w.action("name", **args):` inline. Checks policy, then runs (or blocks), then records.
- **Ledger** — append-only hash chain (`content_hash`, `row_hash = sha256(prev + content)`), backed by a plain JSONL file. `verify()` re-walks and re-hashes; `anchor()` fixes the head in time.
- **Redaction** — `Warrant(redact=...)` strips secrets from action args before they're written.

## Roadmap

- **Now (OSS core):** policy gating, tamper-evident ledger, anchoring, redaction — all dependency-free.
- **Next:** drop-in adapters for LangChain / LlamaIndex / OpenAI tool calls / MCP; a CLI (`warrant verify`, `warrant tail`).
- **Then (hosted):** a dashboard to watch live actions and approve from your phone, team-wide policies, alerting, and one-click compliance export (SOC 2 / EU AI Act evidence).

## License

MIT © 2026 Niki Petrov
