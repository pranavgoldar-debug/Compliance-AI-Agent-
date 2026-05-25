"""SQLAlchemy engine, session factory, and Base.

A single SQLite database file lives at ./compliance.db by default (override
with COMPLIANCE_DB_URL). The schema is created on first run via
Base.metadata.create_all(engine) — see init_db() below.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def _resolve_url() -> str:
    url = os.environ.get("COMPLIANCE_DB_URL")
    if url:
        return url
    db_path = Path(os.environ.get("COMPLIANCE_DB_PATH", "compliance.db")).resolve()
    return f"sqlite:///{db_path}"


DATABASE_URL = _resolve_url()

# check_same_thread=False is safe because we use a session-per-request pattern
# and never share a Session across threads.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create all tables. Idempotent. Safe to call on every boot."""
    # Import here so the model module is registered before create_all.
    from compliance_agent.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency — yields a session that auto-closes after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Use outside FastAPI (e.g. seed scripts, CLI commands)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
