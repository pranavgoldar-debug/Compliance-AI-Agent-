"""Reviewer-style second opinion on a pending obligation.

Aggregates the rule definition + the obligation's filled fields + comments
+ uploaded documents (filenames only — not contents, yet) and asks Claude
for a verdict: approve / needs_more_info / reject, plus reasoning and
next-step suggestions.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from compliance_agent.ai import ai_available
from compliance_agent.db import Comment, Document, Obligation


class SecondOpinion(BaseModel):
    verdict: str = Field(..., description="approve / needs_more_info / reject")
    confidence: str = Field("medium", description="high / medium / low")
    reasoning: str = Field(..., description="2-4 sentence explanation")
    suggested_next_steps: list[str] = Field(
        default_factory=list,
        description="Concrete actions the reviewer should take if not approving.",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Specific things that look off (missing ack, payment mismatch, etc.)",
    )


class SecondOpinionResult(BaseModel):
    available: bool
    opinion: Optional[SecondOpinion] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
def review(db: Session, obligation_id: int) -> SecondOpinionResult:
    if not ai_available():
        return SecondOpinionResult(
            available=False,
            error="AI is off in this deployment.",
        )

    obligation = db.execute(
        select(Obligation)
        .where(Obligation.id == obligation_id)
        .options(
            joinedload(Obligation.rule),
            joinedload(Obligation.entity),
            joinedload(Obligation.assignee),
        )
    ).scalars().unique().one_or_none()
    if obligation is None:
        return SecondOpinionResult(available=True, error="Obligation not found.")

    comments = db.execute(
        select(Comment)
        .where(Comment.obligation_id == obligation_id)
        .options(joinedload(Comment.author))
        .order_by(Comment.created_at.asc())
    ).scalars().unique().all()

    documents = db.execute(
        select(Document).where(Document.obligation_id == obligation_id)
    ).scalars().all()

    try:
        prompt = _build_prompt(obligation, comments, documents)
        opinion = _call_claude(prompt)
        return SecondOpinionResult(available=True, opinion=opinion)
    except Exception as e:
        # Never bubble up as a 500 — surface it inline on the card instead.
        return SecondOpinionResult(available=True, error=f"Second opinion failed: {e}")


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------
def _build_prompt(
    o: Obligation, comments: list[Comment], documents: list[Document]
) -> str:
    parts: list[str] = []
    parts.append("# Obligation")
    parts.append(f"- Entity: {o.entity.name if o.entity else '—'}")
    parts.append(
        f"- Jurisdiction: {o.entity.jurisdiction_code if o.entity else '—'}"
    )
    parts.append(f"- Form / Report: {o.rule.form_name if o.rule else '—'}")
    parts.append(f"- Authority: {o.rule.authority if o.rule else '—'}")
    parts.append(f"- Category: {o.rule.category if o.rule else '—'}")
    parts.append(f"- Frequency: {o.rule.frequency if o.rule else '—'}")
    parts.append(f"- Period: {o.period_label or '—'}")
    parts.append(f"- Due date: {o.due_date}")
    parts.append(f"- Effort band: {o.effort_band.value if o.effort_band else '—'}")
    parts.append(f"- Current status: {o.status.value}")
    parts.append(
        f"- Assignee: {(o.assignee.full_name or o.assignee.email) if o.assignee else 'Unassigned'}"
    )

    parts.append("\n# Operator inputs")
    parts.append(f"- Filing reference: {o.filing_reference or '(empty)'}")
    parts.append(f"- Payment amount: {o.payment_amount or '(empty)'}")
    parts.append(f"- Payment reference: {o.payment_reference or '(empty)'}")
    parts.append(
        f"- Internal notes: {o.notes or '(empty)'}"
    )

    parts.append("\n# Rule definition")
    if o.rule:
        parts.append(f"- Due-date rule: {o.rule.due_date_rule or '—'}")
        parts.append(f"- Payment rule: {o.rule.payment_rule or '—'}")
        parts.append(f"- Applicability: {o.rule.applicability.value if o.rule.applicability else '—'}")
        if o.rule.applicability_note:
            parts.append(f"- Applicability note: {o.rule.applicability_note}")

    parts.append("\n# Attached documents")
    if not documents:
        parts.append("(none)")
    else:
        for d in documents:
            # category / size can be NULL on legacy rows — stay defensive so
            # prompt assembly never throws (used to surface as a 500).
            cat = d.category.value if d.category is not None else "other"
            size_kb = (d.size_bytes or 0) // 1024
            parts.append(f"- {d.filename}  ({cat}, {size_kb} KB)")

    parts.append("\n# Comments (chronological)")
    if not comments:
        parts.append("(none)")
    else:
        for c in comments:
            who = c.author.full_name if c.author else "Unknown"
            parts.append(f"- [{c.created_at:%Y-%m-%d %H:%M}] {who}: {c.body}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Claude call
# ---------------------------------------------------------------------------
_SYSTEM = """\
You are a senior compliance reviewer at a fintech remittance company. The
operator team is asking you to review one obligation that is in "pending
review" state and give a deliberate yes/no/needs-more-info.

You will be given the rule definition, the obligation's filled fields, every
comment thread, and a list of attached document filenames. You DO NOT have
the document contents — only filenames — so don't pretend to.

Return your structured verdict via the provided tool. Be conservative: if
critical evidence is missing (e.g. no filing_reference but status is
"completed"), choose needs_more_info or reject. If everything looks clean
and consistent with the rule's payment + due-date rules, approve.

Be specific in `risk_flags` and `suggested_next_steps` — quote the field
or document by name. No fluff.
"""


def _call_claude(prompt: str) -> SecondOpinion:
    from compliance_agent.ai.llm_client import make_client

    client = make_client()
    tool = {
        "name": "record_opinion",
        "description": "Record the structured second-opinion verdict.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["approve", "needs_more_info", "reject"],
                },
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "reasoning": {"type": "string"},
                "suggested_next_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "risk_flags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["verdict", "reasoning"],
        },
    }

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1500,
        system=_SYSTEM,
        tools=[tool],
        tool_choice={"type": "tool", "name": "record_opinion"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "record_opinion":
            return SecondOpinion(**(block.input or {}))

    raise RuntimeError("Claude didn't call record_opinion.")
