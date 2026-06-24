"""Playbook — the in-app guide shown under Settings → Playbook & Guide.

The whole guide is editable by admins (stored as markdown) and persisted in the
WorkspaceSetting KV table (key ``playbook``) so it survives redeploys without a
new table. Reading is open to any signed-in user; editing is admin-only. When
no custom content has been saved, ``markdown`` is null and the frontend falls
back to its built-in default guide.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import User, WorkspaceSetting, get_session

router = APIRouter(prefix="/api/playbook", tags=["playbook"])

_SETTING_KEY = "playbook"
_MAX_LEN = 100_000


class PlaybookOut(BaseModel):
    # null markdown → the frontend renders its built-in default guide.
    markdown: Optional[str] = None
    updated_at: Optional[datetime] = None


class PlaybookUpdate(BaseModel):
    # Empty string is allowed — it resets the guide back to the built-in default.
    markdown: str = Field(default="", max_length=_MAX_LEN)


@router.get("", response_model=PlaybookOut)
def get_playbook(
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> PlaybookOut:
    """Current playbook content. null markdown = use the built-in default."""
    row = db.get(WorkspaceSetting, _SETTING_KEY)
    if row and isinstance(row.value, dict):
        md = (row.value.get("markdown") or "").strip()
        return PlaybookOut(markdown=md or None, updated_at=row.updated_at)
    return PlaybookOut(markdown=None)


@router.post("", response_model=PlaybookOut)
def update_playbook(
    payload: PlaybookUpdate,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> PlaybookOut:
    """Replace the whole guide (admin only). Save an empty body to reset to default."""
    md = (payload.markdown or "").strip()
    row = db.get(WorkspaceSetting, _SETTING_KEY)
    if row is None:
        row = WorkspaceSetting(key=_SETTING_KEY, value={"markdown": md}, updated_by_id=user.id)
        db.add(row)
    else:
        # Reassign (not in-place mutate) so SQLAlchemy persists the JSON change.
        row.value = {"markdown": md}
        row.updated_by_id = user.id
    db.commit()
    db.refresh(row)
    return PlaybookOut(markdown=md or None, updated_at=row.updated_at)
