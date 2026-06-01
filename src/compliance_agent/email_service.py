"""Outbound email — Resend HTTP API (recommended) or SMTP, with a console
fallback for local dev.

IMPORTANT: Render (and many PaaS) block outbound SMTP ports (25/465/587),
so raw smtp.gmail.com sends fail with "Network is unreachable". On those
hosts use a transactional email HTTP API instead — set RESEND_API_KEY and
we'll send over HTTPS (port 443), which isn't blocked.

Config (env):
  RESEND_API_KEY       — Resend API key (re_...). When set, used first.
  RESEND_FROM          — From address for Resend (defaults to SMTP_FROM).
                         Must be on a domain verified in Resend, or
                         onboarding@resend.dev for testing to your own inbox.
  SMTP_HOST            — e.g. smtp.gmail.com (only works where SMTP isn't blocked)
  SMTP_PORT            — default 587
  SMTP_USER            — SMTP username
  SMTP_PASSWORD        — SMTP password
  SMTP_FROM            — From address (defaults to SMTP_USER)
  SMTP_TLS             — "1" to enable STARTTLS (default), "0" to disable
  COMPLIANCE_BASE_URL  — public base URL for the app (e.g. https://...onrender.com).

When neither Resend nor SMTP is configured, OR sending fails, we fall back
to logging the message to the server console. We never raise to the caller.
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
    """True when we have *any* usable email backend (Resend or SMTP). Kept
    under the old name so existing call sites ('can we email?') still work."""
    return bool(os.environ.get("RESEND_API_KEY") or os.environ.get("SMTP_HOST"))


def _send_via_resend(api_key: str, *, to: str, subject: str, text: str, html: Optional[str]) -> bool:
    """Send through Resend's HTTPS API. Returns True on delivery."""
    from_addr = (
        os.environ.get("RESEND_FROM")
        or os.environ.get("SMTP_FROM")
        or "Aspora Compliance <onboarding@resend.dev>"
    )
    payload: dict = {"from": from_addr, "to": [to], "subject": subject, "text": text}
    if html:
        payload["html"] = html
    try:
        import httpx

        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=15.0,
        )
        if r.status_code in (200, 201):
            logger.info("Sent email via Resend to %s — subject=%r", to, subject)
            return True
        logger.warning("Resend send failed: status=%s body=%r", r.status_code, r.text[:300])
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("Resend send crashed: %s", e)
        return False


def send_email(*, to: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
    """Best-effort send. Returns True if delivered, False if we fell back
    to console-only. Never raises. Prefers Resend (HTTPS) over SMTP."""
    resend_key = os.environ.get("RESEND_API_KEY")
    if resend_key and _send_via_resend(
        resend_key, to=to, subject=subject, text=body_text, html=body_html
    ):
        return True

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
