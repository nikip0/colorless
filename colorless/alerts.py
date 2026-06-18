"""Send a Slack/webhook alert when an agent action is blocked, errors, or needs approval.

Zero dependencies (stdlib urllib). Wire the action alerts to the event hook and the pending-approval
alert to the queue — both fire best-effort and never break the agent:

    from colorless import Colorless
    from colorless.alerts import slack_alerter, approval_alerter
    from colorless.dashboard import ApprovalQueue, queue_approval

    q  = ApprovalQueue(on_request=approval_alerter(SLACK_URL, slack=True))   # "approval needed"
    cl = Colorless("agent.jsonl", on_approval=queue_approval(q))
    cl.subscribe(slack_alerter(SLACK_URL))   # alert when an action is blocked or errors
"""

from __future__ import annotations

import json
import queue
import threading
import urllib.request

# A single shared background worker drains a bounded queue, so a burst of alerts can't spawn
# unbounded threads (each blocking up to `timeout` in urlopen) and a slow endpoint can't stall
# the agent. On overflow we shed load rather than block or grow without bound.
_MAX_QUEUED_ALERTS = 1000
_alert_q: "queue.Queue | None" = None
_alert_lock = threading.Lock()


def _alert_worker(q: "queue.Queue") -> None:
    while True:
        sender, url, payload = q.get()
        try:
            sender(url, payload)
        except Exception:
            pass            # an alert must never break anything
        finally:
            q.task_done()


def _enqueue_alert(sender, url, payload) -> None:
    global _alert_q
    if _alert_q is None:
        with _alert_lock:
            if _alert_q is None:
                _alert_q = queue.Queue(maxsize=_MAX_QUEUED_ALERTS)
                threading.Thread(target=_alert_worker, args=(_alert_q,), daemon=True).start()
    try:
        _alert_q.put_nowait((sender, url, payload))
    except queue.Full:
        pass                # shed rather than block the agent or grow unbounded


def post_json(url: str, payload: dict, timeout: float = 5.0):
    """POST `payload` as JSON. Returns the status code, or None on any failure — an alert must never
    break the agent."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return getattr(r, "status", None) or r.getcode()
    except Exception:
        return None


def _is_alertable(entry: dict) -> bool:
    """Worth alerting on: a blocked action (denied / unapproved) or an errored one."""
    return entry.get("executed") is False or entry.get("ok") is False


def _slack_text(entry: dict) -> str:
    name = (entry.get("action") or {}).get("name", "action")
    if entry.get("decision") == "deny":
        return f":no_entry: colorless blocked *{name}* (policy deny)"
    if entry.get("decision") == "approve" and not entry.get("executed"):
        return f":warning: colorless held *{name}* — approval required and not granted"
    if entry.get("ok") is False:
        return f":x: *{name}* errored: {entry.get('error', '')}"
    return f"colorless: *{name}* ({entry.get('decision')})"


def _dispatch(sender, url, payload, background):
    """Send the alert OFF the agent's hot path by default — a slow/unreachable endpoint must never
    stall the agent. `background=False` (tests) sends synchronously."""
    if background:
        _enqueue_alert(sender, url, payload)
    else:
        sender(url, payload)


def webhook_alerter(url: str, predicate=_is_alertable, sender=post_json, background=True):
    """A `Colorless.subscribe()` callback that POSTs the full entry to `url` for noteworthy events."""
    def cb(entry):
        if predicate(entry):
            _dispatch(sender, url, {"event": "colorless.alert", "entry": entry}, background)
    return cb


def slack_alerter(url: str, predicate=_is_alertable, sender=post_json, background=True):
    """A `Colorless.subscribe()` callback that posts a formatted Slack message for noteworthy events."""
    def cb(entry):
        if predicate(entry):
            _dispatch(sender, url, {"text": _slack_text(entry)}, background)
    return cb


def approval_alerter(url: str, slack: bool = False, sender=post_json, background=True):
    """An `ApprovalQueue(on_request=...)` callback: notify when an action is waiting for a human."""
    def on_request(record):
        name = (record.get("action") or {}).get("name", "action")
        payload = {"text": f":bell: colorless: *{name}* needs approval"} if slack \
            else {"event": "colorless.approval_pending", "request": record}
        _dispatch(sender, url, payload, background)
    return on_request
