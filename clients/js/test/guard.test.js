import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { ApprovalRequired, Colorless, PolicyDenied } from "../index.js";

const tmp = () => join(mkdtempSync(join(tmpdir(), "cl-")), "log.jsonl");

test("allowed action runs and logs", async () => {
  const cl = new Colorless({ ledger: tmp() });
  const send = cl.guard(({ msg }) => `sent ${msg}`, { name: "send" });
  assert.equal(await send({ msg: "hi" }), "sent hi");
  const e = cl.entries("send")[0];
  assert.equal(e.decision, "allow");
  assert.equal(e.executed && e.ok, true);
  assert.equal(cl.verify().ok, true);
});

test("denied action blocks and does not run", async () => {
  const cl = new Colorless({ ledger: tmp() }).deny("drop");
  let ran = false;
  const drop = cl.guard(() => { ran = true; }, { name: "drop" });
  await assert.rejects(() => drop({}), PolicyDenied);
  assert.equal(ran, false);
  assert.equal(cl.entries("drop")[0].executed, false);
  assert.equal(cl.verify().ok, true);
});

test("approval required blocks without handler, runs when granted", async () => {
  const blocked = new Colorless({ ledger: tmp() });
  blocked.requireApproval("refund");
  const r1 = blocked.guard(() => "ok", { name: "refund" });
  await assert.rejects(() => r1({}), ApprovalRequired);

  const ok = new Colorless({ ledger: tmp(), onApproval: async () => true });
  ok.requireApproval("refund");
  const r2 = ok.guard(({ amount }) => `ok ${amount}`, { name: "refund" });
  assert.equal(await r2({ amount: 20 }), "ok 20");
  assert.equal(ok.entries("refund").at(-1).approved, true);
});

test("async tool + error is recorded and rethrown", async () => {
  const cl = new Colorless({ ledger: tmp() });
  const boom = cl.guard(async () => { throw new Error("kaboom"); }, { name: "boom" });
  await assert.rejects(() => boom({}), /kaboom/);
  const e = cl.entries("boom")[0];
  assert.equal(e.ok, false);
  assert.match(e.error, /kaboom/);
  assert.equal(cl.verify().ok, true);
});

test("redaction is on by default", async () => {
  const cl = new Colorless({ ledger: tmp() });
  const call = cl.guard(({ api_key, endpoint }) => "ok", { name: "call_api" });
  await call({ api_key: "sk-supersecret123456", endpoint: "/v1/x" });
  const args = cl.entries("call_api")[0].action.args;
  assert.equal(args.api_key, "***");
  assert.equal(args.endpoint, "/v1/x");
});

test("subscribe fires for every ledger entry (parity with Python)", async () => {
  const cl = new Colorless({ ledger: tmp() }).deny("danger");
  const seen = [];
  cl.subscribe((e) => seen.push(e));
  await cl.run("ok", { a: 1 }, () => "y");                       // allow -> 1 entry
  await assert.rejects(() => cl.run("danger", {}, () => "x"), PolicyDenied);  // deny -> 1 entry
  assert.equal(seen.length, 2);
  assert.equal(seen[1].decision, "deny");
});

test("onApproval can return {approved, approver} -> sealed in the ledger", async () => {
  const cl = new Colorless({ ledger: tmp(), onApproval: async () => ({ approved: true, approver: "alice" }) });
  cl.requireApproval("refund");
  const refund = cl.guard(({ amount }) => `ok ${amount}`, { name: "refund" });
  assert.equal(await refund({ amount: 20 }), "ok 20");
  const e = cl.entries("refund").at(-1);
  assert.equal(e.approved, true);
  assert.equal(e.approver, "alice");
});
