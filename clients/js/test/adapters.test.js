import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { Colorless, PolicyDenied, ToolGuard, UnknownTool } from "../index.js";

const tmp = () => join(mkdtempSync(join(tmpdir(), "cl-")), "log.jsonl");

test("call allowed tool runs and logs", async () => {
  const cl = new Colorless({ ledger: tmp() });
  const tg = new ToolGuard(cl);
  tg.add("get_weather", ({ city }) => `${city}: sunny`);
  assert.equal(await tg.call("get_weather", { city: "NYC" }), "NYC: sunny");
  assert.equal(cl.entries("get_weather")[0].decision, "allow");
  assert.equal(cl.verify().ok, true);
});

test("denied tool is blocked and not run", async () => {
  const cl = new Colorless({ ledger: tmp() }).deny("wire_money");
  let ran = false;
  const tg = new ToolGuard(cl).add("wire_money", () => { ran = true; });
  await assert.rejects(() => tg.call("wire_money", { amount: 9000 }), PolicyDenied);
  assert.equal(ran, false);
  assert.equal(cl.entries("wire_money")[0].executed, false);
});

test("unknown tool throws", async () => {
  const tg = new ToolGuard(new Colorless({ ledger: tmp() }));
  await assert.rejects(() => tg.call("nope", {}), UnknownTool);
});

test("guarded() returns wrapped callables", async () => {
  const cl = new Colorless({ ledger: tmp() }).deny("danger");
  const tg = new ToolGuard(cl).add("safe", () => "ok").add("danger", () => "boom");
  const fns = tg.guarded();
  assert.equal(await fns.safe({}), "ok");
  await assert.rejects(() => fns.danger({}), PolicyDenied);
});

test("simulated agent loop is fully verifiable", async () => {
  const cl = new Colorless({ ledger: tmp() }).deny("drop_table");
  const tg = new ToolGuard(cl).add("query", () => "rows").add("drop_table", () => "dropped");
  const calls = [["query", { sql: "select 1" }], ["drop_table", { name: "users" }], ["query", { sql: "select 2" }]];
  const results = [];
  for (const [name, args] of calls) {
    try { results.push(await tg.call(name, args)); }
    catch (e) { results.push("BLOCKED"); }
  }
  assert.deepEqual(results, ["rows", "BLOCKED", "rows"]);
  assert.equal(cl.entries().length, 3);
  assert.equal(cl.verify().ok, true);
});
