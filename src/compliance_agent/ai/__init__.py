"""AI services — Phase 7 features.

Modules:
    document_extractor   — Read a PDF document and infer filing fields.
    second_opinion       — Reviewer-style assessment of a pending obligation.
    regulation_watcher   — Fetch a rule's source URL, snapshot, diff.

`ai_available()` checks the COMPLIANCE_AGENT_LIVE env var plus either
ANTHROPIC_API_KEY (direct Anthropic) or OPENROUTER_API_KEY (OpenRouter
proxy), so the API layer can disable the corresponding endpoint cleanly
when AI is off. The actual backend selection lives in `llm_client`.
"""
from __future__ import annotations

from compliance_agent.ai.llm_client import active_backend, ai_available, make_client

__all__ = ["ai_available", "active_backend", "make_client"]
