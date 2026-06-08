"""Fetch a rule's source_url, snapshot it, diff against the last snapshot.

The watcher is on-demand only in Phase 7 (no scheduler). When admins click
"Check for changes" on a rule, we:
  1. HEAD/GET the source_url with a sensible UA + 10s timeout
  2. Strip HTML to plain text (best-effort — no heavy DOM parser yet)
  3. Compute a sha256 of the text. If it matches the latest snapshot,
     return {changed: False}; otherwise persist a new snapshot and
     return {changed: True, diff_excerpt, prev_excerpt, new_excerpt}.
  4. Optionally ask Claude to summarise the change in one sentence
     (skipped when AI is off).
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from difflib import unified_diff
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent.ai import ai_available
from compliance_agent.db import Rule, RuleSnapshot, User


USER_AGENT = "AsporaComplianceOS/0.7 (regulation watcher; +https://aspora.com)"
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_S = 10.0


class CheckResult(BaseModel):
    fetched_at: datetime
    http_status: Optional[int] = None
    error: Optional[str] = None
    changed: bool = False
    is_first_snapshot: bool = False
    content_length: int = 0
    content_hash: Optional[str] = None
    new_excerpt: Optional[str] = None
    prev_excerpt: Optional[str] = None
    diff_excerpt: Optional[str] = None
    change_summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Fetch + clean
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(raw: str) -> str:
    # Drop <script>/<style> blocks first.
    raw = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", raw, flags=re.S | re.I)
    text = _TAG_RE.sub(" ", raw)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _fetch(url: str) -> tuple[Optional[int], str, Optional[str]]:
    """Returns (http_status, plain_text, error). Either text or error is set."""
    try:
        import httpx
    except ImportError as e:
        return None, "", f"httpx not installed: {e}"

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=TIMEOUT_S,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = client.get(url)
        body = resp.content[:MAX_BYTES]
        if not resp.is_success:
            return resp.status_code, "", f"HTTP {resp.status_code} from upstream."
        text = body.decode(resp.encoding or "utf-8", errors="ignore")
        return resp.status_code, _strip_html(text), None
    except Exception as e:
        return None, "", f"Fetch failed: {e}"


# ---------------------------------------------------------------------------
# Public entry — checks one rule
# ---------------------------------------------------------------------------
def check(db: Session, rule_id: int, *, actor: Optional[User] = None) -> CheckResult:
    rule = db.get(Rule, rule_id)
    if rule is None:
        return CheckResult(
            fetched_at=datetime.now(tz=timezone.utc),
            error="Rule not found.",
        )
    if not rule.source_url:
        return CheckResult(
            fetched_at=datetime.now(tz=timezone.utc),
            error="This rule has no source_url. Edit it to add the regulator page URL.",
        )

    status, text, err = _fetch(rule.source_url)
    fetched_at = datetime.now(tz=timezone.utc)

    if err and not text:
        # Persist a failure snapshot so the history still shows the attempt.
        db.add(
            RuleSnapshot(
                rule_id=rule.id,
                fetched_at=fetched_at,
                fetched_by_id=actor.id if actor else None,
                http_status=status,
                content_length=0,
                content_hash="error",
                content_excerpt=err,
            )
        )
        db.commit()
        return CheckResult(
            fetched_at=fetched_at, http_status=status, error=err
        )

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    prev = db.execute(
        select(RuleSnapshot)
        .where(RuleSnapshot.rule_id == rule_id, RuleSnapshot.content_hash != "error")
        .order_by(RuleSnapshot.fetched_at.desc())
        .limit(1)
    ).scalars().first()

    excerpt = text[:16_000]
    if prev is not None and prev.content_hash == content_hash:
        # No change — but still record the heartbeat so we know it was checked.
        snapshot = RuleSnapshot(
            rule_id=rule.id,
            fetched_at=fetched_at,
            fetched_by_id=actor.id if actor else None,
            http_status=status,
            content_length=len(text),
            content_hash=content_hash,
            content_excerpt=None,  # don't re-store the body when nothing changed
        )
        db.add(snapshot)
        db.commit()
        return CheckResult(
            fetched_at=fetched_at,
            http_status=status,
            changed=False,
            content_length=len(text),
            content_hash=content_hash,
        )

    # Changed (or first ever snapshot).
    is_first = prev is None
    snapshot = RuleSnapshot(
        rule_id=rule.id,
        fetched_at=fetched_at,
        fetched_by_id=actor.id if actor else None,
        http_status=status,
        content_length=len(text),
        content_hash=content_hash,
        content_excerpt=excerpt,
    )
    db.add(snapshot)

    if not is_first:
        rule.source_changed_at = fetched_at

    diff = None
    summary = None
    if not is_first and prev is not None and prev.content_excerpt:
        diff = _diff(prev.content_excerpt, excerpt)
        if ai_available():
            try:
                summary = _summarise_change(rule.form_name, diff)
                snapshot.change_summary = summary
            except Exception as e:
                summary = f"(change-summary call failed: {e})"

    db.commit()
    return CheckResult(
        fetched_at=fetched_at,
        http_status=status,
        changed=not is_first,
        is_first_snapshot=is_first,
        content_length=len(text),
        content_hash=content_hash,
        new_excerpt=excerpt[:4000],
        prev_excerpt=(prev.content_excerpt[:4000] if prev and prev.content_excerpt else None),
        diff_excerpt=diff,
        change_summary=summary,
    )


def _diff(prev: str, new: str) -> str:
    """A truncated unified diff, line-based, capped at ~80 lines."""
    prev_lines = prev.splitlines() or [prev]
    new_lines = new.splitlines() or [new]
    # If both are one long line, chunk them into ~120-char segments for a
    # readable diff.
    if len(prev_lines) == 1 and len(prev) > 240:
        prev_lines = [prev[i : i + 120] for i in range(0, len(prev), 120)]
    if len(new_lines) == 1 and len(new) > 240:
        new_lines = [new[i : i + 120] for i in range(0, len(new), 120)]
    diff_iter = unified_diff(prev_lines, new_lines, lineterm="", n=2)
    lines = list(diff_iter)[:200]
    return "\n".join(lines) if lines else ""


# ---------------------------------------------------------------------------
# Optional AI summary
# ---------------------------------------------------------------------------
def _summarise_change(form_name: str, diff_text: str) -> str:
    if not diff_text.strip():
        return ""

    from compliance_agent.ai.llm_client import make_client

    client = make_client()
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=400,
        system=(
            "You are a compliance research assistant. Given a unified diff of a "
            "regulation page, write a SINGLE sentence (max 30 words) describing "
            "what substantively changed for filers. Ignore boilerplate, navigation, "
            "or trivial wording shifts. If nothing material changed, say "
            "'No material change.'"
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Rule: {form_name}\n\n"
                    f"Diff (unified):\n```\n{diff_text[:4000]}\n```"
                ),
            }
        ],
    )
    # First text block.
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return (block.text or "").strip()
    return ""
