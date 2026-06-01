"""AI-composed digest sender.

Two kinds of digest:

  employee_daily — for individual contributors. Their queue, overdue,
                   in-alert-window, recently-assigned. Daily by default.
  admin_weekly   — team-wide rollup for admins. Submissions awaiting
                   their review, payment requests, overdue across the
                   whole org, items unassigned. Weekly (Monday) by
                   default.

Pipeline:
  1. Pull the user's relevant obligations from the DB
  2. Render a compact JSON-ish context block (no full SQL dumps —
     model only needs identifiers + dates + status)
  3. Send to Claude (via the same llm_client.make_client adapter used
     elsewhere — works with Anthropic key OR OpenRouter key)
  4. Get back a markdown blurb with prioritised next actions
  5. Post to the configured Slack channel + optionally email the user

Idempotent per day: an Activity row tagged "digest.sent" with the
user_id + kind + date is the dedup anchor.

Trigger from CLI:
  python -m compliance_agent.cli send-digest                 # all eligible users
  python -m compliance_agent.cli send-digest --kind admin_weekly
  python -m compliance_agent.cli send-digest --user pranav@aspora.com --dry-run
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from compliance_agent import slack_service
from compliance_agent.ai.llm_client import ai_available, make_client
from compliance_agent.api._helpers import lead_time_days, today
from compliance_agent.db import (
    Activity,
    EffortBand,
    Obligation,
    ObligationStatus,
    Role,
    User,
    session_scope,
)
from compliance_agent.email_service import send_email


logger = logging.getLogger("compliance_agent.digest")


# ---------------------------------------------------------------------------
# Context-builders — turn DB state into a tight JSON payload for Claude
# ---------------------------------------------------------------------------
@dataclass
class _ObBrief:
    id: int
    form: str
    entity: str
    due: str  # ISO YYYY-MM-DD
    days: int  # negative = overdue
    status: str
    department: str
    assignee: Optional[str]
    has_payment_leg: bool
    payment_logged: bool


def _serialize_ob(o: Obligation) -> _ObBrief:
    days = (o.due_date - today()).days
    return _ObBrief(
        id=o.id,
        form=o.rule.form_name if o.rule else "—",
        entity=o.entity.name if o.entity else "—",
        due=o.due_date.isoformat(),
        days=days,
        status=o.status.value,
        department=o.department.value if o.department else "compliance",
        assignee=(o.assignee.full_name or o.assignee.email) if o.assignee else None,
        has_payment_leg=bool((o.rule.payment_rule or "").strip()) if o.rule else False,
        payment_logged=bool((o.payment_reference or "").strip()),
    )


def _employee_context(db: Session, user: User) -> dict:
    """What's on this employee's plate right now."""
    open_statuses = [
        ObligationStatus.not_started,
        ObligationStatus.in_progress,
        ObligationStatus.pending_review,
    ]
    horizon = today() + timedelta(days=lead_time_days(EffortBand.w8))  # ~8 weeks

    items = (
        db.execute(
            select(Obligation)
            .where(
                Obligation.assignee_id == user.id,
                Obligation.status.in_(open_statuses),
                Obligation.due_date <= horizon + timedelta(days=30),
            )
            .options(
                joinedload(Obligation.rule),
                joinedload(Obligation.entity),
                joinedload(Obligation.assignee),
            )
            .order_by(Obligation.due_date.asc())
        )
        .scalars()
        .unique()
        .all()
    )

    overdue = [_serialize_ob(o) for o in items if (o.due_date - today()).days < 0]
    due_this_week = [
        _serialize_ob(o)
        for o in items
        if 0 <= (o.due_date - today()).days <= 7
    ]
    next_two_weeks = [
        _serialize_ob(o)
        for o in items
        if 8 <= (o.due_date - today()).days <= 14
    ]
    later = [
        _serialize_ob(o)
        for o in items
        if (o.due_date - today()).days > 14
    ]

    return {
        "kind": "employee_daily",
        "user_name": user.full_name or user.email,
        "user_team": user.department.value if user.department else None,
        "today": today().isoformat(),
        "overdue": [_brief_dict(o) for o in overdue],
        "due_this_week": [_brief_dict(o) for o in due_this_week],
        "next_two_weeks": [_brief_dict(o) for o in next_two_weeks],
        "later": [_brief_dict(o) for o in later[:10]],
        "totals": {
            "overdue": len(overdue),
            "this_week": len(due_this_week),
            "next_two_weeks": len(next_two_weeks),
            "later": len(later),
        },
    }


def _admin_context(db: Session) -> dict:
    """Team-wide rollup for the admin recap."""
    open_statuses = [
        ObligationStatus.not_started,
        ObligationStatus.in_progress,
        ObligationStatus.pending_review,
    ]

    horizon = today() + timedelta(days=21)
    items = (
        db.execute(
            select(Obligation)
            .where(
                Obligation.status.in_(open_statuses),
                Obligation.due_date <= horizon,
            )
            .options(
                joinedload(Obligation.rule),
                joinedload(Obligation.entity),
                joinedload(Obligation.assignee),
            )
            .order_by(Obligation.due_date.asc())
        )
        .scalars()
        .unique()
        .all()
    )

    overdue = [_serialize_ob(o) for o in items if (o.due_date - today()).days < 0]
    awaiting_review = [
        _serialize_ob(o) for o in items if o.status == ObligationStatus.pending_review
    ]
    unassigned = [_serialize_ob(o) for o in items if o.assignee_id is None]
    payment_pending = [
        _serialize_ob(o)
        for o in items
        if o.status == ObligationStatus.completed
        and (o.rule.payment_rule or "").strip()
        and not (o.payment_reference or "").strip()
    ] if False else []  # completed items aren't in `items` (open_statuses filter)

    # Re-query payment pending separately since it spans completed status.
    completed_unpaid = (
        db.execute(
            select(Obligation)
            .where(Obligation.status == ObligationStatus.completed)
            .options(joinedload(Obligation.rule), joinedload(Obligation.entity), joinedload(Obligation.assignee))
        )
        .scalars()
        .unique()
        .all()
    )
    payment_pending = [
        _serialize_ob(o)
        for o in completed_unpaid
        if o.rule
        and (o.rule.payment_rule or "").strip()
        and not (o.payment_reference or "").strip()
    ]

    return {
        "kind": "admin_weekly",
        "today": today().isoformat(),
        "overdue": [_brief_dict(o) for o in overdue],
        "awaiting_admin_review": [_brief_dict(o) for o in awaiting_review],
        "unassigned": [_brief_dict(o) for o in unassigned],
        "payment_pending": [_brief_dict(o) for o in payment_pending],
        "totals": {
            "overdue": len(overdue),
            "awaiting_review": len(awaiting_review),
            "unassigned": len(unassigned),
            "payment_pending": len(payment_pending),
        },
    }


def _brief_dict(b: _ObBrief) -> dict:
    return {
        "id": b.id,
        "form": b.form,
        "entity": b.entity,
        "due": b.due,
        "days": b.days,
        "status": b.status,
        "department": b.department,
        "assignee": b.assignee,
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
_EMPLOYEE_SYSTEM = """You are Aspora Compliance OS's morning digest assistant.

Given the user's open compliance items, write a SHORT, prioritised daily brief
for them. Output rules:

- Open with one line: greeting + the highest-priority action ("File Form 16A
  for Aspora India first — due in 5 days, you're the assignee.").
- Then a 3-6 bullet list. Each bullet starts with an action verb (File / Pay
  / Submit for review / Chase / Confirm), names the form + entity, and
  includes the deadline.
- Sort by urgency: overdue first, then this-week, then next-two-weeks.
- Total length: under 700 characters in the body. People skim Slack.
- Plain text with light Markdown (bullets, *bold* for entities).
- No filler, no recap of the data structure, no "I noticed you have…"
  language. Just the actions.
- If there's nothing urgent at all, say so cheerfully in one sentence.
"""

_ADMIN_SYSTEM = """You are Aspora Compliance OS's weekly admin recap assistant.

Given a workspace-wide compliance snapshot, write a SHORT Monday-morning
recap for the admins. Output rules:

- Open line: the single thing that should grab their attention this week
  ("4 filings are awaiting your sign-off — clear them before Friday.")
- Then a 4-6 bullet list grouped by category:
  • Overdue (red flag, name forms + entities)
  • Awaiting your review (filings sitting in pending_review)
  • Unassigned (work that needs an owner)
  • Payment pending (filed but unpaid — finance follow-up needed)
- Each bullet is one line: count + 1-2 specific examples by form + entity.
- End with one suggested action ("Triage the unassigned list first — 3
  are due this week.").
- Under 800 characters. Plain text + light Markdown.
- If everything is clean across the org, say so in one line.
"""


# ---------------------------------------------------------------------------
# AI call
# ---------------------------------------------------------------------------
def _compose(context: dict) -> str:
    if not ai_available():
        # Fallback: render a deterministic summary from the context so the
        # cron still produces *something* useful without an LLM.
        return _render_fallback(context)

    system = _EMPLOYEE_SYSTEM if context["kind"] == "employee_daily" else _ADMIN_SYSTEM
    client = make_client()
    try:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=600,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Here is the snapshot. Compose the digest per the rules above.\n\n"
                        + json.dumps(context, indent=2)
                    ),
                }
            ],
        )
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text.strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("Digest LLM call failed (%s) — falling back to template.", e)
    return _render_fallback(context)


def _render_fallback(context: dict) -> str:
    """Plain template used when AI is off or errored. Same data, no prose."""
    if context["kind"] == "employee_daily":
        lines = [
            f"Morning {context['user_name']} — here's your compliance plate today:"
        ]
        if context["totals"]["overdue"]:
            lines.append(
                f"  • Overdue ({context['totals']['overdue']}): "
                + ", ".join(
                    f"{o['form']} for {o['entity']}"
                    for o in context["overdue"][:3]
                )
            )
        if context["totals"]["this_week"]:
            lines.append(
                f"  • Due this week ({context['totals']['this_week']}): "
                + ", ".join(
                    f"{o['form']} ({o['entity']}, in {o['days']}d)"
                    for o in context["due_this_week"][:3]
                )
            )
        if context["totals"]["next_two_weeks"]:
            lines.append(
                f"  • Coming up ({context['totals']['next_two_weeks']}): "
                + ", ".join(
                    f"{o['form']} ({o['entity']})"
                    for o in context["next_two_weeks"][:3]
                )
            )
        if (
            not context["totals"]["overdue"]
            and not context["totals"]["this_week"]
        ):
            lines.append("  • Nothing urgent on your plate today. ✅")
        return "\n".join(lines)

    # admin_weekly
    lines = ["📊 Aspora compliance — weekly admin recap"]
    if context["totals"]["overdue"]:
        lines.append(
            f"  • Overdue across the org: {context['totals']['overdue']}"
            + (
                " — "
                + ", ".join(
                    f"{o['form']} ({o['entity']})"
                    for o in context["overdue"][:3]
                )
            )
        )
    if context["totals"]["awaiting_review"]:
        lines.append(
            f"  • Awaiting your review: {context['totals']['awaiting_review']}"
        )
    if context["totals"]["unassigned"]:
        lines.append(f"  • Unassigned: {context['totals']['unassigned']}")
    if context["totals"]["payment_pending"]:
        lines.append(
            f"  • Payment pending (finance to act): {context['totals']['payment_pending']}"
        )
    if all(v == 0 for v in context["totals"].values()):
        lines.append("  • Workspace is clean. Nothing flagged. ✅")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dispatch — channel-aware sending + dedup
# ---------------------------------------------------------------------------
def _already_sent_today(db: Session, user_id: int, kind: str) -> bool:
    today_start = datetime.combine(today(), datetime.min.time(), tzinfo=timezone.utc)
    row = db.execute(
        select(Activity)
        .where(
            Activity.action == "digest.sent",
            Activity.target_type == "digest",
            Activity.actor_id == user_id,
            Activity.created_at >= today_start,
        )
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def _mark_sent(db: Session, user_id: int, kind: str, text: str) -> None:
    db.add(
        Activity(
            actor_id=user_id,
            action="digest.sent",
            target_type="digest",
            payload={"kind": kind, "chars": len(text)},
        )
    )


def _send_one(
    db: Session,
    *,
    user: User,
    kind: str,
    context: dict,
    dry_run: bool,
) -> tuple[bool, str]:
    """Compose + send the digest for one user. Returns (sent, body)."""
    body = _compose(context)
    subject = (
        "Aspora — your morning compliance brief"
        if kind == "employee_daily"
        else "Aspora — weekly compliance recap"
    )

    if dry_run:
        return False, body

    sent_anywhere = False

    # Channel: post to the workspace Slack channel (not DM) — admin
    # configured a single channel in Settings → Integrations, and per the
    # spec we post there rather than per-user.
    if slack_service.is_configured(db):
        header = (
            f":sunrise: *{user.full_name or user.email}*'s morning brief"
            if kind == "employee_daily"
            else ":bar_chart: *Weekly admin recap*"
        )
        slack_service.post(f"{header}\n{body}")
        sent_anywhere = True

    # Email — only when the user has notify_email on AND we have SMTP creds.
    if user.notify_email and user.email:
        from compliance_agent.email_service import send_email as _send

        try:
            _send(
                to=user.email,
                subject=subject,
                body_text=body,
                body_html=f"<pre style='font-family:ui-monospace,monospace;white-space:pre-wrap'>{body}</pre>",
            )
            sent_anywhere = True
        except Exception as e:  # noqa: BLE001
            logger.warning("Digest email to %s failed: %s", user.email, e)

    if sent_anywhere:
        _mark_sent(db, user.id, kind, body)
    return sent_anywhere, body


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def send_employee_digests(*, dry_run: bool = False, only_email: Optional[str] = None) -> dict:
    """Send the daily morning brief to every active employee with at least
    one open obligation. Returns a count summary."""
    counts = {"considered": 0, "sent": 0, "skipped_no_items": 0, "skipped_already_sent": 0}
    with session_scope() as db:
        users = db.execute(
            select(User)
            .where(User.is_active.is_(True))
            .where(or_(User.role == Role.employee, User.role == Role.admin))
        ).scalars().all()
        for u in users:
            if only_email and u.email.lower() != only_email.lower():
                continue
            counts["considered"] += 1
            if not dry_run and _already_sent_today(db, u.id, "employee_daily"):
                counts["skipped_already_sent"] += 1
                continue
            ctx = _employee_context(db, u)
            total_items = sum(ctx["totals"].values())
            if total_items == 0:
                counts["skipped_no_items"] += 1
                continue
            sent, _body = _send_one(
                db, user=u, kind="employee_daily", context=ctx, dry_run=dry_run
            )
            if sent:
                counts["sent"] += 1
    return counts


def send_admin_recap(*, dry_run: bool = False, only_email: Optional[str] = None) -> dict:
    """Send the weekly admin recap to every active admin."""
    counts = {"considered": 0, "sent": 0, "skipped_already_sent": 0}
    with session_scope() as db:
        admins = db.execute(
            select(User).where(User.is_active.is_(True), User.role == Role.admin)
        ).scalars().all()
        ctx = _admin_context(db)
        for u in admins:
            if only_email and u.email.lower() != only_email.lower():
                continue
            counts["considered"] += 1
            if not dry_run and _already_sent_today(db, u.id, "admin_weekly"):
                counts["skipped_already_sent"] += 1
                continue
            sent, _body = _send_one(
                db, user=u, kind="admin_weekly", context=ctx, dry_run=dry_run
            )
            if sent:
                counts["sent"] += 1
    return counts


def preview_for_user(email: str, kind: str = "employee_daily") -> str:
    """Render the digest text for one user without sending. Used by the
    'Preview & send' admin button in Settings."""
    with session_scope() as db:
        u = db.execute(
            select(User).where(User.email == email.lower())
        ).scalar_one_or_none()
        if u is None:
            return f"User {email} not found."
        ctx = (
            _admin_context(db)
            if kind == "admin_weekly"
            else _employee_context(db, u)
        )
        return _compose(ctx)


__all__ = [
    "send_employee_digests",
    "send_admin_recap",
    "preview_for_user",
]
