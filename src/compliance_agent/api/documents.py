"""Documents endpoints.

Surface:
  GET    /api/documents                       — list (filterable by entity / obligation / category)
  GET    /api/documents/{id}                  — metadata
  GET    /api/documents/{id}/download         — raw file
  PATCH  /api/documents/{id}                  — rename / re-categorise
  DELETE /api/documents/{id}                  — soft-free disk + remove row
  POST   /api/entities/{id}/documents         — multipart upload (attach to entity)
  POST   /api/obligations/{id}/documents      — multipart upload (attach to obligation + parent entity)

All endpoints are auth-gated. Admin role is NOT required — any active user
can upload and read. (We can tighten if needed in Phase 6.)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from compliance_agent import storage
from compliance_agent.api._helpers import log_activity, serialize_user
from compliance_agent.api.schemas import DocumentOut, DocumentUpdate
from compliance_agent.auth import get_current_user
from compliance_agent.db import (
    Document,
    DocumentCategory,
    Entity,
    Obligation,
    User,
    get_session,
)


router = APIRouter(prefix="/api/documents", tags=["documents"])


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------
def _serialize(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        entity_id=doc.entity_id,
        entity_name=doc.entity.name if doc.entity else None,
        obligation_id=doc.obligation_id,
        obligation_form_name=doc.obligation.rule.form_name
        if doc.obligation and doc.obligation.rule
        else None,
        filename=doc.filename,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        category=doc.category,
        tags=doc.tags,
        uploaded_by=serialize_user(doc.uploaded_by),
        created_at=doc.created_at,
    )


def _eager():
    return [
        joinedload(Document.entity),
        joinedload(Document.obligation).joinedload(Obligation.rule),
        joinedload(Document.uploaded_by),
    ]


# ---------------------------------------------------------------------------
# List + read
# ---------------------------------------------------------------------------
@router.get("", response_model=list[DocumentOut])
def list_documents(
    entity_id: Optional[int] = Query(None),
    obligation_id: Optional[int] = Query(None),
    category: Optional[DocumentCategory] = Query(None),
    q: Optional[str] = Query(None, description="Filename search"),
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[DocumentOut]:
    stmt = select(Document).options(*_eager()).order_by(Document.created_at.desc())
    if entity_id is not None:
        stmt = stmt.where(Document.entity_id == entity_id)
    if obligation_id is not None:
        stmt = stmt.where(Document.obligation_id == obligation_id)
    if category is not None:
        stmt = stmt.where(Document.category == category)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(Document.filename.ilike(needle))
    docs = db.execute(stmt).scalars().unique().all()
    return [_serialize(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> DocumentOut:
    doc = db.execute(
        select(Document).where(Document.id == document_id).options(*_eager())
    ).scalars().unique().one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return _serialize(doc)


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    try:
        stream = storage.open_read(doc.storage_path)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=410, detail="Stored file is missing from disk.")

    return StreamingResponse(
        stream,
        media_type=doc.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{doc.filename}"',
            "Content-Length": str(doc.size_bytes),
        },
    )


# ---------------------------------------------------------------------------
# Update + delete
# ---------------------------------------------------------------------------
@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: int,
    payload: DocumentUpdate,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    doc = db.execute(
        select(Document).where(Document.id == document_id).options(*_eager())
    ).scalars().unique().one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(doc, field, value)
    log_activity(
        db,
        actor_id=user.id,
        action="document.updated",
        target_type="document",
        target_id=doc.id,
        payload={"fields": list(data.keys())},
    )
    db.commit()
    db.refresh(doc)
    return _serialize(doc)


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    # Capture metadata before we drop the row, for the audit payload.
    snapshot = {
        "filename": doc.filename,
        "entity_id": doc.entity_id,
        "obligation_id": doc.obligation_id,
    }
    path = doc.storage_path
    db.delete(doc)
    log_activity(
        db,
        actor_id=user.id,
        action="document.deleted",
        target_type="document",
        target_id=document_id,
        payload=snapshot,
    )
    db.commit()
    # Best-effort filesystem cleanup. If this fails, the row is already gone;
    # operators can sweep orphans periodically.
    try:
        storage.delete(path)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Uploads — attached to an entity (and optionally an obligation)
# ---------------------------------------------------------------------------
MAX_BYTES = 25 * 1024 * 1024  # 25 MB cap; configurable later


def _persist_upload(
    db: Session,
    user: User,
    upload: UploadFile,
    entity_id: int,
    obligation_id: Optional[int],
    category: DocumentCategory,
    tags: Optional[str],
) -> Document:
    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found.")

    # Read header to enforce size cap without buffering the whole thing in RAM.
    storage_path, size = storage.save_bytes(entity_id, upload.filename or "file", upload.file)
    if size > MAX_BYTES:
        storage.delete(storage_path)
        raise HTTPException(status_code=413, detail=f"File too large (>{MAX_BYTES // (1024*1024)} MB).")

    doc = Document(
        entity_id=entity_id,
        obligation_id=obligation_id,
        filename=upload.filename or "file",
        storage_path=storage_path,
        content_type=upload.content_type,
        size_bytes=size,
        category=category,
        tags=tags,
        uploaded_by_id=user.id,
    )
    db.add(doc)
    db.flush()
    log_activity(
        db,
        actor_id=user.id,
        action="document.uploaded",
        target_type="document",
        target_id=doc.id,
        payload={
            "filename": doc.filename,
            "entity_id": entity_id,
            "obligation_id": obligation_id,
            "size_bytes": size,
        },
    )
    db.commit()
    # Reload with relations for the response.
    return db.execute(
        select(Document).where(Document.id == doc.id).options(*_eager())
    ).scalars().unique().one()


entity_uploads = APIRouter(prefix="/api/entities", tags=["documents"])


@entity_uploads.post("/{entity_id}/documents", response_model=DocumentOut, status_code=201)
def upload_to_entity(
    entity_id: int,
    file: UploadFile = File(...),
    category: DocumentCategory = Form(DocumentCategory.other),
    tags: Optional[str] = Form(None),
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    doc = _persist_upload(db, user, file, entity_id, None, category, tags)
    return _serialize(doc)


obligation_uploads = APIRouter(prefix="/api/obligations", tags=["documents"])


@obligation_uploads.post("/{obligation_id}/documents", response_model=DocumentOut, status_code=201)
def upload_to_obligation(
    obligation_id: int,
    file: UploadFile = File(...),
    category: DocumentCategory = Form(DocumentCategory.filings),
    tags: Optional[str] = Form(None),
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    obligation = db.get(Obligation, obligation_id)
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found.")
    doc = _persist_upload(
        db, user, file, obligation.entity_id, obligation_id, category, tags
    )
    return _serialize(doc)
