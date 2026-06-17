# colorless

**Authorize, gate, and prove every action your AI agent takes.**
Tamper-evident. Zero dependencies. ~5 lines of code.

![tests](https://img.shields.io/badge/tests-49%20passing-brightgreen)
![python](https://img.shields.io/badge/python-3.9%2B-blue)
![dependencies](https://img.shields.io/badge/dependencies-0-blueviolet)
![license](https://img.shields.io/badge/license-MIT-green)

> v0.2 — early but real, and useful today: policy gating, a tamper-evident ledger, sync **and
> async** guards, tool-call adapters (OpenAI/Anthropic/MCP/LangChain), **secret-redaction by
> default**, thread-safe appends, and a `colorless` CLI — all zero-dependency, 49 tests green.
> The hosted dashboard + team features are on the roadmap below.

---

## The problem

AI agents have graduated from *answering questions* to *taking actions* — sending emails,
moving money, writing to your database, calling other tools. The moment an agent can act,
two questions decide whether you can actually ship it:

1. **Can you stop the catastrophic action before it happens?** (refund $1M, drop a table, email every customer)
2. **Can you prove, later, exactly what it did — and that every action was authorized?**

Today most teams have neither. They have *traces* and *eval scores from development* — not a
**runtime gate** and not a **tamper-evident record** of what the agent did in production.

`colorless` is that missing layer.

## Install

Not on PyPI yet (the name isn't final). For now, from source — zero dependencies, so it's instant:

```bash
git clone https://github.com/nikip0/colorless.git
cd colorless
pip install -e .
```

Or run straight from a clone with no install at all:

```bash
python3 examples/quickstart.py
```

## Quickstart

```python
from colorless import Colorless

w = Colorless("agent.jsonl", on_approval=ping_slack)   # on_approval(action, decision) -> bool

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

## Drop it into your agent loop (OpenAI / Anthropic / MCP)

LLM agents call tools as `(name, arguments)` — the same shape across OpenAI function-calling,
Anthropic tool use, and MCP servers. `ToolGuard` gates every such call and seals it, with one
line in your dispatch loop:

```python
from colorless import Colorless, ToolGuard, PolicyDenied

w = Colorless("agent.jsonl")
w.deny("delete_repo")
w.require_approval("send_invoice", when=lambda a: a["args"]["amount"] > 1000)

tg = ToolGuard(w)
tg.add("search_web", search_web)
tg.add("send_invoice", send_invoice)

# in your loop, for each tool_call the model emits:
for call in llm_response.tool_calls:
    try:
        result = tg.call(call.name, call.arguments)   # gated + sealed
    except PolicyDenied:
        result = "blocked by policy"                  # hand the refusal back to the model
```

Your tools and your loop don't change — every action is now gated and provable. See
`examples/agent_loop.py`.

## Async agents

`@guard` and `ToolGuard.acall` work with coroutine tools out of the box:

```python
@w.guard
async def search(query):
    return await client.search(query)        # gated + sealed, awaited for you

await tg.acall("search", {"query": "..."})    # async dispatch inside your agent loop
```

## Secrets never hit the ledger

Redaction is **on by default**. Keys named like secrets (`api_key`, `token`, `password`, …) and
values shaped like secrets (OpenAI `sk-…`, `Bearer …`, GitHub/AWS/Slack tokens) are masked to
`***` before anything is written. Disable with `Colorless(redact=None)`, or pass your own function.

## Verify from the terminal (CLI)

Anyone — an auditor, a teammate, CI — can independently check a ledger without touching your code:

```bash
colorless verify        agent.jsonl                   # exits 1 if the chain was tampered with
colorless tail          agent.jsonl -n 20
colorless anchor        agent.jsonl agent.anchor.json  # publish this snapshot externally
colorless verify-anchor agent.jsonl agent.anchor.json
```

## Integrations

The core is framework-agnostic; these add turnkey wiring. Each adapter imports **no** third-party
SDK, so the core stays zero-dependency:

- **MCP** — `colorless.integrations.mcp` + `examples/mcp_server.py` (FastMCP). Gate + seal every tool an MCP client calls. `pip install mcp`.
- **LangChain / LangGraph** — `guard_tools(cl, tools)` in `colorless.integrations.langchain` + `examples/langchain_agent.py`. One line wraps your entire tool list. `pip install langchain-core`.
- **OpenAI / Anthropic tool calls** — use `ToolGuard.call(name, args)` directly in your loop (`examples/agent_loop.py`).

## Why it's different

| | dev-time eval / tracing<br/>(LangSmith, Braintrust, Arize) | prompt guardrails<br/>(Guardrails AI, NeMo) | **colorless** |
|---|---|---|---|
| Stops a forbidden **action** before it runs | ✗ | partial (text only) | ✅ |
| Human-in-the-loop approval gate | ✗ | ✗ | ✅ |
| **Tamper-evident** record of what the agent did | ✗ | ✗ | ✅ |
| Independently verifiable / anchorable proof | ✗ | ✗ | ✅ |
| Built for **production runtime**, not just dev | partial | ✅ | ✅ |
| Secret redaction by default | ✗ | partial | ✅ |
| Independent CLI / CI verification | ✗ | ✗ | ✅ |
| Dependencies | many | several | **zero** |

The leaders watch your agent *while you build it*. `colorless` governs and proves what it does
*once it's live and touching the real world* — the part you actually get fired (or sued) over.

## Core concepts

- **Policy** — ordered rules (`allow` / `deny` / `require_approval`), first match wins, default configurable. Deny-by-default for production: `Colorless(policy=Policy(default="deny"))`.
- **Guard** — `@w.guard` on a function (sync or `async`), or `with w.action("name", **args):` inline. Checks policy, then runs (or blocks), then records.
- **ToolGuard** — wrap an LLM tool registry; `.call(name, args)` / `.acall(...)` gate+seal each tool_call (OpenAI/Anthropic/MCP).
- **Ledger** — append-only hash chain (`content_hash`, `row_hash = sha256(prev + content)`) in a plain JSONL file, **thread-safe** appends. `verify()` re-walks and re-hashes; `anchor()` fixes the head in time.
- **Redaction** — on by default (`redact_secrets`); masks secret-looking keys/values before they're written. `Colorless(redact=None)` to disable.
- **CLI** — `colorless verify | tail | anchor | verify-anchor` for independent, code-free checks.

## Roadmap

- **Now (OSS core):** policy gating, tamper-evident + thread-safe ledger, anchoring, sync/async guards, OpenAI/Anthropic/MCP tool adapters, secret-redaction, CLI — all dependency-free.
- **Next:** turnkey adapters for LangChain / LlamaIndex; an example MCP server; framework middleware.
- **Then (hosted):** a dashboard to watch live actions and approve from your phone, team-wide policies, alerting, and one-click compliance export (SOC 2 / EU AI Act evidence).

## License

MIT © 2026 Niki Petrov
