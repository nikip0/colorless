# colorless (JavaScript / TypeScript)

**Authorize, gate, and prove every action your AI agent takes.** Tamper-evident. Zero
dependencies. First-class TypeScript types. The JS/TS port of [colorless](https://github.com/nikip0/colorless).

```bash
npm install colorless   # zero dependencies (uses only Node built-ins; Node >= 18)
```

```ts
import { Colorless } from "colorless";

const cl = new Colorless({ ledger: "agent.jsonl", onApproval: pingSlack });

cl.deny("delete_database");                                   // never
cl.requireApproval("refund", (a) => a.args.amount > 100);     // big ones need a human

const refund = cl.guard(async ({ amount, to }) => pay(amount, to), { name: "refund" });

await refund({ amount: 80, to: "cust_12" });    // runs — sealed in the chain
await refund({ amount: 5000, to: "cust_12" });  // throws ApprovalRequired until a human says yes

cl.verify();   // { ok: true, length: 412, head: "9f3c…" } — proof nothing was altered
```

## Tool calls (OpenAI / Anthropic / MCP)

```ts
import { Colorless, ToolGuard, PolicyDenied } from "colorless";

const cl = new Colorless({ ledger: "agent.jsonl" });
cl.deny("delete_repo");

const tg = new ToolGuard(cl);
tg.add("search_web", searchWeb);
tg.add("send_invoice", sendInvoice);

for (const call of llmResponse.toolCalls) {
  try {
    const result = await tg.call(call.name, call.arguments);   // gated + sealed
  } catch (e) {
    if (e instanceof PolicyDenied) /* hand the refusal back to the model */;
  }
}
```

## Same ledger, any language

This SDK writes the **exact same JSONL hash-chain format** as the Python engine, so a ledger an
agent writes in Node can be verified from the terminal with the Python CLI:

```bash
colorless verify agent.jsonl    # ✓ verifies a Node-written ledger (ASCII / integer content)
```

## API

- `new Colorless({ ledger, policy, onApproval, redact })` — `redact` defaults to `"auto"` (secrets masked); pass `null` to disable.
- `.deny / .allow / .requireApproval(name?, when?, reason?)` — ordered rules, first match wins.
- `.guard(fn, { name })` — wrap a tool (sync or async). `.run(name, args, fn)` — gate a call directly.
- `.verify()` · `.head()` · `.entries(ref?)` · `.anchor(path)` · `.verifyAgainstAnchor(path)`.
- `ToolGuard(cl).add(name, fn).call(name, args)` — gate + seal one tool call.

MIT © 2026 Niki Petrov
