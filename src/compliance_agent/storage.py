"""Document storage backend — pluggable filesystem implementation.

For now we only ship a local filesystem backend. To swap to S3/R2 later,
implement the same `save_bytes` / `open_read` / `delete` contract and route
through an env var (COMPLIANCE_STORAGE_BACKEND=s3 etc).

Files live under `COMPLIANCE_UPLOADS_DIR` (default: ./uploads). Storage paths
are content-addressed by a UUID4 prefix so re-uploads of the same filename
don't collide. The original filename is kept in the Document.filename column
for display.
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import BinaryIO


def _resolve_root() -> Path:
    root = os.environ.get("COMPLIANCE_UPLOADS_DIR", "uploads")
    p = Path(root).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


ROOT = _resolve_root()


# Filename normalisation — strip path components, control chars, and length-cap.
_FILENAME_BAD = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    """Return a filesystem-safe filename. Always preserves an extension if
    one was present in the original."""
    base = os.path.basename(name or "").strip() or "file"
    # Split off extension first so we can keep it intact.
    if "." in base:
        stem, ext = base.rsplit(".", 1)
        ext = "." + _FILENAME_BAD.sub("", ext)[:16]
    else:
        stem, ext = base, ""
    stem = _FILENAME_BAD.sub("-", stem)[:120] or "file"
    return stem + ext


def save_bytes(entity_id: int, original_filename: str, source: BinaryIO) -> tuple[str, int]:
    """Persist a file. Returns (relative_storage_path, size_bytes).

    The storage path is `entity_<id>/<uuid>__<safe-filename>` so we can browse
    on disk by entity in the worst case.
    """
    safe = _safe_filename(original_filename)
    subdir = ROOT / f"entity_{entity_id}"
    subdir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    target = subdir / f"{token}__{safe}"

    size = 0
    with target.open("wb") as out:
        while True:
            chunk = source.read(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)

    relative = target.relative_to(ROOT).as_posix()
    return relative, size


def absolute_path(storage_path: str) -> Path:
    """Convert a stored relative path back to an absolute filesystem path.
    Raises ValueError if the path tries to escape the uploads root."""
    p = (ROOT / storage_path).resolve()
    # Guard against path traversal (e.g. a malicious DB row "../etc/passwd").
    try:
        p.relative_to(ROOT)
    except ValueError as e:
        raise ValueError("Document path escapes uploads root.") from e
    return p


def open_read(storage_path: str) -> BinaryIO:
    return absolute_path(storage_path).open("rb")


def delete(storage_path: str) -> None:
    p = absolute_path(storage_path)
    if p.exists():
        p.unlink()


def file_size(storage_path: str) -> int:
    p = absolute_path(storage_path)
    return p.stat().st_size if p.exists() else 0


# Convenience for the API — total bytes used by an entity.
def entity_usage_bytes(entity_id: int) -> int:
    subdir = ROOT / f"entity_{entity_id}"
    if not subdir.exists():
        return 0
    return sum(f.stat().st_size for f in subdir.iterdir() if f.is_file())
