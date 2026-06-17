"""Keep secrets out of the ledger.

A trust tool must never become the place your API keys leak. `redact_secrets` masks any arg
whose KEY looks sensitive (api_key, token, password, secret, authorization, ...) or whose VALUE
matches a common secret shape (OpenAI sk- keys, Bearer tokens, GitHub tokens, AWS access keys).
It's the default redactor on `Colorless(...)`; pass `redact=None` to disable, or your own
callable to customise.
"""

from __future__ import annotations

import re

_SECRET_KEY = re.compile(
    r"(api[_-]?key|secret|password|passwd|token|authorization|auth|access[_-]?key|"
    r"private[_-]?key|credential|client[_-]?secret)", re.IGNORECASE)

_SECRET_VALUE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}"          # OpenAI-style keys
    r"|Bearer\s+\S+"                    # bearer tokens
    r"|gh[pousr]_[A-Za-z0-9]{20,}"      # GitHub tokens
    r"|AKIA[0-9A-Z]{16}"                # AWS access key ids
    r"|xox[baprs]-[A-Za-z0-9\-]{10,})") # Slack tokens

MASK = "***"


def _redact_value(v):
    if isinstance(v, dict):
        return redact_secrets(v)
    if isinstance(v, list):
        return [_redact_value(x) for x in v]
    if isinstance(v, str) and _SECRET_VALUE.search(v):
        return MASK
    return v


def redact_secrets(args: dict) -> dict:
    """Return a copy of `args` with sensitive keys and values masked — recursively, so secrets
    nested inside dicts or lists are masked too (a trust tool must not leak a nested key)."""
    out = {}
    for k, v in args.items():
        if isinstance(k, str) and _SECRET_KEY.search(k):
            out[k] = MASK
        else:
            out[k] = _redact_value(v)
    return out
