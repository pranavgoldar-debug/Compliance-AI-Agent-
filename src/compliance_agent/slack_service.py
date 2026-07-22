"""Slack outbound notifications via Incoming Webhook.

Config lives in the `workspace_settings` table under the `slack` key:

  { "webhook_url": "https://hooks.slack.com/services/T.../B.../...",
    "default_channel": "#aspora-compliance",
    "enabled": true }

We never persist tokens in env vars — admins paste the webhook URL into
Settings → Integrations and it lives in the workspace DB. The webhook URL
itself is the bearer; treat it like a secret.

Outgoing posts run in a daemon thread so a slow Slack response never
blocks the API request that triggered the notification.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent.db import (
    EffortBand,
    Obligation,
    User,
    WorkspaceSetting,
    obligation_status_label,
    session_scope,
)


logger = logging.getLogger("compliance_agent.slack")
SETTING_KEY = "slack"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------
def get_config(db: Session) -> dict:
    row = db.get(WorkspaceSetting, SETTING_KEY)
    return dict(row.value or {}) if row else {}


def set_config(db: Session, value: dict, updated_by_id: Optional[int] = None) -> dict:
    row = db.get(WorkspaceSetting, SETTING_KEY)
    if row is None:
        row = WorkspaceSetting(key=SETTING_KEY, value=value, updated_by_id=updated_by_id)
        db.add(row)
    else:
        row.value = value
        row.updated_by_id = updated_by_id
    db.flush()
    return dict(row.value or {})


def is_configured(db: Session) -> bool:
    cfg = get_config(db)
    return bool(cfg.get("webhook_url")) and cfg.get("enabled", True)


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------
def post(
    text: str,
    *,
    blocks: Optional[list] = None,
    sync: bool = False,
    function: Optional[str] = None,
) -> Optional[bool]:
    """Post to the configured workspace channel. Returns True/False on
    delivery when sync=True; otherwise schedules a background send and
    returns None.

    ``function`` routes by owner team: when the config has a webhook saved
    for that function (Finance / Compliance / Legal / HR — a Slack incoming
    webhook is bound to one channel, so per-channel routing means one
    webhook per channel), the message goes there; otherwise it falls back
    to the default webhook.

    Never raises — Slack errors are logged but never bubble up to the API
    caller. The whole point is fire-and-forget alerting.
    """

    def _do_send() -> bool:
        try:
            with session_scope() as db:
                cfg = get_config(db)
            url = (cfg or {}).get("webhook_url")
            if function:
                url = ((cfg or {}).get("function_webhooks") or {}).get(
                    str(function).strip().lower()
                ) or url
            if not url or not (cfg or {}).get("enabled", True):
                return False
            import httpx

            payload: dict = {"text": text}
            if blocks:
                payload["blocks"] = blocks
            channel = cfg.get("default_channel")
            if channel:
                payload["channel"] = channel
            r = httpx.post(url, json=payload, timeout=8.0)
            ok = r.status_code == 200 and r.text == "ok"
            if not ok:
                logger.warning(
                    "Slack post failed: status=%s body=%r", r.status_code, r.text[:300]
                )
            return ok
        except Exception as e:
            logger.warning("Slack post crashed: %s", e)
            return False

    if sync:
        return _do_send()

    threading.Thread(target=_do_send, daemon=True).start()
    return None


# ---------------------------------------------------------------------------
# Pre-baked message builders
#
# Each builder returns a dict with `text` (fallback for notification
# previews) and `blocks` (rich Block Kit payload). Callers can either
# pass the dict straight to post(...) by unpacking, or use the legacy
# string-only helpers below that compose just the `text`.
# ---------------------------------------------------------------------------
def _mention(user: Optional[User]) -> str:
    if user is None:
        return "*unassigned*"
    # Only a real member ID produces a working <@…> mention — anything else
    # (a display name saved before validation existed) falls back to the
    # plain name instead of rendering as broken markup.
    sid = (user.slack_user_id or "").strip().upper()
    if sid and re.fullmatch(r"[UW][A-Z0-9]{5,}", sid):
        return f"<@{sid}>"
    return f"*{(user.full_name or user.email).strip()}*"


def _app_base_url() -> str:
    """Best-effort base URL for the deployed app — drives the "View in
    Aspora" buttons. Falls back to a sensible default if unset."""
    import os
    return os.environ.get("COMPLIANCE_BASE_URL", "").rstrip("/") or "https://compliance-ai-agent-j3l9.onrender.com"


def _obligation_link(obligation: Obligation) -> str:
    return f"{_app_base_url()}/obligations/{obligation.id}"


def _days_word(days: int) -> str:
    """3 → '3 days', 1 → '1 day', 0 → 'today', -2 → '2 days overdue'."""
    if days == 0:
        return "due today"
    if days > 0:
        return f"due in {days} day{'s' if days != 1 else ''}"
    return f"overdue by {abs(days)} day{'s' if days != -1 else ''}"


def _ob_context_fields(obligation: Obligation, *, include_assignee: bool = True) -> list[dict]:
    """The facts that go inside every obligation-related card — rendered as a
    2-col grid in Slack. Assignment cards skip the Assignee field (the first
    line already mentions who's on the hook)."""
    entity = obligation.entity.name if obligation.entity else "—"
    from compliance_agent.api._helpers import days_remaining

    days = days_remaining(obligation.due_date)
    fields = [
        {"type": "mrkdwn", "text": f"*Entity*\n{entity}"},
        {"type": "mrkdwn", "text": f"*Due*\n{obligation.due_date.isoformat()} ({_days_word(days)})"},
    ]
    if include_assignee:
        # Slack <@id> mention renders the assignee's name highlighted (blue).
        fields.append({"type": "mrkdwn", "text": f"*Assignee*\n{_mention(obligation.assignee)}"})
    return fields


def _view_button(obligation: Obligation, label: str = "View in Aspora") -> dict:
    """Action row: a 'View' link plus interactive status buttons. The status
    buttons fire the Slack interactivity endpoint (needs a Slack App with
    Interactivity enabled + SLACK_SIGNING_SECRET set); the link always works."""
    oid = obligation.id
    return {
        "type": "actions",
        "block_id": f"ob_{oid}",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": label},
                "url": _obligation_link(obligation),
                "style": "primary",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "▶ Started"},
                "action_id": "st_in_progress",
                "value": f"{oid}:in_progress",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "🔄 Under Progress"},
                "action_id": "st_pending_review",
                "value": f"{oid}:pending_review",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "✅ Filed"},
                "action_id": "st_completed",
                "value": f"{oid}:completed",
            },
            {
                # Doesn't flip the status directly — the interactivity
                # handler replies asking for a mandatory reason first.
                "type": "button",
                "text": {"type": "plain_text", "text": "🚫 Not Applicable"},
                "action_id": "st_not_applicable",
                "value": f"{oid}:not_applicable",
            },
        ],
    }


def verify_slack_signature(signing_secret: str, timestamp: str, raw_body: bytes, signature: str) -> bool:
    """Verify a Slack request: HMAC-SHA256 of 'v0:{ts}:{body}' with the app's
    signing secret, compared to the X-Slack-Signature header ('v0=...')."""
    import hashlib
    import hmac as _hmac
    import time as _time

    if not signing_secret or not signature or not timestamp:
        return False
    try:
        # Reject stale requests (replay protection) — 5 min window.
        if abs(_time.time() - int(timestamp)) > 300:
            return False
    except ValueError:
        return False
    base = b"v0:" + timestamp.encode() + b":" + raw_body
    digest = "v0=" + _hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return _hmac.compare_digest(digest, signature.strip())


def deadline_blocks(
    *, obligation: Obligation, assignee: Optional[User], days_remaining: int
) -> dict:
    """Deadline-alert card for the channel: urgency dot + due line, the
    canonical key / entity / status context, Open + status buttons (wired to
    the interactivity endpoint) and an Owner footer with the escalation note."""
    rule = obligation.rule
    form = rule.form_name if rule else "Compliance item"
    entity = obligation.entity.name if obligation.entity else "—"
    juris = (rule.jurisdiction_code if rule else "—").upper()
    status = obligation_status_label(obligation.status)
    due = obligation.due_date.strftime("%d-%b-%y")
    dot = "🔴" if days_remaining <= 7 else "🟡" if days_remaining <= 15 else "🟢"
    text = f"{dot} {form} {_days_word(days_remaining)} — {due} ({entity})"
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{dot} *{form}* *{_days_word(days_remaining)}* — {due}\n"
                    f"`{juris}` · `{form}` · {entity} · status: *{status}*"
                ),
            },
        },
        _view_button(obligation, "Open"),
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Owner: {_mention(assignee)} · T-7 copies the assigner, "
                        "overdue pages compliance-leads"
                    ),
                }
            ],
        },
        {"type": "divider"},
    ]
    return {"text": text, "blocks": blocks}


def assignment_blocks(
    *, obligation: Obligation, assignee: User, actor: User
) -> dict:
    """Block-kit payload for an assignment ping."""
    form = obligation.rule.form_name if obligation.rule else "Compliance item"
    entity = obligation.entity.name if obligation.entity else "—"
    text = (
        f":bell: {_mention(assignee)}, you're on "
        f"{form} ({entity})."
    )
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🔔 New assignment — {form}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{_mention(assignee)} you're now on the hook for *{form}*.\n"
                    f"Assigned by {(actor.full_name or actor.email).strip()}."
                ),
            },
        },
        {"type": "section", "fields": _ob_context_fields(obligation, include_assignee=False)},
        _view_button(obligation, "Open the obligation →"),
        {"type": "divider"},
    ]
    return {"text": text, "blocks": blocks}


def mention_blocks(
    *,
    obligation: Obligation,
    mentioned: User,
    actor: User,
    body: str,
) -> dict:
    form = obligation.rule.form_name if obligation.rule else "Compliance item"
    snippet = (body or "").strip().replace("\n", " ")
    if len(snippet) > 240:
        snippet = snippet[:237] + "…"
    text = (
        f":speech_balloon: {mentioned.full_name or mentioned.email} mentioned by "
        f"{(actor.full_name or actor.email).strip()} on {form}."
    )
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"💬 You were mentioned"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{_mention(mentioned)} — *{(actor.full_name or actor.email).strip()}* "
                    f"tagged you on *{form}*:\n"
                    f">>> {snippet}"
                ),
            },
        },
        {"type": "section", "fields": _ob_context_fields(obligation)},
        _view_button(obligation, "Reply in Aspora →"),
        {"type": "divider"},
    ]
    return {"text": text, "blocks": blocks}


def overdue_blocks(*, obligation: Obligation, days_late: int) -> dict:
    form = obligation.rule.form_name if obligation.rule else "Compliance item"
    entity = obligation.entity.name if obligation.entity else "—"
    text = f":rotating_light: {form} for {entity} is overdue by {days_late} day(s)."
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🚨 Overdue — {form}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{form}* for *{entity}* missed its due date by "
                    f"*{days_late} day{'s' if days_late != 1 else ''}*. "
                    f"Assignee: {_mention(obligation.assignee)}."
                ),
            },
        },
        {"type": "section", "fields": _ob_context_fields(obligation)},
        _view_button(obligation, "Open & triage →"),
        {"type": "divider"},
    ]
    return {"text": text, "blocks": blocks}


def filed_blocks(*, obligation: Obligation, actor: User) -> dict:
    form = obligation.rule.form_name if obligation.rule else "Compliance item"
    entity = obligation.entity.name if obligation.entity else "—"
    text = f":white_check_mark: {form} for {entity} filed by {(actor.full_name or actor.email).strip()}."
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"✅ Filed — {form}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{form}* for *{entity}* was just filed by "
                    f"*{(actor.full_name or actor.email).strip()}*."
                ),
            },
        },
        {"type": "section", "fields": _ob_context_fields(obligation)},
        _view_button(obligation, "Open the audit trail →"),
        {"type": "divider"},
    ]
    return {"text": text, "blocks": blocks}


def submit_for_review_blocks(*, obligation: Obligation, actor: User) -> dict:
    """Employee submitted for admin review."""
    form = obligation.rule.form_name if obligation.rule else "Compliance item"
    entity = obligation.entity.name if obligation.entity else "—"
    dept = (obligation.department or "compliance").value if hasattr(obligation.department, "value") else "compliance"
    submitter_label = "payment" if dept == "finance" else "filing"
    text = f":eyes: {form} ({entity}) — {submitter_label} submitted for review by {(actor.full_name or actor.email).strip()}."
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"👀 Awaiting review — {form}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{(actor.full_name or actor.email).strip()}* submitted "
                    f"*{submitter_label}* on *{form}* for admin review."
                ),
            },
        },
        {"type": "section", "fields": _ob_context_fields(obligation)},
        _view_button(obligation, "Review & approve →"),
        {"type": "divider"},
    ]
    return {"text": text, "blocks": blocks}


# ---------------------------------------------------------------------------
# Legacy string builders — kept for backwards compatibility with callers
# that haven't migrated to the dict-returning versions above. Internally
# they just lift `text` from the block payload.
# ---------------------------------------------------------------------------
def assignment_message(*, obligation: Obligation, assignee: User, actor: User) -> str:
    return assignment_blocks(obligation=obligation, assignee=assignee, actor=actor)["text"]


def mention_message(
    *, obligation: Obligation, mentioned: User, actor: User, body: str
) -> str:
    return mention_blocks(
        obligation=obligation, mentioned=mentioned, actor=actor, body=body
    )["text"]


def overdue_message(*, obligation: Obligation, days_late: int) -> str:
    return overdue_blocks(obligation=obligation, days_late=days_late)["text"]


def filed_message(*, obligation: Obligation, actor: User) -> str:
    return filed_blocks(obligation=obligation, actor=actor)["text"]


__all__ = [
    "get_config",
    "set_config",
    "is_configured",
    "post",
    "assignment_message",
    "mention_message",
    "overdue_message",
    "filed_message",
]
