"""Google Calendar sync — pushes assigned filings onto one shared calendar.

The moment a filing is assigned (or re-assigned / re-dated) an all-day event
lands on the shared "Aspora Compliance" calendar on its due date, titled
"<form> — <entity> (Assignee: <name>)". Completing the filing (or marking it
not-applicable / unassigning) removes the event.

Reuses the Gmail integration's OAuth client + refresh token (mint the token
with BOTH scopes: gmail.send AND https://www.googleapis.com/auth/calendar.events),
so there is exactly one Google connection to maintain. Enabled by setting:

  GOOGLE_CALENDAR_ID  — the shared calendar's id (Google Calendar → calendar
                        settings → "Integrate calendar" → Calendar ID).

All pushes are best-effort in a daemon thread — Google being slow or down
never blocks an assignment. Event ids are tracked in the calendar_events
table so re-assignment updates the same event instead of duplicating it.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from sqlalchemy import select

logger = logging.getLogger("compliance_agent.gcal")

_API = "https://www.googleapis.com/calendar/v3"


def calendar_id() -> Optional[str]:
    return (os.environ.get("GOOGLE_CALENDAR_ID") or "").strip() or None


def is_configured() -> bool:
    """True when a calendar id is set AND the Gmail OAuth trio (client id /
    secret / refresh token) is available to mint access tokens."""
    from compliance_agent.email_service import _gmail_client_creds

    cid, secret = _gmail_client_creds()
    return bool(
        calendar_id() and cid and secret and os.environ.get("GMAIL_REFRESH_TOKEN")
    )


def _event_payload(ob) -> dict:
    """All-day event for the obligation's due date."""
    rule = ob.rule
    entity = ob.entity
    form = rule.form_name if rule else "Compliance item"
    entity_name = entity.name if entity else "—"
    assignee = ob.assignee
    who = (assignee.full_name or assignee.email).strip() if assignee else "Unassigned"
    from compliance_agent.email_service import base_url

    day = ob.due_date.isoformat()
    return {
        "summary": f"{form} — {entity_name} (Assignee: {who})",
        "description": (
            f"Aspora Compliance filing.\n"
            f"Entity: {entity_name}\n"
            f"Authority: {(rule.authority if rule else '') or '—'}\n"
            f"Assignee: {who}\n"
            f"Open it: {base_url().rstrip('/')}/obligations/{ob.id}"
        ),
        "start": {"date": day},
        "end": {"date": day},
        "transparency": "transparent",
    }


def _request(method: str, url: str, *, token: str, json_body: Optional[dict] = None):
    import httpx

    return httpx.request(
        method,
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=json_body,
        timeout=12.0,
    )


def _sync(obligation_id: int) -> Optional[str]:
    """Create / update / delete the event for one obligation. Returns a short
    failure reason or None on success. Runs inside its own DB session."""
    from compliance_agent.db import (
        CalendarEvent,
        Obligation,
        ObligationStatus,
        session_scope,
    )
    from compliance_agent.email_service import _gmail_access_token

    cal = calendar_id()
    if not cal:
        return "GOOGLE_CALENDAR_ID is not set."
    token = _gmail_access_token()
    if not token:
        return "Could not mint a Google access token (check the OAuth refresh token / scopes)."

    with session_scope() as db:
        ob = db.get(Obligation, obligation_id)
        mapping = db.execute(
            select(CalendarEvent).where(CalendarEvent.obligation_id == obligation_id)
        ).scalars().first()

        # Event should NOT exist: filing gone, closed, or nobody assigned.
        gone = (
            ob is None
            or ob.assignee_id is None
            or ob.status in (ObligationStatus.completed, ObligationStatus.not_applicable)
        )
        if gone:
            if mapping is not None:
                r = _request(
                    "DELETE", f"{_API}/calendars/{mapping.calendar_id}/events/{mapping.event_id}",
                    token=token,
                )
                if r.status_code not in (200, 204, 404, 410):
                    return f"Google Calendar delete failed: {r.status_code} {r.text[:200]}"
                db.delete(mapping)
                db.commit()
            return None

        payload = _event_payload(ob)
        if mapping is not None and mapping.calendar_id == cal:
            r = _request(
                "PATCH", f"{_API}/calendars/{cal}/events/{mapping.event_id}",
                token=token, json_body=payload,
            )
            if r.status_code == 200:
                db.commit()
                return None
            if r.status_code not in (404, 410):
                return f"Google Calendar update failed: {r.status_code} {r.text[:200]}"
            # Event vanished on Google's side — fall through and recreate.
            db.delete(mapping)
            mapping = None

        r = _request("POST", f"{_API}/calendars/{cal}/events", token=token, json_body=payload)
        if r.status_code != 200:
            return f"Google Calendar insert failed: {r.status_code} {r.text[:200]}"
        event_id = (r.json() or {}).get("id", "")
        if mapping is None:
            db.add(CalendarEvent(obligation_id=obligation_id, event_id=event_id, calendar_id=cal))
        else:
            mapping.event_id, mapping.calendar_id = event_id, cal
        db.commit()
        return None


def sync_obligation(obligation_id: int, *, sync: bool = False) -> Optional[str]:
    """Fire-and-forget sync for one obligation (daemon thread). Pass sync=True
    to run inline and get the failure reason back (used by the test button)."""
    if not is_configured():
        return "Google Calendar is not configured (set GOOGLE_CALENDAR_ID + the Gmail OAuth vars)."

    def _run() -> Optional[str]:
        try:
            reason = _sync(obligation_id)
            if reason:
                logger.warning("gcal sync obligation=%s: %s", obligation_id, reason)
            return reason
        except Exception as e:  # noqa: BLE001 — never break the caller
            logger.warning("gcal sync crashed for obligation=%s: %s", obligation_id, e)
            return f"{type(e).__name__}: {e}"

    if sync:
        return _run()
    threading.Thread(target=_run, daemon=True).start()
    return None


def create_test_event() -> tuple[bool, Optional[str]]:
    """Drop a throwaway event on the configured calendar (today) and delete it
    again — proves credentials + calendar id end to end."""
    from datetime import date

    from compliance_agent.email_service import _gmail_access_token

    if not is_configured():
        return False, "Set GOOGLE_CALENDAR_ID plus the Gmail OAuth env vars first."
    token = _gmail_access_token()
    if not token:
        return False, "Could not mint a Google access token — re-mint the refresh token WITH the calendar.events scope."
    cal = calendar_id()
    day = date.today().isoformat()
    r = _request(
        "POST", f"{_API}/calendars/{cal}/events", token=token,
        json_body={
            "summary": "Aspora Compliance — test event (safe to ignore)",
            "start": {"date": day}, "end": {"date": day},
        },
    )
    if r.status_code != 200:
        return False, f"Insert failed: {r.status_code} — {r.text[:300]}"
    event_id = (r.json() or {}).get("id", "")
    _request("DELETE", f"{_API}/calendars/{cal}/events/{event_id}", token=token)
    return True, None


__all__ = ["is_configured", "sync_obligation", "create_test_event", "calendar_id"]
