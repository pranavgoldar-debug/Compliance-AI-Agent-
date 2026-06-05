"""Custom jurisdictions — admin-managed additions beyond the built-in set.

The built-in jurisdictions live in the frontend (lib/format.ts). Any extras an
admin adds here are persisted in the WorkspaceSetting KV table (key
``custom_jurisdictions``) so they survive redeploys without a new table.
Reading is open to any signed-in user; adding is admin-only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import User, WorkspaceSetting, get_session

router = APIRouter(prefix="/api/jurisdictions", tags=["jurisdictions"])

_SETTING_KEY = "custom_jurisdictions"


class JurisdictionIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=24)
    name: str = Field(..., min_length=1, max_length=80)
    flag: str = Field(default="", max_length=8)
    iso2: str = Field(default="", max_length=2)


class JurisdictionOut(JurisdictionIn):
    pass


def _load(db: Session) -> list[dict]:
    row = db.get(WorkspaceSetting, _SETTING_KEY)
    if row and isinstance(row.value, dict):
        return list(row.value.get("items", []))
    return []


@router.get("", response_model=list[JurisdictionOut])
def list_jurisdictions(
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[dict]:
    """Custom jurisdictions added by an admin (the built-in set is client-side)."""
    return _load(db)


@router.post("", response_model=list[JurisdictionOut], status_code=201)
def add_jurisdiction(
    payload: JurisdictionIn,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> list[dict]:
    """Add a new jurisdiction (admin only). Returns the full custom list."""
    code = payload.code.strip().lower()
    if not code:
        raise HTTPException(status_code=422, detail="Jurisdiction code is required.")
    items = _load(db)
    if any(j.get("code") == code for j in items):
        raise HTTPException(status_code=409, detail="That jurisdiction code already exists.")
    items.append(
        {
            "code": code,
            "name": payload.name.strip(),
            "flag": payload.flag.strip(),
            "iso2": payload.iso2.strip().lower(),
        }
    )
    row = db.get(WorkspaceSetting, _SETTING_KEY)
    if row is None:
        db.add(WorkspaceSetting(key=_SETTING_KEY, value={"items": items}, updated_by_id=user.id))
    else:
        # Reassign (not in-place mutate) so SQLAlchemy persists the JSON change.
        row.value = {"items": items}
        row.updated_by_id = user.id
    db.commit()
    return items
