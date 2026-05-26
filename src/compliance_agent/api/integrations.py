"""Workspace integration config — Slack webhook, SMTP test.

  GET  /api/admin/integrations/slack       — current Slack config (webhook URL masked)
  POST /api/admin/integrations/slack       — set webhook URL / default channel / enabled
  POST /api/admin/integrations/slack/test  — send a test message to Slack
  POST /api/admin/integrations/email/test  — send a test email through configured SMTP

  GET  /api/me/notification-prefs           — current user's prefs
  PATCH /api/me/notification-prefs          — update notify_email / notify_slack / slack_user_id
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from compliance_agent import slack_service
from compliance_agent.api._helpers import log_activity
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import User, get_session
from compliance_agent.email_service import (
    base_url as app_base_url,
    send_email,
    smtp_configured,
)


admin_router = APIRouter(prefix="/api/admin/integrations", tags=["integrations"])
me_router = APIRouter(prefix="/api/me", tags=["integrations"])


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------
def _mask_webhook(url: str | None) -> str | None:
    if not url:
        return None
    # Keep the hooks.slack.com host + the first segment; hide the token tail.
    parts = url.split("/")
    if len(parts) >= 7:
        return "/".join(parts[:5] + ["***", "***"])
    return "https://hooks.slack.com/services/***"


class SlackConfigOut(BaseModel):
    configured: bool
    enabled: bool
    webhook_url_masked: Optional[str] = None
    has_webhook: bool = False
    default_channel: Optional[str] = None


class SlackConfigUpdate(BaseModel):
    webhook_url: Optional[str] = None  # pass empty string "" to clear
    default_channel: Optional[str] = None
    enabled: Optional[bool] = None


@admin_router.get("/slack", response_model=SlackConfigOut)
def get_slack(
    db: Session = Depends(get_session),
    _: User = Depends(require_admin),
) -> SlackConfigOut:
    cfg = slack_service.get_config(db)
    url = cfg.get("webhook_url")
    return SlackConfigOut(
        configured=bool(url),
        enabled=bool(cfg.get("enabled", True)),
        webhook_url_masked=_mask_webhook(url),
        has_webhook=bool(url),
        default_channel=cfg.get("default_channel"),
    )


@admin_router.post("/slack", response_model=SlackConfigOut)
def update_slack(
    payload: SlackConfigUpdate,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> SlackConfigOut:
    cfg = slack_service.get_config(db)

    if payload.webhook_url is not None:
        url = payload.webhook_url.strip()
        if url and not url.startswith("https://hooks.slack.com/"):
            raise HTTPException(
                status_code=400,
                detail="Webhook URL must start with https://hooks.slack.com/",
            )
        cfg["webhook_url"] = url or None
    if payload.default_channel is not None:
        ch = payload.default_channel.strip() or None
        cfg["default_channel"] = ch
    if payload.enabled is not None:
        cfg["enabled"] = bool(payload.enabled)

    slack_service.set_config(db, cfg, updated_by_id=actor.id)
    log_activity(
        db,
        actor_id=actor.id,
        action="integration.slack.updated",
        target_type="integration",
        payload={"has_webhook": bool(cfg.get("webhook_url")), "enabled": cfg.get("enabled", True)},
    )
    db.commit()
    return get_slack(db=db, _=actor)


class TestResult(BaseModel):
    ok: bool
    detail: Optional[str] = None


@admin_router.post("/slack/test", response_model=TestResult)
def test_slack(
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> TestResult:
    if not slack_service.is_configured(db):
        return TestResult(
            ok=False,
            detail="Slack isn't configured. Paste a webhook URL first.",
        )
    sent = slack_service.post(
        f":wave: Test ping from Aspora Compliance OS by "
        f"{actor.full_name or actor.email}. If you see this in Slack, the "
        f"webhook is wired up correctly.",
        sync=True,
    )
    if sent:
        log_activity(
            db,
            actor_id=actor.id,
            action="integration.slack.test_sent",
            target_type="integration",
        )
        db.commit()
        return TestResult(ok=True, detail="Posted to Slack.")
    return TestResult(
        ok=False,
        detail="Slack rejected the post. Double-check the webhook URL and that the channel still exists.",
    )


# ---------------------------------------------------------------------------
# Email (SMTP test only — admin can't set creds at runtime; those live in env)
# ---------------------------------------------------------------------------
class EmailTestRequest(BaseModel):
    to: Optional[str] = Field(
        None, description="Override the recipient. Defaults to the actor's own email."
    )


@admin_router.post("/email/test", response_model=TestResult)
def test_email(
    payload: EmailTestRequest,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> TestResult:
    to = (payload.to or "").strip() or actor.email
    delivered = send_email(
        to=to,
        subject="Aspora Compliance OS — test email",
        body_text=(
            f"Hi,\n\n"
            f"This is a test message from Aspora Compliance OS, triggered by "
            f"{actor.full_name or actor.email} at {app_base_url()}.\n\n"
            f"If you got this, your SMTP config is wired up correctly. If you "
            f"didn't expect this, ignore it — nothing actionable.\n\n"
            f"— Aspora Compliance OS"
        ),
        body_html=(
            f"<p>This is a test message from Aspora Compliance OS, "
            f"triggered by <strong>{actor.full_name or actor.email}</strong>.</p>"
            f'<p style="color:#666">If you got this, your SMTP config is wired up '
            f"correctly. Nothing to do here.</p>"
        ),
    )
    log_activity(
        db,
        actor_id=actor.id,
        action="integration.email.test_sent",
        target_type="integration",
        payload={"to": to, "delivered": delivered, "smtp_configured": smtp_configured()},
    )
    db.commit()
    if not smtp_configured():
        return TestResult(
            ok=False,
            detail=(
                "SMTP isn't configured on the server. The test message was logged "
                "to the server console instead. Set SMTP_HOST / SMTP_USER / "
                "SMTP_PASSWORD in your .env to actually deliver."
            ),
        )
    if not delivered:
        return TestResult(
            ok=False,
            detail="SMTP send failed. Check the server logs for the underlying error.",
        )
    return TestResult(ok=True, detail=f"Sent to {to}.")


# ---------------------------------------------------------------------------
# Per-user notification prefs
# ---------------------------------------------------------------------------
class NotificationPrefsOut(BaseModel):
    notify_email: bool
    notify_slack: bool
    slack_user_id: Optional[str] = None


class NotificationPrefsUpdate(BaseModel):
    notify_email: Optional[bool] = None
    notify_slack: Optional[bool] = None
    slack_user_id: Optional[str] = None  # "" to clear


@me_router.get("/notification-prefs", response_model=NotificationPrefsOut)
def get_my_prefs(user: User = Depends(get_current_user)) -> NotificationPrefsOut:
    return NotificationPrefsOut(
        notify_email=user.notify_email,
        notify_slack=user.notify_slack,
        slack_user_id=user.slack_user_id,
    )


@me_router.patch("/notification-prefs", response_model=NotificationPrefsOut)
def update_my_prefs(
    payload: NotificationPrefsUpdate,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> NotificationPrefsOut:
    data = payload.model_dump(exclude_unset=True)
    if "notify_email" in data:
        user.notify_email = bool(data["notify_email"])
    if "notify_slack" in data:
        user.notify_slack = bool(data["notify_slack"])
    if "slack_user_id" in data:
        s = (data["slack_user_id"] or "").strip()
        user.slack_user_id = s or None
    db.commit()
    db.refresh(user)
    return NotificationPrefsOut(
        notify_email=user.notify_email,
        notify_slack=user.notify_slack,
        slack_user_id=user.slack_user_id,
    )
