"""Branded HTML email templates — assignment + deadline alert.

Both render the Aspora Compliance OS layouts supplied by the design mocks:
masthead (ASPORA. COMPLIANCE OS), bold headline, a grey detail card, an
amber escalation / grey "why you" note, navy filled + outlined buttons and
a small footer link row. All styles are inline (email clients strip
<style> blocks); each renderer returns (subject, text_body, html_body) so
plain-text clients still get a readable message.
"""
from __future__ import annotations

from datetime import date
from typing import Optional


NAVY = "#16325c"
GOLD = "#d69e2e"
TEXT = "#1a202c"
MUTED = "#64748b"
CARD_BG = "#f7f8fa"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _fmt_long(d: Optional[date]) -> str:
    return d.strftime("%A, %d %B %Y") if d else "—"


def _shell(content: str) -> str:
    """Masthead + bordered page wrapper shared by both templates."""
    return (
        f'<div style="background:#ffffff;padding:24px 8px;font-family:{FONT};color:{TEXT}">'
        f'<div style="max-width:680px;margin:0 auto">'
        f'<div style="padding:14px 4px;border-bottom:3px solid {NAVY}">'
        f'<span style="font-size:22px;font-weight:800;color:{NAVY};letter-spacing:0.5px">ASPORA'
        f'<span style="color:{GOLD}">.</span></span>'
        f'<span style="font-size:11px;font-weight:600;color:{NAVY};letter-spacing:3px;margin-left:10px">COMPLIANCE OS</span>'
        f"</div>"
        f'<div style="padding:22px 4px 8px">{content}</div>'
        f"</div></div>"
    )


def _row(label: str, value: str, bold: bool = False) -> str:
    weight = "700" if bold else "400"
    return (
        f'<tr><td style="padding:7px 16px 7px 0;font-size:13px;color:{MUTED};'
        f'vertical-align:top;white-space:nowrap">{label}</td>'
        f'<td style="padding:7px 0;font-size:13px;color:{TEXT};font-weight:{weight}">{value}</td></tr>'
    )


def _button(label: str, url: str) -> str:
    return (
        f'<div style="text-align:center;margin:26px 0 14px">'
        f'<a href="{url}" style="display:inline-block;background:{NAVY};color:#ffffff;'
        f'font-size:14px;font-weight:600;text-decoration:none;padding:12px 26px;border-radius:6px">'
        f"{label}</a></div>"
    )


def _footer_links(parts: list[tuple[str, str, str]]) -> str:
    """parts: (lead-in text, link label, href)."""
    bits = " &nbsp;·&nbsp; ".join(
        f'{lead} <a href="{href}" style="color:{NAVY}">{label}</a>' for lead, label, href in parts
    )
    return f'<div style="text-align:center;font-size:12px;color:{MUTED};margin-bottom:8px">{bits}</div>'


# ---------------------------------------------------------------------------
# Assignment — "X assigned you a task"
# ---------------------------------------------------------------------------
def assignment_email(
    *,
    assignee_name: str,
    assigned_by_name: str,
    assigned_by_role: str,
    assigned_by_email: str,
    task_title: str,
    task_id: str,
    task_description: str,
    linked_obligation_name: str,
    jurisdiction: str,
    form_code: str,
    entity_name: str,
    evidence_required: str,
    due_date: Optional[date],
    assigned_at: Optional[date],
    open_url: str,
) -> tuple[str, str, str]:
    subject = f"[Aspora] {assigned_by_name} assigned you: {task_title}"
    due_long = _fmt_long(due_date)
    assigned_str = _fmt_long(assigned_at)

    text = (
        f"Hi {assignee_name},\n\n"
        f"{assigned_by_name} assigned you a task\n"
        f"Due {due_long} · assigned {assigned_str} by {assigned_by_name} ({assigned_by_role})\n\n"
        f"{task_title}  ({task_id})\n"
        f"{task_description}\n\n"
        f"Linked obligation: {linked_obligation_name}\n"
        f"Canonical key · Entity: {jurisdiction} · {form_code} · {entity_name}\n"
        f"Evidence required: {evidence_required}\n\n"
        f"Open it: {open_url}\n"
        f"Can't take this on? Reply to {assigned_by_email}.\n"
    )


    content = (
        f'<p style="font-size:14px;margin:0 0 6px">Hi {assignee_name},</p>'
        f'<h1 style="font-size:24px;margin:0 0 8px;color:{TEXT}">'
        f"{assigned_by_name} assigned you a task</h1>"
        f'<p style="font-size:13px;color:{MUTED};margin:0 0 20px">'
        f"Due <strong style=\"color:{TEXT}\">{due_long}</strong> · assigned {assigned_str} "
        f"by {assigned_by_name} ({assigned_by_role})</p>"
        # Task card with gold accent edge
        f'<div style="background:{CARD_BG};border-left:4px solid {GOLD};border-radius:8px;'
        f'padding:18px 20px;margin-bottom:18px">'
        f'<div style="font-size:16px;font-weight:700">{task_title}</div>'
        f'<div style="font-size:11px;color:{MUTED};font-family:monospace;margin:2px 0 10px">{task_id}</div>'
        f'<div style="font-size:13px;margin-bottom:14px">{task_description}</div>'
        f'<div style="border-top:1px dashed #d7dbe2;padding-top:12px">'
        f'<table style="border-collapse:collapse">'
        + _row("Linked obligation", linked_obligation_name, bold=True)
        + _row(
            "Canonical key · Entity",
            f'<span style="font-family:monospace">{jurisdiction}</span> · '
            f'<span style="font-family:monospace">{form_code}</span> · {entity_name}',
        )
        + _row("Evidence required", evidence_required)
        + "</table></div></div>"
        + _button("View details", open_url)
        + _footer_links(
            [
                ("Can't take this on?", "Decline &amp; suggest owner", open_url),
                ("Need context?", f"Ask {assigned_by_name}", f"mailto:{assigned_by_email}"),
            ]
        )
    )
    return subject, text, _shell(content)


# ---------------------------------------------------------------------------
# Deadline alert — "X is due in N days"
# ---------------------------------------------------------------------------
def deadline_alert_email(
    *,
    owner_name: str,
    obligation_name: str,
    days_remaining: int,
    due_date: Optional[date],
    regulator_name: str,
    jurisdiction: str,
    form_code: str,
    entity_name: str,
    entity_ref: str,
    obligation_type: str,
    frequency: str,
    period_covered: str,
    status: str,
    last_action: str,
    last_action_date: str,
    open_url: str,
    escalation_contact_name: str = "your manager",
) -> tuple[str, str, str]:
    subject = f"[Aspora] {obligation_name} due in {days_remaining}d — {entity_name}"
    due_long = _fmt_long(due_date)

    text = (
        f"Hi {owner_name},\n\n"
        f"{obligation_name} is due in {days_remaining} days\n"
        f"Filing deadline: {due_long} · Regulator: {regulator_name}\n\n"
        f"Canonical key:   {jurisdiction} · {form_code}\n"
        f"Entity:          {entity_name} ({entity_ref})\n"
        f"Type · Frequency: {obligation_type} · {frequency}\n"
        f"Period covered:  {period_covered}\n"
        f"Current status:  {status} — last action: {last_action} on {last_action_date}\n\n"
        f"Escalation: if this remains unfiled at T-7, {escalation_contact_name} is copied "
        "automatically; at T-1 it moves to the daily compliance stand-up; "
        "overdue items page compliance-leads.\n\n"
        f"Open it: {open_url}\n"
    )

    content = (
        f'<p style="font-size:14px;margin:0 0 6px">Hi {owner_name},</p>'
        f'<h1 style="font-size:24px;margin:0 0 8px;color:{TEXT}">'
        f"{obligation_name} is due in {days_remaining} days</h1>"
        f'<p style="font-size:13px;color:{MUTED};margin:0 0 20px">'
        f'Filing deadline: <strong style="color:{TEXT}">{due_long}</strong> · '
        f"Regulator: {regulator_name}</p>"
        # Detail card
        f'<div style="background:{CARD_BG};border-radius:8px;padding:14px 20px;margin-bottom:18px">'
        f'<table style="border-collapse:collapse">'
        + _row(
            "Canonical key",
            f'<span style="font-family:monospace">{jurisdiction}</span> · '
            f'<span style="font-family:monospace">{form_code}</span>',
        )
        + _row("Entity", f"<strong>{entity_name}</strong> ({entity_ref})")
        + _row("Obligation type · Frequency", f"{obligation_type} · {frequency}")
        + _row("Period covered", period_covered)
        + _row("Current status", f"<strong>{status}</strong> · last action: {last_action} on {last_action_date}")
        + "</table></div>"
        # Escalation note
        f'<div style="background:#fdf3e3;border:1px solid #f0d49b;border-radius:8px;'
        f'padding:12px 16px;font-size:12.5px;color:#7a5a17;margin-bottom:6px">'
        f"<strong>Escalation:</strong> if this remains unfiled at <strong>T-7</strong>, "
        f"{escalation_contact_name} is copied automatically; at <strong>T-1</strong> it moves to the "
        f"daily compliance stand-up; <strong>overdue</strong> items page compliance-leads."
        f"</div>"
        + _button("Open in Compliance OS", open_url)
        + _footer_links(
            [
                ("Already handled outside the system?", "Log the filing", open_url),
                ("Wrong owner?", "Reassign", open_url),
            ]
        )
    )
    return subject, text, _shell(content)


__all__ = ["assignment_email", "deadline_alert_email"]
