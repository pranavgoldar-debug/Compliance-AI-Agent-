"""AI services — Phase 7 features.

Modules:
    document_extractor   — Read a PDF document and infer filing fields.
    second_opinion       — Reviewer-style assessment of a pending obligation.
    regulation_watcher   — Fetch a rule's source URL, snapshot, diff.

Each module exposes a single `available()` predicate that checks the
COMPLIANCE_AGENT_LIVE + ANTHROPIC_API_KEY env vars so the API layer can
disable the corresponding endpoint cleanly when AI is off.
"""
from __future__ import annotations

import os


def ai_available() -> bool:
    """The Phase 4 gate: live mode + a usable API key."""
    return os.environ.get("COMPLIANCE_AGENT_LIVE") == "1" and bool(
        os.environ.get("ANTHROPIC_API_KEY")
    )
