import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { canonical, GENESIS, Ledger } from "../ledger.js";

const tmp = () => join(mkdtempSync(join(tmpdir(), "cl-")), "log.jsonl");
const seed = (led, n = 4) => { for (let i = 0; i < n; i++) led.append("action", `tool_${i}`, { action: { name: `tool_${i}` }, ok: true }); };
const lines = (p) => readFileSync(p, "utf8").split("\n").filter(Boolean);

test("append + verify clean", () => {
  const led = new Ledger(tmp());
  seed(led, 5);
  const r = led.verify();
  assert.equal(r.ok, true);
  assert.equal(r.length, 5);
  assert.equal(led.head().head, r.head);
});

test("genesis links first entry", () => {
  const led = new Ledger(tmp());
  const e = led.append("action", "x");
  assert.equal(e.prev_hash, GENESIS);
  assert.equal(e.seq, 0);
});

test("editing a payload is caught", () => {
  const p = tmp();
  const led = new Ledger(p);
  seed(led, 4);
  const ls = lines(p);
  const row = JSON.parse(ls[1]);
  row.action.name = "EVIL";
  ls[1] = JSON.stringify(row);
  writeFileSync(p, ls.join("\n") + "\n");
  const r = led.verify();
  assert.equal(r.ok, false);
  assert.equal(r.broken_at, 1);
  assert.match(r.reason, /altered/);
});

test("deleting a middle entry is caught", () => {
  const p = tmp();
  const led = new Ledger(p);
  seed(led, 4);
  const ls = lines(p);
  ls.splice(2, 1);
  writeFileSync(p, ls.join("\n") + "\n");
  assert.equal(led.verify().ok, false);
});

test("reordering is caught", () => {
  const p = tmp();
  const led = new Ledger(p);
  seed(led, 4);
  const ls = lines(p);
  [ls[1], ls[2]] = [ls[2], ls[1]];
  writeFileSync(p, ls.join("\n") + "\n");
  assert.equal(led.verify().ok, false);
});

test("tail truncation passes verify but fails anchor", () => {
  const p = tmp();
  const led = new Ledger(p);
  seed(led, 5);
  const anchorPath = p + ".anchor.json";
  led.anchor(anchorPath);
  writeFileSync(p, lines(p).slice(0, 3).join("\n") + "\n");
  assert.equal(led.verify().ok, true); // shorter chain is self-consistent
  const a = led.verifyAgainstAnchor(anchorPath);
  assert.equal(a.matches, false);
});

test("malformed anchor without head is not a match", () => {
  const p = tmp();
  const led = new Ledger(p);
  seed(led, 3);
  const anchorPath = p + ".anchor.json";
  writeFileSync(anchorPath, JSON.stringify({ length: 3 })); // no head field
  const a = led.verifyAgainstAnchor(anchorPath);
  assert.equal(a.anchored, false);
  assert.notEqual(a.matches, true);
});

test("U+007F (DEL) is escaped to match Python ensure_ascii (cross-verify)", () => {
  // Python's json.dumps escapes 0x7f to ; JS must too or a row fails `colorless verify`.
  assert.equal(canonical({ v: "\x7f" }), '{"v":"\\u007f"}');
});
