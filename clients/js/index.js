// colorless — authorize, gate, and prove every action your AI agent takes.
//
//   import { Colorless } from "colorless";
//   const cl = new Colorless({ ledger: "agent.jsonl" });
//   cl.deny("delete_database");
//   cl.requireApproval("refund", (a) => a.args.amount > 100);
//   const refund = cl.guard(async ({ amount, to }) => pay(amount, to), { name: "refund" });
//   await refund({ amount: 80, to: "cust_12" });
//   cl.verify(); // { ok: true, ... } — tamper-evident proof of everything it did

export { Colorless } from "./core.js";
export { ToolGuard } from "./adapters.js";
export { Ledger, GENESIS, canonical } from "./ledger.js";
export { Policy, Decision, ALLOW, DENY, APPROVE } from "./policy.js";
export { redactSecrets } from "./redaction.js";
export { ColorlessError, PolicyDenied, ApprovalRequired, UnknownTool } from "./errors.js";

export const VERSION = "0.2.0";
