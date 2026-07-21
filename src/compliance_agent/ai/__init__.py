"""AI services — Phase 7 features.

Modules:
    document_extractor   — Read a PDF document and infer filing fields.
    second_opinion       — Reviewer-style assessment of a pending obligation.
    regulation_watcher   — Fetch a rule's source URL, snapshot, diff.

Each module exposes a single `available()` predicate that checks the
COMPLIANCE_AGENT_LIVE env var + either ANTHROPIC_API_KEY (direct) or
OPENROUTER_API_KEY (OpenRouter proxy) so the API layer can disable the
corresponding endpoint cleanly when AI is off.
"""
from __future__ import annotations

from compliance_agent.ai.llm_client import ai_available, active_backend, make_client

__all__ = ["ai_available", "active_backend", "make_client"]
