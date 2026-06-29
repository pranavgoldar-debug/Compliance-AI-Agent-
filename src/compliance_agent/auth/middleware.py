"""Sliding-refresh middleware.

After every request, if the incoming session cookie was issued more than
`REFRESH_AFTER_DAYS` ago, we mint a fresh token and replace the cookie on
the outgoing response. Users active daily get perpetual sessions; idle
users still expire at the 7-day cap.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from compliance_agent.auth.jwt import (
    COOKIE_NAME,
    cookie_max_age_seconds,
    cookie_security_kwargs,
    create_token,
    decode_token,
    needs_refresh,
)


class SlidingSessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        token = request.cookies.get(COOKIE_NAME)
        payload = decode_token(token) if token else None

        response = await call_next(request)

        # Only refresh if the request arrived with a valid session that's
        # past the refresh threshold. Never mint a token for unauthenticated
        # requests.
        if payload and needs_refresh(payload):
            try:
                user_id = int(payload["sub"])
            except (KeyError, ValueError, TypeError):
                return response
            new_token = create_token(user_id, role=str(payload.get("role", "")))
            response.set_cookie(
                key=COOKIE_NAME,
                value=new_token,
                max_age=cookie_max_age_seconds(),
                httponly=True,
                **cookie_security_kwargs(),
            )
        return response
