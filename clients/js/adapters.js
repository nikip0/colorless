// Gate + seal LLM tool calls in the universal (name, args) shape (OpenAI / Anthropic / MCP).

import { UnknownTool } from "./errors.js";

export class ToolGuard {
  constructor(colorless, tools = {}) {
    this.cl = colorless;
    this.tools = { ...tools };
  }

  add(name, fn) {
    this.tools[name] = fn;
    return this;
  }

  // Dispatch one tool call through the policy gate + ledger. Throws PolicyDenied /
  // ApprovalRequired when blocked (hand that back to the model as a clean refusal).
  async call(name, args = {}) {
    if (!(name in this.tools)) throw new UnknownTool(name);
    const fn = this.tools[name];
    return this.cl.run(name, args, () => fn(args));
  }

  // { name: wrappedFn } where each is gated + logged.
  guarded() {
    const out = {};
    for (const [name, fn] of Object.entries(this.tools)) {
      out[name] = this.cl.guard(fn, { name });
    }
    return out;
  }
}
