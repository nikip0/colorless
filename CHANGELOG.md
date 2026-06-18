# Changelog

All notable changes to colorless are documented here. This project follows
[Semantic Versioning](https://semver.org).

## [1.0.1] — 2026-06-18

Polish + correctness pass before wider hand-off. No API changes.

### Fixed
- **Cross-language verify for floats** — an integer-valued float (e.g. `10.0`) now serialises as
  `10` (matching JS's `JSON.stringify`), so a Python-written ledger containing amounts/counts
  verifies with the JS SDK and vice-versa. (Scientific-notation floats remain the one edge.)
- **Gate always seals** — a failing redactor (or a non-dict `args`) can no longer crash the gate
  *before* a blocked action is recorded; it now falls back to a marker and still seals the decision.
- **Correct version strings** — `colorless.__version__` and the JS `VERSION` export were stuck at
  `0.2.0`.
- **Docs/install accuracy** — README, the JS README, and the docs site now show the real package
  names (`pip install colorless-audit`, `npm install @nikip0/colorless`), drop the stale `v0.2` /
  "49 tests" claims, and note the cross-language float edge.

## [1.0.0] — 2026-06-17

First public release. Distributed as `colorless-audit` on PyPI (imports as `colorless`)
and `@nikip0/colorless` on npm.

### Core
- **Policy gate** — ordered `allow` / `deny` / `require_approval` rules, first-match-wins,
  with `when=` predicates. Never an auto-approver: an approval-gated action blocks until a
  human grants it.
- **Tamper-evident ledger** — every action sealed into a SHA-256 hash chain
  (`content_hash` + `row_hash`); `verify()` re-walks and catches any edit, delete, reorder,
  or backdate. `anchor()` + `verify_against_anchor()` defend against tail-truncation.
- **Pluggable storage** — zero-dependency JSONL (default) or indexed stdlib SQLite (WAL);
  the same sealed entries produce the same head hash on either backend.
- **Secret + PII redaction** — keep credentials and personal data out of the immutable log
  (args, results, and error messages).

### Surfaces
- **Two SDKs** — Python and JavaScript/TypeScript, with byte-identical canonical JSON so a
  Node-written ledger verifies with the Python `colorless verify` CLI (cross-language proven).
- **CLI** — `verify` / `head` / `tail` / `anchor` / `verify-anchor` / `dashboard`;
  `verify` exits non-zero on a broken chain, so it drops straight into CI.
- **Dashboard** — stdlib web UI: live feed, stats, integrity status, and human approve/deny,
  with token auth, per-IP lockout, and the approver's identity sealed into the ledger.
- **Framework adapters** — MCP, LangChain/LangGraph, CrewAI, LlamaIndex, OpenAI Agents SDK
  (duck-typed; no framework import required).
- **MCP security scan** — detect tool-poisoning, prompt-injection, hidden/bidi unicode, and
  homoglyph names in tool definitions; `pin()` / `diff()` catch rug-pulls.
- **OpenTelemetry export** (`colorless-audit[otel]`) and **Slack/webhook alerting**, both
  off the hot path.

[1.0.0]: https://github.com/nikip0/colorless/releases/tag/v1.0.0
