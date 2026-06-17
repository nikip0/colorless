// Ordered policy engine — first match wins; default applies when nothing matches.

export const ALLOW = "allow";
export const DENY = "deny";
export const APPROVE = "approve";

export class Decision {
  constructor(verdict, reason = "", rule = null) {
    this.verdict = verdict;
    this.reason = reason;
    this.rule = rule;
  }
  get allowed() { return this.verdict === ALLOW; }
  get denied() { return this.verdict === DENY; }
  get needsApproval() { return this.verdict === APPROVE; }
}

class Rule {
  constructor(verdict, name, when, reason) {
    this.verdict = verdict;
    this.name = name;
    this.when = when;
    this.reason = reason;
  }
  matches(action) {
    if (this.name != null && action.name !== this.name) return false;
    if (this.when != null && !this.when(action)) return false;
    return true;
  }
}

export class Policy {
  constructor(defaultVerdict = ALLOW) {
    if (![ALLOW, DENY, APPROVE].includes(defaultVerdict)) {
      throw new Error(`default must be one of allow/deny/approve, got ${defaultVerdict}`);
    }
    this.default = defaultVerdict;
    this.rules = [];
  }
  _add(verdict, name, when, reason) {
    this.rules.push(new Rule(verdict, name ?? null, when ?? null, reason || `matched ${verdict} rule`));
    return this;
  }
  allow(name, when, reason = "") { return this._add(ALLOW, name, when, reason); }
  deny(name, when, reason = "") { return this._add(DENY, name, when, reason); }
  requireApproval(name, when, reason = "") { return this._add(APPROVE, name, when, reason); }
  decide(action) {
    for (const rule of this.rules) {
      if (rule.matches(action)) return new Decision(rule.verdict, rule.reason, rule);
    }
    return new Decision(this.default, `default:${this.default}`);
  }
}
