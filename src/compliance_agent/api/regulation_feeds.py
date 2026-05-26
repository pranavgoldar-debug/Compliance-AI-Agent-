"""Regulation news watcher API.

  GET  /api/regulation-feeds                    - list configured feeds
  POST /api/regulation-feeds                    - admin: add a feed
  PATCH /api/regulation-feeds/{id}              - admin: enable / rename / change URL
  DELETE /api/regulation-feeds/{id}             - admin: remove a feed
  POST /api/regulation-feeds/poll               - admin: poll all (or one) now
  POST /api/regulation-feeds/seed-defaults      - admin: insert built-in feeds

  GET  /api/regulation-news                     - new items grouped feed by feed
  POST /api/regulation-news/{id}/read           - mark item read
  POST /api/regulation-news/{id}/dismiss        - hide from the inbox
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from compliance_agent.api._helpers import log_activity
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import (
    RegulationFeed,
    RegulationFeedItem,
    User,
    get_session,
)
from compliance_agent.regulation_feeds import (
    PollResult,
    poll_all,
    poll_feed,
    seed_default_feeds,
)


feeds_router = APIRouter(prefix="/api/regulation-feeds", tags=["regulation-feeds"])
news_router = APIRouter(prefix="/api/regulation-news", tags=["regulation-news"])


# ---------------------------------------------------------------------------
# Feed CRUD
# ---------------------------------------------------------------------------
class FeedOut(BaseModel):
    id: int
    name: str
    jurisdiction_code: str
    url: str
    feed_type: str
    enabled: bool
    last_polled_at: Optional[datetime]
    last_status: Optional[str]
    last_error: Optional[str]
    unread_count: int = 0
    total_count: int = 0


class FeedCreate(BaseModel):
    name: str
    jurisdiction_code: str
    url: str
    enabled: bool = True


class FeedUpdate(BaseModel):
    name: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    url: Optional[str] = None
    enabled: Optional[bool] = None


def _counts_by_feed(db: Session) -> dict[int, tuple[int, int]]:
    """Return {feed_id: (unread, total)} so the list endpoint doesn't N+1."""
    total_rows = db.execute(
        select(
            RegulationFeedItem.feed_id,
            func.count(RegulationFeedItem.id),
        ).group_by(RegulationFeedItem.feed_id)
    ).all()
    totals = {r[0]: int(r[1] or 0) for r in total_rows}

    unread_rows = db.execute(
        select(
            RegulationFeedItem.feed_id,
            func.count(RegulationFeedItem.id),
        )
        .where(
            RegulationFeedItem.read_at.is_(None),
            RegulationFeedItem.dismissed_at.is_(None),
        )
        .group_by(RegulationFeedItem.feed_id)
    ).all()
    unread = {r[0]: int(r[1] or 0) for r in unread_rows}

    feed_ids = set(totals) | set(unread)
    return {fid: (unread.get(fid, 0), totals.get(fid, 0)) for fid in feed_ids}


def _serialize_feed(feed: RegulationFeed, counts: dict[int, tuple[int, int]]) -> FeedOut:
    unread, total = counts.get(feed.id, (0, 0))
    return FeedOut(
        id=feed.id,
        name=feed.name,
        jurisdiction_code=feed.jurisdiction_code,
        url=feed.url,
        feed_type=feed.feed_type,
        enabled=feed.enabled,
        last_polled_at=feed.last_polled_at,
        last_status=feed.last_status,
        last_error=feed.last_error,
        unread_count=unread,
        total_count=total,
    )


@feeds_router.get("", response_model=list[FeedOut])
def list_feeds(
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[FeedOut]:
    feeds = (
        db.execute(
            select(RegulationFeed).order_by(
                RegulationFeed.jurisdiction_code, RegulationFeed.name
            )
        )
        .scalars()
        .all()
    )
    counts = _counts_by_feed(db)
    return [_serialize_feed(f, counts) for f in feeds]


@feeds_router.post("", response_model=FeedOut, status_code=201)
def create_feed(
    payload: FeedCreate,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> FeedOut:
    feed = RegulationFeed(
        name=payload.name,
        jurisdiction_code=payload.jurisdiction_code,
        url=payload.url,
        enabled=payload.enabled,
        created_by_id=user.id,
    )
    db.add(feed)
    db.flush()
    log_activity(
        db,
        actor_id=user.id,
        action="regulation_feed.created",
        target_type="regulation_feed",
        target_id=feed.id,
        payload={"url": payload.url},
    )
    db.commit()
    db.refresh(feed)
    return _serialize_feed(feed, {})


@feeds_router.patch("/{feed_id}", response_model=FeedOut)
def update_feed(
    feed_id: int,
    payload: FeedUpdate,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> FeedOut:
    feed = db.get(RegulationFeed, feed_id)
    if feed is None:
        raise HTTPException(status_code=404, detail="Feed not found.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(feed, field, value)
    log_activity(
        db,
        actor_id=user.id,
        action="regulation_feed.updated",
        target_type="regulation_feed",
        target_id=feed.id,
        payload=data,
    )
    db.commit()
    db.refresh(feed)
    return _serialize_feed(feed, _counts_by_feed(db))


@feeds_router.delete("/{feed_id}", status_code=204)
def delete_feed(
    feed_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> None:
    feed = db.get(RegulationFeed, feed_id)
    if feed is None:
        raise HTTPException(status_code=404, detail="Feed not found.")
    db.delete(feed)
    log_activity(
        db,
        actor_id=user.id,
        action="regulation_feed.deleted",
        target_type="regulation_feed",
        target_id=feed_id,
    )
    db.commit()


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------
class PollOut(BaseModel):
    feed_id: int
    feed_name: str
    fetched_at: datetime
    http_status: Optional[int]
    new_items: int
    total_items: int
    error: Optional[str] = None


class PollSummary(BaseModel):
    results: list[PollOut]
    total_new: int


def _serialize_result(r: PollResult) -> PollOut:
    return PollOut(
        feed_id=r.feed_id,
        feed_name=r.feed_name,
        fetched_at=r.fetched_at,
        http_status=r.http_status,
        new_items=r.new_items,
        total_items=r.total_items,
        error=r.error,
    )


@feeds_router.post("/poll", response_model=PollSummary)
def poll_now(
    feed_id: Optional[int] = Query(None, description="Poll just this feed if given."),
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> PollSummary:
    if feed_id is not None:
        feed = db.get(RegulationFeed, feed_id)
        if feed is None:
            raise HTTPException(status_code=404, detail="Feed not found.")
        result = poll_feed(db, feed)
        db.commit()
        results = [result]
    else:
        results = poll_all(db)
    log_activity(
        db,
        actor_id=user.id,
        action="regulation_feed.polled",
        target_type="regulation_feed",
        payload={
            "count": len(results),
            "new_items": sum(r.new_items for r in results),
        },
    )
    db.commit()
    return PollSummary(
        results=[_serialize_result(r) for r in results],
        total_new=sum(r.new_items for r in results),
    )


@feeds_router.post("/seed-defaults")
def seed_defaults(
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> dict[str, int]:
    added = seed_default_feeds(db)
    if added:
        log_activity(
            db,
            actor_id=user.id,
            action="regulation_feed.seeded",
            target_type="regulation_feed",
            payload={"added": added},
        )
        db.commit()
    return {"added": added}


# ---------------------------------------------------------------------------
# News inbox
# ---------------------------------------------------------------------------
class FeedItemOut(BaseModel):
    id: int
    feed_id: int
    feed_name: str
    jurisdiction_code: str
    title: str
    link: Optional[str]
    summary: Optional[str]
    published_at: Optional[datetime]
    fetched_at: datetime
    read_at: Optional[datetime]
    dismissed_at: Optional[datetime]
    promoted_rule_id: Optional[int]


@news_router.get("", response_model=list[FeedItemOut])
def list_news(
    unread_only: bool = Query(False),
    jurisdiction_code: Optional[str] = Query(None),
    feed_id: Optional[int] = Query(None),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[FeedItemOut]:
    stmt = (
        select(RegulationFeedItem, RegulationFeed)
        .join(RegulationFeed, RegulationFeed.id == RegulationFeedItem.feed_id)
        .order_by(
            RegulationFeedItem.published_at.desc().nullslast(),
            RegulationFeedItem.fetched_at.desc(),
        )
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(
            RegulationFeedItem.read_at.is_(None),
            RegulationFeedItem.dismissed_at.is_(None),
        )
    if jurisdiction_code:
        stmt = stmt.where(RegulationFeed.jurisdiction_code == jurisdiction_code)
    if feed_id is not None:
        stmt = stmt.where(RegulationFeedItem.feed_id == feed_id)

    rows = db.execute(stmt).all()
    return [
        FeedItemOut(
            id=item.id,
            feed_id=item.feed_id,
            feed_name=feed.name,
            jurisdiction_code=feed.jurisdiction_code,
            title=item.title,
            link=item.link,
            summary=item.summary,
            published_at=item.published_at,
            fetched_at=item.fetched_at,
            read_at=item.read_at,
            dismissed_at=item.dismissed_at,
            promoted_rule_id=item.promoted_rule_id,
        )
        for item, feed in rows
    ]


@news_router.post("/{item_id}/read", status_code=204)
def mark_read(
    item_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> None:
    item = db.get(RegulationFeedItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    if item.read_at is None:
        item.read_at = datetime.utcnow()
        db.commit()


@news_router.post("/{item_id}/dismiss", status_code=204)
def dismiss(
    item_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> None:
    item = db.get(RegulationFeedItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    if item.dismissed_at is None:
        item.dismissed_at = datetime.utcnow()
        db.commit()


@news_router.post("/read-all", status_code=204)
def read_all(
    jurisdiction_code: Optional[str] = Query(None),
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> None:
    stmt = select(RegulationFeedItem).where(RegulationFeedItem.read_at.is_(None))
    if jurisdiction_code:
        stmt = stmt.join(
            RegulationFeed, RegulationFeed.id == RegulationFeedItem.feed_id
        ).where(RegulationFeed.jurisdiction_code == jurisdiction_code)
    now = datetime.utcnow()
    for item in db.execute(stmt).scalars().all():
        item.read_at = now
    db.commit()
