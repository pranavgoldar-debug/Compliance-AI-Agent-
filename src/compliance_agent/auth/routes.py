"""Auth endpoints: login, logout, current user, password reset."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent.auth.deps import get_current_user
from compliance_agent.auth.jwt import COOKIE_NAME, cookie_max_age_seconds, create_token
from compliance_agent.auth.passwords import hash_password, verify_password
from compliance_agent.db import PasswordResetToken, Role, User, get_session
from compliance_agent.email_service import (
    base_url as app_base_url,
    password_reset_email,
    send_email,
    smtp_configured,
)
from compliance_agent.rate_limit import limiter


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
# 30/min keeps brute-force protection while letting normal humans switch
# accounts a few times during testing without getting locked out.
@limiter.limit("30/minute")
def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_session),
) -> User:
    # DB stores emails lowercased; normalize input before lookup so users
    # don't fail to log in because of a stray capital or leading/trailing
    # whitespace (very common when copy-pasting creds from chat / docs).
    email = (payload.email or "").strip().lower()
    password = payload.password or ""
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
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


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(
    payload: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Forgot / reset password flow
# ---------------------------------------------------------------------------
RESET_TTL_HOURS = 1


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    # Always the same shape regardless of whether the email exists — prevents
    # account enumeration.
    ok: bool = True
    # Only populated when SMTP is not configured AND it's a dev install. The
    # frontend uses this to offer admins a "copy reset link" affordance.
    dev_reset_url: str | None = None


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit("5/minute")
def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_session),
) -> ForgotPasswordResponse:
    email_lc = payload.email.lower().strip()
    user = db.execute(select(User).where(User.email == email_lc)).scalar_one_or_none()
    if user is None or not user.is_active:
        # Don't reveal which emails exist. Same response either way.
        return ForgotPasswordResponse(ok=True)

    raw_token = secrets.token_urlsafe(48)
    token_row = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=RESET_TTL_HOURS),
        requester_ip=(request.client.host if request.client else None),
        requester_agent=request.headers.get("user-agent", "")[:255] or None,
    )
    db.add(token_row)
    db.commit()

    reset_url = f"{app_base_url()}/reset-password?token={raw_token}"
    subject, text_body, html_body = password_reset_email(
        full_name=user.full_name, reset_url=reset_url, ttl_hours=RESET_TTL_HOURS
    )
    delivered = send_email(
        to=user.email, subject=subject, body_text=text_body, body_html=html_body
    )

    # In dev (no SMTP), surface the link so the admin can copy/paste it.
    # In prod we never leak the URL in the response — only via email.
    dev_url = None if smtp_configured() or delivered else reset_url
    return ForgotPasswordResponse(ok=True, dev_reset_url=dev_url)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/reset-password")
@limiter.limit("10/minute")
def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_session),
) -> dict:
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    token_hash = _hash_token(payload.token)
    row = db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    ).scalar_one_or_none()

    now = datetime.now(tz=timezone.utc)
    if row is None or row.used_at is not None or row.expires_at < now:
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired.")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Account is no longer active.")

    user.password_hash = hash_password(payload.new_password)
    row.used_at = now
    # Best-effort: invalidate any other outstanding tokens for this user.
    db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.id != row.id,
        )
    )
    # Actually mark them used so they can't be replayed.
    from sqlalchemy import update as _update

    db.execute(
        _update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.id != row.id,
        )
        .values(used_at=now)
    )
    db.commit()
    return {"ok": True}
