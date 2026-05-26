"""Rate limiting via slowapi.

In-memory storage — fine for single-instance Render deploys. If we scale
horizontally we'll switch to a Redis-backed store via `Limiter(storage_uri=…)`.

Keys are derived in priority order:
  1. The authenticated user id (from the session cookie payload)
  2. The X-Forwarded-For client IP (when behind a proxy)
  3. The raw remote address

That way two users behind the same NAT don't get rate-limited together when
they're each authenticated.
"""
from __future__ import annotations

from typing import Optional

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from compliance_agent.auth.jwt import COOKIE_NAME, decode_token


def _key_func(request: Request) -> str:
    """user:<id> if logged in; otherwise the client IP."""
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        payload = decode_token(cookie)
        sub = (payload or {}).get("sub")
        if sub:
            return f"user:{sub}"
    return get_remote_address(request)


limiter = Limiter(
    key_func=_key_func,
    headers_enabled=True,
    # Default applied to every route unless overridden — generous.
    default_limits=["300/minute"],
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Friendly JSON body instead of slowapi's default."""
    retry_after: Optional[int] = None
    # slowapi attaches the limit's reset window on the exception.
    detail = getattr(exc, "detail", None) or "Too many requests."
    return JSONResponse(
        status_code=429,
        content={"detail": detail, "retry_after_seconds": retry_after},
        headers={"Retry-After": "60"},
    )
