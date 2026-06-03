"""Vance Inc. legal-entity org chart → entities + licences.

Source of truth: the "Vance Inc. Legal Entity Organizational Chart" PDF
(Annexure A — Subsidiary Details & Licenses). Used by the admin
"Import from org chart" action to idempotently create the entities and
their licences in the live DB without a server shell. Shareholding
(Annexure B) is intentionally NOT imported.

Everything created here is a normal, fully-editable row — admins can edit
or delete each entity/licence afterwards.
"""
from __future__ import annotations

from datetime import date

# ---------------------------------------------------------------------------
# Entities (Annexure A + Section 2). Shareholding is deliberately excluded.
#   name, jurisdiction_code, legal_type, registration_number, incorporation
# ---------------------------------------------------------------------------
ORG_ENTITIES: list[dict] = [
    {"name": "Vance Inc.", "jurisdiction_code": "us", "legal_type": "C-Corporation (Holding)", "registration_number": None, "incorporation_date": date(2021, 10, 20)},
    {"name": "Real Transfer Limited", "jurisdiction_code": "uk", "legal_type": "Licensed Payments Entity", "registration_number": None, "incorporation_date": date(2007, 6, 15)},
    {"name": "Nesse Technologies Inc.", "jurisdiction_code": "canada", "legal_type": "Money Service Business", "registration_number": "M23142925", "incorporation_date": date(2022, 12, 28)},
    {"name": "Vance Techlabs Limited", "jurisdiction_code": "uae", "legal_type": "DIFC Commercial Entity", "registration_number": "CL6323", "incorporation_date": date(2022, 11, 28)},
    {"name": "Aspora Money Services Pty. Ltd.", "jurisdiction_code": "australia", "legal_type": "Payments Entity", "registration_number": "ABN 46 691 177 929", "incorporation_date": date(2025, 9, 22)},
    {"name": "Vance Money Services LLC", "jurisdiction_code": "us", "legal_type": "LLC (Money Services Business)", "registration_number": "31000302683150", "incorporation_date": date(2023, 6, 7)},
    {"name": "Vance Technologies Limited", "jurisdiction_code": "uk", "legal_type": "Technology Services", "registration_number": "14378396", "incorporation_date": date(2022, 9, 27)},
    {"name": "Aspora Technologies Limited", "jurisdiction_code": "uk", "legal_type": "Technology Services", "registration_number": "17070463", "incorporation_date": date(2026, 3, 4)},
    {"name": "Vance Techlabs Pte. Ltd.", "jurisdiction_code": "singapore", "legal_type": "Technology Services", "registration_number": "UEN 202310510D", "incorporation_date": date(2023, 3, 21)},
    {"name": "Vance Techlabs UAB", "jurisdiction_code": "lithuania", "legal_type": "Technology Services", "registration_number": "306897823", "incorporation_date": date(2024, 7, 1)},
    {"name": "Aspora Money Services Limited", "jurisdiction_code": "uae", "legal_type": "Licensed Financial Services Entity", "registration_number": "CL10541", "incorporation_date": date(2026, 1, 28)},
    {"name": "Aspora Financial Services (IFSC) Private Limited", "jurisdiction_code": "india", "legal_type": "Payment Service Provider (IFSC)", "registration_number": "U66190GJ2025FTC167916", "incorporation_date": date(2025, 9, 18)},
    {"name": "Aspora Technology Services Private Limited", "jurisdiction_code": "india", "legal_type": "Technology Services", "registration_number": "U62013KA2022PTC164100", "incorporation_date": date(2022, 7, 21)},
    {"name": "Aspora Stock Broking (IFSC) Private Limited", "jurisdiction_code": "india", "legal_type": "Stock Broking (IFSC)", "registration_number": "U66120GJ2026FTC176126", "incorporation_date": date(2026, 4, 6)},
    {"name": "UAB Hokodo", "jurisdiction_code": "lithuania", "legal_type": "Electronic Money Institution (EMI)", "registration_number": "305007941", "incorporation_date": date(2019, 2, 4)},
    {"name": "Aspora Financial Services LLC", "jurisdiction_code": "uae", "legal_type": "Capital Market Firm", "registration_number": "LIC-0012530", "incorporation_date": date(2026, 5, 15)},
    {"name": "Aspora Information Technology Services LLC SOC", "jurisdiction_code": "uae", "legal_type": "Technology Services", "registration_number": "1620032", "incorporation_date": date(2026, 5, 1)},
]

# ---------------------------------------------------------------------------
# Licences (Annexure A). entity_name resolves to an entity above.
#   entity_name, name, license_type, authority, jurisdiction_code,
#   license_number, issue_date
# ---------------------------------------------------------------------------
ORG_LICENSES: list[dict] = [
    {"entity_name": "Real Transfer Limited", "name": "FCA Authorized Payment Institution (API)", "license_type": "Authorized Payment Institution (API)", "authority": "FCA", "jurisdiction_code": "uk", "license_number": "FRN 535949", "issue_date": date(2007, 6, 15)},
    {"entity_name": "Nesse Technologies Inc.", "name": "FINTRAC Money Service Business", "license_type": "Money Service Business", "authority": "FINTRAC", "jurisdiction_code": "canada", "license_number": "M23142925", "issue_date": date(2022, 12, 28)},
    {"entity_name": "Vance Techlabs Limited", "name": "DIFC Commercial License", "license_type": "Commercial License", "authority": "DIFC Registrar of Companies", "jurisdiction_code": "uae", "license_number": "CL6323", "issue_date": date(2022, 11, 28)},
    {"entity_name": "Aspora Money Services Pty. Ltd.", "name": "ASIC Company Registration", "license_type": "Company Registration", "authority": "ASIC", "jurisdiction_code": "australia", "license_number": "ABN 46 691 177 929", "issue_date": date(2025, 9, 22)},
    {"entity_name": "Vance Money Services LLC", "name": "FinCEN MSB License (Federal) + State MTLs", "license_type": "MSB License (Federal) + State MTLs (MI, MD, NM, MO, AL, DE)", "authority": "FinCEN + State Regulators", "jurisdiction_code": "us", "license_number": "31000302683150", "issue_date": date(2023, 6, 7)},
    {"entity_name": "Vance Technologies Limited", "name": "Companies House Registration", "license_type": "Company Registration", "authority": "Companies House", "jurisdiction_code": "uk", "license_number": "14378396", "issue_date": date(2022, 9, 27)},
    {"entity_name": "Vance Techlabs Pte. Ltd.", "name": "ACRA Company Registration", "license_type": "Company Registration", "authority": "ACRA", "jurisdiction_code": "singapore", "license_number": "UEN 202310510D", "issue_date": date(2023, 3, 21)},
    {"entity_name": "Vance Techlabs UAB", "name": "Lithuania Company Registration", "license_type": "Company Registration", "authority": "Centre of Registers (Registrų centras)", "jurisdiction_code": "lithuania", "license_number": "306897823", "issue_date": date(2024, 7, 1)},
    {"entity_name": "Aspora Money Services Limited", "name": "DFSA Financial Services License", "license_type": "Financial Services License", "authority": "DFSA (DIFC)", "jurisdiction_code": "uae", "license_number": "CL10541 / F008914", "issue_date": date(2026, 1, 28)},
    {"entity_name": "Aspora Financial Services (IFSC) Private Limited", "name": "IFSCA Payment Service Provider (PSP) Authorization", "license_type": "Payment Service Provider (PSP) Authorization", "authority": "IFSCA", "jurisdiction_code": "india", "license_number": "U66190GJ2025FTC167916", "issue_date": date(2025, 9, 18)},
    {"entity_name": "Aspora Technology Services Private Limited", "name": "MCA Company Registration", "license_type": "Company Registration", "authority": "Ministry of Corporate Affairs (MCA)", "jurisdiction_code": "india", "license_number": "U62013KA2022PTC164100", "issue_date": date(2022, 7, 21)},
    {"entity_name": "Aspora Stock Broking (IFSC) Private Limited", "name": "IFSC Stock Broking License", "license_type": "Stock Broking Services", "authority": "IFSCA", "jurisdiction_code": "india", "license_number": "U66120GJ2026FTC176126", "issue_date": date(2026, 4, 6)},
    {"entity_name": "Aspora Technologies Limited", "name": "Companies House Registration", "license_type": "Company Registration", "authority": "Companies House", "jurisdiction_code": "uk", "license_number": "17070463", "issue_date": date(2026, 3, 4)},
    {"entity_name": "UAB Hokodo", "name": "Electronic Money Institution (EMI) License", "license_type": "Electronic Money Institution License", "authority": "Bank of Lithuania", "jurisdiction_code": "lithuania", "license_number": "305007941", "issue_date": date(2019, 2, 4)},
    {"entity_name": "Aspora Financial Services LLC", "name": "CMA-5 License (in-principle)", "license_type": "CMA-5", "authority": "Capital Market Authority, UAE", "jurisdiction_code": "uae", "license_number": "LIC-0012530", "issue_date": date(2026, 5, 15)},
    {"entity_name": "Aspora Information Technology Services LLC SOC", "name": "Dubai DET Company Registration", "license_type": "Company Registration", "authority": "Department of Economy and Tourism, Dubai", "jurisdiction_code": "uae", "license_number": "1620032", "issue_date": date(2026, 5, 1)},
]


def _norm(s: str) -> str:
    """Normalise a company name for duplicate-safe matching."""
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def _norm_num(s: str | None) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def sync_org_chart() -> dict:
    """Idempotently create the org-chart entities + licences. Existing rows
    (matched by normalised name / licence number) are left untouched. Returns
    a summary of what was created vs already present."""
    from sqlalchemy import select

    from compliance_agent.db import Entity, License, init_db
    from compliance_agent.db.base import SessionLocal

    init_db()
    created_entities = 0
    backfilled_entities = 0
    created_licenses = 0
    skipped_licenses = 0

    with SessionLocal() as db:
        # --- Entities -------------------------------------------------------
        existing = db.execute(select(Entity)).scalars().all()
        by_norm = {_norm(e.name): e for e in existing}

        for spec in ORG_ENTITIES:
            ent = by_norm.get(_norm(spec["name"]))
            if ent is None:
                ent = Entity(
                    name=spec["name"],
                    jurisdiction_code=spec["jurisdiction_code"],
                    legal_type=spec["legal_type"],
                    registration_number=spec["registration_number"],
                    incorporation_date=spec["incorporation_date"],
                )
                db.add(ent)
                db.flush()
                by_norm[_norm(spec["name"])] = ent
                created_entities += 1
            else:
                # Backfill missing details on an existing entity — never
                # overwrite what the admin already set.
                changed = False
                if not ent.registration_number and spec["registration_number"]:
                    ent.registration_number = spec["registration_number"]
                    changed = True
                if not ent.incorporation_date and spec["incorporation_date"]:
                    ent.incorporation_date = spec["incorporation_date"]
                    changed = True
                if not ent.legal_type and spec["legal_type"]:
                    ent.legal_type = spec["legal_type"]
                    changed = True
                if changed:
                    backfilled_entities += 1

        db.flush()

        # --- Licences -------------------------------------------------------
        # Use the plain licence type as the name (no made-up descriptive title)
        # so org-chart licences read like manually-added ones.
        existing_lic = db.execute(select(License)).scalars().all()
        by_num = {
            _norm_num(l.license_number): l for l in existing_lic if l.license_number
        }
        lic_keys = {(l.entity_id, _norm(l.name)) for l in existing_lic}

        for spec in ORG_LICENSES:
            ent = by_norm.get(_norm(spec["entity_name"]))
            if ent is None:
                continue  # entity missing (shouldn't happen) — skip its licence
            plain_name = spec["license_type"] or spec["name"]
            num_key = _norm_num(spec["license_number"])
            existing = by_num.get(num_key) if num_key else None
            if existing is not None:
                # Already imported — simplify the name to the plain type, but
                # never touch a licence the user uploaded a file for (manual).
                if existing.storage_path is None and existing.name != plain_name:
                    existing.name = plain_name
                skipped_licenses += 1
                continue
            if (ent.id, _norm(plain_name)) in lic_keys:
                skipped_licenses += 1
                continue
            db.add(
                License(
                    entity_id=ent.id,
                    name=plain_name,
                    license_type=spec["license_type"],
                    authority=spec["authority"],
                    jurisdiction_code=spec["jurisdiction_code"],
                    license_number=spec["license_number"],
                    issue_date=spec["issue_date"],
                )
            )
            if num_key:
                by_num[num_key] = None  # mark seen
            lic_keys.add((ent.id, _norm(plain_name)))
            created_licenses += 1

        db.commit()

    return {
        "created_entities": created_entities,
        "backfilled_entities": backfilled_entities,
        "created_licenses": created_licenses,
        "skipped_licenses": skipped_licenses,
    }
