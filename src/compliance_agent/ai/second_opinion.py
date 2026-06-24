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

    # Everything below — DB reads, prompt build, Claude call — is wrapped so a
    # bad row, a lazy-load, or a model error surfaces inline on the card
    # instead of bubbling up as an HTTP 500.
    try:
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

        prompt = _build_prompt(obligation, comments, documents)
        opinion = _call_claude(prompt)
        return SecondOpinionResult(available=True, opinion=opinion)
    except Exception as e:  # noqa: BLE001
        # Never bubble up as a 500 — surface it inline on the card instead.
        import logging

        logging.getLogger(__name__).exception(
            "Second opinion failed for obligation %s", obligation_id
        )
        return SecondOpinionResult(
            available=True, error=f"Second opinion failed: {type(e).__name__}: {e}"
        )


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
            who = (c.author.full_name or c.author.email) if c.author else "Unknown"
            when = f"{c.created_at:%Y-%m-%d %H:%M}" if c.created_at else "—"
            parts.append(f"- [{when}] {who}: {c.body or ''}")

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
    # Structured output via the shared parse path (same as discovery): on
    # OpenRouter this falls back to plain-JSON extraction + Pydantic validation,
    # so it works whether the backend is Anthropic-direct or OpenRouter. The
    # previous Anthropic-native tool-use call 500'd on OpenRouter-only setups.
    from compliance_agent.ai.llm_client import log_usage, make_client

    client = make_client()
    response = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=1500,
        temperature=0,
        system=[
            {
                "type": "text",
                "text": _SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": prompt}],
        output_format=SecondOpinion,
    )
    log_usage(response, model="claude-opus-4-8", label="second-opinion")
    opinion = response.parsed_output
    if opinion is None:
        raise RuntimeError("Second opinion model returned no structured output.")
    return opinion
