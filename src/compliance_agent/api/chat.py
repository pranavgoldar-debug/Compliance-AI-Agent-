"""Ask Aspora — chat assistant that can read the compliance DB.

Uses Claude with a small set of tools that wrap the existing SQL queries.
The model decides which tool(s) to call to answer the user's question.

To stay safe: every tool query is scoped to the authenticated user's
workspace (which is everyone, since this app is single-tenant). No tool
can mutate data — it's strictly read-only inspection.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Any, Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from compliance_agent.api._helpers import ALERT_WINDOW_DAYS, today
from compliance_agent.auth import get_current_user
from compliance_agent.db import (
    Entity,
    Obligation,
    ObligationStatus,
    Rule,
    User,
    get_session,
)


router = APIRouter(prefix="/api/chat", tags=["chat"])


SYSTEM_PROMPT = """You are 'Ask Aspora', an embedded compliance copilot inside Aspora Compliance OS.

You answer questions about the user's compliance data: legal entities, regulatory rules, and per-entity obligations (filings/returns/reports/notifications). You can call read-only tools to look the data up.

Rules:
- Use tools to ground every factual answer. Don't fabricate counts, dates, or IDs.
- Cite specific records when relevant: "Aspora India Pvt Ltd — GSTR-3B due 2026-06-20 (obligation #4123)".
- For overview questions, prefer dashboard_summary; for entity-level questions use list_obligations with entity_id.
- Today is treated as the current calendar day — pass dates as ISO YYYY-MM-DD when filtering.
- If the user asks for advice (e.g. "what should I do first"), give a prioritised plain-language answer grounded in the data you fetched.
- Keep responses tight. Bullet points for lists. No long preambles. Use Markdown sparingly (bold for entity names, code for IDs).
- If a question is outside the scope of compliance data (general legal advice, opinions, off-topic), politely redirect.
"""


def _is_live() -> bool:
    return os.environ.get("COMPLIANCE_AGENT_LIVE") == "1"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "dashboard_summary",
        "description": (
            "High-level counts across all entities: overdue, in-alert-window (next 14 days), "
            "in-safe-zone, completed-this-month. Use this for any 'overview' / 'how are we "
            "doing' question."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_entities",
        "description": (
            "List the user's legal entities with active obligation counts. "
            "Optionally filter to a single jurisdiction."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "jurisdiction_code": {
                    "type": "string",
                    "enum": [
                        "india", "uk", "us", "eu", "uae", "singapore", "canada", "lithuania",
                    ],
                    "description": "Restrict to one jurisdiction.",
                }
            },
        },
    },
    {
        "name": "list_obligations",
        "description": (
            "List obligations the team owes. Filterable by entity, jurisdiction, status, "
            "and due-date range. Returns at most 40 rows; if you hit the cap, suggest the "
            "user narrow further."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "integer"},
                "entity_name": {
                    "type": "string",
                    "description": "Fuzzy-match an entity name when you don't know its ID.",
                },
                "jurisdiction_code": {
                    "type": "string",
                    "enum": [
                        "india", "uk", "us", "eu", "uae", "singapore", "canada", "lithuania",
                    ],
                },
                "status": {
                    "type": "string",
                    "enum": [
                        "not_started", "in_progress", "pending_review",
                        "completed", "not_applicable", "overdue", "in_alert_window",
                    ],
                    "description": (
                        "'overdue' = due_date < today AND not completed. "
                        "'in_alert_window' = due_date within next 14 days AND not completed."
                    ),
                },
                "category": {"type": "string"},
                "due_from": {"type": "string", "description": "ISO date inclusive."},
                "due_to": {"type": "string", "description": "ISO date inclusive."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 40},
            },
        },
    },
    {
        "name": "list_rules",
        "description": (
            "Look up rule templates. Useful for 'which rules apply to country X' or "
            "'what authorities does the team file to'. Returns at most 40 rows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "jurisdiction_code": {"type": "string"},
                "category": {"type": "string"},
                "search": {"type": "string", "description": "Free-text on name/form/authority."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 40},
            },
        },
    },
    {
        "name": "get_today",
        "description": "Return today's date in YYYY-MM-DD form. Use whenever date math is needed.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _tool_dashboard_summary(db: Session, _args: dict[str, Any]) -> dict[str, Any]:
    open_statuses = [ObligationStatus.not_started, ObligationStatus.in_progress, ObligationStatus.pending_review]
    overdue = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.due_date < today(),
            Obligation.status.in_(open_statuses),
        )
    ).scalar_one()
    in_alert = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.due_date >= today(),
            Obligation.due_date <= today() + timedelta(days=ALERT_WINDOW_DAYS),
            Obligation.status.in_(open_statuses),
        )
    ).scalar_one()
    safe = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.due_date > today() + timedelta(days=ALERT_WINDOW_DAYS),
            Obligation.status.in_(open_statuses),
        )
    ).scalar_one()
    first_of_month = today().replace(day=1)
    completed = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.status == ObligationStatus.completed,
            Obligation.completed_at >= first_of_month,
        )
    ).scalar_one()
    return {
        "overdue": overdue,
        "in_alert_window_next_14_days": in_alert,
        "in_safe_zone": safe,
        "completed_this_month": completed,
        "today": today().isoformat(),
    }


def _tool_list_entities(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    stmt = select(Entity).where(Entity.archived_at.is_(None))
    if jc := args.get("jurisdiction_code"):
        stmt = stmt.where(Entity.jurisdiction_code == jc)
    stmt = stmt.order_by(Entity.name)
    entities = db.execute(stmt).scalars().all()
    return {
        "entities": [
            {
                "id": e.id,
                "name": e.name,
                "jurisdiction_code": e.jurisdiction_code,
                "legal_type": e.legal_type,
                "fiscal_year_end": e.fiscal_year_end,
            }
            for e in entities
        ],
    }


def _tool_list_obligations(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    limit = min(40, max(1, int(args.get("limit") or 40)))
    stmt = select(Obligation).options(
        joinedload(Obligation.rule), joinedload(Obligation.entity)
    )

    if entity_id := args.get("entity_id"):
        stmt = stmt.where(Obligation.entity_id == int(entity_id))
    elif name := args.get("entity_name"):
        like = f"%{name.lower()}%"
        entity_ids = db.execute(
            select(Entity.id).where(func.lower(Entity.name).like(like))
        ).scalars().all()
        if not entity_ids:
            return {"obligations": [], "note": f"No entity matched '{name}'."}
        stmt = stmt.where(Obligation.entity_id.in_(entity_ids))

    status = args.get("status")
    open_statuses = [ObligationStatus.not_started, ObligationStatus.in_progress, ObligationStatus.pending_review]
    if status == "overdue":
        stmt = stmt.where(
            Obligation.due_date < today(),
            Obligation.status.in_(open_statuses),
        )
    elif status == "in_alert_window":
        stmt = stmt.where(
            Obligation.due_date >= today(),
            Obligation.due_date <= today() + timedelta(days=ALERT_WINDOW_DAYS),
            Obligation.status.in_(open_statuses),
        )
    elif status:
        stmt = stmt.where(Obligation.status == ObligationStatus(status))

    if due_from := args.get("due_from"):
        stmt = stmt.where(Obligation.due_date >= date.fromisoformat(due_from))
    if due_to := args.get("due_to"):
        stmt = stmt.where(Obligation.due_date <= date.fromisoformat(due_to))

    stmt = stmt.order_by(Obligation.due_date.asc()).limit(limit)
    items = db.execute(stmt).scalars().unique().all()

    if jc := args.get("jurisdiction_code"):
        items = [o for o in items if o.rule.jurisdiction_code == jc]
    if cat := args.get("category"):
        items = [o for o in items if o.rule.category.lower() == cat.lower()]

    return {
        "obligations": [
            {
                "id": o.id,
                "entity": o.entity.name,
                "entity_id": o.entity_id,
                "jurisdiction": o.entity.jurisdiction_code,
                "form_name": o.rule.form_name,
                "authority": o.rule.authority,
                "category": o.rule.category,
                "frequency": o.rule.frequency,
                "due_date": o.due_date.isoformat(),
                "status": o.status.value,
                "period": o.period_label,
                "is_overdue": o.due_date < today()
                and o.status not in (ObligationStatus.completed, ObligationStatus.not_applicable),
            }
            for o in items
        ],
        "truncated": len(items) >= limit,
    }


def _tool_list_rules(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    limit = min(40, max(1, int(args.get("limit") or 40)))
    stmt = select(Rule)
    if jc := args.get("jurisdiction_code"):
        stmt = stmt.where(Rule.jurisdiction_code == jc)
    if cat := args.get("category"):
        stmt = stmt.where(Rule.category == cat)
    if needle := args.get("search"):
        like = f"%{needle.lower()}%"
        stmt = stmt.where(
            func.lower(Rule.name).like(like)
            | func.lower(Rule.form_name).like(like)
            | func.lower(Rule.authority).like(like)
        )
    stmt = stmt.order_by(Rule.jurisdiction_code, Rule.name).limit(limit)
    rules = db.execute(stmt).scalars().all()
    return {
        "rules": [
            {
                "id": r.id,
                "name": r.name,
                "form_name": r.form_name,
                "jurisdiction": r.jurisdiction_code,
                "authority": r.authority,
                "category": r.category,
                "frequency": r.frequency,
                "due_date_rule": r.due_date_rule,
            }
            for r in rules
        ],
        "truncated": len(rules) >= limit,
    }


def _tool_get_today(_db: Session, _args: dict[str, Any]) -> dict[str, Any]:
    return {"today": today().isoformat()}


TOOL_HANDLERS = {
    "dashboard_summary": _tool_dashboard_summary,
    "list_entities": _tool_list_entities,
    "list_obligations": _tool_list_obligations,
    "list_rules": _tool_list_rules,
    "get_today": _tool_get_today,
}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    available: bool
    reply: str
    tool_calls: int = 0


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> ChatResponse:
    if not _is_live():
        return ChatResponse(
            available=False,
            reply=(
                "Ask Aspora is off in this deployment. "
                "Set COMPLIANCE_AGENT_LIVE=1 and ANTHROPIC_API_KEY on the server, "
                "then retry. Anything you'd ask me to do, the dashboards already cover."
            ),
        )

    if not payload.messages:
        raise HTTPException(status_code=400, detail="Provide at least one message.")

    # Build the API messages list. The last user turn comes from the client;
    # prior turns may have content from us (assistant) and earlier prompts.
    api_messages: list[dict[str, Any]] = []
    for m in payload.messages:
        if m.role not in ("user", "assistant"):
            continue
        api_messages.append({"role": m.role, "content": m.content})

    try:
        client = anthropic.Anthropic()
        tool_call_count = 0
        max_iterations = 6
        for _ in range(max_iterations):
            response = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=api_messages,
            )
            api_messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                handler = TOOL_HANDLERS.get(block.name)
                if handler is None:
                    result: dict[str, Any] = {"error": f"Unknown tool {block.name}."}
                else:
                    try:
                        result = handler(db, block.input or {})
                    except Exception as exc:  # noqa: BLE001
                        result = {"error": f"Tool {block.name} failed: {exc}"}
                tool_call_count += 1
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    }
                )
            api_messages.append({"role": "user", "content": tool_results})
        else:
            # Loop didn't terminate naturally — return whatever text we have so far.
            pass

        # Pull text out of the final assistant message.
        last_assistant = next(
            (m for m in reversed(api_messages) if m["role"] == "assistant"),
            None,
        )
        if last_assistant is None:
            return ChatResponse(available=True, reply="(no reply)", tool_calls=tool_call_count)
        reply_text = ""
        for block in last_assistant["content"]:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    reply_text += block.get("text", "")
            else:
                # anthropic SDK block object
                if getattr(block, "type", None) == "text":
                    reply_text += getattr(block, "text", "")
        return ChatResponse(
            available=True,
            reply=reply_text.strip() or "(no reply)",
            tool_calls=tool_call_count,
        )

    except anthropic.APIStatusError as exc:
        detail = getattr(exc, "message", None) or str(exc)
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc
