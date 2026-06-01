"""Document storage backend — database-backed blobs.

Uploaded files (license PDFs, documents) are stored as rows in the
`file_blobs` table rather than on local disk. This is deliberate: Render's
free tier (and most PaaS) give web services an EPHEMERAL filesystem, so any
file written to disk is wiped on every redeploy/restart — which silently
lost every upload. The database persists, so blobs survive deploys.

The public contract is unchanged: `save_bytes` returns a string
`storage_path` key (kept in License.storage_path / Document.storage_path),
and `open_read` / `read_bytes` / `delete` / `file_size` operate on that key.
The key format stays `entity_<id>/<uuid>__<safe-filename>` for readability.

To swap to S3/R2 later, reimplement the same contract behind an env switch.
"""
from __future__ import annotations

import io
import os
import re
import uuid
from typing import BinaryIO, Optional


# Filename normalisation — strip path components, control chars, length-cap.
_FILENAME_BAD = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    """Return a safe filename. Always preserves an extension if present."""
    base = os.path.basename(name or "").strip() or "file"
    if "." in base:
        stem, ext = base.rsplit(".", 1)
        ext = "." + _FILENAME_BAD.sub("", ext)[:16]
    else:
        stem, ext = base, ""
    stem = _FILENAME_BAD.sub("-", stem)[:120] or "file"
    return stem + ext


def save_bytes(
    entity_id: int,
    original_filename: str,
    source: BinaryIO,
    content_type: Optional[str] = None,
) -> tuple[str, int]:
    """Persist a file in the DB. Returns (storage_path_key, size_bytes)."""
    from compliance_agent.db import session_scope
    from compliance_agent.db.models import FileBlob

    safe = _safe_filename(original_filename)
    key = f"entity_{entity_id}/{uuid.uuid4().hex}__{safe}"

    data = source.read()
    if isinstance(data, str):
        data = data.encode("utf-8")
    size = len(data)

    with session_scope() as db:
        db.add(
            FileBlob(path=key, data=data, size_bytes=size, content_type=content_type)
        )
    return key, size


def read_bytes(storage_path: str) -> Optional[bytes]:
    """Return the stored bytes for a key, or None if it doesn't exist."""
    if not storage_path:
        return None
    from compliance_agent.db import session_scope
    from compliance_agent.db.models import FileBlob

    with session_scope() as db:
        blob = db.get(FileBlob, storage_path)
        return bytes(blob.data) if blob else None


def open_read(storage_path: str) -> BinaryIO:
    """Return a binary stream over the stored bytes (empty if missing)."""
    return io.BytesIO(read_bytes(storage_path) or b"")


def delete(storage_path: str) -> None:
    if not storage_path:
        return
    from compliance_agent.db import session_scope
    from compliance_agent.db.models import FileBlob

    with session_scope() as db:
        blob = db.get(FileBlob, storage_path)
        if blob is not None:
            db.delete(blob)


def file_size(storage_path: str) -> int:
    if not storage_path:
        return 0
    from compliance_agent.db import session_scope
    from compliance_agent.db.models import FileBlob

    with session_scope() as db:
        blob = db.get(FileBlob, storage_path)
        return blob.size_bytes if blob else 0


def entity_usage_bytes(entity_id: int) -> int:
    from sqlalchemy import func, select

    from compliance_agent.db import session_scope
    from compliance_agent.db.models import FileBlob

    with session_scope() as db:
        total = db.execute(
            select(func.coalesce(func.sum(FileBlob.size_bytes), 0)).where(
                FileBlob.path.like(f"entity_{entity_id}/%")
            )
        ).scalar_one()
        return int(total or 0)
