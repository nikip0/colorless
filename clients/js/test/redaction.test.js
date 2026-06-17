import assert from "node:assert/strict";
import { test } from "node:test";
import { redactSecrets } from "../redaction.js";

test("redacts by key name", () => {
  const out = redactSecrets({ api_key: "abc", password: "p", city: "NYC" });
  assert.equal(out.api_key, "***");
  assert.equal(out.password, "***");
  assert.equal(out.city, "NYC");
});

test("redacts by value pattern", () => {
  const out = redactSecrets({ blob: "sk-ABCDEFGH12345678", note: "hello" });
  assert.equal(out.blob, "***");
  assert.equal(out.note, "hello");
});

test("redacts bearer / github / aws / slack", () => {
  const out = redactSecrets({
    a: "Bearer xyz.123",
    b: "ghp_" + "A".repeat(22),
    c: "AKIA" + "B".repeat(16),
    d: "xoxb-" + "1".repeat(12),
  });
  for (const k of ["a", "b", "c", "d"]) assert.equal(out[k], "***");
});

test("redacts nested objects and arrays", () => {
  const out = redactSecrets({
    config: { api_key: "abc", host: "x" },
    items: [{ token: "t" }, "sk-ABCDEFGH12345678", "plain"],
    ok: "fine",
  });
  assert.equal(out.config.api_key, "***");
  assert.equal(out.config.host, "x");
  assert.equal(out.items[0].token, "***");
  assert.equal(out.items[1], "***");
  assert.equal(out.items[2], "plain");
  assert.equal(out.ok, "fine");
});
