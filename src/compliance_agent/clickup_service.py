"""ClickUp integration — two-way sync for finance payment tasks.

When compliance requests a payment from finance, we create a task in a
configured ClickUp list so the finance team can action it in the tool they
already live in. When that ClickUp task is closed, a webhook calls back and
we mark the obligation completed. When the obligation is completed in-app,
we close the ClickUp task. That's the two-way loop.

Config lives in the `workspace_settings` table under the `clickup` key:

  { "api_token": "pk_...",          # ClickUp personal API token (a secret)
    "list_id": "901100...",         # list where finance tasks are created
    "team_id": "12345",             # workspace id (for webhook registration)
    "done_status": "complete",      # status name treated as / set to "done"
    "webhook_id": "...",            # set after two-way sync is connected
    "webhook_secret": "...",        # used to verify inbound webhook signatures
    "enabled": true }

The api_token is the bearer — treat it like a secret (the GET endpoint
masks it). All outbound calls are best-effort: ClickUp being down must
never break the in-app payment flow, so failures are logged, not raised.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from compliance_agent.db import Obligation, WorkspaceSetting

logger = logging.getLogger("compliance_agent.clickup")
SETTING_KEY = "clickup"
API_BASE = "https://api.clickup.com/api/v2"
_TIMEOUT = 10.0


# ---------------------------------------------------------------------------
# Config helpers (mirror slack_service)
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
    return (
        bool(cfg.get("api_token"))
        and bool(cfg.get("list_id"))
        and cfg.get("enabled", True)
    )


def _headers(token: str) -> dict:
    # ClickUp personal tokens go in Authorization with no scheme prefix.
    return {"Authorization": token, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Outbound — create / close tasks
# ---------------------------------------------------------------------------
def _description(obligation: Obligation, amount: str, notes: str, app_url: str) -> str:
    rule = obligation.rule
    entity = obligation.entity
    lines = [
        f"**Payment request from Compliance**",
        "",
        f"- Filing: {rule.form_name if rule else '—'}",
        f"- Entity: {entity.name if entity else '—'}",
        f"- Authority: {rule.authority if rule else '—'}",
        f"- Amount: {amount}",
        f"- Due date: {obligation.due_date.isoformat()}",
    ]
    if rule and (rule.payment_rule or "").strip():
        lines.append(f"- Payment rule: {rule.payment_rule}")
    if (notes or "").strip():
        lines.append(f"- Notes: {notes}")
    if app_url:
        lines += ["", f"Open in Compliance OS: {app_url}/obligations/{obligation.id}"]
    lines += [
        "",
        "_Closing this task marks the payment complete in Compliance OS._",
    ]
    return "\n".join(lines)


def create_payment_task(
    db: Session,
    obligation: Obligation,
    *,
    amount: str,
    notes: str = "",
    app_url: str = "",
) -> Optional[tuple[str, str]]:
    """Create a finance task in the configured ClickUp list. Returns
    (task_id, task_url) on success, None otherwise. Never raises."""
    cfg = get_config(db)
    if not is_configured(db):
        return None
    token = cfg["api_token"]
    list_id = cfg["list_id"]
    rule = obligation.rule
    entity = obligation.entity
    name = (
        f"Pay {amount} — {rule.form_name if rule else 'filing'}"
        f" ({entity.name if entity else 'entity'})"
    )
    # ClickUp due_date is unix ms.
    due_ms = int(
        datetime(
            obligation.due_date.year,
            obligation.due_date.month,
            obligation.due_date.day,
            tzinfo=timezone.utc,
        ).timestamp()
        * 1000
    )
    body = {
        "name": name[:255],
        "description": _description(obligation, amount, notes, app_url),
        "due_date": due_ms,
    }
    try:
        import httpx

        r = httpx.post(
            f"{API_BASE}/list/{list_id}/task",
            headers=_headers(token),
            json=body,
            timeout=_TIMEOUT,
        )
        if r.status_code not in (200, 201):
            logger.warning(
                "ClickUp create task failed: status=%s body=%r",
                r.status_code,
                r.text[:300],
            )
            return None
        data = r.json()
        return str(data.get("id")), data.get("url") or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("ClickUp create task crashed: %s", e)
        return None


def close_task(db: Session, task_id: str) -> bool:
    """Set the ClickUp task to the configured done status. Best-effort."""
    cfg = get_config(db)
    token = cfg.get("api_token")
    if not token or not task_id:
        return False
    done_status = cfg.get("done_status") or "complete"
    try:
        import httpx

        r = httpx.put(
            f"{API_BASE}/task/{task_id}",
            headers=_headers(token),
            json={"status": done_status},
            timeout=_TIMEOUT,
        )
        ok = r.status_code == 200
        if not ok:
            logger.warning(
                "ClickUp close task failed: status=%s body=%r",
                r.status_code,
                r.text[:300],
            )
        return ok
    except Exception as e:  # noqa: BLE001
        logger.warning("ClickUp close task crashed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Webhook registration + verification (two-way sync)
# ---------------------------------------------------------------------------
def list_teams(token: str) -> list[dict]:
    """Return the workspaces (teams) the token can see. Raises on error so
    the caller can surface a clear message."""
    import httpx

    r = httpx.get(f"{API_BASE}/team", headers=_headers(token), timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json().get("teams", [])


def register_webhook(db: Session, *, endpoint: str, updated_by_id: Optional[int] = None) -> dict:
    """Create a taskStatusUpdated webhook in ClickUp pointed at `endpoint`,
    storing the returned secret. Returns the updated (masked-safe) config.
    Raises ValueError with a friendly message on failure."""
    import httpx

    cfg = get_config(db)
    token = cfg.get("api_token")
    list_id = cfg.get("list_id")
    if not token or not list_id:
        raise ValueError("Set the API token + list ID first.")

    team_id = cfg.get("team_id")
    if not team_id:
        teams = list_teams(token)
        if not teams:
            raise ValueError("No ClickUp workspace is visible to this token.")
        team_id = str(teams[0]["id"])
        cfg["team_id"] = team_id

    # Remove any stale webhook we previously created so we don't stack dupes.
    old = cfg.get("webhook_id")
    if old:
        try:
            httpx.delete(
                f"{API_BASE}/webhook/{old}", headers=_headers(token), timeout=_TIMEOUT
            )
        except Exception:  # noqa: BLE001
            pass

    r = httpx.post(
        f"{API_BASE}/team/{team_id}/webhook",
        headers=_headers(token),
        json={
            "endpoint": endpoint,
            "events": ["taskStatusUpdated"],
            "list_id": list_id,
        },
        timeout=_TIMEOUT,
    )
    if r.status_code not in (200, 201):
        raise ValueError(f"ClickUp rejected the webhook: {r.text[:300]}")
    data = r.json()
    hook = data.get("webhook") or {}
    cfg["webhook_id"] = str(hook.get("id") or data.get("id") or "")
    cfg["webhook_secret"] = hook.get("secret") or ""
    return set_config(db, cfg, updated_by_id=updated_by_id)


def verify_signature(secret: str, raw_body: bytes, signature: str) -> bool:
    """ClickUp signs each webhook with HMAC-SHA256(raw_body, secret), hex,
    in the X-Signature header. Constant-time compare."""
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature.strip())
