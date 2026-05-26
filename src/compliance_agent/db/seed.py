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
from compliance_agent.db import (
    Applicability,
    EffortBand,
    Entity,
    Obligation,
    ObligationStatus,
    Role,
    Rule,
    RuleStatus,
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
# Mirrors the Aspora Global Compliance Tracker — one entity per CSV
# (UK / UAE / Canada / Lithuania) plus the two USA legal entities listed in
# the USA tab. India / Singapore / EU are not in the tracker and are
# intentionally absent.
DEMO_ENTITIES = [
    {
        "name": "Aspora UK Ltd",
        "legal_type": "Private Limited Company",
        "jurisdiction_code": "uk",
        "registration_number": "01234567",
        "incorporation_date": date(2018, 2, 18),
        "fiscal_year_end": "31-Mar",
        "country_lead_email": "pranavgoldar.iitb@gmail.com",
    },
    {
        "name": "Vance Inc",
        "legal_type": "C-Corporation",
        "jurisdiction_code": "us",
        "registration_number": "US-VANCE-2021",
        "incorporation_date": date(2021, 1, 1),
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranav.goldar@aspora.com",
    },
    {
        "name": "Vance Money Services",
        "legal_type": "Money Services Business",
        "jurisdiction_code": "us",
        "registration_number": "US-VMS-2022",
        "incorporation_date": date(2022, 1, 1),
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranav.goldar@aspora.com",
    },
    {
        "name": "Aspora DMCC",
        "legal_type": "DMCC Free Zone Company",
        "jurisdiction_code": "uae",
        "registration_number": "DMCC-987654",
        "incorporation_date": date(2020, 5, 5),
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranavgoldar.moodi@gmail.com",
    },
    {
        "name": "Aspora Lithuania UAB",
        "legal_type": "Uždaroji akcinė bendrovė",
        "jurisdiction_code": "lithuania",
        "registration_number": "LT304567890",
        "incorporation_date": date(2021, 3, 14),
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranav.goldar@aspora.com",
    },
    {
        "name": "Aspora Canada Inc",
        "legal_type": "Federal Corporation",
        "jurisdiction_code": "canada",
        "registration_number": "987654-3",
        "incorporation_date": date(2022, 1, 20),
        "fiscal_year_end": "31-Dec",
        "country_lead_email": "pranav.goldar@aspora.com",
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


def _applicability_from_str(s: str) -> Applicability:
    s = (s or "").strip().lower()
    if s.startswith("mandatory"):
        return Applicability.mandatory
    if s.startswith("conditional"):
        return Applicability.conditional
    return Applicability.sector_specific


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


def _ensure_obligations(db: Session, rules: list[Rule], users: dict[str, User]) -> int:
    """Generate obligations for every (rule, entity) combination using the
    frequency to spread due dates across a sensible window."""
    base = date.today()
    rng = random.Random(20260525)
    assignable = [u for u in users.values() if u.role == Role.employee]

    created_count = 0
    for rule in rules:
        offsets = _offsets_for_frequency(rule.frequency)
        for entity in rule.entities:
            for offset in offsets:
                due = base + timedelta(days=offset)
                existing = db.execute(
                    select(Obligation).where(
                        Obligation.rule_id == rule.id,
                        Obligation.entity_id == entity.id,
                        Obligation.due_date == due,
                    )
                ).scalar_one_or_none()
                if existing:
                    continue

                # Status — historic ones mostly completed; near-due partially in
                # progress; the rest not started.
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

                    completed_at = datetime(due.year, due.month, due.day, tzinfo=timezone.utc)
                    completed_by_id = assignee.id if assignee else None

                obligation = Obligation(
                    rule_id=rule.id,
                    entity_id=entity.id,
                    due_date=due,
                    period_label=_period_label_for_frequency(rule.frequency, due),
                    status=status,
                    effort_band=_effort_band_for_frequency(rule.frequency),
                    assignee_id=assignee.id if assignee else None,
                    completed_at=completed_at,
                    completed_by_id=completed_by_id,
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


def run_seed() -> dict[str, int]:
    """Idempotent seed. Returns counts of created objects."""
    from compliance_agent.db import init_db

    init_db()
    with session_scope() as db:
        users = _ensure_users(db)
        entities_map = _ensure_entities(db, users)
        rules = _ensure_rules(db, list(entities_map.values()))
        ob_count = _ensure_obligations(db, rules, users)
        backfilled = _backfill_effort_bands(db)
    return {
        "users": len(users),
        "entities": len(entities_map),
        "rules": len(rules),
        "obligations_created": ob_count,
        "effort_bands_backfilled": backfilled,
    }


if __name__ == "__main__":
    counts = run_seed()
    print(counts)
