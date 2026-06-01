# Aspora Compliance OS — How It Works

A first-time guide to the whole workflow, from setting up an entity to filing
on time. Read this top to bottom once and the app will make sense.

---

## 1. The big picture

Aspora Compliance OS keeps track of **every regulatory filing and payment your
companies owe, who owns each one, and when it's due** — and nudges people on
Slack/email before deadlines.

The data flows in one direction:

```
Entity  →  License  →  Rules  →  Obligations (filings)  →  Calendar / Tasks
(company)  (permit)   (what you   (one per due date)        (where you
                       must file)                            work on them)
```

- **Entity** — a company you manage (e.g. *Vance Techlabs Limited*).
- **License** — a permit/authorisation that company holds (e.g. *DIFC
  Registrar*, *FCA Authorisation*). Drives which rules apply.
- **Rule** — a recurring requirement (e.g. *"File a Change Notification to the
  DIFC Registrar"*, monthly/quarterly/annual).
- **Obligation (a.k.a. "filing")** — one concrete instance of a rule with a
  real due date (e.g. *that notification, due 2026‑07‑31*). This is the thing
  people actually work on.

---

## 2. Who can do what (roles)

| Role | Can do |
|------|--------|
| **Admin** | Everything — add entities/licenses, run AI extraction, promote rules, schedule filings, assign work to people, verify & close filings, delete filings. |
| **Employee** | Works on the filings assigned to them — updates status, adds the filing reference/payment details, uploads proof, submits for review. Cannot reassign or close other people's work. |

---

## 3. One-time setup — getting a filing onto the calendar

This is the path from "I have a license PDF" to "the filing shows up on the
calendar". **Admin** does all of this.

```
1. Upload the license
   Licenses page → Add license → fill the details (or attach the PDF
   and let AI auto-fill the form).
                ↓
2. Extract filings with AI
   Open the license → click "Extract with AI". Claude reads the PDF and
   returns candidate filings, each tagged with applicability:
   ★ Mandatory  /  Conditional  /  Sector-specific.
                ↓
3. Keep the ones that apply
   Tick the candidates you want → they're created as STAGING rules,
   attached to this license's entity. (Staging = draft, not live yet.)
                ↓
4. Review & promote to Production
   Go to the Rules page (or the license's rule list), check each staging
   rule, then promote it to PRODUCTION. Only production rules can be
   scheduled.
                ↓
5. Schedule the filing
   On a rule's row — or in the license's "Applicable regulations" table —
   click [ + Schedule ]. This creates an Obligation with a sensible
   due date (monthly → +30d, quarterly → +90d, annual → +1y, etc.).
   You can also pick the due date and assign an owner here.
                ↓
6. It's now on the Calendar
   The obligation appears on the Calendar at its due date. Use the
   "★ Mandatory only" filter to see just the must-files, or filter by
   tax type (Direct / Indirect / Not a Tax), entity, or jurisdiction.
```

> **Tip:** You only do steps 1–4 once per license. After that you just
> schedule new periods (step 5) whenever a new filing cycle starts.

---

## 4. Day-to-day — the filing workflow

Once a filing is scheduled and assigned, it moves through a **4-step team
handoff**. The colored stepper at the top of every filing shows exactly where
it is and who owns it right now.

```
Step 1 — COMPLIANCE: Prepare filing
   The compliance owner fills in the filing reference + uploads supporting
   docs, then clicks "Mark filing complete" (submit for review).
                ↓
Step 2 — ADMIN: Verify filing
   Admin reviews the work and either:
     • "Approve & hand off to finance"  (if a payment is needed), or
     • "Approve without payment"        (closes it — done), or
     • "Send back"                      (returns it to compliance).
                ↓
Step 3 — FINANCE: Log payment   (only if a payment is needed)
   The finance owner enters the payment amount + UTR / transaction id,
   then clicks "Mark payment complete" (submit for review).
                ↓
Step 4 — ADMIN: Final sign-off
   Admin verifies the payment reference and clicks "Approve & close".
   The filing is now Done. ✓
```

**Status meanings** (the colored pill on each filing):

| Status | Means |
|--------|-------|
| Not started | Nobody has begun yet |
| In progress | Someone is actively working on it |
| Pending review | Submitted — waiting for admin to verify |
| Completed | Done & signed off ("Filed") |
| Not applicable | Admin marked it as not relevant (escape hatch) |

---

## 5. The everyday buttons (filing detail)

- **Update status** — move within your own leg (Haven't started ↔ Working on
  it). The final "done" move is the big primary button so you can't submit by
  accident.
- **Assign** — (admin) give the filing to a person. Shows a ✓ when someone is
  assigned, a ＋ when it's still unassigned.
- **Mark filing complete / Mark payment complete** — submit your leg for admin
  review.
- **Approve & close / Send back / Reopen** — admin-only verification controls.
- **Delete** — (admin, far right, in red) permanently remove a filing. Used
  when a license/rule no longer applies. Uploaded proof documents are kept;
  comments and notifications are removed. There's a confirm prompt — it can't
  be undone.

---

## 6. Where everything lives

| Page | What you'll find |
|------|------------------|
| **Dashboard** | At-a-glance: overdue, due-soon, awaiting review, by team. |
| **Calendar** | Every filing on its due date. Filter by ★ Mandatory, tax type, entity, jurisdiction, status, assignee. |
| **Tasks** | Your personal work inbox. Tabs: *Assigned to me* / *Watching* / *Completed* / *All*. **A "Filed" / completed filing moves to the "Completed" tab here.** |
| **Entities** | Your companies. Open one to see its Licenses, rules, and obligations. |
| **Licenses** | Upload, AI-extract, and schedule from licenses. |
| **Rules** | All requirements. Staging rules are reviewed/promoted here. |
| **Documents** | Every uploaded file (license PDFs, proof-of-filing, etc.). |
| **Audit log** | Who did what, when. (Admins can clear it.) |

---

## 7. Reminders & Slack

- **Reminders** go out before each due date — Monthly: 7 days, Quarterly: 30
  days, Annual: 45 days before.
- They arrive by **email** and as **Slack cards**. Each Slack card has:
  - **Open the obligation →** — opens the filing in the app.
  - **In progress / For review / Filed** — change the status straight from
    Slack, no need to open the site.
- Weekly admin digest + daily employee brief are also delivered automatically.

---

## 8. Quick glossary

- **Obligation = Filing** — the same thing (one due-dated task).
- **Applicability** — how strongly a rule applies: **★ Mandatory** (must file),
  **Conditional** (only if certain things are true), **Sector-specific**.
- **Tax type** — **Direct Tax**, **Indirect Tax**, or **Not a Tax** — used to
  filter the calendar.
- **Staging vs Production** — staging rules are drafts; only production rules
  can be scheduled into real filings.
- **Leg** — one side of a filing: the *compliance* (filing) leg or the
  *finance* (payment) leg.

---

### TL;DR for a brand-new user
1. Add an **entity** (company).
2. Add its **license** → **Extract with AI** → keep the filings you need.
3. **Promote** them to production → **Schedule** them.
4. They show up on the **Calendar** and in people's **Tasks**.
5. Compliance prepares → Admin verifies → Finance pays → Admin signs off → **Filed.**
