"""Auth endpoints: login, logout, current user."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent.auth.deps import get_current_user
from compliance_agent.auth.jwt import COOKIE_NAME, cookie_max_age_seconds, create_token
from compliance_agent.auth.passwords import verify_password
from compliance_agent.db import Role, User, get_session


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: Role

    class Config:
        from_attributes = True


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_session),
) -> User:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    token = create_token(user.id, role=user.role.value)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=cookie_max_age_seconds(),
        httponly=True,
        samesite="lax",
        # secure=True in production behind HTTPS; FastAPI handles this when
        # the proxy forwards X-Forwarded-Proto. For local dev, keep False.
        secure=False,
    )
    user.last_login_at = datetime.now(tz=timezone.utc)
    db.commit()
    return user


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
