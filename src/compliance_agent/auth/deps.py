"""FastAPI dependencies for authentication and role-based access control."""
from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from compliance_agent.auth.jwt import COOKIE_NAME, decode_token
from compliance_agent.db import Role, User, get_session


def get_current_user_optional(
    aspora_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_session),
) -> Optional[User]:
    """Return the User if a valid session cookie is present; None otherwise."""
    if not aspora_session:
        return None
    payload = decode_token(aspora_session)
    if not payload:
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    """Require an authenticated, active user. 401 otherwise."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require an admin user. 403 otherwise."""
    if user.role != Role.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required.",
        )
    return user
