// Settings — proper tabbed shell. Profile is available to every user; the
// rest are admin-only (visible to non-admins with a Lock badge but read-only).
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Copy,
  Lock,
  Mail,
  Slack,
  Calendar as CalendarIcon,
  Plus,
  ChevronRight,
  Globe,
  Bell,
  Key,
  CheckCheck,
  Building2,
  ListChecks,
  Loader2,
  Trash2,
  Pencil,
  X,
  BookOpen,
  RotateCcw,
} from "lucide-react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/EmptyState";
import { Markdown } from "@/components/Markdown";
import { useAuth } from "@/contexts/AuthContext";
import { JURISDICTIONS, userInitials } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/api";
import type { Entity, Role, Rule, UserBrief, UserOut } from "@/types/api";


type TabKey =
  | "playbook"
  | "profile"
  | "users"
  | "integrations"
  | "jurisdictions"
  | "alerts"
  | "retention"
  | "api";


const TABS: { key: TabKey; label: string; adminOnly?: boolean; icon: React.ComponentType<{ className?: string }> }[] = [
  // Everyone — how the workspace works + the rules for writing due dates.
  { key: "profile", label: "Profile", icon: Bell },
  { key: "playbook", label: "Playbook & Guide", icon: BookOpen },
  { key: "users", label: "Users & Roles", adminOnly: true, icon: Building2 },
  { key: "integrations", label: "Integrations", adminOnly: true, icon: Slack },
  { key: "jurisdictions", label: "Jurisdictions", adminOnly: true, icon: Globe },
  { key: "alerts", label: "Alert policies", adminOnly: true, icon: ListChecks },
  { key: "retention", label: "Audit retention", adminOnly: true, icon: Trash2 },
  // "api" / "API & Webhooks" tab is hidden until the endpoints exist.
  // Re-add the entry above with the same shape once tokens + webhook
  // delivery ship for real.
];


export function SettingsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = (searchParams.get("tab") as TabKey | null) ?? "profile";
  const [tab, setTabState] = useState<TabKey>(initialTab);

  function setTab(next: TabKey) {
    setTabState(next);
    // Mirror to the URL so deep-linking + back-button work.
    const next_params = new URLSearchParams(searchParams);
    if (next === "profile") next_params.delete("tab");
    else next_params.set("tab", next);
    setSearchParams(next_params, { replace: true });
  }

  if (!user) return null;

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Your account, workspace, and integrations." />

      <div className="grid grid-cols-1 md:grid-cols-[220px_1fr] gap-6">
        <nav className="space-y-1">
          {TABS.map((t) => {
            const Icon = t.icon;
            const gated = t.adminOnly && !isAdmin;
            return (
              <button
                key={t.key}
                onClick={() => !gated && setTab(t.key)}
                disabled={gated}
                className={cn(
                  "w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2",
                  tab === t.key
                    ? "bg-aspora-50 text-aspora-800 font-medium"
                    : "hover:bg-secondary text-foreground/80",
                  gated && "text-muted-foreground/60 cursor-not-allowed",
                )}
              >
                <Icon className="h-3.5 w-3.5 shrink-0" />
                <span className="flex-1 truncate">{t.label}</span>
                {gated && <Lock className="h-3 w-3 shrink-0 opacity-60" />}
                {!gated && tab === t.key && <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
              </button>
            );
          })}
        </nav>

        <div className="min-w-0">
          {tab === "playbook" && <PlaybookTab />}
          {tab === "profile" && <ProfileTab user={user} />}
          {tab === "users" && isAdmin && <UsersTab />}
          {tab === "integrations" && isAdmin && <IntegrationsTab />}
          {tab === "jurisdictions" && isAdmin && <JurisdictionsTab />}
          {tab === "alerts" && isAdmin && <AlertPoliciesTab />}
          {tab === "retention" && isAdmin && <RetentionTab />}
        </div>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Playbook & Guide — everyone-visible guide; admins can edit the whole thing.
// Content is markdown, persisted server-side (/api/playbook). When nothing is
// saved we render DEFAULT_PLAYBOOK_MD below, which is also what the editor
// seeds from — so admins edit from the real guide, not a blank box.
// ---------------------------------------------------------------------------
const DEFAULT_PLAYBOOK_MD = `## Aspora Compliance OS — Playbook & Guide

New here? Read this once, top to bottom. It walks the whole journey — from adding a company to a filing being signed off — in the order you'll actually do it. **Admins** set everything up; **employees** work the filings assigned to them.

### How it all fits together

Everything flows in one direction — each step feeds the next:

\`\`\`
Entity → Licence → Primary Activity → Compliance (discover) →
Review & Assign (approve + owner) → Calendar → Filings (do the work) → Filed
\`\`\`

- **Entity** — a company you manage (e.g. *Aspora UK Ltd*).
- **Licence** — a permit/authorisation it holds. Helps the AI work out what it must file.
- **Rule** — a recurring requirement (e.g. *VAT return, quarterly*).
- **Obligation / Filing** — one real, due-dated instance of a rule (e.g. *that VAT return, due 7 Aug*). This is what people actually work on.

---

### Step 1 — Add the entity (company)

Go to **Entities → "Add entity"** (admin only). Fill in:

- **Legal name** and **Jurisdiction** — required.
- **Legal type**, **Short code**, **Registration number** — optional identifiers.
- **Nature of operation** — one line on what the company does (e.g. *cross-border remittance & payments*). **The AI reads this to discover regulations**, so write it properly.
- **Fiscal year end** — *important.* Many deadlines are "X months after financial year-end", so the calendar can't place them without it.
- **Ownership** — optional parent → subsidiary chain.

Save, then open the entity. You'll see five tabs: **Overview · Licences · Primary Activity · Compliance · Documents.**

---

### Step 2 — Add its licence(s)

Open the **Licences** tab → **"Upload license"**. Attach the licence PDF (the AI can auto-fill the details) or type them in. A licence records the authority, number and expiry — and, with the nature of operations, tells discovery what this company is regulated to do.

> **Required before discovery:** the **Refresh Regulations** button stays disabled until the entity has at least one licence uploaded *and* a nature of operations — the AI reads the licence text itself to ground what it finds.

---

### Step 3 — Set the Primary Activity

Open the **Primary Activity** tab and answer each activity **Yes / No / TBD** (TBD = *to be decided* — everything starts there until you answer) — e.g. *"Does the entity trade cross-border?"*

- **What they do:** gate the follow-up questions, and decide whether a discovered filing ends up **mandatory** or **conditional** for this entity.
- **What they don't do:** they **don't change what discovery finds.** Discovery always assumes every activity could apply; the assessment narrows it down afterwards.

---

### Step 4 — Discover the regulations

Open the **Compliance** tab → **"Refresh Regulations"** (the Sparkles button). The AI reads the nature of operations, jurisdiction and licences (~20–30s) and fills the **"Discovered (AI generated)"** list with every finance filing this company could owe. (Finance only — Legal / HR / governance are out of scope.)

Missed something? Use **"Add regulation"** — a two-tab dialog:

- **Manual entry** — type the filing and build its due date visually (frequency → rule) with a live **"Next due"** preview, so you don't guess. Where the app knows authoritative links for the jurisdiction, pick one under **Suggested sources**.
- **Import** — upload your obligations register as **Excel or CSV**. Columns auto-map (adjustable), each row is validated, and a blank template is downloadable.

Anything you add lands as a **draft on this entity's discovered list** — exactly like the AI's finds. Nothing is live yet.

---

### Step 5 — Find what actually applies

Still in **Compliance**, click **"Activities"**. Answer the follow-up and operation-specific questions (they appear based on your Primary Activity answers), then click **"Find applicable regulations"** (~15–25s). The AI sorts the discovered list into three columns:

- **Mandatory** — required for this entity now.
- **Conditional** — applies only if a threshold or trigger is met.
- **Not applicable** — ruled out by your activity answers; it won't be filed.

Tick the ones you want (mandatory + conditional come pre-ticked) and click **"Add … to Review & Assign"**. That is the moment a draft leaves the entity and enters the shared **Review & Assign** queue.

---

### Step 6 — Review & Assign (approve + pick owners)

Open **Review & Assign** in the sidebar (admin only). Two tabs:

- **For Action** — everything waiting for you; each item carries an **"Awaiting review"** badge.
- **Approved** — already live.

Click a **For Action** card to expand it, then:

1. **Check / fix the details** — hit **"Edit"** to correct the form name, authority, category, due-date rule, applicability, tax type, etc.
2. **Assign ownership** — set an **Assignee** (the person who does the work) and an **Approver** (the admin who signs it off). The app may auto-suggest a team.
3. Click **"Approve & assign"**.

On approve, the rule moves to **Approved** and the app **automatically generates the dated obligation(s)** from its frequency + due-date rule — and they show up on the Calendar immediately. (You can still change the owner later from the Approved tab; it re-syncs to the calendar.)

*Don't need it?* **Archive** (reversible, keeps history) or **Delete** (permanent).

---

### Step 7 — It's on the Calendar

Open **Calendar** ("Compliance Calendar") — every obligation across every entity, on its due date. Only **Approved** rules appear here. Two views: **Heatmap** (triage at a glance) and **List** (scan / sort). Filter by **entity, jurisdiction, tax type, applicability, authority, category, status,** and **assignee**. In **List** view you can multi-select rows and **assign** or **change status** in bulk from the bar at the bottom.

---

### Step 8 — Do the work (Filings)

**Filings** (sidebar) is each person's queue. Tabs: **Assigned to me · Completed · All**. Items are grouped **Overdue → In alert window → In progress → Upcoming → Completed**, each with a coloured **status pill**: *Not started · In progress · Pending review · Completed · N/A.*

Open a filing and the buttons walk you through a **4-step handoff**:

1. **Compliance prepares** — add the filing reference, upload proof, then **"Mark filing complete"**.
2. **Admin verifies** — **"Approve & hand off to finance"** (if a payment is due), or close it; or **"Send back"** to fix.
3. **Finance pays** — enter the amount + transaction reference, then **"Mark payment complete"**.
4. **Admin signs off** — **"Approve & close"**. The filing is now **Filed** and moves to Completed.

(No payment needed? The admin just closes it at step 2.)

---

### Writing due dates

Most of the time you'll use the **visual due-date builder** in *Add regulation* — pick the frequency and the rule, and watch the **"Next due"** preview. You only type a due date as **free text** when editing a rule's deadline in Review & Assign, or in an **import file's deadline column**. When you do, use one of these shapes:

| What you want | Type it like this | Frequency |
|---|---|---|
| Monthly, on a fixed day | \`by the 25th of the following month\` | Monthly |
| Annual, fixed calendar date | \`by 30 Jun\` · \`31 Dec\` | Annually |
| Within N months of FY-end | \`within 9 months of the financial year end\` | Annually |
| Month + day after period end | \`15th day of the 6th month after the end of the tax period\` | Annually / Quarterly |

> **Avoid vague text** like \`annually\`, \`as required\`, or \`see regulation\`. If the parser can't read a real deadline it falls back to "today + interval", so the date drifts day-to-day instead of sitting on the true statutory deadline.

**What the frequencies mean:**

| Frequency | Meaning | Example |
|---|---|---|
| Annual | Once a year | Annual accounts |
| Semi-annual | Twice a year | Half-yearly regulatory return |
| Quarterly | Every quarter | VAT return |
| Monthly | Every month | Payroll / RTI |
| One-time | Once, on a specific date | Initial registration |
| Event-based | Only when something happens — no scheduled date | Change-in-control notification |
| Continuous | Must be kept in place at all times — no scheduled date | AML programme, sanctions screening |

> **Event-based** and **Continuous** filings don't get calendar dates — pick them in the due-date builder and the rule is tracked without a schedule.

---

### Reminders & Slack

Reminders go out **before** each due date (Monthly ≈ 7 days, Quarterly ≈ 30 days, Annual ≈ 45 days ahead) by **email** and **Slack**. From a Slack card you can open the filing or change its status (**In progress / For review / Filed**) without leaving Slack — the website updates automatically.

**Get @-mentioned in Slack (one-time, per person):** Slack only pings you when the app knows your Slack **member ID** — a display name isn't enough.

1. In Slack: click your profile photo → **Profile** → **⋮ (three dots)** → **"Copy member ID"** (looks like \`U07ABC123\`).
2. In the app: **Settings → Profile → "Your Slack member id"** → paste → **Save**.

Once set, alert cards mention you with a real blue **@name** (and your status-button clicks in Slack are credited to your user). Without it, cards just show your name in bold — no ping. Turn the email/Slack toggles on under **Settings → Profile**.

### Google Calendar

Every **assigned** filing is pushed automatically to the shared **"Aspora Compliance"** Google Calendar — an all-day event on the filing's **due date**, titled *"filing — entity (Assignee: name)"*, with a link back to the filing.

- **Assign / reassign** → the event appears or updates within seconds.
- **Complete, mark N/A, or unassign** (in the app or via the Slack buttons) → the event disappears.
- One filing = one event, no duplicates — the app keeps them in sync on its own.

**Seeing the calendar (one-time, per person):** ask an admin to share the *Aspora Compliance* calendar with you ("See all event details"), then click **"Add this calendar"** in the invite email and make sure its checkbox is ticked in Google Calendar's sidebar. After that, every assignment shows up automatically — nothing to do per filing.

> **The app is the source of truth.** Don't edit or delete these events inside Google Calendar — the app will overwrite manual changes on its next sync. To change a date or owner, change it on the filing.

*(Admins: the connection itself is configured once under **Settings → Integrations → Google Calendar** — setup steps and a "Send test event" button live on that card.)*

---

### Where everything lives

| Page | What it's for |
|---|---|
| **Home** | Overdue / due-soon / awaiting-review at a glance. |
| **Calendar** | Every due date across entities — the source of truth. |
| **Filings** | Your work queue: prepare, attach proof, mark complete. |
| **Documents** | Licence PDFs and proof-of-filing. |
| **Entities** | Companies, fiscal year-ends, and licences (admin). |
| **Review & Assign** | Approve discovered filings and set owners (admin). |
| **Regulation Library** | Browse the full finance-filing catalogue. |
| **Audit Log** | Who did what, when (admin). |

---

### In one breath

Add the **entity** → upload its **licence** → set its **Primary Activity** → **Refresh Regulations** → **Find applicable regulations** → send them to **Review & Assign** → **Approve & assign** an owner → it lands on the **Calendar** and in that person's **Filings** → Compliance prepares, Admin verifies, Finance pays, Admin closes → **Filed.**

Most days you live in **Calendar** and **Filings**; the setup steps (1–6) you only repeat when you add a company or a new licence.
`;


interface PlaybookData {
  markdown: string | null;
  updated_at: string | null;
}


function PlaybookTab() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ["playbook"],
    queryFn: () => api.get<PlaybookData>("/api/playbook"),
  });

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const save = useMutation({
    mutationFn: (markdown: string) =>
      api.post<PlaybookData>("/api/playbook", { markdown }),
    onSuccess: (fresh) => {
      queryClient.setQueryData(["playbook"], fresh);
      setEditing(false);
    },
  });

  const content = data?.markdown ?? DEFAULT_PLAYBOOK_MD;

  if (editing) {
    return (
      <Card>
        <CardContent className="p-6 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-semibold">Edit the Playbook</h3>
            <span className="text-[11px] text-muted-foreground">
              Markdown — headings (#), **bold**, lists, tables, and &gt; callouts
            </span>
          </div>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
            className="w-full h-[60vh] rounded-md border border-input bg-background p-3 font-mono text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-aspora-300"
          />
          {save.error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {(save.error as Error).message}
            </div>
          )}
          <div className="flex items-center gap-2">
            <Button onClick={() => save.mutate(draft)} disabled={save.isPending}>
              {save.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Save
            </Button>
            <Button variant="outline" onClick={() => setEditing(false)} disabled={save.isPending}>
              <X className="h-3.5 w-3.5" />
              Cancel
            </Button>
            <Button
              variant="ghost"
              className="ml-auto text-muted-foreground"
              onClick={() => setDraft(DEFAULT_PLAYBOOK_MD)}
              disabled={save.isPending}
              title="Replace the editor contents with the built-in default guide"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reset to default
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-6">
        {isAdmin && (
          <div className="flex justify-end -mt-1 mb-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setDraft(data?.markdown ?? DEFAULT_PLAYBOOK_MD);
                setEditing(true);
              }}
            >
              <Pencil className="h-3.5 w-3.5" />
              Edit
            </Button>
          </div>
        )}
        <Markdown source={content} />
      </CardContent>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------
interface NotificationPrefs {
  notify_email: boolean;
  notify_slack: boolean;
  slack_user_id: string | null;
}


function ProfileTab({ user }: { user: UserBrief }) {
  const queryClient = useQueryClient();
  const { data: prefs } = useQuery({
    queryKey: ["notification-prefs"],
    queryFn: () => api.get<NotificationPrefs>("/api/me/notification-prefs"),
  });

  const patchPrefs = useMutation({
    mutationFn: (patch: Partial<NotificationPrefs>) =>
      api.patch<NotificationPrefs>("/api/me/notification-prefs", patch),
    onSuccess: (fresh) => queryClient.setQueryData(["notification-prefs"], fresh),
  });

  const [slackId, setSlackId] = useState(prefs?.slack_user_id ?? "");
  useEffect(() => {
    if (prefs?.slack_user_id !== undefined) setSlackId(prefs.slack_user_id ?? "");
  }, [prefs?.slack_user_id]);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-6 space-y-4">
          <div className="flex items-center gap-4">
            <Avatar className="h-14 w-14">
              <AvatarFallback className="text-lg">
                {userInitials(user.full_name || user.email)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <div className="font-semibold">{user.full_name || "—"}</div>
              <div className="text-sm text-muted-foreground">{user.email}</div>
              <Badge variant="default" className="mt-1 capitalize">
                {user.role}
              </Badge>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 max-w-md">
            <div>
              <label className="text-xs text-muted-foreground">Timezone</label>
              <select className="h-9 w-full mt-1 rounded-md border border-input bg-background px-2 text-sm">
                <option>Asia/Kolkata (default)</option>
                <option>Europe/London</option>
                <option>America/New_York</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Language</label>
              <select className="h-9 w-full mt-1 rounded-md border border-input bg-background px-2 text-sm">
                <option>English</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6 space-y-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Notification preferences
          </h3>
          <ToggleRow
            icon={<Slack className="h-4 w-4" />}
            label="Slack alerts"
            description="Pings the workspace channel on assignment / submit-for-review / overdue. Needs an admin to paste a webhook URL under Settings → Integrations."
            checked={prefs?.notify_slack ?? true}
            onChange={(v) => patchPrefs.mutate({ notify_slack: v })}
          />
          <ToggleRow
            icon={<Mail className="h-4 w-4" />}
            label="Email"
            description="Assignment alerts, deadline reminders and password resets to your inbox — sent via the email integration configured under Settings → Integrations."
            checked={prefs?.notify_email ?? true}
            onChange={(v) => patchPrefs.mutate({ notify_email: v })}
          />

          <div className="pt-3 border-t border-border">
            <label className="text-xs font-medium text-muted-foreground">
              Your Slack member id (optional)
            </label>
            <div className="flex gap-2 mt-1.5 max-w-md">
              <Input
                value={slackId}
                onChange={(e) => setSlackId(e.target.value)}
                placeholder="U0123ABCD"
                className="font-mono text-xs"
              />
              <Button
                variant="outline"
                onClick={() =>
                  patchPrefs.mutate({ slack_user_id: slackId.trim() || null })
                }
                disabled={patchPrefs.isPending || slackId === (prefs?.slack_user_id ?? "")}
              >
                Save
              </Button>
            </div>
            {slackId.trim() !== "" &&
              !/\b[UW][A-Za-z0-9]{5,}\b/.test(slackId.trim().toUpperCase()) && (
                <div className="mt-1 text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1.5 max-w-md">
                  That doesn't look like a member ID — it starts with{" "}
                  <span className="font-mono">U</span> (e.g.{" "}
                  <span className="font-mono">U07ABC123</span>). Your display name
                  won't work: in Slack click your profile photo → <strong>Profile</strong>{" "}
                  → <strong>⋮</strong> → <strong>"Copy member ID"</strong>.
                </div>
              )}
            {patchPrefs.error && (
              <div className="mt-1 text-[11px] text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1.5 max-w-md">
                {(patchPrefs.error as Error).message}
              </div>
            )}
            <p className="text-[11px] text-muted-foreground mt-1">
              When set, Slack alerts ping you with a real <code className="font-mono">@</code>{" "}
              mention — and your status-button clicks in Slack are credited to you.
              Find it in Slack → your profile → ⋮ → "Copy member ID".
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6 space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Reminder schedule
          </h3>
          <p className="text-xs text-muted-foreground">
            When `compliance-agent send-reminders` runs (daily cron), it pings
            the assignee at the offset below for the filing's cadence. Each
            (person, filing, offset) fires exactly once.
          </p>
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Typical cadence</th>
                  <th className="px-3 py-2 text-left font-medium">Reminders sent</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {[
                  { cadence: "Monthly", offsets: "7 days before" },
                  { cadence: "Quarterly", offsets: "30 days before" },
                  { cadence: "Half-yearly", offsets: "45 days before" },
                  { cadence: "Annual", offsets: "60 days before" },
                  { cadence: "Multi-year / long-form", offsets: "90 days before" },
                ].map((r) => (
                  <tr key={r.cadence}>
                    <td className="px-3 py-2 text-muted-foreground">{r.cadence}</td>
                    <td className="px-3 py-2">{r.offsets}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <ChangePasswordCard />
    </div>
  );
}


function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmNext, setConfirmNext] = useState("");
  const [message, setMessage] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  const changeMutation = useMutation({
    mutationFn: () =>
      api.post<{ ok: boolean }>("/api/auth/change-password", {
        current_password: current,
        new_password: next,
      }),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setConfirmNext("");
      setMessage({ tone: "ok", text: "Password updated." });
    },
    onError: (e) =>
      setMessage({
        tone: "err",
        text: e instanceof ApiError ? e.message : String(e),
      }),
  });

  function submit() {
    setMessage(null);
    if (next.length < 6) {
      setMessage({ tone: "err", text: "Password must be at least 6 characters." });
      return;
    }
    if (next !== confirmNext) {
      setMessage({ tone: "err", text: "Confirm password doesn't match." });
      return;
    }
    changeMutation.mutate();
  }

  return (
    <Card>
      <CardContent className="p-6 space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Change password
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-2xl">
          <Input
            type="password"
            placeholder="Current password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
          <Input
            type="password"
            placeholder="New password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
          <Input
            type="password"
            placeholder="Confirm new password"
            value={confirmNext}
            onChange={(e) => setConfirmNext(e.target.value)}
          />
        </div>
        {message && (
          <div
            className={cn(
              "rounded-lg px-3 py-2 text-sm",
              message.tone === "ok"
                ? "border border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border border-destructive/30 bg-destructive/5 text-destructive",
            )}
          >
            {message.text}
          </div>
        )}
        <div>
          <Button
            onClick={submit}
            disabled={!current || !next || !confirmNext || changeMutation.isPending}
          >
            {changeMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Update password
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}


function ToggleRow({
  icon,
  label,
  description,
  checked,
  onChange,
}: {
  icon: React.ReactNode;
  label: string;
  description: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 border-b border-border last:border-0">
      <div className="flex items-start gap-3 min-w-0">
        <span className="h-8 w-8 rounded-md bg-secondary grid place-items-center text-foreground/70 shrink-0">
          {icon}
        </span>
        <div className="min-w-0">
          <div className="text-sm font-medium">{label}</div>
          <div className="text-xs text-muted-foreground">{description}</div>
        </div>
      </div>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-5 w-9 items-center rounded-full transition-colors shrink-0",
          checked ? "bg-aspora-600" : "bg-slate-300",
        )}
        role="switch"
        aria-checked={checked}
      >
        <span
          className={cn(
            "inline-block h-4 w-4 transform rounded-full bg-white transition-transform",
            checked ? "translate-x-4" : "translate-x-0.5",
          )}
        />
      </button>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Users & Roles — admin CRUD
// ---------------------------------------------------------------------------
function UsersTab() {
  const queryClient = useQueryClient();
  const { user: me } = useAuth();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [createdCredentials, setCreatedCredentials] = useState<{
    email: string;
    password: string;
  } | null>(null);
  const [editing, setEditing] = useState<UserOut | null>(null);

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users", "admin"],
    queryFn: () => api.get<UserOut[]>("/api/users/admin"),
  });

  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div>
            <div className="font-semibold">Workspace users</div>
            <div className="text-xs text-muted-foreground">
              Admin creates with an initial password; the user changes it on first sign-in.
            </div>
          </div>
          <Button onClick={() => setInviteOpen(true)}>
            <Plus className="h-3.5 w-3.5" />
            Invite user
          </Button>
        </div>
        {isLoading ? (
          <div className="p-6 space-y-3">
            <div className="h-10 bg-secondary/50 animate-pulse rounded" />
            <div className="h-10 bg-secondary/50 animate-pulse rounded" />
            <div className="h-10 bg-secondary/50 animate-pulse rounded" />
          </div>
        ) : (
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-secondary/30 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-5 py-2.5 text-left font-medium">Name</th>
                <th className="px-5 py-2.5 text-left font-medium">Email</th>
                <th className="px-5 py-2.5 text-left font-medium">Role</th>
                <th className="px-5 py-2.5 text-left font-medium">Team</th>
                <th className="px-5 py-2.5 text-left font-medium">Last active</th>
                <th className="px-5 py-2.5 text-left font-medium">Status</th>
                <th className="px-5 py-2.5 pr-6 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map((u) => (
                <tr key={u.id} className={cn("hover:bg-secondary/30", !u.is_active && "opacity-60")}>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <Avatar className="h-7 w-7">
                        <AvatarFallback className="text-[10px]">
                          {userInitials(u.full_name)}
                        </AvatarFallback>
                      </Avatar>
                      <span className="truncate">{u.full_name}</span>
                      {u.id === me?.id && (
                        <Badge variant="default" className="text-[10px]">
                          you
                        </Badge>
                      )}
                    </div>
                  </td>
                  <td className="px-5 py-3 text-muted-foreground truncate">{u.email}</td>
                  <td className="px-5 py-3">
                    <Badge variant={u.role === "admin" ? "default" : "neutral"} className="capitalize">
                      {u.role}
                    </Badge>
                  </td>
                  <td className="px-5 py-3">
                    {u.department ? (
                      <Badge variant="neutral" className="capitalize">
                        {u.department}
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-xs text-muted-foreground">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : "Never"}
                  </td>
                  <td className="px-5 py-3">
                    {u.is_active ? (
                      <Badge variant="completed">Active</Badge>
                    ) : (
                      <Badge variant="neutral">Inactive</Badge>
                    )}
                  </td>
                  <td className="px-5 py-3 pr-6 text-right whitespace-nowrap">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditing(u)}
                      disabled={u.id === me?.id && !u.is_active}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      Edit
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </CardContent>

      <InviteUserDialog
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        onCreated={(email, password) => {
          setCreatedCredentials({ email, password });
          queryClient.invalidateQueries({ queryKey: ["users"] });
        }}
      />
      <CredentialsRevealedDialog
        creds={createdCredentials}
        onClose={() => setCreatedCredentials(null)}
      />
      <EditUserDialog
        user={editing}
        onClose={() => setEditing(null)}
        meId={me?.id ?? null}
      />
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Invite (create) dialog — admin sets initial password.
// ---------------------------------------------------------------------------
function InviteUserDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: (email: string, password: string) => void;
}) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<Role>("employee");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  function generatePassword() {
    const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
    let out = "";
    const buf = new Uint32Array(12);
    crypto.getRandomValues(buf);
    for (const n of buf) out += chars[n % chars.length];
    setPassword(out);
  }

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<UserOut>("/api/users/admin", {
        email: email.trim().toLowerCase(),
        full_name: fullName.trim(),
        role,
        password,
      }),
    onSuccess: (u) => {
      onCreated(u.email, password);
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setEmail("");
      setFullName("");
      setRole("employee");
      setPassword("");
      setError(null);
      onOpenChange(false);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) setError(null); onOpenChange(v); }}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Invite user</DialogTitle>
        </DialogHeader>
        <div className="p-6 space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium">Email</label>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="finance.lead@aspora.com"
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">Full name</label>
            <Input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Riya Mehta"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            >
              <option value="employee">Employee</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">Initial password</label>
            <div className="flex gap-2">
              <Input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 6 characters"
                className="font-mono"
              />
              <Button variant="outline" type="button" onClick={generatePassword}>
                Generate
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              You'll see this password once on the next screen — copy it before closing. The
              user can change it from their Profile.
            </p>
          </div>
          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => createMutation.mutate()}
            disabled={
              !email.trim() || !password || password.length < 6 || createMutation.isPending
            }
          >
            {createMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Create user
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


// ---------------------------------------------------------------------------
// Show the freshly-created credentials once.
// ---------------------------------------------------------------------------
function CredentialsRevealedDialog({
  creds,
  onClose,
}: {
  creds: { email: string; password: string } | null;
  onClose: () => void;
}) {
  if (!creds) return null;
  return (
    <Dialog open={!!creds} onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>User created</DialogTitle>
        </DialogHeader>
        <div className="p-6 space-y-3">
          <p className="text-sm">
            Share these credentials with{" "}
            <span className="font-medium">{creds.email}</span>. You won't see them again.
          </p>
          <CredCopyRow label="Email" value={creds.email} />
          <CredCopyRow label="Password" value={creds.password} mono />
        </div>
        <DialogFooter>
          <Button onClick={onClose}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function CredCopyRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }
  return (
    <div>
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div className="flex gap-2">
        <Input
          value={value}
          readOnly
          className={mono ? "font-mono" : undefined}
        />
        <Button variant="outline" type="button" onClick={copy}>
          {copied ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Edit user dialog
// ---------------------------------------------------------------------------
function EditUserDialog({
  user,
  onClose,
  meId,
}: {
  user: UserOut | null;
  onClose: () => void;
  meId: number | null;
}) {
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [role, setRole] = useState<Role>(user?.role ?? "employee");
  const [department, setDepartment] = useState<string>(user?.department ?? "");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);

  // Reset state when the dialog opens with a new user.
  useEffect(() => {
    if (user) {
      setFullName(user.full_name);
      setRole(user.role);
      setDepartment(user.department ?? "");
      setNewPassword("");
      setError(null);
      setConfirmDeactivate(false);
    }
  }, [user]);

  const patchMutation = useMutation({
    mutationFn: () => {
      if (!user) throw new Error("No user");
      const body: Record<string, unknown> = {};
      if (fullName !== user.full_name) body.full_name = fullName;
      if (role !== user.role) body.role = role;
      if ((department || null) !== (user.department || null)) {
        body.department = department; // "" clears it server-side
      }
      if (newPassword) body.password = newPassword;
      return api.patch<UserOut>(`/api/users/admin/${user.id}`, body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });

  const deactivateMutation = useMutation({
    mutationFn: () => api.delete<void>(`/api/users/admin/${user!.id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });

  const reactivateMutation = useMutation({
    mutationFn: () => api.patch<UserOut>(`/api/users/admin/${user!.id}`, { is_active: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });

  if (!user) return null;
  const isSelf = user.id === meId;

  return (
    <Dialog open={!!user} onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="md" className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit user — {user.email}</DialogTitle>
        </DialogHeader>
        <div className="p-6 space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium">Full name</label>
            <Input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              disabled={isSelf}
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            >
              <option value="employee">Employee</option>
              <option value="admin">Admin</option>
            </select>
            {isSelf && (
              <p className="text-[11px] text-muted-foreground">
                You can't demote your own account.
              </p>
            )}
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">Team</label>
            <select
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            >
              <option value="">— None —</option>
              <option value="compliance">Compliance</option>
              <option value="finance">Finance</option>
              <option value="legal">Legal</option>
              <option value="hr">HR</option>
            </select>
            <p className="text-[11px] text-muted-foreground">
              The function this person owns — drives routing and the
              Workspace's team filter. Pick "None" for admins or non-team
              accounts.
            </p>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">Reset password</label>
            <Input
              type="text"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Leave blank to keep current"
              className="font-mono"
            />
          </div>

          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {!isSelf && (
            <div className="pt-3 border-t border-border">
              {user.is_active ? (
                confirmDeactivate ? (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 space-y-2">
                    <div className="text-sm font-medium text-red-800">
                      Deactivate {user.full_name}?
                    </div>
                    <div className="text-xs text-red-700/80">
                      They lose access immediately. Obligations they own keep referencing them.
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setConfirmDeactivate(false)}
                      >
                        <X className="h-3.5 w-3.5" />
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        className="bg-red-600 hover:bg-red-700"
                        onClick={() => deactivateMutation.mutate()}
                        disabled={deactivateMutation.isPending}
                      >
                        {deactivateMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                        Yes, deactivate
                      </Button>
                    </div>
                  </div>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setConfirmDeactivate(true)}
                    className="text-red-700 border-red-200 hover:bg-red-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Deactivate user
                  </Button>
                )
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => reactivateMutation.mutate()}
                  disabled={reactivateMutation.isPending}
                >
                  {reactivateMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Reactivate
                </Button>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => patchMutation.mutate()} disabled={patchMutation.isPending}>
            {patchMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


// ---------------------------------------------------------------------------
// Integrations — Slack + Gmail (SMTP) + coming-soon cards
// ---------------------------------------------------------------------------
interface SlackConfig {
  configured: boolean;
  enabled: boolean;
  webhook_url_masked: string | null;
  has_webhook: boolean;
  default_channel: string | null;
  function_webhooks_masked: Record<string, string>;
}

// Owner teams that can have their own Slack channel (one incoming webhook is
// bound to one channel, so per-team routing = one webhook per team).
const SLACK_FUNCTIONS = ["finance", "compliance", "legal", "hr"] as const;
const SLACK_FUNCTION_LABEL: Record<string, string> = {
  finance: "Finance",
  compliance: "Compliance",
  legal: "Legal",
  hr: "HR",
};

interface ClickUpConfig {
  configured: boolean;
  enabled: boolean;
  has_token: boolean;
  api_token_masked: string | null;
  list_id: string | null;
  done_status: string | null;
  two_way_connected: boolean;
}


function IntegrationsTab() {
  return (
    <div className="space-y-4">
      <SlackCard />
      <ClickUpCard />
      <GmailCard />
      <GoogleCalendarCard />
      <ComingSoonGrid />
    </div>
  );
}


function SlackCard() {
  const queryClient = useQueryClient();
  const { data: cfg, isLoading } = useQuery({
    queryKey: ["integrations", "slack"],
    queryFn: () => api.get<SlackConfig>("/api/admin/integrations/slack"),
  });

  const [editing, setEditing] = useState(false);
  const [webhook, setWebhook] = useState("");
  const [channel, setChannel] = useState("");
  const [fnHooks, setFnHooks] = useState<Record<string, string>>({});
  const [result, setResult] = useState<{ ok: boolean; detail: string | null } | null>(null);

  useEffect(() => {
    if (cfg) setChannel(cfg.default_channel || "");
  }, [cfg]);

  const saveMutation = useMutation({
    mutationFn: (body: {
      webhook_url?: string;
      default_channel?: string;
      enabled?: boolean;
      function_webhooks?: Record<string, string>;
    }) => api.post<SlackConfig>("/api/admin/integrations/slack", body),
    onSuccess: (fresh) => {
      queryClient.setQueryData(["integrations", "slack"], fresh);
      setEditing(false);
      setWebhook("");
      setFnHooks({});
      setResult(null);
    },
  });

  const testMutation = useMutation({
    mutationFn: () =>
      api.post<{ ok: boolean; detail: string | null }>("/api/admin/integrations/slack/test"),
    onSuccess: (r) => setResult(r),
  });

  if (isLoading || !cfg) {
    return <Card><CardContent className="p-4 text-sm text-muted-foreground">Loading Slack config…</CardContent></Card>;
  }

  return (
    <Card>
      <CardContent className="p-5 space-y-4">
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 rounded-lg bg-secondary grid place-items-center text-foreground/80 shrink-0">
            <Slack className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="font-semibold">Slack workspace</div>
              {cfg.configured && cfg.enabled ? (
                <Badge variant="completed">
                  <CheckCircle2 className="h-3 w-3 mr-0.5" />
                  Connected
                </Badge>
              ) : cfg.configured ? (
                <Badge variant="alert">Paused</Badge>
              ) : (
                <Badge variant="neutral">Not connected</Badge>
              )}
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">
              Channel-wide alerts on overdue / assignment / mention via Slack Incoming Webhook.
            </div>
          </div>

          {cfg.configured && !editing && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => testMutation.mutate()}
              disabled={testMutation.isPending}
            >
              {testMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Slack className="h-3.5 w-3.5" />}
              Send test
            </Button>
          )}
        </div>

        {cfg.configured && !editing && (
          <div className="rounded-lg border border-border bg-secondary/30 px-3 py-2 text-xs space-y-1">
            <div className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground">Webhook</span>
              <span className="font-mono truncate">{cfg.webhook_url_masked}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground">Default channel</span>
              <span className="font-mono">{cfg.default_channel || "(webhook default)"}</span>
            </div>
            {SLACK_FUNCTIONS.filter((fn) => cfg.function_webhooks_masked?.[fn]).map((fn) => (
              <div key={fn} className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">{SLACK_FUNCTION_LABEL[fn]} channel</span>
                <span className="flex items-center gap-1.5 min-w-0">
                  <span className="font-mono truncate">{cfg.function_webhooks_masked[fn]}</span>
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-red-600"
                    title={`Remove the ${SLACK_FUNCTION_LABEL[fn]} channel webhook`}
                    onClick={() => saveMutation.mutate({ function_webhooks: { [fn]: "" } })}
                  >
                    ✕
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}

        {result && (
          <div
            className={cn(
              "rounded-lg border px-3 py-2 text-sm",
              result.ok
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-destructive/30 bg-destructive/5 text-destructive",
            )}
          >
            {result.detail}
          </div>
        )}

        {!editing ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              {cfg.configured ? "Update webhook" : "Connect"}
            </Button>
            {cfg.configured && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => saveMutation.mutate({ enabled: !cfg.enabled })}
                  disabled={saveMutation.isPending}
                >
                  {cfg.enabled ? "Pause alerts" : "Resume alerts"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-red-600"
                  onClick={() => {
                    if (window.confirm("Disconnect Slack? Alerts will stop until you re-paste a webhook.")) {
                      saveMutation.mutate({ webhook_url: "" });
                    }
                  }}
                >
                  Disconnect
                </Button>
              </>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">
                Incoming webhook URL
              </label>
              <Input
                autoFocus
                value={webhook}
                onChange={(e) => setWebhook(e.target.value)}
                placeholder="https://hooks.slack.com/services/T…/B…/…"
                className="font-mono text-xs mt-1"
              />
              {webhook.trim() &&
                !webhook.trim().startsWith("https://hooks.slack.com/") && (
                  <div className="mt-1 text-[11px] text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1.5">
                    That doesn't look like a webhook URL. A webhook starts with{" "}
                    <span className="font-mono">https://hooks.slack.com/services/</span> —
                    a channel link like <span className="font-mono">slack.com/archives/…</span>{" "}
                    won't work.
                  </div>
                )}
              <p className="text-[11px] text-muted-foreground mt-1">
                Get one at{" "}
                <a
                  href="https://api.slack.com/apps"
                  target="_blank"
                  rel="noreferrer"
                  className="text-aspora-700 hover:underline"
                >
                  api.slack.com/apps
                </a>{" "}
                → Create New App → From scratch → enable "Incoming Webhooks"
                → "Add New Webhook to Workspace" → pick a channel → copy URL.
              </p>
              {saveMutation.error && (
                <div className="mt-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1.5">
                  {(saveMutation.error as Error).message}
                </div>
              )}
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">
                Override channel (optional)
              </label>
              <Input
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
                placeholder="#aspora-compliance"
                className="font-mono text-xs mt-1"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">
                Per-team channels (optional) — alerts route to the owner team's channel
              </label>
              <p className="text-[11px] text-muted-foreground mt-0.5 mb-1">
                A webhook is bound to one channel, so paste one webhook per team
                (same Slack app → "Add New Webhook to Workspace" → pick that
                team's channel). Anything without a team webhook uses the default above.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {SLACK_FUNCTIONS.map((fn) => (
                  <div key={fn}>
                    <label className="text-[11px] text-muted-foreground">
                      {SLACK_FUNCTION_LABEL[fn]}
                      {cfg.function_webhooks_masked?.[fn] ? " (set — paste to replace)" : ""}
                    </label>
                    <Input
                      value={fnHooks[fn] ?? ""}
                      onChange={(e) => setFnHooks((h) => ({ ...h, [fn]: e.target.value }))}
                      placeholder="https://hooks.slack.com/services/…"
                      className="font-mono text-xs mt-0.5"
                    />
                  </div>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setEditing(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  const fw: Record<string, string> = {};
                  for (const fn of SLACK_FUNCTIONS) {
                    if ((fnHooks[fn] ?? "").trim()) fw[fn] = fnHooks[fn].trim();
                  }
                  saveMutation.mutate({
                    webhook_url: webhook.trim() || undefined,
                    default_channel: channel.trim() || undefined,
                    enabled: true,
                    ...(Object.keys(fw).length ? { function_webhooks: fw } : {}),
                  });
                }}
                disabled={
                  saveMutation.isPending ||
                  (!webhook.trim() && !cfg.configured) ||
                  (webhook.trim().length > 0 &&
                    !webhook.trim().startsWith("https://hooks.slack.com/"))
                }
              >
                {saveMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Save
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}


function ClickUpCard() {
  const queryClient = useQueryClient();
  const { data: cfg, isLoading } = useQuery({
    queryKey: ["integrations", "clickup"],
    queryFn: () => api.get<ClickUpConfig>("/api/admin/integrations/clickup"),
  });

  const [editing, setEditing] = useState(false);
  const [token, setToken] = useState("");
  const [listId, setListId] = useState("");
  const [doneStatus, setDoneStatus] = useState("");
  const [result, setResult] = useState<{ ok: boolean; detail: string | null } | null>(null);

  useEffect(() => {
    if (cfg) {
      setListId(cfg.list_id || "");
      setDoneStatus(cfg.done_status || "");
    }
  }, [cfg]);

  const saveMutation = useMutation({
    mutationFn: (body: {
      api_token?: string;
      list_id?: string;
      done_status?: string;
      enabled?: boolean;
    }) => api.post<ClickUpConfig>("/api/admin/integrations/clickup", body),
    onSuccess: (fresh) => {
      queryClient.setQueryData(["integrations", "clickup"], fresh);
      setEditing(false);
      setToken("");
      setResult(null);
    },
  });

  const testMutation = useMutation({
    mutationFn: () =>
      api.post<{ ok: boolean; detail: string | null }>("/api/admin/integrations/clickup/test"),
    onSuccess: (r) => setResult(r),
  });

  const connectMutation = useMutation({
    mutationFn: () =>
      api.post<ClickUpConfig>("/api/admin/integrations/clickup/connect-webhook"),
    onSuccess: (fresh) => {
      queryClient.setQueryData(["integrations", "clickup"], fresh);
      setResult({ ok: true, detail: "Two-way sync connected — ClickUp will now push status updates back." });
    },
    onError: (e: unknown) =>
      setResult({ ok: false, detail: (e as Error).message }),
  });

  if (isLoading || !cfg) {
    return <Card><CardContent className="p-4 text-sm text-muted-foreground">Loading ClickUp config…</CardContent></Card>;
  }

  return (
    <Card>
      <CardContent className="p-5 space-y-4">
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 rounded-lg bg-secondary grid place-items-center text-foreground/80 shrink-0">
            <ListChecks className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="font-semibold">ClickUp</div>
              {cfg.configured && cfg.enabled ? (
                <Badge variant="completed">
                  <CheckCircle2 className="h-3 w-3 mr-0.5" />
                  Connected
                </Badge>
              ) : cfg.configured ? (
                <Badge variant="alert">Paused</Badge>
              ) : (
                <Badge variant="neutral">Not connected</Badge>
              )}
              {cfg.two_way_connected && (
                <Badge variant="default">Two-way sync</Badge>
              )}
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">
              When compliance requests a payment, a task is created in your finance ClickUp list. Closing it there marks the obligation complete here.
            </div>
          </div>

          {cfg.configured && !editing && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => testMutation.mutate()}
              disabled={testMutation.isPending}
            >
              {testMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ListChecks className="h-3.5 w-3.5" />}
              Test
            </Button>
          )}
        </div>

        {cfg.configured && !editing && (
          <div className="rounded-lg border border-border bg-secondary/30 px-3 py-2 text-xs space-y-1">
            <div className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground">API token</span>
              <span className="font-mono truncate">{cfg.api_token_masked}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground">List ID</span>
              <span className="font-mono">{cfg.list_id}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground">Done status</span>
              <span className="font-mono">{cfg.done_status || "complete"}</span>
            </div>
          </div>
        )}

        {result && (
          <div
            className={cn(
              "rounded-lg border px-3 py-2 text-sm",
              result.ok
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-destructive/30 bg-destructive/5 text-destructive",
            )}
          >
            {result.detail}
          </div>
        )}

        {!editing ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              {cfg.configured ? "Update" : "Connect"}
            </Button>
            {cfg.configured && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => connectMutation.mutate()}
                  disabled={connectMutation.isPending}
                >
                  {connectMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {cfg.two_way_connected ? "Re-connect two-way sync" : "Enable two-way sync"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => saveMutation.mutate({ enabled: !cfg.enabled })}
                  disabled={saveMutation.isPending}
                >
                  {cfg.enabled ? "Pause" : "Resume"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-red-600"
                  onClick={() => {
                    if (window.confirm("Disconnect ClickUp? New payment requests won't create tasks.")) {
                      saveMutation.mutate({ api_token: "" });
                    }
                  }}
                >
                  Disconnect
                </Button>
              </>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">
                ClickUp API token
              </label>
              <Input
                autoFocus
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder={cfg.has_token ? "•••• (leave blank to keep current)" : "pk_12345678_ABCDEF…"}
                className="font-mono text-xs mt-1"
              />
              <p className="text-[11px] text-muted-foreground mt-1">
                ClickUp → your avatar → Settings → Apps → Generate / copy your API token.
              </p>
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">
                Finance list ID
              </label>
              <Input
                value={listId}
                onChange={(e) => setListId(e.target.value)}
                placeholder="901100123456"
                className="font-mono text-xs mt-1"
              />
              <p className="text-[11px] text-muted-foreground mt-1">
                Open the ClickUp list → ⋯ → Copy link. The number after /li/ (or /v/li/) is the List ID.
              </p>
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">
                Done status (optional)
              </label>
              <Input
                value={doneStatus}
                onChange={(e) => setDoneStatus(e.target.value)}
                placeholder="complete"
                className="font-mono text-xs mt-1"
              />
              <p className="text-[11px] text-muted-foreground mt-1">
                The list status that means "paid". Defaults to <code>complete</code>.
              </p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setEditing(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() =>
                  saveMutation.mutate({
                    api_token: token.trim() || undefined,
                    list_id: listId.trim() || undefined,
                    done_status: doneStatus.trim() || undefined,
                    enabled: true,
                  })
                }
                disabled={
                  saveMutation.isPending ||
                  (!token.trim() && !cfg.has_token) ||
                  !listId.trim()
                }
              >
                {saveMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Save
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}


function GmailCard() {
  const [recipient, setRecipient] = useState("");
  const [result, setResult] = useState<{ ok: boolean; detail: string | null } | null>(null);

  const testMutation = useMutation({
    mutationFn: () =>
      api.post<{ ok: boolean; detail: string | null }>(
        "/api/admin/integrations/email/test",
        recipient.trim() ? { to: recipient.trim() } : {},
      ),
    onSuccess: (r) => setResult(r),
  });

  return (
    <Card>
      <CardContent className="p-5 space-y-4">
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 rounded-lg bg-secondary grid place-items-center text-foreground/80 shrink-0">
            <Mail className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="font-semibold">Email (Gmail API)</div>
              <Badge variant="neutral">Config via .env</Badge>
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">
              Sends password-reset, assignment, overdue + weekly-digest emails when notification
              prefs are on.
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-secondary/30 px-4 py-3 text-sm space-y-2">
          <div className="font-medium">Set up Gmail API (one-time)</div>
          <ol className="list-decimal list-inside text-xs text-muted-foreground space-y-1">
            <li>
              Google Cloud Console → new project → enable the <strong>Gmail API</strong>.
            </li>
            <li>
              OAuth consent screen → add scope{" "}
              <span className="font-mono">.../auth/gmail.send</span> → add your email as a test user.
            </li>
            <li>
              Credentials → <strong>OAuth client ID</strong> (Web app) → redirect URI{" "}
              <span className="font-mono">https://developers.google.com/oauthplayground</span> →
              copy the client id + secret.
            </li>
            <li>
              At <span className="font-mono">developers.google.com/oauthplayground</span> → gear →
              “Use your own credentials” → authorize the gmail.send scope → exchange for a{" "}
              <strong>refresh token</strong>.
            </li>
            <li>
              Set these env vars (Render → Environment), then redeploy:
              <pre className="mt-1 bg-background border border-border rounded p-2 text-[11px] font-mono whitespace-pre-wrap">
{`GMAIL_CLIENT_ID=xxxx.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-xxxx
GMAIL_REFRESH_TOKEN=1//xxxx
GMAIL_SENDER=you@aspora.com`}
              </pre>
            </li>
          </ol>
        </div>

        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="text-xs font-medium text-muted-foreground">
              Send a test email to (optional)
            </label>
            <Input
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              placeholder="Defaults to your own email"
              type="email"
            />
          </div>
          <Button
            onClick={() => testMutation.mutate()}
            disabled={testMutation.isPending}
          >
            {testMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mail className="h-3.5 w-3.5" />}
            Send test
          </Button>
        </div>

        {result && (
          <div
            className={cn(
              "rounded-lg border px-3 py-2 text-sm",
              result.ok
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-amber-200 bg-amber-50 text-amber-900",
            )}
          >
            {result.detail}
          </div>
        )}
      </CardContent>
    </Card>
  );
}


interface GoogleCalendarConfig {
  configured: boolean;
  calendar_id: string | null;
  has_oauth: boolean;
}

function GoogleCalendarCard() {
  const { data: cfg } = useQuery({
    queryKey: ["integrations", "gcal"],
    queryFn: () => api.get<GoogleCalendarConfig>("/api/admin/integrations/google-calendar"),
  });
  const [result, setResult] = useState<{ ok: boolean; detail: string | null } | null>(null);
  const testMutation = useMutation({
    mutationFn: () =>
      api.post<{ ok: boolean; detail: string | null }>(
        "/api/admin/integrations/google-calendar/test",
      ),
    onSuccess: (r) => setResult(r),
  });
  if (!cfg) return null;

  return (
    <Card>
      <CardContent className="p-5 space-y-4">
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 rounded-lg bg-secondary grid place-items-center text-foreground/80 shrink-0">
            <CalendarIcon className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="font-semibold">Google Calendar</div>
              {cfg.configured ? (
                <Badge variant="completed">
                  <CheckCircle2 className="h-3 w-3 mr-0.5" />
                  Connected
                </Badge>
              ) : (
                <Badge variant="neutral">Not configured</Badge>
              )}
              <Badge variant="neutral">Config via .env</Badge>
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">
              Pushes every assigned filing onto a shared calendar the moment it's
              assigned — titled "filing — entity (Assignee: name)". Reassign updates
              the event; completing removes it.
            </div>
          </div>
          {cfg.configured && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => testMutation.mutate()}
              disabled={testMutation.isPending}
            >
              {testMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <CalendarIcon className="h-3.5 w-3.5" />
              )}
              Send test event
            </Button>
          )}
        </div>

        {cfg.configured && (
          <div className="rounded-lg border border-border bg-secondary/30 px-3 py-2 text-xs flex items-center justify-between gap-2">
            <span className="text-muted-foreground">Calendar ID</span>
            <span className="font-mono truncate">{cfg.calendar_id}</span>
          </div>
        )}

        {result && (
          <div
            className={cn(
              "rounded-lg border px-3 py-2 text-sm",
              result.ok
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-destructive/30 bg-destructive/5 text-destructive",
            )}
          >
            {result.detail}
          </div>
        )}

        {!cfg.configured && (
          <div className="rounded-lg border border-border bg-secondary/30 px-4 py-3 text-sm space-y-2">
            <div className="font-medium">Set up (one-time — reuses the Gmail OAuth client)</div>
            <ol className="list-decimal list-inside text-xs text-muted-foreground space-y-1">
              <li>
                Google Cloud Console → same project → enable the <strong>Google Calendar API</strong>.
              </li>
              <li>
                Re-mint the refresh token at developers.google.com/oauthplayground with BOTH scopes:{" "}
                <code className="font-mono">…/auth/gmail.send</code> and{" "}
                <code className="font-mono">…/auth/calendar.events</code> → update{" "}
                <code className="font-mono">GMAIL_REFRESH_TOKEN</code>.
              </li>
              <li>
                In Google Calendar: create an "Aspora Compliance" calendar → its settings →
                "Integrate calendar" → copy the <strong>Calendar ID</strong> → share the calendar
                with the team.
              </li>
              <li>
                Render → Environment: set <code className="font-mono">GOOGLE_CALENDAR_ID</code> to
                that ID → redeploy → use "Send test event".
              </li>
            </ol>
          </div>
        )}
      </CardContent>
    </Card>
  );
}


function ComingSoonGrid() {
  const items: { name: string; description: string; icon: React.ReactNode }[] = [
    {
      name: "Zoho Books",
      description: "Sync filed-payment amounts back to accounting",
      icon: <CheckCheck className="h-5 w-5" />,
    },
    {
      name: "Ramp",
      description: "Auto-attach payment proofs from card transactions",
      icon: <CheckCheck className="h-5 w-5" />,
    },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {items.map((i) => (
        <Card key={i.name}>
          <CardContent className="p-4 flex items-start gap-3">
            <div className="h-10 w-10 rounded-lg bg-secondary grid place-items-center text-foreground/80 shrink-0">
              {i.icon}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <div className="font-semibold truncate">{i.name}</div>
                <Badge variant="alert">Coming soon</Badge>
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">{i.description}</div>
            </div>
            <Button variant="outline" size="sm" disabled>
              Notify me
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Jurisdictions
// ---------------------------------------------------------------------------
type CustomJurisdiction = { code: string; name: string; flag: string; iso2: string };

function JurisdictionsTab() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);

  const { data: entities = [] } = useQuery({
    queryKey: ["entities"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
  });
  const { data: rules = [] } = useQuery({
    queryKey: ["rules", "production"],
    queryFn: () => api.get<Rule[]>("/api/rules?status=production"),
  });
  const { data: custom = [] } = useQuery({
    queryKey: ["jurisdictions"],
    queryFn: () => api.get<CustomJurisdiction[]>("/api/jurisdictions"),
  });

  // Built-in set + any admin-added jurisdictions (custom wins on code clash).
  const merged: Record<string, { name: string; flag: string; iso2: string }> = {
    ...JURISDICTIONS,
  };
  for (const j of custom) {
    merged[j.code] = { name: j.name, flag: j.flag || "🏳️", iso2: j.iso2 };
  }
  const customCodes = new Set(custom.map((j) => j.code));

  const del = useMutation({
    mutationFn: (code: string) => api.delete(`/api/jurisdictions/${code}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jurisdictions"] }),
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  return (
    <Card>
      <CardContent className="p-0">
        <div className="px-5 py-4 border-b border-border">
          <div className="font-semibold">Active jurisdictions</div>
          <div className="text-xs text-muted-foreground">
            Toggle a jurisdiction on/off. Each one shows its entity count, active rules, and last
            rule update.
          </div>
        </div>
        <ul className="divide-y divide-border">
          {Object.entries(merged).map(([code, j]) => {
            const entCount = entities.filter((e) => e.jurisdiction_code === code).length;
            const ruleCount = rules.filter((r) => r.jurisdiction_code === code).length;
            const lastUpdate = rules
              .filter((r) => r.jurisdiction_code === code)
              .sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0]?.updated_at;
            const active = entCount > 0 || ruleCount > 0;
            return (
              <li key={code} className="flex items-center gap-4 px-5 py-3">
                <span className="text-xl">{j.flag}</span>
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{j.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {entCount} entit{entCount === 1 ? "y" : "ies"} · {ruleCount} active rule{ruleCount === 1 ? "" : "s"}
                  </div>
                </div>
                <div className="text-xs text-muted-foreground">
                  {lastUpdate ? "Updated " + new Date(lastUpdate).toLocaleDateString() : "—"}
                </div>
                <Badge variant={active ? "completed" : "neutral"}>{active ? "Active" : "Inactive"}</Badge>
                {isAdmin && customCodes.has(code) && (
                  <button
                    type="button"
                    title="Delete this jurisdiction"
                    disabled={del.isPending}
                    onClick={() => {
                      if (
                        entCount > 0 || ruleCount > 0
                          ? window.confirm(
                              `"${j.name}" still has ${entCount} entit${entCount === 1 ? "y" : "ies"} and ${ruleCount} rule(s). Delete it anyway? (They keep their jurisdiction code; it just won't show a name/flag.)`,
                            )
                          : window.confirm(`Delete "${j.name}"?`)
                      ) {
                        del.mutate(code);
                      }
                    }}
                    className="text-muted-foreground hover:text-destructive disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
        {isAdmin && (
          <div className="px-5 py-3 border-t border-border text-right">
            <Button variant="outline" size="sm" onClick={() => setAddOpen(true)}>
              <Plus className="h-4 w-4" />
              Add jurisdiction
            </Button>
          </div>
        )}
      </CardContent>
      <AddJurisdictionDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        existingCodes={Object.keys(merged)}
        onAdded={() => queryClient.invalidateQueries({ queryKey: ["jurisdictions"] })}
      />
    </Card>
  );
}


function AddJurisdictionDialog({
  open,
  onOpenChange,
  existingCodes,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  existingCodes: string[];
  onAdded: () => void;
}) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [flag, setFlag] = useState("");
  const [iso2, setIso2] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName("");
      setCode("");
      setFlag("");
      setIso2("");
      setError(null);
    }
  }, [open]);

  const add = useMutation({
    mutationFn: () =>
      api.post("/api/jurisdictions", {
        code: code.trim().toLowerCase(),
        name: name.trim(),
        flag: flag.trim(),
        iso2: iso2.trim().toLowerCase(),
      }),
    onSuccess: () => {
      onAdded();
      onOpenChange(false);
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  });

  const dupCode = code.trim() && existingCodes.includes(code.trim().toLowerCase());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Add jurisdiction</DialogTitle>
        </DialogHeader>
        <div className="p-6 space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium">Name</label>
            <Input value={name} placeholder="e.g. Saudi Arabia" autoFocus onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1 col-span-1">
              <label className="text-xs font-medium">Code</label>
              <Input value={code} placeholder="ksa" onChange={(e) => setCode(e.target.value)} />
            </div>
            <div className="space-y-1 col-span-1">
              <label className="text-xs font-medium">ISO-2</label>
              <Input value={iso2} placeholder="sa" maxLength={2} onChange={(e) => setIso2(e.target.value)} />
            </div>
            <div className="space-y-1 col-span-1">
              <label className="text-xs font-medium">Flag</label>
              <Input value={flag} placeholder="🇸🇦" onChange={(e) => setFlag(e.target.value)} />
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Code is the short id stored on entities/rules (lowercase, e.g.{" "}
            <code className="font-mono">uae</code>).
          </p>
          {dupCode && (
            <div className="text-xs text-amber-700">That code already exists.</div>
          )}
          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => add.mutate()}
            disabled={add.isPending || !name.trim() || !code.trim() || !!dupCode}
          >
            {add.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Add jurisdiction
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


// ---------------------------------------------------------------------------
// Alert policies
// ---------------------------------------------------------------------------
function AlertPoliciesTab() {
  return (
    <Card>
      <CardContent className="p-6 space-y-5">
        <div>
          <h3 className="font-semibold">Reminder lead times</h3>
          <p className="text-xs text-muted-foreground">Filing cadence → days before the due date the first alert fires, and how often reminders then repeat.</p>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-secondary/30 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Filing cadence</th>
              <th className="px-3 py-2 text-left font-medium">Days before due</th>
              <th className="px-3 py-2 text-left font-medium">Reminder cadence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {[
              { cadence: "Monthly", d: 7, c: "Daily after alert" },
              { cadence: "Quarterly", d: 30, c: "Every 2 days" },
              { cadence: "Half-yearly", d: 45, c: "Weekly" },
              { cadence: "Annual", d: 60, c: "Weekly until 14d, daily after" },
              { cadence: "Multi-year / long-form", d: 90, c: "Bi-weekly until 28d, weekly after" },
            ].map((r) => (
              <tr key={r.cadence}>
                <td className="px-3 py-2">{r.cadence}</td>
                <td className="px-3 py-2 tabular-nums">{r.d}</td>
                <td className="px-3 py-2 text-muted-foreground">{r.c}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="space-y-1 pt-4 border-t border-border">
          <h3 className="font-semibold">Escalation rules</h3>
          <p className="text-xs text-muted-foreground">When an item is overdue by N days, who else gets pinged.</p>
        </div>
        <ul className="space-y-2 text-sm">
          <li className="rounded-lg border border-border px-3 py-2 flex items-center justify-between">
            <span>Overdue 1 day</span>
            <span className="text-muted-foreground text-xs">Notify country lead</span>
          </li>
          <li className="rounded-lg border border-border px-3 py-2 flex items-center justify-between">
            <span>Overdue 3 days</span>
            <span className="text-muted-foreground text-xs">Notify Head of Compliance</span>
          </li>
          <li className="rounded-lg border border-border px-3 py-2 flex items-center justify-between">
            <span>Overdue 7 days</span>
            <span className="text-muted-foreground text-xs">Email CFO</span>
          </li>
        </ul>
      </CardContent>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// API & Webhooks
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Audit retention
// ---------------------------------------------------------------------------
interface RetentionStatus {
  retention_days: number;
  total_activities: number;
  older_than_window: number;
  oldest_at: string | null;
}


function RetentionTab() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["retention"],
    queryFn: () => api.get<RetentionStatus>("/api/admin/retention"),
  });

  const purgeMutation = useMutation({
    mutationFn: () =>
      api.post<{ deleted: number; retention_days: number }>("/api/admin/retention/purge"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["retention"] });
      queryClient.invalidateQueries({ queryKey: ["audit-log"] });
    },
  });

  const [confirming, setConfirming] = useState(false);

  if (isLoading || !data) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">Loading…</CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-6 space-y-4">
        <div>
          <h3 className="font-semibold">Audit log retention</h3>
          <p className="text-xs text-muted-foreground mt-1">
            Activity rows older than the retention window can be purged. The window is set
            via{" "}
            <code className="font-mono text-[11px] bg-secondary/60 px-1.5 py-0.5 rounded">
              COMPLIANCE_AUDIT_RETENTION_DAYS
            </code>{" "}
            (min 30, default 365).
          </p>
        </div>

        <dl className="grid grid-cols-3 gap-3 text-sm">
          <Stat label="Retention window" value={`${data.retention_days} days`} />
          <Stat label="Total events" value={data.total_activities.toLocaleString()} />
          <Stat
            label="Older than window"
            value={data.older_than_window.toLocaleString()}
            tone={data.older_than_window > 0 ? "warn" : "neutral"}
          />
        </dl>

        {data.oldest_at && (
          <p className="text-xs text-muted-foreground">
            Oldest event: {new Date(data.oldest_at).toLocaleString()}
          </p>
        )}

        {purgeMutation.data && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            Purged {purgeMutation.data.deleted.toLocaleString()} events older than{" "}
            {purgeMutation.data.retention_days} days.
          </div>
        )}

        <div className="pt-3 border-t border-border">
          {!confirming ? (
            <Button
              variant="outline"
              onClick={() => setConfirming(true)}
              disabled={data.older_than_window === 0}
              className={data.older_than_window > 0 ? "text-red-700 border-red-200 hover:bg-red-50" : ""}
            >
              <Trash2 className="h-3.5 w-3.5" />
              {data.older_than_window > 0
                ? `Purge ${data.older_than_window.toLocaleString()} old events`
                : "Nothing to purge"}
            </Button>
          ) : (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 space-y-2">
              <div className="text-sm font-medium text-red-800">
                Permanently delete {data.older_than_window.toLocaleString()} events?
              </div>
              <div className="text-xs text-red-700/80">
                This can't be undone. The purge itself will be logged.
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  className="bg-red-600 hover:bg-red-700"
                  onClick={() => {
                    purgeMutation.mutate();
                    setConfirming(false);
                  }}
                  disabled={purgeMutation.isPending}
                >
                  {purgeMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Yes, purge
                </Button>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}


function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "warn";
}) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div
        className={cn(
          "text-xl font-semibold tabular-nums",
          tone === "warn" ? "text-amber-700" : "text-foreground",
        )}
      >
        {value}
      </div>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground mt-0.5">{label}</div>
    </div>
  );
}
