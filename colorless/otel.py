"""Export colorless actions as OpenTelemetry GenAI spans — so the tamper-evident audit feeds your
existing observability stack (Datadog, Honeycomb, Grafana, ...) instead of being an island.

Optional: the core stays zero-dependency. OpenTelemetry is only needed if you ask colorless to
build a tracer for you (`pip install 'colorless-audit[otel]'`); you can also pass any tracer-like object
(anything with `start_span(name) -> span` where the span has `set_attribute` and `end`).

    from colorless import Colorless
    from colorless.otel import instrument
    cl = Colorless("agent.jsonl")
    instrument(cl)                 # live: every gated action becomes a span
    # ...or batch-export an existing ledger into your backend:
    from colorless.otel import export_ledger
    export_ledger("agent.jsonl")
"""

from __future__ import annotations

import json

from .ledger import Ledger

# OTel backends cap attribute value length; keep the serialized args well under typical limits.
_MAX_ARG_LEN = 4096


def _as_int(v, default=-1):
    """Coerce safely — a foreign/corrupt row with a non-int seq must not crash the exporter."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def genai_attributes(entry: dict) -> dict:
    """Map one sealed ledger entry to OpenTelemetry GenAI semantic-convention attributes (plus a
    `colorless.*` namespace for the gate decision + chain hash). Pure — no OTel needed."""
    action = entry.get("action") or {}
    attrs = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": action.get("name", ""),
        "colorless.decision": entry.get("decision", ""),
        "colorless.executed": bool(entry.get("executed", False)),
        "colorless.ok": bool(entry.get("ok", False)),
        "colorless.ref": entry.get("ref", ""),
        "colorless.seq": _as_int(entry.get("seq")),
        "colorless.row_hash": entry.get("row_hash", ""),
    }
    args = action.get("args")
    if args is not None:
        blob = json.dumps(args, sort_keys=True, default=str)
        if len(blob) > _MAX_ARG_LEN:
            blob = blob[:_MAX_ARG_LEN] + "...(truncated)"
        attrs["gen_ai.tool.call.arguments"] = blob
    if entry.get("reason"):
        attrs["colorless.reason"] = entry["reason"]
    if entry.get("error"):
        attrs["error.type"] = entry["error"]
    return attrs


class OtelEmitter:
    """Emits one span per ledger entry on the given tracer."""

    def __init__(self, tracer):
        self.tracer = tracer

    def emit(self, entry: dict) -> None:
        action = entry.get("action") or {}
        span = self.tracer.start_span(f"execute_tool {action.get('name', 'action')}")
        try:
            for k, v in genai_attributes(entry).items():
                span.set_attribute(k, v)
        finally:
            span.end()


def _default_tracer():
    try:
        from opentelemetry import trace
    except ImportError as e:  # pragma: no cover - exercised only without the optional dep
        raise RuntimeError(
            "OpenTelemetry is not installed. Run `pip install 'colorless-audit[otel]'`, or pass your "
            "own tracer to instrument()/export_ledger()."
        ) from e
    return trace.get_tracer("colorless")


def instrument(colorless, tracer=None) -> OtelEmitter:
    """Live: subscribe an emitter so every gated action (allowed, denied, or blocked) becomes a span.
    Pass a tracer, or let colorless build the global OTel one."""
    emitter = OtelEmitter(tracer or _default_tracer())
    colorless.subscribe(emitter.emit)
    return emitter


def export_ledger(path: str, tracer=None) -> int:
    """Batch: replay an existing ledger file into your tracing backend. Returns the span count."""
    emitter = OtelEmitter(tracer or _default_tracer())
    n = 0
    for entry in Ledger(path).entries():
        try:
            emitter.emit(entry)
            n += 1
        except Exception:
            continue   # one bad row (or a backend rejecting an attr) must not abort the whole batch
    return n
