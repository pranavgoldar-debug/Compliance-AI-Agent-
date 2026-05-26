"""Regulation news watcher.

Polls public regulator RSS / Atom feeds, dedupes by GUID, persists new items
as `RegulationFeedItem` rows so the team finds out about new filings without
having to read every regulator's website by hand.

Stdlib XML parser — no feedparser dep. Most regulator feeds are simple
RSS 2.0 or Atom; we tolerate the common encoding quirks (CDATA, malformed
namespaces) by walking the tree manually.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent.db import RegulationFeed, RegulationFeedItem


USER_AGENT = "AsporaComplianceOS/1.0 (regulation-watcher)"
TIMEOUT_S = 15.0
MAX_BYTES = 2_500_000  # 2.5 MB — generous; RSS feeds rarely exceed 1 MB.

# Strip XML namespaces so we can match tags by local-name irrespective of
# the feed's chosen namespace decoration.
_NS_RE = re.compile(r"^\{[^}]+\}")


def _local(tag: str) -> str:
    return _NS_RE.sub("", tag or "")


def _text(elem: Optional[ET.Element]) -> Optional[str]:
    if elem is None:
        return None
    txt = (elem.text or "").strip()
    return txt or None


def _find_child(parent: ET.Element, name: str) -> Optional[ET.Element]:
    for child in parent:
        if _local(child.tag) == name:
            return child
    return None


def _find_children(parent: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in parent if _local(c.tag) == name]


@dataclass
class ParsedItem:
    guid: str
    title: str
    link: Optional[str]
    summary: Optional[str]
    published_at: Optional[datetime]


@dataclass
class PollResult:
    feed_id: int
    feed_name: str
    fetched_at: datetime
    http_status: Optional[int]
    new_items: int
    total_items: int
    error: Optional[str] = None


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    raw = raw.strip()
    # RFC 822 (RSS 2.0) — "Mon, 26 May 2026 09:30:00 GMT"
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        pass
    # ISO 8601 (Atom)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def _extract_summary(item: ET.Element) -> Optional[str]:
    for name in ("description", "summary", "content"):
        el = _find_child(item, name)
        if el is not None:
            text = _text(el)
            if text:
                # Strip HTML tags + collapse whitespace.
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
                return text[:2000]
    return None


def _extract_link(item: ET.Element) -> Optional[str]:
    # RSS: <link>https://…</link>
    el = _find_child(item, "link")
    if el is not None:
        # Atom uses <link href="…"/> — both forms covered.
        href = el.attrib.get("href")
        if href:
            return href
        text = _text(el)
        if text:
            return text
    return None


def _extract_guid(item: ET.Element, fallback_link: Optional[str], title: str) -> str:
    el = _find_child(item, "guid") or _find_child(item, "id")
    if el is not None:
        text = _text(el)
        if text:
            return text[:512]
    if fallback_link:
        return fallback_link[:512]
    # Last resort: hash the title — better than dropping the item.
    return (title or "untitled")[:512]


def parse_feed(body: bytes) -> tuple[str, list[ParsedItem]]:
    """Parse RSS or Atom. Returns (feed_type, items). Raises on hard parse errors."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        raise ValueError(f"feed XML is malformed: {e}") from e

    tag = _local(root.tag).lower()
    items: list[ParsedItem] = []

    if tag == "rss":
        channel = _find_child(root, "channel")
        if channel is None:
            return "rss", []
        for item in _find_children(channel, "item"):
            items.append(_build_item(item))
        return "rss", items

    if tag == "feed":  # Atom
        for entry in _find_children(root, "entry"):
            items.append(_build_item(entry))
        return "atom", items

    raise ValueError(f"unrecognised feed root <{tag}>")


def _build_item(item: ET.Element) -> ParsedItem:
    title = _text(_find_child(item, "title")) or "(untitled)"
    link = _extract_link(item)
    summary = _extract_summary(item)
    published = _parse_date(
        _text(_find_child(item, "pubDate"))
        or _text(_find_child(item, "published"))
        or _text(_find_child(item, "updated"))
    )
    guid = _extract_guid(item, link, title)
    return ParsedItem(
        guid=guid,
        title=title.strip()[:512],
        link=link,
        summary=summary,
        published_at=published,
    )


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------
def _fetch(
    url: str,
    *,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None,
) -> tuple[Optional[int], bytes, dict[str, str], Optional[str]]:
    """Returns (status, body, response_headers, error)."""
    try:
        import httpx
    except ImportError as e:
        return None, b"", {}, f"httpx not installed: {e}"

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5",
    }
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=TIMEOUT_S,
            headers=headers,
        ) as client:
            resp = client.get(url)
        return resp.status_code, resp.content[:MAX_BYTES], dict(resp.headers), None
    except Exception as e:  # noqa: BLE001
        return None, b"", {}, f"fetch failed: {e}"


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------
def poll_feed(db: Session, feed: RegulationFeed) -> PollResult:
    now = datetime.utcnow()
    status, body, headers, err = _fetch(
        feed.url,
        etag=feed.last_etag,
        last_modified=feed.last_modified,
    )
    feed.last_polled_at = now

    if err:
        feed.last_status = "error"
        feed.last_error = err
        return PollResult(
            feed_id=feed.id,
            feed_name=feed.name,
            fetched_at=now,
            http_status=status,
            new_items=0,
            total_items=0,
            error=err,
        )

    # 304 Not Modified — nothing changed since last poll.
    if status == 304:
        feed.last_status = "not-modified"
        feed.last_error = None
        return PollResult(
            feed_id=feed.id,
            feed_name=feed.name,
            fetched_at=now,
            http_status=status,
            new_items=0,
            total_items=0,
        )

    if not status or status >= 400:
        feed.last_status = f"http-{status or 'error'}"
        feed.last_error = f"HTTP {status} from upstream."
        return PollResult(
            feed_id=feed.id,
            feed_name=feed.name,
            fetched_at=now,
            http_status=status,
            new_items=0,
            total_items=0,
            error=feed.last_error,
        )

    try:
        feed_type, items = parse_feed(body)
    except ValueError as e:
        feed.last_status = "parse-error"
        feed.last_error = str(e)
        return PollResult(
            feed_id=feed.id,
            feed_name=feed.name,
            fetched_at=now,
            http_status=status,
            new_items=0,
            total_items=0,
            error=str(e),
        )

    feed.feed_type = feed_type
    feed.last_etag = headers.get("etag") or feed.last_etag
    feed.last_modified = headers.get("last-modified") or feed.last_modified

    # Look up existing GUIDs in a single query — avoids N+1 on busy feeds.
    incoming_guids = [it.guid for it in items]
    existing: set[str] = set()
    if incoming_guids:
        existing = set(
            db.execute(
                select(RegulationFeedItem.guid).where(
                    RegulationFeedItem.feed_id == feed.id,
                    RegulationFeedItem.guid.in_(incoming_guids),
                )
            )
            .scalars()
            .all()
        )

    new_count = 0
    for it in items:
        if it.guid in existing:
            continue
        db.add(
            RegulationFeedItem(
                feed_id=feed.id,
                guid=it.guid,
                title=it.title,
                link=it.link,
                summary=it.summary,
                published_at=it.published_at,
            )
        )
        new_count += 1

    feed.last_status = f"ok ({new_count} new)" if new_count else "ok"
    feed.last_error = None
    return PollResult(
        feed_id=feed.id,
        feed_name=feed.name,
        fetched_at=now,
        http_status=status,
        new_items=new_count,
        total_items=len(items),
    )


def poll_all(db: Session, *, only_enabled: bool = True) -> list[PollResult]:
    stmt = select(RegulationFeed)
    if only_enabled:
        stmt = stmt.where(RegulationFeed.enabled.is_(True))
    stmt = stmt.order_by(RegulationFeed.jurisdiction_code, RegulationFeed.name)
    feeds: Iterable[RegulationFeed] = db.execute(stmt).scalars().all()
    results: list[PollResult] = []
    for feed in feeds:
        try:
            result = poll_feed(db, feed)
        except Exception as e:  # noqa: BLE001
            feed.last_status = "exception"
            feed.last_error = str(e)
            result = PollResult(
                feed_id=feed.id,
                feed_name=feed.name,
                fetched_at=datetime.utcnow(),
                http_status=None,
                new_items=0,
                total_items=0,
                error=str(e),
            )
        results.append(result)
        # Commit per-feed so a later crash doesn't lose earlier progress.
        db.commit()
    return results


# ---------------------------------------------------------------------------
# Default feeds — seeded once on first boot. Admins can disable / add more.
# ---------------------------------------------------------------------------
DEFAULT_FEEDS: list[dict[str, str]] = [
    {
        "name": "IRS Newsroom",
        "jurisdiction_code": "us",
        "url": "https://www.irs.gov/newsroom/news-releases-for-current-month/feed",
    },
    {
        "name": "SEC Press Releases",
        "jurisdiction_code": "us",
        "url": "https://www.sec.gov/news/pressreleases.rss",
    },
    {
        "name": "HMRC News (GOV.UK)",
        "jurisdiction_code": "uk",
        "url": "https://www.gov.uk/government/organisations/hm-revenue-customs.atom",
    },
    {
        "name": "Companies House News",
        "jurisdiction_code": "uk",
        "url": "https://www.gov.uk/government/organisations/companies-house.atom",
    },
    {
        "name": "CBIC India",
        "jurisdiction_code": "india",
        "url": "https://www.cbic.gov.in/feed.rss",
    },
    {
        "name": "RBI Press Releases",
        "jurisdiction_code": "india",
        "url": "https://www.rbi.org.in/Scripts/Rss.aspx",
    },
    {
        "name": "MAS Singapore",
        "jurisdiction_code": "singapore",
        "url": "https://www.mas.gov.sg/rss/news",
    },
    {
        "name": "CRA Canada",
        "jurisdiction_code": "canada",
        "url": "https://www.canada.ca/en/revenue-agency/news.rss.xml",
    },
    {
        "name": "VMI Lithuania",
        "jurisdiction_code": "lithuania",
        "url": "https://www.vmi.lt/evmi/rss",
    },
    {
        "name": "European Commission — Finance",
        "jurisdiction_code": "eu",
        "url": "https://finance.ec.europa.eu/news_en.rss",
    },
]


def seed_default_feeds(db: Session) -> int:
    """Idempotent — only inserts feeds that aren't already in the DB."""
    existing_urls = set(
        db.execute(select(RegulationFeed.url)).scalars().all()
    )
    added = 0
    for spec in DEFAULT_FEEDS:
        if spec["url"] in existing_urls:
            continue
        db.add(
            RegulationFeed(
                name=spec["name"],
                jurisdiction_code=spec["jurisdiction_code"],
                url=spec["url"],
                enabled=True,
            )
        )
        added += 1
    if added:
        db.commit()
    return added
