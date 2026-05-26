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
import threading
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent.db import (
    EffortBand,
    Obligation,
    User,
    WorkspaceSetting,
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
def post(text: str, *, blocks: Optional[list] = None, sync: bool = False) -> Optional[bool]:
    """Post to the configured workspace channel. Returns True/False on
    delivery when sync=True; otherwise schedules a background send and
    returns None.

    Never raises — Slack errors are logged but never bubble up to the API
    caller. The whole point is fire-and-forget alerting.
    """

    def _do_send() -> bool:
        try:
            with session_scope() as db:
                cfg = get_config(db)
            url = (cfg or {}).get("webhook_url")
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
# ---------------------------------------------------------------------------
def _mention(user: Optional[User]) -> str:
    if user is None:
        return "*unassigned*"
    if user.slack_user_id:
        return f"<@{user.slack_user_id}>"
    return f"*{user.full_name or user.email}*"


def assignment_message(*, obligation: Obligation, assignee: User, actor: User) -> str:
    entity = obligation.entity.name if obligation.entity else "—"
    form = obligation.rule.form_name if obligation.rule else "Compliance item"
    return (
        f":bell: {_mention(assignee)} you're now on the hook for "
        f"*{form}* ({entity}) — due `{obligation.due_date.isoformat()}`. "
        f"Assigned by {actor.full_name or actor.email}."
    )


def mention_message(
    *, obligation: Obligation, mentioned: User, actor: User, body: str
) -> str:
    entity = obligation.entity.name if obligation.entity else "—"
    form = obligation.rule.form_name if obligation.rule else "Compliance item"
    snippet = (body or "").strip().replace("\n", " ")
    if len(snippet) > 240:
        snippet = snippet[:237] + "…"
    return (
        f":speech_balloon: {_mention(mentioned)} mentioned by "
        f"{actor.full_name or actor.email} on *{form}* ({entity}):\n> {snippet}"
    )


def overdue_message(*, obligation: Obligation, days_late: int) -> str:
    entity = obligation.entity.name if obligation.entity else "—"
    form = obligation.rule.form_name if obligation.rule else "Compliance item"
    band = (obligation.effort_band or EffortBand.w4).value
    return (
        f":rotating_light: *{form}* for *{entity}* is now overdue "
        f"by {days_late} day{'s' if days_late != 1 else ''} "
        f"(effort band {band}). Assignee: {_mention(obligation.assignee)}."
    )


def filed_message(*, obligation: Obligation, actor: User) -> str:
    entity = obligation.entity.name if obligation.entity else "—"
    form = obligation.rule.form_name if obligation.rule else "Compliance item"
    return (
        f":white_check_mark: *{form}* for *{entity}* marked filed by "
        f"{actor.full_name or actor.email}."
    )


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
