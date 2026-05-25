"""Password hashing using bcrypt."""
from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    """Return a bcrypt-hashed password ready for DB storage."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if `plain` matches `hashed`. Constant-time."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
