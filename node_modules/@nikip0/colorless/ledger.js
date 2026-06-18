// Tamper-evident, append-only ledger — JS port of the Python engine.
//
// Same on-disk format and hashing as the Python SDK: each line is canonical JSON with
//   content_hash = sha256(canonical(entry without chain fields))
//   row_hash     = sha256(prev_hash + content_hash)
// so a ledger written here verifies with `colorless verify` too (ASCII/int content).
//
// Zero dependencies — uses only node:crypto and node:fs.

import { createHash } from "node:crypto";
import { appendFileSync, existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";

export const GENESIS = "0".repeat(64);
const CHAIN_FIELDS = new Set(["content_hash", "prev_hash", "row_hash"]);

function sha(s) {
  return createHash("sha256").update(s, "utf8").digest("hex");
}

// Deterministic JSON matching Python's json.dumps(sort_keys=True, separators=(",",":"),
// ensure_ascii=True): recursively sorted keys, no whitespace, non-ASCII escaped to \uXXXX.
function stableStringify(v) {
  if (v === null || v === undefined) return "null";
  if (Array.isArray(v)) return "[" + v.map(stableStringify).join(",") + "]";
  if (typeof v === "object") {
    const keys = Object.keys(v).sort();
    return "{" + keys.map((k) => JSON.stringify(k) + ":" + stableStringify(v[k])).join(",") + "}";
  }
  return JSON.stringify(v);
}

function escapeNonAscii(s) {
  let out = "";
  for (let i = 0; i < s.length; i++) {
    const code = s.charCodeAt(i);
    // >= 0x7f, not > 0x7f: Python's ensure_ascii escapes U+007F (DEL) too, so a literal 0x7f here
    // would make a JS-written row fail `colorless verify` in Python (and vice-versa).
    out += code >= 0x7f ? "\\u" + code.toString(16).padStart(4, "0") : s[i];
  }
  return out;
}

export function canonical(value) {
  return escapeNonAscii(stableStringify(value));
}

function contentHash(entry) {
  const body = {};
  for (const k of Object.keys(entry)) if (!CHAIN_FIELDS.has(k)) body[k] = entry[k];
  return sha(canonical(body));
}

export class Ledger {
  constructor(path = "colorless.jsonl") {
    this.path = String(path);
  }

  _read() {
    if (!existsSync(this.path)) return [];
    const rows = [];
    for (const line of readFileSync(this.path, "utf8").split("\n")) {
      const t = line.trim();
      if (t) rows.push(JSON.parse(t));
    }
    return rows;
  }

  // Synchronous read-compute-write: the Node event loop runs this to completion without
  // interleaving, so concurrent async callers can't fork the chain (single-process).
  append(kind, ref = "", payload = {}) {
    const rows = this._read();
    const prev = rows.length ? rows[rows.length - 1].row_hash : GENESIS;
    // payload first, then chain/meta fields — a payload key named seq/ts/kind/ref can't overwrite
    // a structural field and corrupt the chain (key order doesn't affect the hash: canonical sorts).
    const entry = {
      ...payload,
      seq: rows.length,
      ts: new Date().toISOString(),
      kind,
      ref: String(ref || ""),
    };
    const ch = contentHash(entry);
    entry.content_hash = ch;
    entry.prev_hash = prev;
    entry.row_hash = sha(prev + ch);
    appendFileSync(this.path, canonical(entry) + "\n");
    return entry;
  }

  head() {
    const rows = this._read();
    if (!rows.length) return { head: GENESIS, length: 0 };
    return { head: rows[rows.length - 1].row_hash, length: rows.length };
  }

  entries(ref = null) {
    return this._read().filter((r) => ref === null || r.ref === ref);
  }

  verify() {
    const rows = this._read();
    let prev = GENESIS;
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      if (r.seq !== i) return broken(rows, i, "seq out of order (entry inserted, deleted, or reordered)");
      if (contentHash(r) !== r.content_hash) return broken(rows, i, "entry payload altered");
      if (r.prev_hash !== prev) return broken(rows, i, "prev_hash discontinuity (broken or forked link)");
      if (r.row_hash !== sha(prev + r.content_hash)) return broken(rows, i, "row_hash mismatch");
      prev = r.row_hash;
    }
    return { ok: true, length: rows.length, head: prev, broken_at: null };
  }

  anchor(path) {
    const h = this.head();
    h.anchored_at = new Date().toISOString();
    const tmp = String(path) + ".tmp";
    writeFileSync(tmp, JSON.stringify(h, null, 2));
    renameSync(tmp, String(path)); // atomic
    return h;
  }

  verifyAgainstAnchor(path) {
    let a;
    try {
      a = JSON.parse(readFileSync(path, "utf8"));
    } catch {
      return { anchored: false, reason: "no anchor published yet" };
    }
    const head = a.head;
    if (!head) {
      // a truncated/corrupt anchor with no head commits nothing — don't report it as a match
      return { anchored: false, reason: "anchor missing head — malformed or truncated" };
    }
    const present = this._read().some((r) => r.row_hash === head);
    if (head && head !== GENESIS && !present) {
      return { anchored: true, matches: false, anchored_head: head,
               reason: "anchored head not in ledger — truncated or replayed below the anchor" };
    }
    return { anchored: true, matches: true, anchored_head: head, anchored_at: a.anchored_at };
  }
}

function broken(rows, i, reason) {
  return { ok: false, length: rows.length, broken_at: i, reason };
}
