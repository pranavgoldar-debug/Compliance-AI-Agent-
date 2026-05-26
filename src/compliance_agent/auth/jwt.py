"""JWT encode/decode for the auth cookie.

Tokens live in an HTTP-only Secure cookie named `aspora_session`. Default
TTL is 7 days. Secret comes from APP_SECRET (set in Render env vars / .env);
for local dev a stable file-backed secret is generated if missing.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import jwt

_TOKEN_TTL_DAYS = 7
_ALGORITHM = "HS256"
COOKIE_NAME = "aspora_session"


def _bootstrap_secret() -> str:
    """Return APP_SECRET from env, or generate + persist one for local dev."""
    secret = os.environ.get("APP_SECRET")
    if secret:
        return secret

    secret_file = Path(".app_secret")
    if secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()

    new_secret = secrets.token_urlsafe(64)
    try:
        secret_file.write_text(new_secret + "\n", encoding="utf-8")
    except OSError:
        # Read-only file system (e.g. some PaaS). Fall back to in-memory.
        pass
    return new_secret


_SECRET = _bootstrap_secret()


def create_token(user_id: int, *, role: str, ttl_days: int = _TOKEN_TTL_DAYS) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=ttl_days)).timestamp()),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def decode_token(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError:
        return None


def cookie_max_age_seconds() -> int:
    return _TOKEN_TTL_DAYS * 24 * 60 * 60


# ---------------------------------------------------------------------------
# Sliding-refresh helpers
#
# We mint a fresh token (and re-set the cookie) on each authenticated request
# whose existing token was issued more than REFRESH_AFTER_DAYS ago. Net effect:
# anyone using the app daily never has to re-login; idle users still expire
# at the 7-day cap. The cap resets every refresh, so heavy users get
# perpetual sessions — which matches the cookie semantics of every modern
# SaaS the team already uses.
# ---------------------------------------------------------------------------
REFRESH_AFTER_DAYS = 3


def needs_refresh(payload: dict[str, Any]) -> bool:
    """True if the token's `iat` is older than REFRESH_AFTER_DAYS."""
    iat = payload.get("iat")
    if not isinstance(iat, (int, float)):
        return False
    issued = datetime.fromtimestamp(iat, tz=timezone.utc)
    return datetime.now(tz=timezone.utc) - issued >= timedelta(days=REFRESH_AFTER_DAYS)
