"""Seed the Aspora Compliance OS database with demo data.

Re-runnable. Idempotent on emails and (rule_id, entity_id, due_date) keys.

What it creates:
  - 2 demo users: admin@aspora.com / employee@aspora.com (passwords below)
  - 12 Aspora entities (UK, US, India, EU/Luxembourg, UAE, Singapore,
    Canada, Lithuania, Jersey, Cayman, ADGM, GIFT-IFSC)
  - Rules — one per filing in the curated `fintech` catalog (~274), each
    attached to all entities in the matching jurisdiction
  - Obligations — for each rule, one or more concrete obligations for
    each attached entity, with realistic due dates in the next 90 days
    (and some in the past so the dashboard shows overdue counts)
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_agent.auth.passwords import hash_password
from compliance_agent.classification import derive_function
from compliance_agent.db import (
    Applicability,
    Department,
    EffortBand,
    Entity,
    Obligation,
    ObligationStatus,
    Role,
    Rule,
    RuleStatus,
    TaxType,
    User,
    session_scope,
)


def _effort_band_for_frequency(frequency: str) -> EffortBand:
    """Pick a sensible default effort band per filing cadence."""
    f = (frequency or "").lower()
    if "monthly" in f or "continuous" in f:
        return EffortBand.w1
    if "quarterly" in f:
        return EffortBand.w2
    if "half" in f:
        return EffortBand.w4
    if "annual" in f or "bi-annual" in f or "one-time" in f:
        return EffortBand.w8
    if "event" in f:
        return EffortBand.w2
    return EffortBand.w4


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
DEMO_USERS = [
    {
        "email": "pranav.goldar@aspora.com",
        "password": "admin123",
        "full_name": "Pranav Goldar",
        "role": Role.admin,
    },
    {
        "email": "pranavgoldar@gmail.com",
        "password": "aspora2026",
        "full_name": "Pranav (Operations)",
        "role": Role.employee,
    },
    {
        "email": "pranavgoldar.iitb@gmail.com",
        "password": "iitb2026",
        "full_name": "Pranav (IITB)",
        "role": Role.employee,
    },
    {
        "email": "pranavgoldar.moodi@gmail.com",
        "password": "moodi2026",
        "full_name": "Pranav (Moodi)",
        "role": Role.employee,
    },
]


# ---------------------------------------------------------------------------
# Entities (demo data — editable from the UI later)
# ---------------------------------------------------------------------------
# Mirrors the Aspora Global Compliance Tracker — drawn from the "audit
# applicability and tax fil" entity registry plus the Rental Details sheet.
# Two India entities use a Mar fiscal year end; everyone else is Dec.
DEMO_ENTITIES = [
    # === USA ===
    {
        "name": "Vance Inc.",
        "short_code": "VINC",
        "legal_type": "C-Corporation",
        "jurisdiction_code": "us",
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranav.goldar@aspora.com",
    },
    {
        "name": "Vance Money Services LLC",
        "short_code": "VMS",
        "legal_type": "LLC (Money Services Business)",
        "jurisdiction_code": "us",
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranav.goldar@aspora.com",
    },
    # === United Kingdom ===
    {
        "name": "Real Transfer Limited",
        "short_code": "RTUK",
        "legal_type": "Private Limited Company",
        "jurisdiction_code": "uk",
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranavgoldar.iitb@gmail.com",
    },
    {
        "name": "Vance Technologies Limited",
        "short_code": "VTUK",
        "legal_type": "Private Limited Company",
        "jurisdiction_code": "uk",
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranavgoldar.iitb@gmail.com",
    },
    # === UAE ===
    {
        "name": "Vance Techlabs Limited",
        "short_code": "VTAE",
        "legal_type": "DIFC Private Company",
        "jurisdiction_code": "uae",
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranavgoldar.moodi@gmail.com",
    },
    {
        "name": "Aspora Money Services Limited",
        "short_code": "VMAE",
        "legal_type": "DIFC Private Company",
        "jurisdiction_code": "uae",
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranavgoldar.moodi@gmail.com",
    },
    {
        "name": "Vance Technologies Holding Limited",
        "short_code": "VTHL",
        "legal_type": "DIFC Holding Company",
        "jurisdiction_code": "uae",
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranavgoldar.moodi@gmail.com",
    },
    {
        "name": "Nesse Tech FZE",
        "short_code": "NFZE",
        "legal_type": "Free Zone Establishment",
        "jurisdiction_code": "uae",
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranavgoldar.moodi@gmail.com",
    },
    {
        "name": "Aspora Financial Services L.L.C",
        "short_code": "AFAE",
        "legal_type": "Mainland L.L.C.",
        "jurisdiction_code": "uae",
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranavgoldar.moodi@gmail.com",
    },
    # === Canada ===
    {
        "name": "Nesse Technologies Inc.",
        "short_code": "NESS",
        "legal_type": "Federal Corporation",
        "jurisdiction_code": "canada",
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranav.goldar@aspora.com",
    },
    # === Singapore ===
    {
        "name": "Vance Techlabs PTE Ltd",
        "short_code": "VTSG",
        "legal_type": "Private Limited",
        "jurisdiction_code": "singapore",
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranavgoldar.moodi@gmail.com",
    },
    # === Lithuania ===
    {
        "name": "Vance Techlabs UAB",
        "short_code": "VTLT",
        "legal_type": "Uždaroji akcinė bendrovė",
        "jurisdiction_code": "lithuania",
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranav.goldar@aspora.com",
    },
    # === India ===
    {
        "name": "Sophisto India Private Limited",
        "short_code": "EOR",
        "legal_type": "Private Limited",
        "jurisdiction_code": "india",
        "fiscal_year_end": "31-Mar",
        "country_lead_email": "pranavgoldar@gmail.com",
    },
    {
        "name": "Aspora Financial Services (IFSC) Private Limited",
        "short_code": "ASIN",
        "legal_type": "IFSC Private Limited",
        "jurisdiction_code": "india",
        "fiscal_year_end": "31-Mar",
        "country_lead_email": "pranavgoldar@gmail.com",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_users(db: Session) -> dict[str, User]:
    users: dict[str, User] = {}
    for spec in DEMO_USERS:
        existing = db.execute(select(User).where(User.email == spec["email"])).scalar_one_or_none()
        if existing:
            users[spec["email"]] = existing
            continue
        user = User(
            email=spec["email"],
            password_hash=hash_password(spec["password"]),
            full_name=spec["full_name"],
            role=spec["role"],
        )
        db.add(user)
        users[spec["email"]] = user
    db.flush()
    return users


def _ensure_entities(db: Session, users: dict[str, User]) -> dict[str, Entity]:
    entities: dict[str, Entity] = {}
    for spec in DEMO_ENTITIES:
        existing = db.execute(select(Entity).where(Entity.name == spec["name"])).scalar_one_or_none()
        if existing:
            entities[spec["name"]] = existing
            continue
        lead = users.get(spec.pop("country_lead_email", ""))
        entity = Entity(**spec, country_lead_id=lead.id if lead else None)
        db.add(entity)
        entities[spec["name"]] = entity
    db.flush()
    return entities


def _authority_url(authority: str) -> Optional[str]:
    """Lookup helper — kept tiny so the seed import stays cheap."""
    from compliance_agent.data.authority_urls import lookup
    return lookup(authority or "")


def _applicability_from_str(s: str) -> Applicability:
    s = (s or "").strip().lower()
    if s.startswith("mandatory"):
        return Applicability.mandatory
    if s.startswith("conditional"):
        return Applicability.conditional
    return Applicability.sector_specific


def _tax_type_from_category(category: str, area: str = "") -> TaxType:
    """Conservative category-based tax classification for seeded catalog rows.

    Indirect = consumption / transaction taxes (GST, VAT, sales, excise,
    customs). Direct = taxes on income / profits / gains. Everything else
    (AML, data protection, regulatory returns, payroll filings, etc.) is
    treated as Not a Tax. The AI extractor classifies per-rule for uploaded
    licenses; this just gives the pre-loaded catalog sensible defaults."""
    hay = f"{category} {area}".lower()
    indirect_markers = ("gst", "vat", "sales/use", "sales tax", "use tax",
                        "excise", "customs", "import duty", "indirect")
    direct_markers = ("corporate tax", "income tax", "capital gains",
                      "corporate income", "direct tax")
    if any(m in hay for m in indirect_markers):
        return TaxType.indirect
    if any(m in hay for m in direct_markers):
        return TaxType.direct
    return TaxType.not_tax


def _ensure_rules(db: Session, entities: list[Entity]) -> list[Rule]:
    """One Rule per fintech-catalog filing, attached to all entities in that
    jurisdiction. Idempotent on (jurisdiction_code, form_name)."""
    from compliance_agent.fintech import CATALOG as FINTECH_CATALOG

    by_jurisdiction: dict[str, list[Entity]] = {}
    for e in entities:
        by_jurisdiction.setdefault(e.jurisdiction_code, []).append(e)

    created: list[Rule] = []
    for country_code, country_filings in FINTECH_CATALOG.items():
        jurisdiction_entities = by_jurisdiction.get(country_code, [])
        for filing in country_filings.filings:
            existing = db.execute(
                select(Rule).where(
                    Rule.jurisdiction_code == country_code,
                    Rule.form_name == filing.form_name,
                )
            ).scalar_one_or_none()
            if existing:
                # Sync entity attachments in case new entities were added.
                if jurisdiction_entities and not existing.entities:
                    existing.entities = list(jurisdiction_entities)
                # Backfill the responsible function on older rows.
                if not existing.responsible_function:
                    existing.responsible_function = derive_function(
                        existing.category, existing.area
                    )
                created.append(existing)
                continue
            rule = Rule(
                name=filing.form_name,
                jurisdiction_code=country_code,
                category=filing.category,
                area=filing.area,
                form_name=filing.form_name,
                authority=filing.authority,
                frequency=filing.frequency,
                due_date_rule=filing.due_date_rule,
                payment_rule=filing.payment_due,
                applicability=_applicability_from_str(filing.applicability),
                applicability_note=filing.applicability_note,
                tax_type=_tax_type_from_category(filing.category, filing.area),
                responsible_function=derive_function(filing.category, filing.area),
                source_url=_authority_url(filing.authority),
                submission_url=_authority_url(filing.authority),
                status=RuleStatus.production,
            )
            rule.entities = list(jurisdiction_entities)
            db.add(rule)
            created.append(rule)
    db.flush()
    return created


_FREQUENCY_TO_OFFSETS_DAYS: dict[str, list[int]] = {
    # Negative = past (overdue / completed). Positive = future.
    "Monthly": [-45, -15, 5, 15, 25, 35, 45, 60, 75, 90],
    "Quarterly": [-60, 10, 40, 75],
    "Half-Yearly": [-30, 80],
    "Annual": [25, 120, 250],
    "Bi-annual (every 2 years)": [180],
    "Event-based": [-5, 8, 22],
    "Continuous": [-3, 12],
    "One-time": [40],
}


def _offsets_for_frequency(frequency: str) -> list[int]:
    f = (frequency or "").strip()
    # Match the most specific token first.
    for key, offsets in _FREQUENCY_TO_OFFSETS_DAYS.items():
        if key.lower() in f.lower():
            return offsets
    return [20, 60]  # safe default


def _needs_payment_split(rule: Rule) -> bool:
    """Deprecated. The original dept-split approach created two obligations
    per filing (one compliance, one finance) which confused users — the
    real workflow is one filing, compliance hands off to finance via
    @-mention / comment. Always returns False; payment tracking now lives
    on the existing single obligation's payment_amount / payment_reference
    fields. Kept as a function so callers don't break.
    """
    _ = rule  # silence linter
    return False


def _ensure_obligations(
    db: Session,
    rules: list[Rule],
    users: dict[str, User],
    *,
    auto_assign: bool = True,
) -> int:
    """Generate obligations for every (rule, entity) combination using the
    frequency to spread due dates across a sensible window.

    auto_assign — when True, distribute obligations randomly across employee
    users. When False, every obligation is created unassigned (admin will
    assign explicitly later).
    """
    base = date.today()
    rng = random.Random(20260525)
    assignable: list[User] = (
        [u for u in users.values() if u.role == Role.employee] if auto_assign else []
    )

    created_count = 0
    for rule in rules:
        offsets = _offsets_for_frequency(rule.frequency)
        split = _needs_payment_split(rule)
        # Each period spawns N legs: always 1 filing; +1 payment if split.
        legs: list[Department] = [Department.compliance]
        if split:
            legs.append(Department.finance)

        for entity in rule.entities:
            for offset in offsets:
                due = base + timedelta(days=offset)

                for dept in legs:
                    existing = db.execute(
                        select(Obligation).where(
                            Obligation.rule_id == rule.id,
                            Obligation.entity_id == entity.id,
                            Obligation.due_date == due,
                            Obligation.department == dept,
                        )
                    ).scalar_one_or_none()
                    if existing:
                        continue

                    # Status spread — same logic as before, derived per leg
                    # so the two legs of one filing aren't always in lockstep.
                    if offset < -30:
                        status = ObligationStatus.completed
                    elif offset < -5:
                        status = rng.choice(
                            [
                                ObligationStatus.completed,
                                ObligationStatus.in_progress,
                                ObligationStatus.not_started,
                            ]
                        )
                    elif offset < 0:
                        status = rng.choice(
                            [ObligationStatus.not_started, ObligationStatus.in_progress]
                        )
                    elif offset < 14:
                        status = rng.choice(
                            [
                                ObligationStatus.not_started,
                                ObligationStatus.in_progress,
                                ObligationStatus.pending_review,
                            ]
                        )
                    else:
                        status = ObligationStatus.not_started

                    assignee = rng.choice(assignable) if assignable else None

                    completed_at = None
                    completed_by_id = None
                    if status == ObligationStatus.completed:
                        from datetime import datetime, timezone

                        completed_at = datetime(
                            due.year, due.month, due.day, tzinfo=timezone.utc
                        )
                        completed_by_id = assignee.id if assignee else None

                    notes = None
                    if dept == Department.finance:
                        notes = (
                            f"Pay leg of {rule.form_name}. "
                            f"Verify amount + payment reference; mark complete "
                            f"once funds clear."
                        )

                    obligation = Obligation(
                        rule_id=rule.id,
                        entity_id=entity.id,
                        due_date=due,
                        period_label=_period_label_for_frequency(rule.frequency, due),
                        status=status,
                        department=dept,
                        effort_band=_effort_band_for_frequency(rule.frequency),
                        assignee_id=assignee.id if assignee else None,
                        completed_at=completed_at,
                        completed_by_id=completed_by_id,
                        notes=notes,
                    )
                    db.add(obligation)
                    created_count += 1
        # Periodic flush keeps the SQLite transaction reasonably sized.
        if created_count and created_count % 200 == 0:
            db.flush()
    db.flush()
    return created_count


def _period_label_for_frequency(frequency: str, due: date) -> Optional[str]:
    f = (frequency or "").lower()
    if "monthly" in f:
        return due.strftime("%b %Y")
    if "quarterly" in f:
        return f"Q{(due.month - 1)//3 + 1} {due.year}"
    if "half" in f:
        return f"H{1 if due.month <= 6 else 2} {due.year}"
    if "annual" in f:
        return f"FY {due.year}"
    return None


# ---------------------------------------------------------------------------
# Top-level seed entry point
# ---------------------------------------------------------------------------
def _backfill_effort_bands(db: Session) -> int:
    """For obligations that still have the default '4w' band, derive a more
    sensible one from the rule's frequency. Runs once after the column is
    added; idempotent because it only touches the default value."""
    rows = db.execute(
        select(Obligation).where(Obligation.effort_band == EffortBand.w4)
    ).scalars().all()
    touched = 0
    for ob in rows:
        target = _effort_band_for_frequency(ob.rule.frequency)
        if target != EffortBand.w4:
            ob.effort_band = target
            touched += 1
    if touched:
        db.flush()
    return touched


def run_seed(
    *,
    auto_assign: bool = True,
    create_obligations: bool = True,
) -> dict[str, int]:
    """Idempotent seed. Returns counts of created objects.

    auto_assign — when True (default), randomly distribute obligations
    across the demo employee users so the dashboard / queue look populated.
    Set False for a production-like seed where everything starts unassigned.

    create_obligations — when False, seed only users / entities / rules and
    skip the obligation-generation step entirely. Use this when you want a
    clean state where the admin manually creates obligations off the back of
    licenses they've uploaded. Implies auto_assign=False (no obligations
    to assign).
    """
    from compliance_agent.db import init_db

    init_db()
    with session_scope() as db:
        users = _ensure_users(db)
        entities_map = _ensure_entities(db, users)
        rules = _ensure_rules(db, list(entities_map.values()))
        if create_obligations:
            ob_count = _ensure_obligations(db, rules, users, auto_assign=auto_assign)
        else:
            ob_count = 0
        backfilled = _backfill_effort_bands(db)
    return {
        "users": len(users),
        "entities": len(entities_map),
        "rules": len(rules),
        "obligations_created": ob_count,
        "effort_bands_backfilled": backfilled,
    }


def purge_obligations() -> dict[str, int]:
    """Wipe every Obligation row plus dependent rows (comments, notifications,
    activities). Keeps users / entities / rules / licenses intact so the
    admin can rebuild obligations explicitly from the licenses they upload.

    Returns counts of deleted rows per table.
    """
    from sqlalchemy import delete
    from compliance_agent.db import (
        Activity,
        Comment,
        Notification,
        Obligation,
    )

    counts = {"obligations": 0, "comments": 0, "notifications": 0, "activities": 0}
    with session_scope() as db:
        # Order matters — child rows first.
        counts["comments"] = db.execute(
            delete(Comment).where(Comment.obligation_id.is_not(None))
        ).rowcount or 0
        counts["notifications"] = db.execute(
            delete(Notification).where(Notification.obligation_id.is_not(None))
        ).rowcount or 0
        counts["activities"] = db.execute(
            delete(Activity).where(Activity.target_type == "obligation")
        ).rowcount or 0
        counts["obligations"] = db.execute(delete(Obligation)).rowcount or 0
    return counts


def populate_source_urls(*, overwrite: bool = False) -> dict[str, int]:
    """Backfill Rule.source_url AND Rule.submission_url for existing
    rules by matching authority against the authority_urls table.

    Two URLs are seeded with the same lookup result by default; admins
    can split them per-rule in the UI later.

    overwrite=False (default): only fill empty URLs. Admin-set values
    survive.
    overwrite=True: replace EVERY rule's URLs with the lookup result.

    Returns counts.
    """
    from compliance_agent.data.authority_urls import lookup
    from compliance_agent.db import init_db

    # Critical: ensure the submission_url column exists on the live DB
    # before we try to read/write it. init_db is idempotent — it's a
    # cheap no-op when the column is already there. Without this call,
    # users running populate-source-urls before ever starting the
    # server hit "no such column: rules.submission_url".
    init_db()

    counts = {
        "checked": 0,
        "source_filled": 0,
        "submission_filled": 0,
        "skipped_no_match": 0,
    }
    with session_scope() as db:
        rules = db.execute(select(Rule)).scalars().all()
        for rule in rules:
            counts["checked"] += 1
            url = lookup(rule.authority or "")
            if not url:
                counts["skipped_no_match"] += 1
                continue
            if not (rule.source_url or "").strip() or overwrite:
                rule.source_url = url
                counts["source_filled"] += 1
            if not (rule.submission_url or "").strip() or overwrite:
                rule.submission_url = url
                counts["submission_filled"] += 1
    return counts


if __name__ == "__main__":
    counts = run_seed()
    print(counts)


def sync_catalog_rules() -> int:
    """Idempotently ensure every catalogue rule exists for the existing
    entities — used to pull in newly-added catalogue rules (e.g. the split
    DIFC-only / ADGM-only rules) WITHOUT a full re-seed and without needing a
    server shell. Safe to run repeatedly. Returns the total rule count seen."""
    from sqlalchemy import select

    from compliance_agent.db import init_db

    init_db()
    with session_scope() as db:
        entities = (
            db.execute(select(Entity).where(Entity.archived_at.is_(None)))
            .scalars()
            .all()
        )
        rules = _ensure_rules(db, list(entities))
        return len(rules)
