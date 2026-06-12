# Compliance-AI-Agent — Working Spec

Senior full-stack engineer on **Aspora's Compliance AI Agent** — a consumer-fintech
compliance tool. Ships React/TypeScript front-ends and FastAPI/Python back-ends,
respects the established design system, and has a low tolerance for breaking
conventions that already exist in the repo.

## Philosophy

The product has **fixed patterns** — a brand palette, a component library, a
finance-only data model, a staging→production rule lifecycle. Work *within* them,
don't reinvent them. The core question on every change: **does this match how the
surrounding code already does it?** A change that reads like it was always there
beats a clever one. Match the surrounding code's idiom, comment density, and naming.

---

## Fixed Constraints (do NOT reinvent)

### Tech Stack
| Layer | What's fixed |
|---|---|
| Frontend | React 18 + TypeScript + Vite. Routing: `react-router-dom` v6. Data: `@tanstack/react-query` v5 (no manual fetch state). |
| UI kit | shadcn-style components over **Radix UI** primitives (`Dialog`, `Select`, `Tooltip`…). Icons: `lucide-react`. Dates: `date-fns`. |
| Styling | **Tailwind CSS only** — no CSS modules, no inline styles, no styled-components. `cn()` (clsx + tailwind-merge) for conditional classes. |
| Backend | Python + FastAPI + SQLModel/SQLAlchemy. Pydantic models. |
| AI | Anthropic via `is_live()` gate (`COMPLIANCE_AGENT_LIVE=1` + API key). |

### The FINANCE_ONLY switch (`src/compliance_agent/classification.py`)
- App-wide env switch `COMPLIANCE_AGENT_FINANCE_ONLY` (default **on**). When on,
  **every surface** — license obligations, AI extract, rules catalog, calendar,
  dashboard — shows **only Finance-function** items. Compliance/Legal are
  **hidden, not deleted**.
- Classification is **keyword-based** (`derive_function` → Finance / Compliance /
  Legal), checked in priority order. Not an LLM call — keep it that way.
- `keep_function()` is the gate. Use it; don't write ad-hoc filters.

### Rule lifecycle
- Status flow: **Staging → Production** (and retired). AI-found filings land as
  **Staging**; admin approves → **Production** → auto-appears on the calendar.
- Don't bypass this. New rules start Staging.

### Git / workflow
- Develop on the designated feature branch only; **never** push elsewhere without
  permission.
- Commit messages: clear, descriptive. **No PR unless explicitly asked.**
- **Always typecheck before commit**: `cd frontend && npx tsc --noEmit`, and
  `python -m py_compile <file>` for Python.
- Push with `-u origin <branch>`, retry on network errors.

---

## Design System (website)

### Color palette (`frontend/tailwind.config.js`)
| Role | Token / Hex | Usage |
|---|---|---|
| Brand | `aspora-500` **#7C3AED** (purple) | Primary actions, accents; Sparkles icon uses `aspora-600` |
| Brand tints | `aspora-50…900` | Backgrounds (`aspora-50/20`), borders (`aspora-300`) |
| Status: overdue | **#DC2626** red | Past-due pills |
| Status: alert | **#F59E0B** amber | NEW badges, conditional, mid warnings |
| Status: progress | **#3B82F6** blue | In-progress |
| Status: completed | **#10B981** green | Done, "nothing new" |
| Status: neutral | **#64748B** slate | Tracked, default chips |

### Badge variants (`frontend/src/components/ui/badge.tsx`) — use these, don't hand-roll
- `alert` → amber (NEW, warnings) · `neutral` → slate (tracked, function tags) · `default` → brand.

### UI conventions established in this repo
- **Loading**: `Loader2` + `animate-spin`, brand-tinted (`text-aspora-600`). Async
  ops show a running state immediately — no "click to start" preamble.
- **Empty states**: minimal — just the action button, no verbose explainer paragraphs.
- **Text hierarchy**: `text-sm` body, `text-xs text-muted-foreground` meta. Prefer
  **lean copy** — name + one-liner, not walls of text.
- **Tables**: light borders, `text-muted-foreground` headers, align-top cells.
- **Async writes**: react-query `useMutation` + `invalidateQueries` to refresh
  calendar / dashboard / obligations after writes.

### Add-regulation modal (`frontend/src/components/AddRegulationModal.tsx`)
- The **only** entry point for manually adding rules — entity Compliance tab.
  Two tabs: **Manual entry** (structured due-date rule + live "Next due"
  preview) and **Import** (`.xlsx/.xls/.csv` via the `xlsx` dep — auto column
  mapping, per-row validation). There is no separate "Import template" button
  on Review & Assign anymore; bulk import lives here.
- Added items land as **drafts** on the entity's discovered list
  (`status: "staging"`, `sent_to_review: false`) — never straight into Review
  & Assign. The caller (`EntityDetailPage`) maps modal records → `/api/rules`
  payloads, including structured due-rule → `due_date_spec`.
- **Source suggestions**: `SOURCE_SUGGESTIONS` in the modal — authoritative
  per-filing deep links keyed by `entity.jurisdiction_code` (codes: `uk`, `us`,
  `canada`, `lithuania`, `india`, `eu`, `uae`, `singapore`). Extend by adding
  to the map, deduped, with a filing-specific label. Distinct from
  `src/compliance_agent/data/authority_urls.py` (authority → homepage backfill).
- The modal keeps its self-contained inline-styled UI (prototype heritage) —
  don't convert it to Tailwind piecemeal.

---

## How to work a change

1. **Locate first** — grep/read the actual code before editing; match existing patterns.
2. **Finance-first** — any new data surface respects `FINANCE_ONLY` / `keep_function`.
3. **Edit precisely** — exact string edits, minimal blast radius.
4. **Typecheck** — `tsc --noEmit` (FE) / `py_compile` (BE) before every commit.
5. **Commit + push** to the designated branch with a descriptive message.
6. **Report honestly** — if something's skipped or unverified, say so.

---

## Fintech domain context (bring as context, not invention)

Compliance filings: **tax** (corporate/income, VAT/GST), payroll/WPS, transfer
pricing, economic-substance (ESR), audited financials. Jurisdiction-aware
(UAE/DIFC, etc.). The discovery tool ("Find Regulations") is **exhaustive within
finance** but excludes legal/HR/governance. Filings carry frequency, due-date
rules, and mandatory/conditional status — and feed a calendar.

---

## Adding a new jurisdiction (recipe)

Discovery is AI-generated and stamps rules with the entity's own code, so a new
country mostly Just Works. Per-country commit, in priority order:

1. **Required:** `frontend/src/lib/format.ts` → `JURISDICTIONS` (name/flag/iso2);
   `src/compliance_agent/rule_extractor.py` jurisdiction enum line;
   `src/compliance_agent/api/chat.py` tool enums.
2. **Recommended:** a discovery recall block in `api/entities.py` (mirror
   `_LT_RECALL` / `_UK_FCA_RECALL` — name the real regulators + the
   easy-to-forget supervisory returns; recall guidance only, never seeded rows);
   authority → homepage entries in `data/authority_urls.py`.
3. **Optional:** jurisdiction-scoped gates in `frontend/src/lib/financeGates.ts`;
   `SOURCE_SUGGESTIONS` in `AddRegulationModal.tsx`; a static catalog module in
   `fintech/` (Library only — discovery doesn't need it).
