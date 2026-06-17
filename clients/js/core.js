// Colorless — gate every action your AI agent takes, and seal it into a verifiable ledger.
// Async-native: guard() works with sync or async tools; run()/onApproval are awaited.

import { ApprovalRequired, PolicyDenied } from "./errors.js";
import { Ledger } from "./ledger.js";
import { APPROVE, DENY, Policy } from "./policy.js";
import { redactSecrets } from "./redaction.js";

function safe(v) {
  try {
    JSON.stringify(v);
    return v;
  } catch {
    return String(v);
  }
}

function isPlainObject(v) {
  return v != null && typeof v === "object" && !Array.isArray(v);
}

export class Colorless {
  constructor({ ledger = "colorless.jsonl", policy = null, onApproval = null, redact = "auto" } = {}) {
    this.ledger = ledger instanceof Ledger ? ledger : new Ledger(ledger);
    this.policy = policy || new Policy();
    this.onApproval = onApproval; // async (action, decision) -> boolean; null => approval blocks
    this.redact = redact === "auto" ? redactSecrets : redact; // null => no redaction
  }

  allow(name, when, reason) { this.policy.allow(name, when, reason); return this; }
  deny(name, when, reason) { this.policy.deny(name, when, reason); return this; }
  requireApproval(name, when, reason) { this.policy.requireApproval(name, when, reason); return this; }

  check(name, args = {}) {
    return this.policy.decide({ name, args });
  }

  _loggedArgs(args) {
    return this.redact ? this.redact(args) : args;
  }

  async _gate(action) {
    const decision = this.policy.decide(action);
    const logAction = { name: action.name, args: this._loggedArgs(action.args || {}) };
    if (decision.denied) {
      this.ledger.append("action", action.name, { action: logAction, decision: DENY, reason: decision.reason, executed: false });
      throw new PolicyDenied(action, decision);
    }
    if (decision.needsApproval) {
      const approved = this.onApproval ? Boolean(await this.onApproval(action, decision)) : false;
      if (!approved) {
        this.ledger.append("action", action.name, { action: logAction, decision: APPROVE, approved: false, reason: decision.reason, executed: false });
        throw new ApprovalRequired(action, decision);
      }
    }
    return { decision, logAction };
  }

  _record(name, logAction, decision, ok, result, error) {
    const payload = { action: logAction, decision: decision.verdict, executed: true, ok };
    if (decision.needsApproval) payload.approved = true;
    if (ok && result !== undefined) payload.result = safe(result);
    if (!ok) payload.error = error;
    return this.ledger.append("action", name, payload);
  }

  // Gate (name, args), run fn() if allowed, record the outcome, return its result.
  async run(name, args, fn) {
    const { decision, logAction } = await this._gate({ name, args });
    let result;
    try {
      result = await fn();
    } catch (e) {
      this._record(name, logAction, decision, false, undefined, `${e?.name || "Error"}: ${e?.message || e}`);
      throw e;
    }
    this._record(name, logAction, decision, true, result);
    return result;
  }

  // Wrap a tool/function so every call is policy-checked and logged. If called with a single
  // object arg, that object is logged as the args; otherwise positional args are captured.
  guard(fn, { name } = {}) {
    const actionName = name || fn.name || "action";
    return async (...callArgs) => {
      const logged = callArgs.length === 1 && isPlainObject(callArgs[0]) ? callArgs[0] : { args: callArgs };
      return this.run(actionName, logged, () => fn(...callArgs));
    };
  }

  verify() { return this.ledger.verify(); }
  head() { return this.ledger.head(); }
  entries(ref = null) { return this.ledger.entries(ref); }
  anchor(path) { return this.ledger.anchor(path); }
  verifyAgainstAnchor(path) { return this.ledger.verifyAgainstAnchor(path); }
}
