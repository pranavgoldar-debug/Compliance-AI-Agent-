"""Outbound email — Resend HTTP API (recommended) or SMTP, with a console
fallback for local dev.

IMPORTANT: Render (and many PaaS) block outbound SMTP ports (25/465/587),
so raw smtp.gmail.com sends fail with "Network is unreachable". On those
hosts use a transactional email HTTP API instead — set RESEND_API_KEY and
we'll send over HTTPS (port 443), which isn't blocked.

Config (env):
  GMAIL_CLIENT_ID      — Google OAuth client id. When the Gmail trio is set,
  GMAIL_CLIENT_SECRET    we send through Gmail's HTTPS API (gmail.send scope)
  GMAIL_REFRESH_TOKEN    over port 443 — works on Render, no third party.
  GMAIL_SENDER         — From address (your Gmail / Workspace, e.g. you@aspora.com).
  RESEND_API_KEY       — Resend API key (re_...). Used next when set.
  RESEND_FROM          — From for Resend. Needs a domain verified in Resend
                         to email anyone; onboarding@resend.dev only reaches
                         your own Resend account inbox.
  BREVO_API_KEY        — Brevo (Sendinblue) key (xkeysib-...). Used next.
                         Brevo lets you verify a SINGLE sender email (click a
                         link, no DNS) and then email anyone — fastest path.
  BREVO_FROM           — Verified Brevo sender email (e.g. compliance@aspora.com).
  BREVO_FROM_NAME      — Display name for Brevo sends (default "Aspora Compliance").
  SMTP_HOST            — e.g. smtp.gmail.com (blocked on Render; local/self-host only)
  SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM / SMTP_TLS
  COMPLIANCE_BASE_URL  — public base URL for the app (e.g. https://...onrender.com).

Send order: Gmail API → Resend → Brevo → SMTP → console fallback. Never raises.
"""
from __future__ import annotations

import base64
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional


logger = logging.getLogger("compliance_agent.email")


def base_url() -> str:
    return os.environ.get("COMPLIANCE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _gmail_configured() -> bool:
    return bool(
        os.environ.get("GMAIL_CLIENT_ID")
        and os.environ.get("GMAIL_CLIENT_SECRET")
        and os.environ.get("GMAIL_REFRESH_TOKEN")
    )


def smtp_configured() -> bool:
    """True when we have *any* usable email backend. Kept under the old name
    so existing call sites ('can we email?') still work."""
    return bool(
        _gmail_configured()
        or os.environ.get("RESEND_API_KEY")
        or os.environ.get("BREVO_API_KEY")
        or os.environ.get("SMTP_HOST")
    )


def _build_mime(*, sender: str, to: str, subject: str, text: str, html: Optional[str]) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def _gmail_access_token() -> Optional[str]:
    """Exchange the long-lived refresh token for a short-lived access token."""
    try:
        import httpx

        r = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": os.environ["GMAIL_CLIENT_ID"],
                "client_secret": os.environ["GMAIL_CLIENT_SECRET"],
                "refresh_token": os.environ["GMAIL_REFRESH_TOKEN"],
                "grant_type": "refresh_token",
            },
            timeout=15.0,
        )
        if r.status_code == 200:
            return r.json().get("access_token")
        logger.warning("Gmail token refresh failed: status=%s body=%r", r.status_code, r.text[:300])
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("Gmail token refresh crashed: %s", e)
        return None


def _send_via_gmail_api(*, to: str, subject: str, text: str, html: Optional[str]) -> bool:
    """Send through the Gmail HTTPS API (gmail.send scope). Uses the configured
    refresh token to mint an access token, then posts the raw MIME message.
    Works on hosts that block SMTP (e.g. Render). Returns True on delivery."""
    sender = (
        os.environ.get("GMAIL_SENDER")
        or os.environ.get("SMTP_FROM")
        or os.environ.get("SMTP_USER")
        or "me"
    )
    token = _gmail_access_token()
    if not token:
        return False
    try:
        import httpx

        msg = _build_mime(sender=sender, to=to, subject=subject, text=text, html=html)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        r = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"raw": raw},
            timeout=15.0,
        )
        if r.status_code in (200, 201):
            logger.info("Sent email via Gmail API to %s — subject=%r", to, subject)
            return True
        logger.warning("Gmail API send failed: status=%s body=%r", r.status_code, r.text[:300])
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("Gmail API send crashed: %s", e)
        return False


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


def _send_via_brevo(api_key: str, *, to: str, subject: str, text: str, html: Optional[str]) -> bool:
    """Send through Brevo's HTTPS API. Returns True on delivery. The sender
    email must be a verified sender (or verified domain) in the Brevo account."""
    sender_email = (
        os.environ.get("BREVO_FROM")
        or os.environ.get("SMTP_FROM")
        or os.environ.get("SMTP_USER")
        or "no-reply@aspora.com"
    )
    sender_name = os.environ.get("BREVO_FROM_NAME", "Aspora Compliance")
    payload: dict = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": text,
    }
    if html:
        payload["htmlContent"] = html
    try:
        import httpx

        r = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": api_key,
                "accept": "application/json",
                "content-type": "application/json",
            },
            json=payload,
            timeout=15.0,
        )
        if r.status_code in (200, 201):
            logger.info("Sent email via Brevo to %s — subject=%r", to, subject)
            return True
        logger.warning("Brevo send failed: status=%s body=%r", r.status_code, r.text[:300])
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("Brevo send crashed: %s", e)
        return False


def send_email(*, to: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
    """Best-effort send. Returns True if delivered, False if we fell back
    to console-only. Never raises. Prefers HTTPS APIs (Gmail, Resend, Brevo)
    over SMTP, since hosts like Render block outbound SMTP ports."""
    if _gmail_configured() and _send_via_gmail_api(
        to=to, subject=subject, text=body_text, html=body_html
    ):
        return True

    resend_key = os.environ.get("RESEND_API_KEY")
    if resend_key and _send_via_resend(
        resend_key, to=to, subject=subject, text=body_text, html=body_html
    ):
        return True

    brevo_key = os.environ.get("BREVO_API_KEY")
    if brevo_key and _send_via_brevo(
        brevo_key, to=to, subject=subject, text=body_text, html=body_html
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
