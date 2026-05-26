"""Outbound email — SMTP with a console fallback for local dev.

Config (env):
  SMTP_HOST            — e.g. smtp.sendgrid.net
  SMTP_PORT            — default 587
  SMTP_USER            — SMTP username
  SMTP_PASSWORD        — SMTP password
  SMTP_FROM            — From address (defaults to SMTP_USER)
  SMTP_TLS             — "1" to enable STARTTLS (default), "0" to disable
  COMPLIANCE_BASE_URL  — public base URL for the app (e.g. https://aspora-compliance.onrender.com).
                         Used to build reset-link URLs. Defaults to "http://127.0.0.1:8000".

When SMTP_HOST is unset OR sending fails, we fall back to logging the
message body (with the reset link) to the server console so devs can grab
the link without setting up a mailer. We never raise to the caller — the
forgot-password endpoint always succeeds the same way regardless of whether
delivery actually worked, to avoid leaking which emails exist.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional


logger = logging.getLogger("compliance_agent.email")


def base_url() -> str:
    return os.environ.get("COMPLIANCE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def send_email(*, to: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
    """Best-effort send. Returns True if delivered, False if we fell back
    to console-only. Never raises."""
    host = os.environ.get("SMTP_HOST")
    if not host:
        _log_to_console(to, subject, body_text)
        return False

    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    from_addr = os.environ.get("SMTP_FROM") or user or "no-reply@aspora.com"
    use_tls = os.environ.get("SMTP_TLS", "1") == "1"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.ehlo()
            if use_tls:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        logger.info("Sent email to %s — subject=%r", to, subject)
        return True
    except Exception as e:
        logger.warning("SMTP send failed (%s) — falling back to console log.", e)
        _log_to_console(to, subject, body_text)
        return False


def _log_to_console(to: str, subject: str, body: str) -> None:
    logger.warning(
        "=" * 72 + "\n"
        "EMAIL (console fallback — SMTP not configured or send failed):\n"
        f"  To:      {to}\n"
        f"  Subject: {subject}\n"
        "  Body:\n"
        + "\n".join("    " + line for line in body.splitlines())
        + "\n" + "=" * 72,
    )


# ---------------------------------------------------------------------------
# Password reset template
# ---------------------------------------------------------------------------
def password_reset_email(*, full_name: str, reset_url: str, ttl_hours: int = 1) -> tuple[str, str, str]:
    """Returns (subject, text_body, html_body) for the reset message."""
    name = (full_name or "").strip() or "there"
    subject = "Reset your Aspora Compliance OS password"
    text = (
        f"Hi {name},\n\n"
        "Someone (hopefully you) asked to reset your password for Aspora Compliance OS.\n\n"
        "Open this link to set a new password — it expires in "
        f"{ttl_hours} hour{'s' if ttl_hours != 1 else ''}:\n\n"
        f"  {reset_url}\n\n"
        "If you didn't request this, you can ignore the email — your current password\n"
        "stays valid.\n\n"
        "— Aspora Compliance OS"
    )
    html = (
        f"<p>Hi {name},</p>"
        "<p>Someone (hopefully you) asked to reset your password for Aspora Compliance OS.</p>"
        "<p>"
        f'<a href="{reset_url}" style="display:inline-block;padding:10px 16px;'
        'background:#7C3AED;color:white;text-decoration:none;border-radius:6px;font-weight:600">'
        "Set a new password</a></p>"
        f'<p style="color:#666;font-size:12px">Link expires in {ttl_hours} hour{"s" if ttl_hours != 1 else ""}. '
        "If you didn't request this, ignore the email — your current password stays valid.</p>"
        '<p style="color:#999;font-size:11px">— Aspora Compliance OS</p>'
    )
    return subject, text, html
