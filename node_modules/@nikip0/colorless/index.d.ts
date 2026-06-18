// Type definitions for colorless (JS/TS SDK).

export type Verdict = "allow" | "deny" | "approve";
export const ALLOW: "allow";
export const DENY: "deny";
export const APPROVE: "approve";

export interface Action {
  name: string;
  args: Record<string, any>;
}

export class Decision {
  verdict: Verdict;
  reason: string;
  rule: unknown;
  get allowed(): boolean;
  get denied(): boolean;
  get needsApproval(): boolean;
}

export type Predicate = (action: Action) => boolean;

export class Policy {
  constructor(defaultVerdict?: Verdict);
  default: Verdict;
  allow(name?: string | null, when?: Predicate, reason?: string): this;
  deny(name?: string | null, when?: Predicate, reason?: string): this;
  requireApproval(name?: string | null, when?: Predicate, reason?: string): this;
  decide(action: Action): Decision;
}

export interface VerifyResult {
  ok: boolean;
  length: number;
  head?: string;
  broken_at: number | null;
  reason?: string;
}
export interface HeadResult {
  head: string;
  length: number;
}

export const GENESIS: string;
export function canonical(value: unknown): string;

export class Ledger {
  constructor(path?: string);
  path: string;
  append(kind: string, ref?: string, payload?: Record<string, any>): Record<string, any>;
  head(): HeadResult;
  entries(ref?: string | null): Array<Record<string, any>>;
  verify(): VerifyResult;
  anchor(path: string): Record<string, any>;
  verifyAgainstAnchor(path: string): Record<string, any>;
}

export function redactSecrets(args: Record<string, any>): Record<string, any>;

export class ColorlessError extends Error {}
export class PolicyDenied extends ColorlessError {
  action: Action;
  decision: Decision;
}
export class ApprovalRequired extends ColorlessError {
  action: Action;
  decision: Decision;
}
export class UnknownTool extends ColorlessError {
  tool: string;
}

export type ApprovalDecision = boolean | { approved: boolean; approver?: string | null };
export type ApprovalHandler = (action: Action, decision: Decision) => ApprovalDecision | Promise<ApprovalDecision>;
export type Redactor = (args: Record<string, any>) => Record<string, any>;
export type LedgerEntry = Record<string, any>;

export interface ColorlessOptions {
  ledger?: string | Ledger;
  policy?: Policy;
  onApproval?: ApprovalHandler | null;
  redact?: "auto" | null | Redactor;
}

export class Colorless {
  constructor(opts?: ColorlessOptions);
  ledger: Ledger;
  policy: Policy;
  allow(name?: string | null, when?: Predicate, reason?: string): this;
  deny(name?: string | null, when?: Predicate, reason?: string): this;
  requireApproval(name?: string | null, when?: Predicate, reason?: string): this;
  check(name: string, args?: Record<string, any>): Decision;
  subscribe(cb: (entry: LedgerEntry) => void): (entry: LedgerEntry) => void;
  run<T>(name: string, args: Record<string, any>, fn: () => T | Promise<T>): Promise<T>;
  guard<F extends (...args: any[]) => any>(
    fn: F,
    opts?: { name?: string }
  ): (...args: Parameters<F>) => Promise<Awaited<ReturnType<F>>>;
  verify(): VerifyResult;
  head(): HeadResult;
  entries(ref?: string | null): Array<Record<string, any>>;
  anchor(path: string): Record<string, any>;
  verifyAgainstAnchor(path: string): Record<string, any>;
}

export type Tool = (args: Record<string, any>) => any;

export class ToolGuard {
  constructor(colorless: Colorless, tools?: Record<string, Tool>);
  tools: Record<string, Tool>;
  add(name: string, fn: Tool): this;
  call(name: string, args?: Record<string, any>): Promise<any>;
  guarded(): Record<string, (...args: any[]) => Promise<any>>;
}

export const VERSION: string;
