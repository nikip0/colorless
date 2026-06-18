import assert from "node:assert/strict";
import { test } from "node:test";
import { Policy } from "../policy.js";

const act = (name, args = {}) => ({ name, args });

test("default allow", () => assert.equal(new Policy().decide(act("x")).allowed, true));
test("default deny", () => assert.equal(new Policy("deny").decide(act("x")).denied, true));

test("deny by name", () => {
  const p = new Policy().deny("delete_db");
  assert.equal(p.decide(act("delete_db")).denied, true);
  assert.equal(p.decide(act("read")).allowed, true);
});

test("require approval with predicate", () => {
  const p = new Policy().requireApproval("refund", (a) => a.args.amount > 100);
  assert.equal(p.decide(act("refund", { amount: 500 })).needsApproval, true);
  assert.equal(p.decide(act("refund", { amount: 50 })).allowed, true);
});

test("first match wins", () => {
  const p = new Policy().allow("refund", (a) => a.args.amount < 10).deny("refund");
  assert.equal(p.decide(act("refund", { amount: 5 })).allowed, true);
  assert.equal(p.decide(act("refund", { amount: 999 })).denied, true);
});

test("invalid default throws", () => {
  assert.throws(() => new Policy("maybe"));
});

test("predicate error fails closed to deny", () => {
  // a when() that throws (missing arg) must not crash the gate open — it denies
  const p = new Policy().deny("transfer", (a) => a.args.amount > 1000);
  const d = p.decide({ name: "transfer" });        // args undefined -> throws in predicate
  assert.equal(d.denied, true);
  assert.match(d.reason, /predicate error/);
});

test("early allow predicate error does not fall through to allow", () => {
  const p = new Policy()
    .allow("tool", (a) => a.args.safe)              // throws: args undefined
    .deny("tool");
  assert.equal(p.decide({ name: "tool" }).denied, true);
});

test("non-callable when throws at authoring", () => {
  assert.throws(() => new Policy().deny("x", true), TypeError);
});
