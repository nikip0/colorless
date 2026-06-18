"""Content guardrails — detect PII, prompt-injection, and jailbreak attempts in the TEXT an agent
handles, and gate on it through the SAME policy + tamper-evident audit.

    from colorless import Colorless
    from colorless.guardrails import has_injection, has_pii, redact_pii

    cl = Colorless("agent.jsonl", redact=redact_pii)   # also keep PII out of the log
    cl.deny(when=has_injection)                          # block any action whose args carry an injection
    cl.require_approval(when=has_pii)                    # any action carrying PII needs a human

Zero-dependency and pattern-based: a fast first line you can *prove* you ran (every block is sealed
in the chain). For ML-grade detection, plug in Presidio/Lakera as your own `when=` predicate —
colorless gives you the gate and the audit, not the model.
"""

from __future__ import annotations

import re

# --- PII patterns (credit cards are handled separately, with a Luhn check) ---
_PII = {
    "email": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "ip": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}
_CC_CANDIDATE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

# --- prompt-injection / jailbreak phrases ---
_INJECTION = re.compile(
    r"ignore (the |all )?(previous|above|prior|earlier|preceding) (instructions|prompts?|context)"
    r"|disregard (all|the|your|any|previous|above)"
    r"|forget (everything|all|your|the) (you|instructions|previous|rules|above)?"
    r"|you are now (in )?(dan|developer mode|do anything now)"
    r"|developer mode (enabled|on)"
    r"|do anything now"
    r"|jailbreak"
    r"|reveal (your |the )?(system )?(prompt|instructions)"
    r"|(what (is|are)|show me|print|repeat) (your |the )?(system )?(prompt|instructions)"
    r"|act as (an? )?(unrestricted|uncensored|jailbroken)"
    r"|pretend (you are|to be) (an? )?(unrestricted|jailbroken|dan)",
    re.IGNORECASE)

_PII_CATEGORIES = frozenset({"email", "phone", "ssn", "ip", "credit_card"})


def _luhn(s: str) -> bool:
    digits = [int(c) for c in s if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def find(text) -> set:
    """Categories detected in a single string: PII types + 'prompt_injection'."""
    cats = set()
    if not isinstance(text, str):
        return cats
    for name, rx in _PII.items():
        if rx.search(text):
            cats.add(name)
    if any(_luhn(m.group()) for m in _CC_CANDIDATE.finditer(text)):
        cats.add("credit_card")
    if _INJECTION.search(text):
        cats.add("prompt_injection")
    return cats


def scan(value) -> set:
    """Recursively scan a value (str / number / dict / list) and union the categories found."""
    if isinstance(value, str):
        return find(value)
    if isinstance(value, dict):
        out = set()
        for v in value.values():
            out |= scan(v)
        return out
    if isinstance(value, (list, tuple)):
        out = set()
        for v in value:
            out |= scan(v)
        return out
    if isinstance(value, bool):
        return set()
    if isinstance(value, (int, float)):
        return find(str(value))   # PII passed as a NUMBER (SSN/card/phone as int) is still caught
    return set()


def flags(action: dict) -> set:
    """All guardrail categories tripped by an action's args (action = {name, args})."""
    return scan((action or {}).get("args", {}))


def has_pii(action: dict) -> bool:
    """Policy `when=` predicate: the action's args contain PII."""
    return bool(flags(action) & _PII_CATEGORIES)


def has_injection(action: dict) -> bool:
    """Policy `when=` predicate: the action's args contain a prompt-injection / jailbreak attempt."""
    return "prompt_injection" in flags(action)


# --- PII redaction (so detected PII doesn't itself land in the ledger) ---
def _redact_text(s: str) -> str:
    # cards first (longest digit run) so the phone matcher can't eat part of a card and mislabel it
    s = _CC_CANDIDATE.sub(lambda m: "[card]" if _luhn(m.group()) else m.group(), s)
    s = _PII["ssn"].sub("[ssn]", s)
    s = _PII["phone"].sub("[phone]", s)
    s = _PII["email"].sub("[email]", s)
    s = _PII["ip"].sub("[ip]", s)
    return s


def _redact_value(v):
    if isinstance(v, str):
        return _redact_text(v)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        masked = _redact_text(str(v))                  # PII passed as a number is masked too
        return masked if masked != str(v) else v       # keep the original number/type when it's not PII
    if isinstance(v, dict):
        return {k: _redact_value(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_redact_value(x) for x in v]
    return v


def redact_pii(args: dict) -> dict:
    """Recursive PII-masking redactor — pass as `Colorless(redact=redact_pii)` so PII is masked in
    the ledger too. Compose with secret redaction: `redact=lambda a: redact_pii(redact_secrets(a))`."""
    return {k: _redact_value(v) for k, v in args.items()}
