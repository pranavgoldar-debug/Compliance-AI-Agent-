# Regulatory Obligations Discovery Engine — Implementation Specification

**Status:** build-ready · **Audience:** engineering team (Backend, Frontend, AI, DevOps, QA)
**Stack:** React 18 + TypeScript (Vite) · FastAPI + SQLAlchemy/SQLModel · PostgreSQL · Anthropic Claude (structured output)
**Core principle:** Round 1 discovers a *maximal candidate set* (LLM). Rounds 2–3 assign Mandatory/Conditional deterministically (code, no LLM). Round 4 is the human gate before anything drives a live deadline.

---

## 1. System Architecture

### 1.1 Components

| Layer | Responsibility | Tech |
|---|---|---|
| **Frontend** | Entity CRUD, licence upload, trigger discovery, activity questionnaire, review board, calendar | React/TS, react-query, Tailwind |
| **Backend API** | REST endpoints, orchestration, auth (cookie JWT, admin gate) | FastAPI, Pydantic |
| **Compliance Engine** | Orchestrates the 4 rounds; owns round transitions + gap detection | Python service module |
| **LLM Discovery Service** | Round-1 call: prompt build → Claude (temp 0, structured) → validate → persist candidates | Python, Anthropic SDK |
| **Rule Engine** | Condition-tree evaluator (Rounds 2–3) + deterministic owner-team function | Pure Python, no I/O |
| **Calendar Engine** | `deadline_rule` parser + recurring/event deadline-instance generation | Pure Python (dates) |
| **Review Workflow** | State machine (draft→review→approved→live), overrides, audit log | Python + DB |
| **Database** | Source of truth: entities, licences, obligations + versions, calendar, audit | PostgreSQL |

### 1.2 Request flow (end-to-end)

```
[1] POST /entities                         → create entity (jurisdiction, legal_form, FYE)
[2] POST /entities/{id}/licenses           → upload licence (file → text extract, metadata)
[3] POST /entities/{id}/discovery          → ROUND 1 (LLM)
        ├─ build prompt (entity + licence + activity flags ALL assumed on)
        ├─ Claude call (temperature 0, output_format=DiscoveryResult)
        ├─ validate (schema, owner_team enum, condition grammar, source present)
        ├─ retry on invalid/empty (≤3, backoff)
        └─ persist obligations (status=candidate) + coverage_notes
[4] PUT  /entities/{id}/activities         → ROUND 2 (deterministic)
        └─ store Yes/No/TBC; No removes family (kept w/ reason), TBC keeps + "verify"
[5] POST /entities/{id}/filter             → ROUND 3 (deterministic)
        ├─ evaluate each candidate's condition over attributes
        ├─ label Mandatory / Conditional / Not-applicable
        └─ run GAP DETECTION → may re-trigger scoped Round 1
[6] POST /entities/{id}/reviews            → ROUND 4 (human)
        ├─ approve / reject / override owner / edit
        └─ on approve → promote obligation to live
[7] POST /entities/{id}/calendar/generate  → Calendar Engine
        └─ for each live obligation: parse deadline_rule → create deadline_instances
[8] GET  /entities/{id}/deadlines          → calendar read
```

**LLM is invoked only at [3] and the scoped re-call inside [5].** Everything else is deterministic.

---

## 2. Database Schema (PostgreSQL, SQL-ready)

```sql
-- ───────────────────────── reference data ─────────────────────────
CREATE TABLE jurisdictions (
    id            SERIAL PRIMARY KEY,
    code          VARCHAR(16) NOT NULL UNIQUE,        -- 'uae-difc', 'uk', 'canada'
    name          VARCHAR(120) NOT NULL,
    parent_code   VARCHAR(16) REFERENCES jurisdictions(code),  -- sub-national → national
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE regulators (
    id              SERIAL PRIMARY KEY,
    jurisdiction_id INTEGER NOT NULL REFERENCES jurisdictions(id),
    name            VARCHAR(255) NOT NULL,             -- 'FINTRAC', 'DFSA', 'CRA'
    kind            VARCHAR(32) NOT NULL,              -- conduct|prudential|tax|registry|aml|data_protection|workers_comp
    website_url     TEXT,
    UNIQUE (jurisdiction_id, name)
);
CREATE INDEX ix_regulators_jur ON regulators(jurisdiction_id);

CREATE TABLE source_references (
    id              SERIAL PRIMARY KEY,
    obligation_id   INTEGER NOT NULL REFERENCES obligations(id) ON DELETE CASCADE,
    authority       TEXT NOT NULL,                     -- 'PCMLTFA s.9.3'
    url             TEXT,                              -- official URL if available
    confidence      VARCHAR(64) NOT NULL,              -- see confidence enum below
    retrieved_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_source_obl ON source_references(obligation_id);

-- ───────────────────────── entity + licence ───────────────────────
CREATE TABLE entities (
    id                 SERIAL PRIMARY KEY,
    name               VARCHAR(255) NOT NULL,
    legal_form         VARCHAR(120),                   -- 'Private Company', 'Federal corporation'
    jurisdiction_id    INTEGER NOT NULL REFERENCES jurisdictions(id),
    sub_jurisdiction   VARCHAR(64),                    -- province/state/free-zone, optional
    registration_no    VARCHAR(120),
    incorporation_date DATE,
    fiscal_year_end    VARCHAR(10),                    -- canonical 'DD-Mon' e.g. '31-Dec'
    nature_of_ops      TEXT,
    archived_at        TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_entities_jur ON entities(jurisdiction_id);
CREATE INDEX ix_entities_active ON entities(archived_at) WHERE archived_at IS NULL;

CREATE TABLE licenses (
    id              SERIAL PRIMARY KEY,
    entity_id       INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    regulator_id    INTEGER REFERENCES regulators(id),
    name            VARCHAR(255) NOT NULL,
    license_type    VARCHAR(255),
    license_number  VARCHAR(255),
    issue_date      DATE,
    expiry_date     DATE,
    authorized_activities JSONB DEFAULT '[]',          -- normalized activity ids extracted from doc
    storage_path    TEXT,                              -- uploaded file
    extracted_text  TEXT,                              -- parsed text (PDF/txt)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_licenses_entity ON licenses(entity_id);

-- ───────────────────────── activities + thresholds ────────────────
-- Catalogue of the canonical activity flags (seed data).
CREATE TABLE activities (
    id           SERIAL PRIMARY KEY,
    flag_id      VARCHAR(64) NOT NULL UNIQUE,          -- 'employs_staff', 'licensed_financial_activity'
    label        TEXT NOT NULL,
    kind         VARCHAR(16) NOT NULL DEFAULT 'primary' -- primary|secondary
);

-- Per-entity answers to the activity flags + secondary parameters (Round 2/3 inputs).
CREATE TABLE entity_activities (
    id          SERIAL PRIMARY KEY,
    entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    flag_id     VARCHAR(64) NOT NULL,                  -- activities.flag_id OR a secondary param key
    answer      VARCHAR(32),                           -- 'yes'|'no'|'tbc'|'monthly'|'above'|'below'|...
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_id, flag_id)
);
CREATE INDEX ix_entact_entity ON entity_activities(entity_id);

-- Catalogue of secondary thresholds (declarative; drives Round-3 questions).
CREATE TABLE thresholds (
    id              SERIAL PRIMARY KEY,
    key             VARCHAR(64) NOT NULL UNIQUE,        -- 'corporate_tax_threshold_met'
    gating_flag_id  VARCHAR(64) NOT NULL,               -- asked only when this flag is 'yes'
    jurisdiction_id INTEGER REFERENCES jurisdictions(id),  -- null = global
    question        TEXT NOT NULL,
    figure          TEXT,                               -- the REAL figure shown ('CAD 500,000')
    answer_type     VARCHAR(16) NOT NULL                -- 'bool'|'band'|'enum'
);

-- ───────────────────────── obligations + versions ─────────────────
CREATE TYPE obligation_status AS ENUM ('candidate','in_review','approved','live','retired');
CREATE TYPE obligation_type   AS ENUM ('scheduled','event_based');
CREATE TYPE owner_team        AS ENUM ('Finance','Compliance','Legal','HR');
CREATE TYPE applicability      AS ENUM ('candidate','mandatory','conditional','not_applicable');

CREATE TABLE obligations (
    id                   SERIAL PRIMARY KEY,
    entity_id            INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    external_id          VARCHAR(64),                   -- stable e.g. 'AE-DIFC-S05'
    filing               VARCHAR(255) NOT NULL,         -- form/return name
    regulator_id         INTEGER REFERENCES regulators(id),
    regulator_text       VARCHAR(255),                  -- raw recipient if not matched
    type                 obligation_type NOT NULL,
    frequency            VARCHAR(64),                   -- scheduled only
    trigger_event        VARCHAR(255),                  -- event_based only
    deadline_rule        VARCHAR(255) NOT NULL,         -- 'financial_year_end + 9 months'
    anchor               VARCHAR(64),                   -- 'financial_year_end'
    triggering_activity  VARCHAR(64),                   -- flag id or 'NEEDS_NEW_FLAG'
    condition            JSONB NOT NULL DEFAULT '{"always":true}',  -- boolean tree (§5)
    owner_team           owner_team,                    -- LLM proposal; may be overridden
    owner_team_overridden BOOLEAN NOT NULL DEFAULT false,
    applicability        applicability NOT NULL DEFAULT 'candidate',
    applicability_note   TEXT,
    status               obligation_status NOT NULL DEFAULT 'candidate',
    confidence           VARCHAR(64),
    content_hash         VARCHAR(64),                   -- dedupe signature (name+freq+regulator)
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_id, content_hash)
);
CREATE INDEX ix_obl_entity_status ON obligations(entity_id, status);
CREATE INDEX ix_obl_owner ON obligations(owner_team);

-- Immutable history: every change to an obligation (discovery re-run, edit, override).
CREATE TABLE obligation_versions (
    id              SERIAL PRIMARY KEY,
    obligation_id   INTEGER NOT NULL REFERENCES obligations(id) ON DELETE CASCADE,
    version_no      INTEGER NOT NULL,
    snapshot        JSONB NOT NULL,                     -- full obligation row at this version
    change_reason   VARCHAR(64) NOT NULL,              -- 'discovery'|'review_edit'|'owner_override'|'rediscovery'
    actor_id        INTEGER,                            -- user id, null for system
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (obligation_id, version_no)
);
CREATE INDEX ix_oblver_obl ON obligation_versions(obligation_id);

-- ───────────────────────── review + ownership ─────────────────────
CREATE TYPE review_state AS ENUM ('pending','approved','rejected','changes_requested');

CREATE TABLE reviews (
    id              SERIAL PRIMARY KEY,
    obligation_id   INTEGER NOT NULL REFERENCES obligations(id) ON DELETE CASCADE,
    state           review_state NOT NULL DEFAULT 'pending',
    reviewer_id     INTEGER,
    comment         TEXT,
    decided_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_reviews_obl ON reviews(obligation_id);

CREATE TABLE owner_assignments (
    id              SERIAL PRIMARY KEY,
    obligation_id   INTEGER NOT NULL REFERENCES obligations(id) ON DELETE CASCADE,
    team            owner_team NOT NULL,
    source          VARCHAR(16) NOT NULL,              -- 'llm'|'engine'|'human'
    actor_id        INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_ownasg_obl ON owner_assignments(obligation_id);

-- ───────────────────────── calendar + deadlines ───────────────────
CREATE TABLE compliance_calendar (
    id              SERIAL PRIMARY KEY,
    entity_id       INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    horizon_end     DATE NOT NULL,                      -- generated instances up to here
    UNIQUE (entity_id)
);

CREATE TYPE deadline_status AS ENUM ('upcoming','due_soon','overdue','completed','not_applicable');

CREATE TABLE deadline_instances (
    id              SERIAL PRIMARY KEY,
    obligation_id   INTEGER NOT NULL REFERENCES obligations(id) ON DELETE CASCADE,
    entity_id       INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    due_date        DATE NOT NULL,
    period_label    VARCHAR(64),                        -- 'FY2026', 'Q1-2026'
    status          deadline_status NOT NULL DEFAULT 'upcoming',
    assignee_id     INTEGER,
    completed_at    TIMESTAMPTZ,
    UNIQUE (obligation_id, entity_id, due_date)         -- idempotent generation
);
CREATE INDEX ix_di_entity_due ON deadline_instances(entity_id, due_date);
CREATE INDEX ix_di_status ON deadline_instances(status);
```

**Notes:** `obligations.content_hash` = normalized(filing)+frequency+regulator → enforces dedupe at the DB level. `deadline_instances` unique key makes regeneration idempotent. `obligation_versions` is append-only (audit).

---

## 3. API Design (OpenAPI-style)

All routes are admin-gated (cookie JWT). Errors: `{ "detail": "..." }` with appropriate 4xx/5xx.

```yaml
# ── Create entity ─────────────────────────────────────────────
POST /api/entities
request:
  { name: string, legal_form?: string, jurisdiction_code: string,
    sub_jurisdiction?: string, fiscal_year_end?: string }   # FYE accepts any form; server canonicalizes
response 201:
  { id: int, name, jurisdiction_code, fiscal_year_end: "31-Dec", ... }

# ── Upload licence ────────────────────────────────────────────
POST /api/entities/{entity_id}/licenses           # multipart/form-data
request: file=<binary>, name, license_type?, license_number?, issue_date?, expiry_date?
response 201:
  { id, entity_id, name, license_type, authorized_activities: string[],
    extracted_chars: int }

# ── Run discovery (ROUND 1, LLM) ──────────────────────────────
POST /api/entities/{entity_id}/discovery
request: { force?: bool }                          # force re-run even if candidates exist
response 200:
  { available: bool, created: int, updated: int, duplicates_removed: int,
    coverage_notes: [{domain, status, note}], notes?: string }

# ── Update activities (ROUND 2) ───────────────────────────────
PUT /api/entities/{entity_id}/activities
request: { answers: { [flag_id: string]: "yes"|"no"|"tbc" } }
response 200: { updated: int }

# ── Run filtering (ROUND 3 + gap detection) ───────────────────
POST /api/entities/{entity_id}/filter
request: { thresholds?: { [key: string]: string } }
response 200:
  { mandatory: int, conditional: int, not_applicable: int,
    gaps: [{type: "empty_domain"|"incomplete_domain"|"missing_flag",
            domain?: string, flag?: string, action: "rediscover"|"surface"}] }

# ── Review obligations (ROUND 4) ──────────────────────────────
GET  /api/entities/{entity_id}/obligations?status=in_review&owner=Compliance
response 200: { items: Obligation[] }

POST /api/obligations/{id}/review
request: { decision: "approve"|"reject"|"request_changes", comment?: string }
response 200: { id, status: obligation_status, review_state }

# ── Override owner assignment ─────────────────────────────────
PATCH /api/obligations/{id}/owner
request: { team: "Finance"|"Compliance"|"Legal"|"HR", reason?: string }
response 200: { id, owner_team, owner_team_overridden: true }

# ── Generate calendar ─────────────────────────────────────────
POST /api/entities/{entity_id}/calendar/generate
request: { horizon_months?: int }                  # default 18
response 200: { generated: int, removed: int, horizon_end: date }

# ── Get deadlines ─────────────────────────────────────────────
GET /api/entities/{entity_id}/deadlines?from=2026-01-01&to=2026-12-31&status=upcoming
response 200:
  { items: [{ id, obligation_id, filing, owner_team, due_date,
              period_label, status, assignee_id }] }
```

---

## 4. LLM Discovery Service (Round 1)

**Inputs:** entity (name, jurisdiction, legal_form, FYE), licence(s) (type, number, issue_date, extracted_text, authorized_activities), the fixed activity-flag id list, licence constraints (“facts on, forbidden off”).

**Output schema:** `DiscoveryResult` (Pydantic), matching the doc's §3 contract — `obligations[]` (id, filing, regulator, type, frequency|trigger, deadline_rule, anchor, triggering_activity, condition, owner, applicability, source_authority, source_url, confidence) + `coverage_notes[]`.

```python
CONFIDENCE = {"Confirmed – official source", "Confirmed scope – entity check needed",
              "Standard rule – verify applicability", "Pending verification – official source check"}
FLAG_IDS = {"registered_company","licensed_financial_activity","holds_customer_funds",
            "employs_staff","grants_equity","takes_foreign_investment","intra_group_transactions",
            "holds_personal_data","vat_gst_registered","has_owners_controllers",
            "sanctions_exposure","conducts_esr_relevant_activity","NEEDS_NEW_FLAG"}

def run_discovery(entity, licenses) -> DiscoveryResult:
    prompt = build_prompt(entity, licenses)          # §2 system prompt, {braces} filled
    last_err = None
    for attempt in range(3):                          # retry strategy
        resp = claude.messages.parse(
            model="claude-opus-4-x",
            temperature=0,                            # DETERMINISTIC — same entity → same set
            max_tokens=16000,
            system=[{"type":"text","text":prompt,"cache_control":{"type":"ephemeral"}}],
            messages=[{"role":"user","content":context_block(entity, licenses)}],
            output_format=DiscoveryResult,            # structured output, schema-enforced
        )
        result = resp.parsed_output
        if result is None:
            last_err = f"stop_reason={resp.stop_reason}"; continue
        ok, errs = validate(result)
        if ok:
            return result
        last_err = errs
        # feed the validation errors back into the next attempt's user message
    raise DiscoveryError(last_err)

def validate(result) -> (bool, list):                 # hallucination + contract guards
    errs = []
    for o in result.obligations:
        if o.owner not in {"Finance","Compliance","Legal","HR"}:  errs.append(f"{o.id}: bad owner")
        if o.triggering_activity not in FLAG_IDS:                 errs.append(f"{o.id}: bad flag")
        if o.confidence not in CONFIDENCE:                        errs.append(f"{o.id}: bad confidence")
        if not (o.source_authority or o.source_url):              errs.append(f"{o.id}: NO SOURCE")  # never assert w/o source
        if o.applicability and o.applicability_is_mandatory():    errs.append(f"{o.id}: must NOT pre-label mandatory")
        validate_condition_grammar(o.condition, errs)             # §5 grammar
        if "year" in o.deadline_rule and "+" not in o.deadline_rule and is_hardcoded_date(o.deadline_rule):
            errs.append(f"{o.id}: deadline must be a RULE, not a date")
    if not result.coverage_notes:                                 errs.append("coverage_notes required")
    return (len(errs) == 0, errs)
```

**Hallucination prevention:** (a) structured `output_format` (no free-text), (b) **every row must cite a source** or be rejected, (c) confidence enum forced, (d) candidates only — no “mandatory” allowed from the model, (e) temperature 0 for stable, reviewable output, (f) `coverage_notes` mandatory so the reviewer sees swept-vs-skimmed.

**Persistence:** dedupe by `content_hash`; insert new as `status=candidate`; write `obligation_versions` (`change_reason='discovery'`); store each source in `source_references`.

---

## 5. Filtering Engine (Rounds 2–3)

### 5.1 Condition grammar evaluator (unknown → safe-include)

```python
def evaluate(cond: dict, attrs: dict) -> (bool, bool):
    """Returns (applies, needs_verify). Unknown attr → TRUE + verify (never drop)."""
    if "always" in cond: return (True, False)
    if "all_of" in cond:
        rs = [evaluate(c, attrs) for c in cond["all_of"]]
        return (all(a for a,_ in rs), any(v for _,v in rs))
    if "any_of" in cond:
        rs = [evaluate(c, attrs) for c in cond["any_of"]]
        return (any(a for a,_ in rs), any(v for _,v in rs))
    if "none_of" in cond:
        rs = [evaluate(c, attrs) for c in cond["none_of"]]
        return (not any(a for a,_ in rs), any(v for _,v in rs))
    # leaf: {"attr": name, "<op>": value}
    name = cond["attr"]; val = attrs.get(name)
    if val is None:                       # TBC / unanswered
        return (True, True)               # SAFE-INCLUDE + flag verify
    op, target = next((k,v) for k,v in cond.items() if k != "attr")
    return (OPS[op](val, target), False)

OPS = {"eq": op.eq, "neq": op.ne, "gte": op.ge, "lte": op.le, "gt": op.gt, "lt": op.lt,
       "in": lambda v,l: (set(v) <= set(l)) if isinstance(v,(list,set)) else (v in l)}
```

### 5.2 Round 2 — primary activity filter, Round 3 — threshold filter + labelling

```python
def run_filter(entity) -> dict:
    attrs = build_attrs(entity)           # flags (yes/no/tbc→true/false/None) + secondary params
    counts = {"mandatory":0,"conditional":0,"not_applicable":0}
    for o in candidates_for(entity):
        # ROUND 2: family switched OFF by a primary flag answered "no"
        if o.triggering_activity in attrs and attrs[o.triggering_activity] is False:
            label(o, "not_applicable", reason=f"{o.triggering_activity} answered No")
            counts["not_applicable"] += 1; continue
        # ROUND 3: evaluate the full condition over flags + thresholds
        applies, verify = evaluate(o.condition, attrs)
        if not applies:
            label(o, "not_applicable", reason="threshold/condition not met")
            counts["not_applicable"] += 1
        elif verify:                       # gated on a TBC/threshold not yet confirmed
            label(o, "conditional", reason="verify — unconfirmed trigger/threshold")
            counts["conditional"] += 1
        else:
            label(o, "mandatory", reason="condition fully met")
            counts["mandatory"] += 1
    return counts
```

**Mandatory** = condition fully TRUE with no unknowns. **Conditional** = applies but ≥1 clause is TBC/unconfirmed (the `verify` bit). **Not-applicable** = a primary flag is No or a threshold confirms it doesn't apply. **Unknown/TBC** never drops a row — it lands Conditional. Statutory **audit is DERIVED** from `company_size_band`/`audit_exemption_ineligible`, never asked.

---

## 6. Owner-Team Engine (deterministic)

The LLM proposes `owner_team` in Round 1; this function is the deterministic ground truth used to **validate/override** the model and to re-tag identically on every rediscovery. Output is always one of the four. Human override (§9) is the final word and is persisted.

### 6.1 Decision tree

```
RULE 1  recipient = conduct/prudential regulator (FCA/DFSA/central-bank-as-conduct)
        OR filing ∈ {AML/financial-crime return, prudential/capital return, regulator
        supervision fee, controllers report to regulator, client-money/safeguarding
        report, money-services auditor's report, material-event/breach/change-in-control
        notification to regulator}                              → Compliance   [check FIRST]
RULE 2  subject ∈ {corporate/income tax return, tax audit report, VAT/GST return,
        withholding/TDS incl. on salaries, transfer-pricing, FDI/central-bank statistical,
        audited financial statements filed to a REGISTRY}        → Finance
RULE 3  employee-facing ∈ {Form-16-type cert, provident fund, state insurance,
        pension/social-security contribution, EOSB/DEWS}         → HR
RULE 4  registry/governance/ownership/data-protection ∈ {annual accounts, annual return/
        confirmation statement, director KYC, trade-licence renewal, deposits return,
        beneficial-ownership return to a REGISTRY, data-protection reg/fee/breach} → Legal
RULE 5  fallback by triggering activity:
          licensed_financial_activity|holds_customer_funds|sanctions_exposure → Compliance
          vat_gst_registered|intra_group_transactions|takes_foreign_investment → Finance
          employs_staff                                          → HR
          registered_company|has_owners_controllers|holds_personal_data → Legal
TIE-BREAKERS (apply within the rules above):
  A) audited financial statements to a REGISTRY → Finance (about the numbers), NOT Legal
  B) client-money/safeguarding audit OR auditor's report to a REGULATOR about conduct
     → Compliance, NOT Finance
  C) data protection (reg/fee/breach) → Legal
AMBIGUOUS → earliest matching rule order: Compliance > Finance > HR > Legal; flag in note.
```

### 6.2 Pseudocode

```python
def owner_team(o) -> str:
    recipient = (o.regulator_text or "").lower()
    subj = f"{o.filing} {o.applicability_note or ''}".lower()
    is_regulator = o.regulator_kind in ("conduct","prudential","aml") or \
                   any(k in recipient for k in ("fca","dfsa","fintrac","central bank","authority"))

    # Tie-breaker B before Rule 2 (audit-about-conduct beats the word "audit")
    if ("client money" in subj or "safeguarding" in subj or
        ("audit" in subj and is_regulator and "financial statement" not in subj)):
        return "Compliance"
    # Tie-breaker A (audited FS to a REGISTRY → Finance, even though registry receives it)
    if "financial statement" in subj and ("registr" in recipient or "registry" in subj):
        return "Finance"
    # Tie-breaker C
    if "data protection" in subj or "privacy" in subj:
        return "Legal"

    # RULE 1 — regulator-facing / financial-crime / prudential (recipient wins)
    if is_regulator or any(k in subj for k in (
        "aml","financial crime","prudential","capital","supervision fee","controllers",
        "change in control","change-in-control","breach","material event","money services")):
        return "Compliance"
    # RULE 2 — tax / audited numbers
    if any(k in subj for k in ("corporate tax","income tax","tax return","vat","gst",
        "withholding","tds","transfer pricing","fdi","statistical","audited financial")):
        return "Finance"
    # RULE 3 — employee-facing
    if any(k in subj for k in ("form 16","provident fund","state insurance","pension",
        "social security","eosb","dews","payroll certificate","p60","record of employment")):
        return "HR"
    # RULE 4 — registry / governance / ownership / data
    if any(k in subj for k in ("annual accounts","annual return","confirmation statement",
        "director","trade licence","deposits return","beneficial owner","ubo","psc","ben-2")):
        return "Legal"
    # RULE 5 — fallback by triggering activity
    return {
        "licensed_financial_activity":"Compliance","holds_customer_funds":"Compliance",
        "sanctions_exposure":"Compliance","vat_gst_registered":"Finance",
        "intra_group_transactions":"Finance","takes_foreign_investment":"Finance",
        "employs_staff":"HR","registered_company":"Legal",
        "has_owners_controllers":"Legal","holds_personal_data":"Legal",
    }.get(o.triggering_activity, "Compliance")   # ambiguous → earliest (Compliance)
```

**Edge cases & expected outputs (regression fixtures):** “DFSA Annual AML Return”→Compliance (R1) · “TDS on salary (24Q)”→Finance (R2) · “Form 16 to employees”→HR (R3) · “Audited Financial Statements to the Registrar”→Finance (TB-A) · “Client Money Auditor’s Report to DFSA”→Compliance (TB-B) · “BEN-2 to the registry”→Legal (R4) · “Change-in-control approval to the DFSA”→Compliance (R1 beats R4) · “Data protection notification”→Legal (TB-C). These 8 ship as a unit test.

**LLM-vs-engine policy:** persist the LLM proposal *and* the engine result; if they disagree, surface the disagreement in Round-4 review (don't silently override). Human decision writes `owner_assignments(source='human')` and is reused forever.

---

## 7. Compliance Calendar Engine

### 7.1 Deadline-rule grammar + parser

```
deadline_rule := <anchor> ("+" <n> <unit>)?
anchor        := financial_year_end | quarter_end | month_end | issue_date | event_date | <calendar_date>
unit          := day[s] | month[s]
examples: "financial_year_end + 4 months", "financial_year_end + 9 months",
          "quarter_end + 30 days", "event_date + 15 days", "issue_date + 3 months"
```

```python
RULE_RE = re.compile(r"^\s*(\w+)\s*(?:\+\s*(\d+)\s*(day|days|month|months))?\s*$", re.I)

def parse_rule(text) -> (str, int, str):
    m = RULE_RE.match(text)
    if not m: raise ParseError(text)
    anchor, n, unit = m.group(1).lower(), int(m.group(2) or 0), (m.group(3) or "day").rstrip("s").lower()
    return anchor, n, unit
```

### 7.2 Execution (anchor resolution + offset)

```python
def resolve_anchor(anchor, ctx, period_start) -> date:
    if anchor == "financial_year_end": return fye_for_period(ctx.fiscal_year_end, period_start)
    if anchor == "quarter_end":        return quarter_end_for(period_start)
    if anchor == "month_end":          return month_end_for(period_start)
    if anchor == "issue_date":         return ctx.license_issue_date
    if anchor == "event_date":         return ctx.event_date            # event_based only
    return parse_calendar_date(anchor) # explicit date

def compute_due(rule, ctx, period_start) -> date:
    anchor, n, unit = parse_rule(rule)
    base = resolve_anchor(anchor, ctx, period_start)
    return add_months(base, n) if unit == "month" else base + timedelta(days=n)
```

### 7.3 Recurring (scheduled) instance generation

```python
def generate_scheduled(obl, ctx, horizon_end) -> list[date]:
    step = {"annual":12,"half-yearly":6,"quarterly":3,"monthly":1}[obl.frequency.lower()]
    out, period = [], current_period_start(obl.frequency, ctx)
    while True:
        due = compute_due(obl.deadline_rule, ctx, period)
        if due > horizon_end: break
        if due >= date.today(): out.append((due, period_label(period, obl.frequency)))
        period = add_months(period, step)
    return out   # → upsert deadline_instances (unique on obligation+entity+due_date → idempotent)
```

### 7.4 Event-based generation

```python
def generate_event(obl, event_date) -> date:
    # created on demand when the triggering event is recorded (e.g. breach occurs,
    # change-in-control filed). No future projection; one instance per event.
    return compute_due(obl.deadline_rule, ctx(event_date=event_date), period_start=event_date)
```

Generation is **idempotent** (DB unique key); regen on FYE change or obligation edit re-points future, not-yet-completed instances; completed instances are preserved.

---

## 8. Gap Detection Engine

Runs after Round 2/3. Three checks; outputs actions.

```python
def detect_gaps(entity) -> list[Gap]:
    gaps = []
    answers = activity_answers(entity)           # flag → yes/no/tbc

    # CHECK 1 — empty domain: flag = Yes but zero candidates gated on it → never researched
    for flag, ans in answers.items():
        if ans == "yes":
            n = count_obligations(entity, triggering_activity=flag)
            if n == 0:
                gaps.append(Gap("empty_domain", flag=flag, action="rediscover"))

    # CHECK 2 — incomplete domain: coverage_notes status = Partial
    for cn in coverage_notes(entity):
        if cn.status.startswith("Partial"):
            gaps.append(Gap("incomplete_domain", domain=cn.domain, action="surface"))

    # CHECK 3 — missing flag: any NEEDS_NEW_FLAG obligation, or a known jurisdiction
    #           trigger with no flag at all
    if exists_obligation(entity, triggering_activity="NEEDS_NEW_FLAG"):
        gaps.append(Gap("missing_flag", action="surface"))
    return gaps
```

**SQL backing the checks:**
```sql
-- empty domain
SELECT a.flag_id FROM entity_activities a
 LEFT JOIN obligations o
   ON o.entity_id = a.entity_id AND o.triggering_activity = a.flag_id
 WHERE a.entity_id = :eid AND a.answer = 'yes'
 GROUP BY a.flag_id HAVING count(o.id) = 0;

-- missing flag
SELECT 1 FROM obligations
 WHERE entity_id = :eid AND triggering_activity = 'NEEDS_NEW_FLAG' LIMIT 1;
```

**Rediscovery trigger:** any `empty_domain` gap → re-call Round 1 **scoped to that domain/flag** (not a full re-run), merge new candidates by `content_hash`. `incomplete_domain` and `missing_flag` → surface in UI (block “complete”), human-driven. Never auto-mark a domain "done" while a gap is open.

---

## 9. Human Review Workflow (Round 4)

### 9.1 Obligation state machine

```
 candidate ──(send to review)──▶ in_review ──(approve)──▶ approved ──(promote)──▶ live
     ▲                              │  │                                            │
     │                       (reject│  │request_changes)                     (retire)│
     └──────────────────────────────┘  ▼                                            ▼
                                     candidate(edited)                            retired
```

### 9.2 Review state machine

```
 pending ──approve──▶ approved          (→ obligation: approved → live)
 pending ──reject───▶ rejected          (→ obligation: retired)
 pending ──request_changes──▶ changes_requested  (→ obligation: back to candidate, editable)
```

### 9.3 Owner override flow

```
obligation.owner_team (llm) ─┐
engine owner_team ───────────┼─ disagree? → flag in review → human picks
                             └─ PATCH /obligations/{id}/owner
                                  → set owner_team, owner_team_overridden=true
                                  → owner_assignments(source='human')
                                  → reused on all future rediscovery (sticky)
```

### 9.4 Audit logging

Every transition writes `obligation_versions` (snapshot + `change_reason` + actor) and, for owner changes, `owner_assignments`. Reviews write `reviews` (state, reviewer, comment, decided_at). Nothing drives a `deadline_instance` until `status='live'`.

---

## 10. Engineering Tickets (Jira)

**Backend**
- `BE-1` Schema + migrations (all §2 tables, enums, indexes). *deps: none · 5pts*
- `BE-2` Entity + licence CRUD endpoints; FYE canonicalizer. *deps: BE-1 · 3pts*
- `BE-3` Licence file ingest (PDF/txt extract, store text + authorized_activities). *deps: BE-2 · 5pts*
- `BE-4` Condition evaluator + `build_attrs` (Round 2/3). *deps: BE-1 · 5pts*
- `BE-5` Filtering endpoint + labelling. *deps: BE-4 · 3pts*
- `BE-6` Owner-team engine + 8-case fixtures. *deps: BE-1 · 3pts*
- `BE-7` Calendar engine (parser, scheduled, event, idempotent upsert). *deps: BE-1 · 8pts*
- `BE-8` Gap detection + scoped rediscovery trigger. *deps: BE-5, AI-2 · 5pts*
- `BE-9` Review workflow + state machine + audit (versions/owner_assignments). *deps: BE-1 · 5pts*
- `BE-10` Dedupe (`content_hash`) + obligation versioning on writes. *deps: BE-1 · 3pts*

**AI**
- `AI-1` `DiscoveryResult` Pydantic schema + condition grammar validators. *deps: BE-1 · 3pts*
- `AI-2` Discovery service: prompt build, Claude call (temp 0), validate, retry. *deps: AI-1 · 8pts*
- `AI-3` Hallucination guards (source-required, no-mandatory, confidence enum) + coverage_notes persistence. *deps: AI-2 · 3pts*
- `AI-4` LLM-vs-engine owner reconciliation surfacing. *deps: AI-2, BE-6 · 2pts*

**Frontend**
- `FE-1` Entity create/edit (incl. FYE day+month picker). *deps: BE-2 · 3pts*
- `FE-2` Licence upload UI + extracted-activities display. *deps: BE-3 · 3pts*
- `FE-3` Discovery trigger + progress + coverage-notes panel. *deps: AI-2 · 3pts*
- `FE-4` Activity questionnaire (Yes/No/TBC, secondary thresholds, multi-select, real figures). *deps: BE-5 · 5pts*
- `FE-5` Review board (states, approve/reject, owner override, function filter w/ all 4 teams). *deps: BE-9 · 5pts*
- `FE-6` Calendar + deadlines view. *deps: BE-7 · 5pts*
- `FE-7` Gap banners (empty/incomplete/missing-flag). *deps: BE-8 · 2pts*

**DevOps**
- `OPS-1` CI (lint, `tsc --noEmit`, `py_compile`, unit tests). *deps: none · 3pts*
- `OPS-2` Migrations runner + seed (jurisdictions, regulators, activities, thresholds). *deps: BE-1 · 3pts*
- `OPS-3` Secrets/env (Anthropic key, LIVE flag), per-env config. *deps: none · 2pts*
- `OPS-4` LLM cost/latency dashboards + alerting. *deps: AI-2 · 3pts*

**QA**
- `QA-1` Owner-team 8-fixture regression. *deps: BE-6 · 2pts*
- `QA-2` Condition-evaluator unit suite (incl. unknown→safe-include). *deps: BE-4 · 3pts*
- `QA-3` Calendar golden tests (FYE+9mo, quarter_end+30d, event+15d, leap/clamp). *deps: BE-7 · 3pts*
- `QA-4` Gap-detection integration (empty/incomplete/missing). *deps: BE-8 · 3pts*
- `QA-5` Discovery determinism test (same input → same `content_hash` set). *deps: AI-2 · 2pts*

---

## 11. Production Risks

| Failure mode | Detection / monitoring | Mitigation |
|---|---|---|
| **LLM hallucinated obligation (no real source)** | Validator reject-rate metric; reviewer rejects | Source-required gate; confidence enum; human Round-4 gate before live |
| **Missed obligation (research gap)** | Gap-detection counts; `coverage_notes=Partial`; reviewer feedback | Assume-all-on Round 1; gap checks block "complete"; scoped rediscovery |
| **Non-deterministic discovery (drift across runs)** | Determinism test; alert if same entity yields new `content_hash`es | temperature 0; dedupe by hash; reconcile drafts to latest run |
| **Mandatory mislabel (pre-Round-3)** | Invariant test: no `mandatory` before filter ran | Model forbidden to label; labels only set in Rounds 2–3 |
| **Owner mistag** | LLM-vs-engine disagreement rate; 8-fixture CI | Deterministic engine + human override (sticky) |
| **Wrong deadline (parse/anchor)** | Calendar golden tests; alert on un-parseable `deadline_rule` | Strict parser; FYE canonicalized; idempotent regen; clamp month-ends |
| **DB column overflow / 500** | 5xx rate, Sentry | Canonicalize/clamp inputs (e.g. FYE→`DD-Mon`); typed columns |
| **LLM latency/timeout (cold start)** | p95 latency, timeout rate | Retry w/ backoff; async job + status poll; prompt caching |
| **Duplicate accumulation across refresh** | Obligation count growth alert | `content_hash` dedupe + reconcile-to-latest-run |
| **Anthropic outage / quota** | API error rate, budget alert | Graceful "AI off" response; queue + retry; per-env key |

**Observability requirements:** structured logs per round (entity_id, round, counts, gaps), discovery audit log (extracted facts + obligation source counts), LLM token/cost/latency metrics, validator reject reasons, deadline-generation counts, audit trail queryable by obligation.

---

## 12. Final Deliverable — build order

A team can start immediately in this order (critical path bolded):

1. **`BE-1` schema + `OPS-2` seed** → foundation.
2. **`AI-1` + `AI-2`** discovery service (temp 0, validated) ∥ `BE-2/3` entity+licence.
3. **`BE-4/5` condition evaluator + filtering** ∥ `BE-6` owner engine (+`QA-1`).
4. `BE-8` gap detection → scoped rediscovery; `BE-7` calendar (+`QA-3`).
5. `BE-9` review workflow + audit; `BE-10` dedupe/versioning.
6. Frontend `FE-1…FE-7` against the live APIs.
7. `OPS-1/3/4` CI + observability; `QA-2/4/5` integration + determinism.

**Non-negotiable invariants** (encode as tests): Round 1 never labels Mandatory · unknown attribute → safe-include + verify · every obligation has a source or is rejected · owner_team ∈ {Finance,Compliance,Legal,HR} always · deadlines stored as rules, computed live · nothing drives a deadline_instance until `status='live'` · discovery is deterministic (temp 0) and deduped by `content_hash`.
