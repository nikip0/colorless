# Changelog

All notable changes to colorless are documented here. This project follows
[Semantic Versioning](https://semver.org).

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
