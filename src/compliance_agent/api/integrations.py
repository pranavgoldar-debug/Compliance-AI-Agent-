"""Workspace integration config — Slack webhook, SMTP test.

  GET  /api/admin/integrations/slack       — current Slack config (webhook URL masked)
  POST /api/admin/integrations/slack       — set webhook URL / default channel / enabled
  POST /api/admin/integrations/slack/test  — send a test message to Slack
  POST /api/admin/integrations/email/test  — send a test email through configured SMTP

  GET  /api/me/notification-prefs           — current user's prefs
  PATCH /api/me/notification-prefs          — update notify_email / notify_slack / slack_user_id
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent import clickup_service, slack_service
from compliance_agent.api._helpers import log_activity
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import (
    Obligation,
    ObligationStatus,
    User,
    get_session,
    session_scope,
)
from compliance_agent.email_service import (
    base_url as app_base_url,
    send_email,
    smtp_configured,
)

logger = logging.getLogger("compliance_agent.integrations")


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
# ClickUp — finance payment tasks + two-way status sync
# ---------------------------------------------------------------------------
def _mask_token(tok: Optional[str]) -> Optional[str]:
    if not tok:
        return None
    if len(tok) <= 10:
        return "***"
    return f"{tok[:5]}…{tok[-4:]}"


class ClickUpConfigOut(BaseModel):
    configured: bool
    enabled: bool
    has_token: bool = False
    api_token_masked: Optional[str] = None
    list_id: Optional[str] = None
    done_status: Optional[str] = None
    two_way_connected: bool = False


class ClickUpConfigUpdate(BaseModel):
    api_token: Optional[str] = None  # "" to clear
    list_id: Optional[str] = None
    done_status: Optional[str] = None
    enabled: Optional[bool] = None


def _clickup_out(cfg: dict) -> ClickUpConfigOut:
    tok = cfg.get("api_token")
    return ClickUpConfigOut(
        configured=bool(tok) and bool(cfg.get("list_id")),
        enabled=bool(cfg.get("enabled", True)),
        has_token=bool(tok),
        api_token_masked=_mask_token(tok),
        list_id=cfg.get("list_id"),
        done_status=cfg.get("done_status") or "complete",
        two_way_connected=bool(cfg.get("webhook_id")),
    )


@admin_router.get("/clickup", response_model=ClickUpConfigOut)
def get_clickup(
    db: Session = Depends(get_session),
    _: User = Depends(require_admin),
) -> ClickUpConfigOut:
    return _clickup_out(clickup_service.get_config(db))


@admin_router.post("/clickup", response_model=ClickUpConfigOut)
def update_clickup(
    payload: ClickUpConfigUpdate,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> ClickUpConfigOut:
    cfg = clickup_service.get_config(db)
    if payload.api_token is not None:
        cfg["api_token"] = payload.api_token.strip() or None
    if payload.list_id is not None:
        cfg["list_id"] = payload.list_id.strip() or None
    if payload.done_status is not None:
        cfg["done_status"] = payload.done_status.strip() or None
    if payload.enabled is not None:
        cfg["enabled"] = bool(payload.enabled)
    clickup_service.set_config(db, cfg, updated_by_id=actor.id)
    log_activity(
        db,
        actor_id=actor.id,
        action="integration.clickup.updated",
        target_type="integration",
        payload={"has_token": bool(cfg.get("api_token")), "list_id": cfg.get("list_id")},
    )
    db.commit()
    return _clickup_out(cfg)


@admin_router.post("/clickup/test", response_model=TestResult)
def test_clickup(
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> TestResult:
    cfg = clickup_service.get_config(db)
    token = cfg.get("api_token")
    if not token:
        return TestResult(ok=False, detail="Add your ClickUp API token first.")
    try:
        teams = clickup_service.list_teams(token)
    except Exception as exc:  # noqa: BLE001
        return TestResult(ok=False, detail=f"ClickUp rejected the token: {exc}")
    if not cfg.get("list_id"):
        return TestResult(
            ok=False,
            detail=f"Token works ({len(teams)} workspace(s)), but set a List ID to create tasks.",
        )
    names = ", ".join(t.get("name", "?") for t in teams[:3])
    return TestResult(ok=True, detail=f"Connected to ClickUp ({names}).")


@admin_router.post("/clickup/connect-webhook", response_model=ClickUpConfigOut)
def connect_clickup_webhook(
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> ClickUpConfigOut:
    base = app_base_url()
    if not base or base.startswith("http://localhost") or "127.0.0.1" in base:
        raise HTTPException(
            status_code=400,
            detail=(
                "Set COMPLIANCE_BASE_URL to your public app URL first — ClickUp "
                "needs a reachable https endpoint to send webhooks to."
            ),
        )
    endpoint = f"{base.rstrip('/')}/api/webhooks/clickup"
    try:
        cfg = clickup_service.register_webhook(
            db, endpoint=endpoint, updated_by_id=actor.id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_activity(
        db,
        actor_id=actor.id,
        action="integration.clickup.webhook_connected",
        target_type="integration",
        payload={"endpoint": endpoint},
    )
    db.commit()
    return _clickup_out(cfg)


# Public, signature-verified — ClickUp posts here when a task changes status.
webhook_router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@webhook_router.post("/clickup")
async def clickup_webhook(request: Request) -> dict:
    raw = await request.body()
    signature = request.headers.get("X-Signature", "")
    with session_scope() as db:
        cfg = clickup_service.get_config(db)
        secret = cfg.get("webhook_secret") or ""
        if not clickup_service.verify_signature(secret, raw, signature):
            raise HTTPException(status_code=401, detail="Invalid signature.")

        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Bad JSON.")

        if data.get("event") != "taskStatusUpdated":
            return {"ok": True, "ignored": "event"}

        task_id = str(data.get("task_id") or "")
        done_status = (cfg.get("done_status") or "complete").lower()
        became_done = False
        for h in data.get("history_items", []):
            if h.get("field") not in (None, "status"):
                continue
            after = h.get("after") or {}
            if isinstance(after, dict):
                name = str(after.get("status") or "").lower()
                kind = str(after.get("type") or "").lower()
            else:
                name, kind = str(after).lower(), ""
            if kind == "closed" or (name and name == done_status):
                became_done = True
                break

        if not (task_id and became_done):
            return {"ok": True, "ignored": "no-op"}

        ob = db.execute(
            select(Obligation).where(Obligation.clickup_task_id == task_id)
        ).scalars().first()
        if ob is None:
            return {"ok": True, "ignored": "unmatched"}
        if ob.status == ObligationStatus.completed:
            return {"ok": True, "ignored": "already-complete"}

        ob.status = ObligationStatus.completed
        ob.completed_at = datetime.now(tz=timezone.utc)
        log_activity(
            db,
            actor_id=None,
            action="obligation.completed_via_clickup",
            target_type="obligation",
            target_id=ob.id,
            payload={"clickup_task_id": task_id},
        )
        # session_scope commits on exit.
        return {"ok": True, "obligation_id": ob.id}


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
