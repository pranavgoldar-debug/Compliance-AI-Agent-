"""Rule CRUD endpoints (admin-managed)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, select, update as sa_update
from sqlalchemy.orm import Session

from compliance_agent.activity_gate import entity_applicability
from compliance_agent.api._helpers import log_activity, serialize_user
from compliance_agent.classification import (
    derive_function,
    derive_tax_type,
    keep_function,
    owner_team_engine,
)
from compliance_agent.api.schemas import RuleCreate, RuleOut, RuleSnapshotOut, RuleUpdate
from compliance_agent.auth import get_current_user, require_admin
from compliance_agent.db import (
    Comment,
    Document,
    Entity,
    Notification,
    Obligation,
    Rule,
    RuleSnapshot,
    RuleStatus,
    User,
    get_session,
)


router = APIRouter(prefix="/api/rules", tags=["rules"])


def ensure_obligations_for_rule(db: Session, rule: Rule) -> None:
    """Create a calendar obligation for each attached entity on the computed
    due date (idempotent), and keep the assignee in sync with the rule's owner.
    ONLY runs for APPROVED (production) rules — a rule sitting in Review & Assign
    (staging, even sent_to_review) does NOT hit the calendar until it's approved,
    and lands there the moment it is."""
    if rule.status != RuleStatus.production:
        return
    if not rule.entities:
        return
    from datetime import date
    from compliance_agent.api.licenses import _next_due_for_rule, _parse_fy_end
    from compliance_agent.db import ObligationStatus, Department

    today = date.today()
    for ent in rule.entities:
        # NO Primary-Activity gating here: production rules are human-approved
        # (Review & Assign), and that explicit decision outranks the keyword
        # gate — an approved filing must reach the calendar/Filings with its
        # assignee, never be silently skipped because an activity answer says
        # "No". The gate still flags applicability on the display surfaces
        # (entity Compliance list / rule serialization); if a filing truly
        # doesn't apply, the reviewer archives it instead of approving.
        # Deadline anchored on THIS entity's fiscal year-end (per-entity).
        due = _next_due_for_rule(rule, today, _parse_fy_end(ent.fiscal_year_end))

        # `due` is recomputed from today on every run. For rules whose
        # due_date_rule isn't a parseable deadline, _next_due_for_rule falls
        # back to today + interval, so the date DRIFTS day-to-day — and because
        # obligation identity keyed on the exact due_date, re-running on a later
        # day used to mint a near-duplicate obligation (e.g. an Annual Return on
        # both 8-Jun and 9-Jun, one day apart). Fix: keep at most one active
        # obligation per tight cluster — collapse active copies whose due dates
        # fall within a week of each other (drift artifacts), keeping the
        # earliest, while leaving genuinely-spaced recurrences (e.g. monthly,
        # ~30 days apart) untouched. Only create when no active copy exists.
        active = (
            db.execute(
                select(Obligation)
                .where(
                    Obligation.rule_id == rule.id,
                    Obligation.entity_id == ent.id,
                    Obligation.department == Department.compliance,
                    Obligation.status.notin_(
                        [ObligationStatus.completed, ObligationStatus.not_applicable]
                    ),
                )
                .order_by(Obligation.due_date)
            )
            .scalars()
            .all()
        )
        kept: list[Obligation] = []
        dupe_ids: list[int] = []
        for o in active:
            if kept and (o.due_date - kept[-1].due_date).days <= 7:
                dupe_ids.append(o.id)
            else:
                kept.append(o)
        if dupe_ids:
            db.execute(sa_delete(Obligation).where(Obligation.id.in_(dupe_ids)))
        if not kept:
            db.add(
                Obligation(
                    rule_id=rule.id,
                    entity_id=ent.id,
                    due_date=due,
                    status=ObligationStatus.not_started,
                    department=Department.compliance,
                    assignee_id=rule.owner_id,
                )
            )
        elif rule.owner_id and kept[0].assignee_id != rule.owner_id:
            kept[0].assignee_id = rule.owner_id


def _delete_pending_for_entity_rule(db: Session, rule_id: int, entity_id: int) -> None:
    """Remove one entity's not-yet-completed obligations for a rule (e.g. when
    the entity's answers make the filing not applicable). Completed kept."""
    from compliance_agent.db import ObligationStatus

    db.execute(
        sa_delete(Obligation).where(
            Obligation.rule_id == rule_id,
            Obligation.entity_id == entity_id,
            Obligation.status.in_(
                [ObligationStatus.not_started, ObligationStatus.in_progress]
            ),
        )
    )


def remove_pending_obligations_for_rule(db: Session, rule: Rule) -> None:
    """Remove a rule's not-yet-completed obligations from the calendar (e.g.
    when it's archived). Completed filings are kept for history."""
    from compliance_agent.db import ObligationStatus

    db.execute(
        sa_delete(Obligation).where(
            Obligation.rule_id == rule.id,
            Obligation.status.in_(
                [ObligationStatus.not_started, ObligationStatus.in_progress]
            ),
        )
    )


@router.post("/ensure-calendar")
def ensure_calendar(
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Reconcile the calendar with rule status. Every APPROVED (production) rule
    gets its calendar obligation; anything still in Review & Assign (staging) has
    its pending obligations removed — so the calendar reflects ONLY approved
    rules, and any in-review obligations left over from the old behaviour are
    cleaned up. Safe to call repeatedly — idempotent."""
    rules = (
        db.execute(
            select(Rule).where(
                Rule.status.in_([RuleStatus.staging, RuleStatus.production])
            )
        )
        .scalars()
        .all()
    )
    made = 0
    for rule in rules:
        try:
            if rule.status == RuleStatus.production:
                ensure_obligations_for_rule(db, rule)
            else:
                remove_pending_obligations_for_rule(db, rule)
            made += 1
        except Exception:  # noqa: BLE001 — one bad rule shouldn't block the rest
            continue
    db.commit()
    return {"checked": len(rules), "processed": made}


def _serialize_rule(rule: Rule, entity_applicability: Optional[str] = None) -> RuleOut:
    _current_owner = rule.responsible_function or derive_function(rule.category, rule.area)
    _engine_owner = owner_team_engine(
        rule.name, rule.authority, rule.category, rule.area,
        getattr(rule, "triggering_activity", None),
    )
    return RuleOut(
        entity_applicability=entity_applicability,
        id=rule.id,
        name=rule.name,
        jurisdiction_code=rule.jurisdiction_code,
        category=rule.category,
        area=rule.area,
        form_name=rule.form_name,
        authority=rule.authority,
        frequency=rule.frequency,
        due_date_rule=rule.due_date_rule,
        due_date_spec=getattr(rule, "due_date_spec", None),
        payment_rule=rule.payment_rule,
        applicability=rule.applicability,
        applicability_note=rule.applicability_note,
        responsible_function=_current_owner,
        owner_team_suggested=(_engine_owner if _engine_owner != _current_owner else None),
        confidence=getattr(rule, "confidence", None),
        tax_type=(
            derive_tax_type(rule.name, rule.form_name, rule.category, rule.area)
            or rule.tax_type
        ),
        status=rule.status,
        source_url=rule.source_url,
        submission_url=rule.submission_url,
        source_text=rule.source_text,
        source_changed_at=rule.source_changed_at,
        entity_ids=[e.id for e in rule.entities],
        owner_id=rule.owner_id,
        reviewer_id=rule.reviewer_id,
        approver_id=rule.approver_id,
        approved_at=rule.approved_at,
        sent_to_review=rule.sent_to_review,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.post("/dedupe")
def dedupe_rules(
    status: Optional[RuleStatus] = Query(None),
    in_review: Optional[bool] = Query(None),
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
):
    """On-demand AI de-dup for the Review & Assign list — for duplicates that
    already reached the list (which the discovery-time pass deliberately leaves
    alone). Groups the matching rules by entity and clusters each entity's set
    with the model. Never removes an Approved (production) rule; collapses
    redundant staging / archived copies (and their per-entity obligations),
    always keeping the safest copy. Mirrors the For Action filter via in_review."""
    from collections import defaultdict
    from compliance_agent.api.entities import _run_ai_dedupe

    stmt = select(Rule)
    if status is not None:
        stmt = stmt.where(Rule.status == status)
    if in_review:
        stmt = stmt.where(Rule.sent_to_review.is_(True))
    rules = db.execute(stmt).scalars().all()

    by_entity: dict = defaultdict(list)
    for r in rules:
        for e in r.entities:
            by_entity[e].append(r)

    removed = 0
    for entity, ent_rules in by_entity.items():
        removed += _run_ai_dedupe(
            db,
            entity,
            ent_rules,
            removable=lambda r: r.status != RuleStatus.production,
            min_count=2,
        )
    if removed:
        log_activity(
            db, actor_id=user.id, action="rules.deduped",
            target_type="rule", target_id=None, payload={"removed": removed},
        )
    db.commit()
    return {"removed": removed}


@router.get("", response_model=list[RuleOut])
def list_rules(
    jurisdiction_code: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[RuleStatus] = Query(None),
    entity_id: Optional[int] = Query(
        None,
        description="When set, annotate each rule with its Primary-Activity "
        "verdict (applicable / not_applicable) for that entity.",
    ),
    in_review: Optional[bool] = Query(
        None,
        description="When true, only rules a human has explicitly sent to "
        "Review & Assign (sent_to_review is True); hides discovered drafts.",
    ),
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[RuleOut]:
    stmt = select(Rule)
    if jurisdiction_code:
        stmt = stmt.where(Rule.jurisdiction_code == jurisdiction_code)
    if category:
        stmt = stmt.where(Rule.category == category)
    if status:
        stmt = stmt.where(Rule.status == status)
    if in_review:
        stmt = stmt.where(Rule.sent_to_review.is_(True))
    stmt = stmt.order_by(Rule.jurisdiction_code, Rule.category, Rule.name)
    rows = db.execute(stmt).scalars().all()
    # FINANCE_ONLY switch: hide non-Finance rules from the catalog.
    rows = [r for r in rows if keep_function(r.category, r.area, r.responsible_function)]

    profile = None
    if entity_id is not None:
        ent = db.get(Entity, entity_id)
        profile = getattr(ent, "finance_profile", None) if ent else None

    def verdict(r: Rule) -> Optional[str]:
        if entity_id is None:
            return None
        return entity_applicability(
            profile, name=r.name, form_name=r.form_name,
            category=r.category, area=r.area,
        )

    return [_serialize_rule(r, verdict(r)) for r in rows]


@router.get("/{rule_id}", response_model=RuleOut)
def get_rule(
    rule_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> RuleOut:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    return _serialize_rule(rule)


def _attach_entities(rule: Rule, entity_ids: list[int], db: Session) -> None:
    if not entity_ids:
        rule.entities = []
        return
    entities = db.execute(select(Entity).where(Entity.id.in_(entity_ids))).scalars().all()
    rule.entities = list(entities)


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(
    payload: RuleCreate,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> RuleOut:
    data = payload.model_dump()
    entity_ids = data.pop("entity_ids", [])
    rule = Rule(**data, created_by_id=user.id)
    db.add(rule)
    db.flush()
    _attach_entities(rule, entity_ids, db)
    log_activity(
        db, actor_id=user.id, action="rule.created", target_type="rule", target_id=rule.id
    )
    db.commit()
    db.refresh(rule)
    return _serialize_rule(rule)


@router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: int,
    payload: RuleUpdate,
    db: Session = Depends(get_session),
    user: User = Depends(require_admin),
) -> RuleOut:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    old_status = rule.status
    old_owner_id = rule.owner_id
    data = payload.model_dump(exclude_unset=True)
    entity_ids = data.pop("entity_ids", None)
    for field, value in data.items():
        setattr(rule, field, value)
    if entity_ids is not None:
        _attach_entities(rule, entity_ids, db)

    # When the Due-Date Builder sets a structured spec, keep the human-readable
    # frequency + due_date_rule columns in sync from it (they drive table/export
    # display while the spec drives the calendar).
    if "due_date_spec" in data and rule.due_date_spec:
        from compliance_agent.due_date_spec import summarize, freq_label

        rule.due_date_rule = summarize(rule.due_date_spec) or rule.due_date_rule
        label = freq_label(rule.due_date_spec)
        if label:
            rule.frequency = label

    # A staging → production transition is a meaningful milestone — log it
    # distinctly so it shows clearly in the activity feed.
    promoted = (
        old_status != RuleStatus.production
        and rule.status == RuleStatus.production
    )
    # Stamp the approval time + approver when an obligation is confirmed.
    if promoted:
        rule.approved_at = datetime.utcnow()
        if rule.approver_id is None:
            rule.approver_id = user.id

    # Calendar sync: a rule appears on the calendar ONLY once it's APPROVED
    # (production). While it's in Review & Assign (staging / sent_to_review) or
    # archived, any pending obligation is removed so it stays off the calendar
    # until approval.
    if rule.status == RuleStatus.production:
        ensure_obligations_for_rule(db, rule)
        # Assigning an owner here ("Approve & assign" / the Approved-tab
        # dropdown) syncs the obligations' assignee above — notify them
        # directly (in-app + Slack + the branded assignment email), same as a
        # direct assignment on the Filings page. emit_assignment itself skips
        # self-assignments and is best-effort.
        if rule.owner_id and rule.owner_id != old_owner_id:
            from compliance_agent.api.notifications import emit_assignment
            from compliance_agent.db import ObligationStatus

            # The session runs autoflush=False — flush so the obligations
            # ensure_obligations_for_rule just created/re-assigned are visible
            # to the query below (otherwise it reads the pre-approve DB state,
            # finds nothing, and no assignment email ever goes out).
            db.flush()
            new_owner = db.get(User, rule.owner_id)
            if new_owner is not None:
                assigned_obs = (
                    db.execute(
                        select(Obligation)
                        .where(
                            Obligation.rule_id == rule.id,
                            Obligation.assignee_id == rule.owner_id,
                            Obligation.status.not_in(
                                [ObligationStatus.completed, ObligationStatus.not_applicable]
                            ),
                        )
                        .order_by(Obligation.due_date)
                    )
                    .scalars()
                    .all()
                )
                for ob in assigned_obs:
                    try:
                        emit_assignment(db, assignee=new_owner, obligation=ob, actor=user)
                    except Exception:  # noqa: BLE001 — never block the approval on notify
                        import logging

                        logging.getLogger(__name__).warning(
                            "emit_assignment failed for obligation %s", ob.id, exc_info=True
                        )
    else:
        remove_pending_obligations_for_rule(db, rule)
    log_activity(
        db,
        actor_id=user.id,
        action="rule.promoted" if promoted else "rule.updated",
        target_type="rule",
        target_id=rule.id,
        payload={"form_name": rule.form_name, "from": old_status.value, "to": rule.status.value}
        if promoted
        else None,
    )
    db.commit()
    # Google Calendar sync for this rule's open obligations (post-commit so
    # the background thread sees the approved/assigned state).
    from compliance_agent import calendar_service

    if calendar_service.is_configured():
        from compliance_agent.db import ObligationStatus as _OS

        ob_ids = db.execute(
            select(Obligation.id).where(
                Obligation.rule_id == rule.id,
                Obligation.status.not_in([_OS.completed, _OS.not_applicable]),
            )
        ).scalars().all()
        for oid in ob_ids:
            calendar_service.sync_obligation(oid)
    db.refresh(rule)
    return _serialize_rule(rule)


# ---------------------------------------------------------------------------
# Delete — hard-remove a rule and everything that hangs off it.
# ---------------------------------------------------------------------------
def _delete_rule_cascade(db: Session, rule: Rule) -> int:
    """Delete a rule plus its obligations (and their comments/notifications),
    keeping any uploaded proof documents (just unlinked). rule_entities and
    rule snapshots are cleared explicitly so it works even where the legacy
    production FKs predate ON DELETE clauses. Returns the obligation count
    that was removed."""
    ob_ids = [
        oid
        for (oid,) in db.execute(
            select(Obligation.id).where(Obligation.rule_id == rule.id)
        ).all()
    ]
    if ob_ids:
        db.execute(
            sa_update(Document)
            .where(Document.obligation_id.in_(ob_ids))
            .values(obligation_id=None)
        )
        db.execute(sa_delete(Notification).where(Notification.obligation_id.in_(ob_ids)))
        db.execute(sa_delete(Comment).where(Comment.obligation_id.in_(ob_ids)))
        db.execute(sa_delete(Obligation).where(Obligation.id.in_(ob_ids)))

    db.execute(sa_delete(RuleSnapshot).where(RuleSnapshot.rule_id == rule.id))
    # rule_entities is the secondary link table — clear the associations.
    rule.entities = []
    db.flush()
    db.delete(rule)
    return len(ob_ids)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> Response:
    """Admin-only: permanently delete a rule (staging or production) and any
    filings scheduled from it. Proof documents are kept (unlinked)."""
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    form_name = rule.form_name
    removed = _delete_rule_cascade(db, rule)
    log_activity(
        db,
        actor_id=actor.id,
        action="rule.deleted",
        target_type="rule",
        target_id=rule_id,
        payload={"form_name": form_name, "obligations_removed": removed},
    )
    db.commit()
    return Response(status_code=204)


class BulkDeletePayload(BaseModel):
    ids: list[int]


class BulkDeleteResult(BaseModel):
    deleted: int


@router.post("/bulk-delete", response_model=BulkDeleteResult)
def bulk_delete_rules(
    payload: BulkDeletePayload,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> BulkDeleteResult:
    """Admin-only: permanently delete exactly the given rules (and their
    obligations). Used to clear ONE section (For Action / Approved / Archived)
    independently — the caller passes only that section's rule ids, so clearing
    one section never touches the others."""
    deleted = 0
    for rid in payload.ids:
        rule = db.get(Rule, rid)
        if rule is not None:
            _delete_rule_cascade(db, rule)
            deleted += 1
    log_activity(
        db, actor_id=actor.id, action="rules.bulk_deleted",
        target_type="rule", target_id=None, payload={"deleted": deleted},
    )
    db.commit()
    return BulkDeleteResult(deleted=deleted)


class CleanupRecentResult(BaseModel):
    deleted_rules: int
    deleted_obligations: int


@router.post("/cleanup-recent-production", response_model=CleanupRecentResult)
def cleanup_recent_production(
    hours: int = Query(24, ge=1, le=168),
    mine_only: bool = Query(True),
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> CleanupRecentResult:
    """Admin-only cleanup: delete STAGING (draft / AI-extracted) rules created
    in the last N hours (default 24). Production catalogue rules are NEVER
    touched here, so an experiment can't wipe the live catalogue. By default
    limited to rules the calling admin created. Also removes any filings
    scheduled from those draft rules; proof documents are kept (unlinked)."""
    # created_at is stored naive (server now()), so compare against a naive
    # UTC cutoff to avoid tz-offset surprises on Postgres.
    cutoff = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    conds = [Rule.status == RuleStatus.staging, Rule.created_at >= cutoff]
    if mine_only:
        conds.append(Rule.created_by_id == actor.id)

    rules = db.execute(select(Rule).where(*conds)).scalars().all()
    total_obs = 0
    for r in rules:
        total_obs += _delete_rule_cascade(db, r)
    log_activity(
        db,
        actor_id=actor.id,
        action="rules.cleanup_recent_production",
        target_type="rule",
        target_id=None,
        payload={
            "hours": hours,
            "mine_only": mine_only,
            "deleted_rules": len(rules),
            "deleted_obligations": total_obs,
        },
    )
    db.commit()
    return CleanupRecentResult(deleted_rules=len(rules), deleted_obligations=total_obs)


class RestoreCatalogueResult(BaseModel):
    rules_total: int


@router.post("/restore-catalogue", response_model=RestoreCatalogueResult)
def restore_catalogue(
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> RestoreCatalogueResult:
    """Admin-only recovery: idempotently re-create every catalogue rule that's
    missing from the live DB (e.g. after an accidental delete) and re-attach
    them to existing entities. Safe to run repeatedly — existing rules are left
    untouched and no obligations are created. No server shell needed."""
    from compliance_agent.db.seed import sync_catalog_rules

    total = sync_catalog_rules()
    log_activity(
        db,
        actor_id=actor.id,
        action="rules.restore_catalogue",
        target_type="rule",
        target_id=None,
        payload={"rules_total": total},
    )
    db.commit()
    return RestoreCatalogueResult(rules_total=total)


class WipeCatalogueResult(BaseModel):
    rules: int
    obligations: int


@router.post("/wipe-catalogue", response_model=WipeCatalogueResult)
def wipe_catalogue_endpoint(
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> WipeCatalogueResult:
    """Admin-only: empty the catalogue + calendar — delete EVERY rule and
    obligation (and their dependent rows). Keeps users / entities / licenses.
    For the AI-first flow: start clean, then rebuild via 'Find Regulations' →
    approve to production. No server shell needed."""
    from compliance_agent.db.seed import wipe_catalogue

    counts = wipe_catalogue()
    log_activity(
        db,
        actor_id=actor.id,
        action="rules.wipe_catalogue",
        target_type="rule",
        target_id=None,
        payload=counts,
    )
    db.commit()
    return WipeCatalogueResult(
        rules=counts.get("rules", 0), obligations=counts.get("obligations", 0)
    )


class BackfillUrlsResult(BaseModel):
    checked: int
    source_filled: int
    submission_filled: int
    skipped_no_match: int


@router.post("/backfill-source-urls", response_model=BackfillUrlsResult)
def backfill_source_urls(
    overwrite: bool = Query(False),
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> BackfillUrlsResult:
    """Admin-only: fill every rule's regulator source_url + submission_url from
    the authority lookup table, so the 'View regulation' / 'Submit & pay on
    portal' links appear on obligations. Only fills empty URLs unless
    overwrite=true. Idempotent."""
    from compliance_agent.db.seed import populate_source_urls

    counts = populate_source_urls(overwrite=overwrite)
    log_activity(
        db,
        actor_id=actor.id,
        action="rules.backfill_source_urls",
        target_type="rule",
        target_id=None,
        payload=counts,
    )
    db.commit()
    return BackfillUrlsResult(**counts)


# ---------------------------------------------------------------------------
# Snapshots (Phase 7) — history of regulation-change checks
# ---------------------------------------------------------------------------
from sqlalchemy.orm import joinedload as _joinedload


@router.get("/{rule_id}/snapshots", response_model=list[RuleSnapshotOut])
def list_rule_snapshots(
    rule_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[RuleSnapshotOut]:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    rows = db.execute(
        select(RuleSnapshot)
        .where(RuleSnapshot.rule_id == rule_id)
        .options(_joinedload(RuleSnapshot.fetched_by))
        .order_by(RuleSnapshot.fetched_at.desc())
        .limit(50)
    ).scalars().unique().all()
    return [
        RuleSnapshotOut(
            id=s.id,
            rule_id=s.rule_id,
            fetched_at=s.fetched_at,
            fetched_by=serialize_user(s.fetched_by),
            http_status=s.http_status,
            content_length=s.content_length,
            content_hash=s.content_hash,
            content_excerpt=s.content_excerpt,
            change_summary=s.change_summary,
        )
        for s in rows
    ]


# ---------------------------------------------------------------------------
# AI page summary — fetch the rule's source_url, ask Claude to extract
# the form name, where to download the template, and key filing rules.
# Read-only, no DB writes. Used by the "Ask Claude about this page" button
# on the obligation drawer + the rules table.
# ---------------------------------------------------------------------------
class PageSummary(BaseModel):
    available: bool
    rule_id: int
    url: Optional[str] = None
    form_name: Optional[str] = None
    template_url: Optional[str] = None
    key_requirements: list[str] = []
    summary: Optional[str] = None
    error: Optional[str] = None


@router.post("/{rule_id}/read-source", response_model=PageSummary)
def read_source_with_claude(
    rule_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> PageSummary:
    """Have Claude read the rule's regulator page and surface the form
    template name, where to download it, and the key requirements.
    Compliance + finance both call this — anyone with a login can read
    the regulation summary."""
    from compliance_agent.ai import ai_available
    from compliance_agent.ai.llm_client import make_client
    from compliance_agent.ai.regulation_watcher import _fetch

    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")

    url = (rule.source_url or "").strip()
    if not url:
        return PageSummary(
            available=False,
            rule_id=rule_id,
            error="No source URL set for this rule. Admin can add one on Compliance Rules → click the source cell.",
        )

    if not ai_available():
        return PageSummary(
            available=False,
            rule_id=rule_id,
            url=url,
            error="AI is off. Set COMPLIANCE_AGENT_LIVE=1 + an API key on the server.",
        )

    status, text, err = _fetch(url)
    if err or not text:
        return PageSummary(
            available=False,
            rule_id=rule_id,
            url=url,
            error=err or "Empty page body — regulator may have blocked the fetch.",
        )

    text = text[:20000]  # cap input

    system = (
        "You read regulator portal pages and extract three things that a "
        "compliance team needs before filing:\n"
        "  1. form_name   — the official name/code of the form (e.g. "
        "     'GSTR-3B', 'Form 16A', 'STR via FINCAR'). null if not "
        "     explicit on the page.\n"
        "  2. template_url — an absolute URL on the same domain that links "
        "     directly to the form template / PDF / instructions. null if "
        "     not found.\n"
        "  3. key_requirements — 3-6 bullets of must-do items the filer "
        "     needs to remember (deadlines, attachments, fees, where to "
        "     submit). One sentence each, plain English.\n"
        "Also write a 2-sentence summary of what this filing is for.\n"
        "If the page is irrelevant or a generic homepage, set form_name and "
        "template_url to null and explain in summary."
    )

    tool = {
        "name": "record_summary",
        "description": "Record the extracted page summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "form_name": {"type": ["string", "null"]},
                "template_url": {"type": ["string", "null"]},
                "key_requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "summary": {"type": "string"},
            },
            "required": ["summary", "key_requirements"],
        },
    }

    try:
        client = make_client()
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1500,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": "record_summary"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Rule context: form_name={rule.form_name!r}, "
                        f"authority={rule.authority!r}, "
                        f"frequency={rule.frequency!r}.\n\n"
                        f"Page text from {url}:\n\n~~~\n{text}\n~~~"
                    ),
                }
            ],
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "record_summary":
                raw = block.input or {}
                return PageSummary(
                    available=True,
                    rule_id=rule_id,
                    url=url,
                    form_name=raw.get("form_name"),
                    template_url=raw.get("template_url"),
                    key_requirements=raw.get("key_requirements") or [],
                    summary=raw.get("summary"),
                )
    except Exception as e:  # noqa: BLE001
        return PageSummary(
            available=False, rule_id=rule_id, url=url, error=f"Claude call failed: {e}"
        )
    return PageSummary(
        available=False, rule_id=rule_id, url=url, error="No structured response from Claude."
    )


@router.post("/{rule_id}/verify-due-date")
def verify_rule_due_date(
    rule_id: int,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> dict:
    """Verify this rule's filing deadline against the LIVE regulator source via
    Claude's web search. Read-only: returns the confirmed deadline + a citation
    (source URL + verbatim quote) + confidence. Does NOT mutate the rule — a
    human decides whether to apply it. Anthropic-only (web search)."""
    from compliance_agent.ai.due_date_verifier import verify_due_date_from_source

    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")

    result = verify_due_date_from_source(
        form_name=rule.form_name or rule.name,
        authority=rule.authority,
        jurisdiction=rule.jurisdiction_code,
        frequency=rule.frequency,
        current_rule_text=rule.due_date_rule,
    )
    if result.available:
        log_activity(
            db,
            actor_id=actor.id,
            action="rule.due_date_verified",
            target_type="rule",
            target_id=rule_id,
            payload={"verified": result.verified, "source_url": result.source_url},
        )
        db.commit()
    return result.model_dump()


class ApplyDueDatePayload(BaseModel):
    due_date_rule: str
    source_url: Optional[str] = None


@router.post("/{rule_id}/apply-due-date")
def apply_rule_due_date(
    rule_id: int,
    payload: ApplyDueDatePayload,
    db: Session = Depends(get_session),
    actor: User = Depends(require_admin),
) -> dict:
    """Apply a verified deadline to the rule: overwrite due_date_rule (+ source
    URL), then recompute and update the pending obligations' due dates from the
    new rule. Used by the 'Apply' action after source verification."""
    from datetime import date
    from compliance_agent.api.licenses import _next_due_for_rule, _parse_fy_end
    from compliance_agent.db import ObligationStatus

    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    new_text = (payload.due_date_rule or "").strip()
    if not new_text:
        raise HTTPException(status_code=400, detail="due_date_rule is required.")

    rule.due_date_rule = new_text
    if payload.source_url:
        rule.source_url = payload.source_url.strip()
    db.flush()

    # Recompute each entity's next due date from the corrected rule and move its
    # pending (not completed / not-applicable) obligations onto that date.
    today = date.today()
    updated = 0
    next_due = None
    for ent in rule.entities:
        new_due = _next_due_for_rule(rule, today, _parse_fy_end(ent.fiscal_year_end))
        next_due = new_due
        obs = (
            db.execute(
                select(Obligation).where(
                    Obligation.rule_id == rule.id,
                    Obligation.entity_id == ent.id,
                    Obligation.status.notin_(
                        [ObligationStatus.completed, ObligationStatus.not_applicable]
                    ),
                )
            )
            .scalars()
            .all()
        )
        for ob in obs:
            ob.due_date = new_due
            updated += 1

    log_activity(
        db,
        actor_id=actor.id,
        action="rule.due_date_applied",
        target_type="rule",
        target_id=rule_id,
        payload={"due_date_rule": new_text, "obligations_updated": updated},
    )
    db.commit()
    return {
        "due_date_rule": rule.due_date_rule,
        "source_url": rule.source_url,
        "obligations_updated": updated,
        "next_due": next_due.isoformat() if next_due else None,
    }
