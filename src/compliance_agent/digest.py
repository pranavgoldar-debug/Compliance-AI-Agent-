"""Weekly admin digest — automated tracking summary for admins.

Deterministic (no LLM): a structured roll-up of what needs the admin's
attention, sent by email + Slack. Designed to run on a weekly cron:

    python -m compliance_agent.cli send-digest            # actually send
    python -m compliance_agent.cli send-digest --dry-run  # print only

Contents:
  - Overdue obligations (past due, still open)
  - Upcoming filings due within the next 7 days
  - Items waiting on admin sign-off (pending_review)

Goes to every active admin with email alerts on, plus a single Slack post
to the workspace channel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from compliance_agent import slack_service
from compliance_agent.api._helpers import today
from compliance_agent.db import (
    Obligation,
    ObligationStatus,
    Role,
    User,
    session_scope,
)
from compliance_agent.email_service import base_url, send_email, smtp_configured

_OPEN = (
    ObligationStatus.not_started,
    ObligationStatus.in_progress,
    ObligationStatus.pending_review,
)
_UPCOMING_DAYS = 7


@dataclass
class DigestRow:
    form: str
    entity: str
    due_date: str
    days: int
    assignee: str


@dataclass
class DigestSummary:
    overdue: list[DigestRow] = field(default_factory=list)
    upcoming: list[DigestRow] = field(default_factory=list)
    pending_review: list[DigestRow] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.overdue) + len(self.upcoming) + len(self.pending_review)


@dataclass
class DigestResult:
    sent_emails: int = 0
    slack_sent: bool = False
    summary: DigestSummary = field(default_factory=DigestSummary)


def _row(o: Obligation, day0) -> DigestRow:
    return DigestRow(
        form=o.rule.form_name if o.rule else "Compliance item",
        entity=o.entity.name if o.entity else "—",
        due_date=o.due_date.isoformat(),
        days=(o.due_date - day0).days,
        assignee=(o.assignee.full_name or o.assignee.email) if o.assignee else "Unassigned",
    )


def build_admin_digest(db: Session) -> DigestSummary:
    day0 = today()
    week_end = day0 + timedelta(days=_UPCOMING_DAYS)
    rows = (
        db.execute(
            select(Obligation)
            .where(Obligation.status.in_(_OPEN))
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
    s = DigestSummary()
    for o in rows:
        if o.due_date < day0:
            s.overdue.append(_row(o, day0))
        elif o.due_date <= week_end:
            s.upcoming.append(_row(o, day0))
        if o.status == ObligationStatus.pending_review:
            s.pending_review.append(_row(o, day0))
    return s


def _render(summary: DigestSummary) -> tuple[str, str, str, str]:
    subject = (
        f"Aspora weekly compliance digest — "
        f"{len(summary.overdue)} overdue, {len(summary.upcoming)} due this week"
    )

    def text_block(title: str, rows: list[DigestRow]) -> str:
        if not rows:
            return f"{title}: none\n"
        lines = [f"{title} ({len(rows)}):"]
        for r in rows:
            when = f"{abs(r.days)}d ago" if r.days < 0 else f"in {r.days}d"
            lines.append(f"  • {r.form} — {r.entity} — due {r.due_date} ({when}) — {r.assignee}")
        return "\n".join(lines) + "\n"

    text = "\n".join(
        [
            "Your weekly compliance roll-up:",
            "",
            text_block("OVERDUE", summary.overdue),
            text_block("DUE WITHIN 7 DAYS", summary.upcoming),
            text_block("AWAITING YOUR SIGN-OFF", summary.pending_review),
            f"Open the dashboard: {base_url().rstrip('/')}/",
        ]
    )

    def html_block(title: str, rows: list[DigestRow], color: str) -> str:
        if not rows:
            return f'<h3 style="color:{color};margin:16px 0 4px">{title}: none</h3>'
        items = "".join(
            f"<li><strong>{r.form}</strong> — {r.entity} — due {r.due_date} "
            f"({'%dd ago' % abs(r.days) if r.days < 0 else 'in %dd' % r.days}) — "
            f"<em>{r.assignee}</em></li>"
            for r in rows
        )
        return (
            f'<h3 style="color:{color};margin:16px 0 4px">{title} ({len(rows)})</h3>'
            f'<ul style="margin:0;padding-left:18px">{items}</ul>'
        )

    html = (
        '<div style="font-family:system-ui,sans-serif;font-size:14px;color:#222">'
        "<p>Your weekly compliance roll-up:</p>"
        + html_block("Overdue", summary.overdue, "#b91c1c")
        + html_block("Due within 7 days", summary.upcoming, "#b45309")
        + html_block("Awaiting your sign-off", summary.pending_review, "#7c3aed")
        + f'<p style="margin-top:16px"><a href="{base_url().rstrip("/")}/">Open the dashboard →</a></p>'
        + "</div>"
    )

    slack_text = (
        f":calendar: *Weekly compliance digest*\n"
        f"• Overdue: *{len(summary.overdue)}*\n"
        f"• Due within 7 days: *{len(summary.upcoming)}*\n"
        f"• Awaiting sign-off: *{len(summary.pending_review)}*"
    )
    return subject, text, html, slack_text


def send_admin_digest(*, dry_run: bool = False) -> DigestResult:
    """Build + send the weekly digest to every active admin. Idempotent in
    the sense that it's a snapshot — safe to run on any schedule."""
    with session_scope() as db:
        summary = build_admin_digest(db)
        subject, text, html, slack_text = _render(summary)

        admins = (
            db.execute(
                select(User).where(User.is_active.is_(True), User.role == Role.admin)
            )
            .scalars()
            .all()
        )

        result = DigestResult(summary=summary)
        if dry_run:
            return result

        if smtp_configured():
            for admin in admins:
                if not admin.notify_email:
                    continue
                try:
                    if send_email(
                        to=admin.email,
                        subject=subject,
                        body_text=text,
                        body_html=html,
                    ):
                        result.sent_emails += 1
                except Exception:  # noqa: BLE001
                    pass

        if slack_service.is_configured(db):
            result.slack_sent = bool(slack_service.post(slack_text, sync=True))

        return result
