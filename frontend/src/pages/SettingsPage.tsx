// Settings — proper tabbed shell. Profile is available to every user; the
// rest are admin-only (visible to non-admins with a Lock badge but read-only).
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
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
} from "lucide-react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/EmptyState";
import { useAuth } from "@/contexts/AuthContext";
import { JURISDICTIONS, userInitials } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Entity, Rule, UserBrief } from "@/types/api";


type TabKey =
  | "profile"
  | "users"
  | "integrations"
  | "jurisdictions"
  | "alerts"
  | "api";


const TABS: { key: TabKey; label: string; adminOnly?: boolean; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: "profile", label: "Profile", icon: Bell },
  { key: "users", label: "Users & Roles", adminOnly: true, icon: Building2 },
  { key: "integrations", label: "Integrations", adminOnly: true, icon: Slack },
  { key: "jurisdictions", label: "Jurisdictions", adminOnly: true, icon: Globe },
  { key: "alerts", label: "Alert policies", adminOnly: true, icon: ListChecks },
  { key: "api", label: "API & Webhooks", adminOnly: true, icon: Key },
];


export function SettingsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState<TabKey>("profile");

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
          {tab === "profile" && <ProfileTab user={user} />}
          {tab === "users" && isAdmin && <UsersTab />}
          {tab === "integrations" && isAdmin && <IntegrationsTab />}
          {tab === "jurisdictions" && isAdmin && <JurisdictionsTab />}
          {tab === "alerts" && isAdmin && <AlertPoliciesTab />}
          {tab === "api" && isAdmin && <ApiTab />}
        </div>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------
function ProfileTab({ user }: { user: UserBrief }) {
  const [slackOn, setSlackOn] = useState(true);
  const [emailOn, setEmailOn] = useState(true);
  const [calOn, setCalOn] = useState(false);
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
            label="Slack direct message"
            description="Pings you on overdue items and approaching alert-window items"
            checked={slackOn}
            onChange={setSlackOn}
          />
          <ToggleRow
            icon={<Mail className="h-4 w-4" />}
            label="Email"
            description="Daily digest at 8am IST, plus immediate for overdue"
            checked={emailOn}
            onChange={setEmailOn}
          />
          <ToggleRow
            icon={<CalendarIcon className="h-4 w-4" />}
            label="Google Calendar events"
            description="Adds an all-day event on each due date"
            checked={calOn}
            onChange={setCalOn}
          />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6 space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Personal alert lead times
          </h3>
          <p className="text-xs text-muted-foreground">
            By default the system fires at 2× the effort band before the due date. Override per
            band below.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-md">
            {(["1w", "2w", "4w", "8w", "12w"] as const).map((b) => (
              <div key={b} className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                <span className="text-sm">{b} effort</span>
                <span className="text-xs text-muted-foreground">→ {Number(b.replace("w", "")) * 2}d before</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
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
// Users & Roles
// ---------------------------------------------------------------------------
function UsersTab() {
  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserBrief[]>("/api/users"),
  });

  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div>
            <div className="font-semibold">Workspace users</div>
            <div className="text-xs text-muted-foreground">
              Real CRUD UI ships in Phase 5 — use `compliance-agent create-user` CLI in the meantime.
            </div>
          </div>
          <Button disabled>
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
          <table className="w-full text-sm">
            <thead className="bg-secondary/30 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-5 py-2.5 text-left font-medium">Name</th>
                <th className="px-5 py-2.5 text-left font-medium">Email</th>
                <th className="px-5 py-2.5 text-left font-medium">Role</th>
                <th className="px-5 py-2.5 text-left font-medium">Status</th>
                <th className="px-5 py-2.5 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-secondary/30">
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <Avatar className="h-7 w-7">
                        <AvatarFallback className="text-[10px]">
                          {userInitials(u.full_name)}
                        </AvatarFallback>
                      </Avatar>
                      <span>{u.full_name}</span>
                    </div>
                  </td>
                  <td className="px-5 py-3 text-muted-foreground">{u.email}</td>
                  <td className="px-5 py-3">
                    <Badge variant={u.role === "admin" ? "default" : "neutral"} className="capitalize">
                      {u.role}
                    </Badge>
                  </td>
                  <td className="px-5 py-3">
                    <Badge variant="completed">Active</Badge>
                  </td>
                  <td className="px-5 py-3 text-right">
                    <Button variant="ghost" size="sm" disabled>
                      Edit
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Integrations
// ---------------------------------------------------------------------------
const INTEGRATIONS: {
  name: string;
  description: string;
  status: "connected" | "disconnected" | "coming";
  icon: React.ReactNode;
}[] = [
  {
    name: "Slack workspace",
    description: "Channel alerts and direct mentions on overdue items",
    status: "connected",
    icon: <Slack className="h-5 w-5" />,
  },
  {
    name: "ClickUp",
    description: "Push obligations as tasks for execution by the ops team",
    status: "disconnected",
    icon: <ListChecks className="h-5 w-5" />,
  },
  {
    name: "Google Calendar",
    description: "Per-user OAuth — drops events on each due date",
    status: "disconnected",
    icon: <CalendarIcon className="h-5 w-5" />,
  },
  {
    name: "Zoho Books",
    description: "Sync filed-payment amounts back to accounting",
    status: "coming",
    icon: <CheckCheck className="h-5 w-5" />,
  },
  {
    name: "Ramp",
    description: "Auto-attach payment proofs to obligations from card transactions",
    status: "coming",
    icon: <CheckCheck className="h-5 w-5" />,
  },
];


function IntegrationsTab() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {INTEGRATIONS.map((i) => (
        <Card key={i.name}>
          <CardContent className="p-4 flex items-start gap-3">
            <div className="h-10 w-10 rounded-lg bg-secondary grid place-items-center text-foreground/80 shrink-0">
              {i.icon}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <div className="font-semibold truncate">{i.name}</div>
                {i.status === "connected" ? (
                  <Badge variant="completed">
                    <CheckCircle2 className="h-3 w-3 mr-0.5" />
                    Connected
                  </Badge>
                ) : i.status === "disconnected" ? (
                  <Badge variant="neutral">Disconnected</Badge>
                ) : (
                  <Badge variant="alert">Coming soon</Badge>
                )}
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">{i.description}</div>
            </div>
            <div className="shrink-0">
              {i.status === "connected" ? (
                <Button variant="outline" size="sm" disabled>
                  Configure
                </Button>
              ) : (
                <Button variant="outline" size="sm" disabled>
                  {i.status === "coming" ? "Notify me" : "Connect"}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Jurisdictions
// ---------------------------------------------------------------------------
function JurisdictionsTab() {
  const { data: entities = [] } = useQuery({
    queryKey: ["entities"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
  });
  const { data: rules = [] } = useQuery({
    queryKey: ["rules", "production"],
    queryFn: () => api.get<Rule[]>("/api/rules?status=production"),
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
          {Object.entries(JURISDICTIONS).map(([code, j]) => {
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
              </li>
            );
          })}
        </ul>
        <div className="px-5 py-3 border-t border-border text-right">
          <button className="text-xs text-aspora-700 hover:underline" disabled>
            Request a new jurisdiction →
          </button>
        </div>
      </CardContent>
    </Card>
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
          <h3 className="font-semibold">Lead-time mapping</h3>
          <p className="text-xs text-muted-foreground">Effort band → days before due date the alert fires.</p>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-secondary/30 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Effort band</th>
              <th className="px-3 py-2 text-left font-medium">Days before due</th>
              <th className="px-3 py-2 text-left font-medium">Reminder cadence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {[
              { b: "1w", d: 14, c: "Daily after alert" },
              { b: "2w", d: 28, c: "Every 2 days" },
              { b: "4w", d: 56, c: "Weekly until 14d, daily after" },
              { b: "8w", d: 112, c: "Weekly" },
              { b: "12w", d: 168, c: "Bi-weekly until 28d, weekly after" },
            ].map((r) => (
              <tr key={r.b}>
                <td className="px-3 py-2">
                  <Badge variant="default">{r.b}</Badge>
                </td>
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
function ApiTab() {
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-6 space-y-3">
          <h3 className="font-semibold">API keys</h3>
          <p className="text-xs text-muted-foreground">
            Personal access tokens for programmatic access to the Compliance OS API.
          </p>
          <div className="flex items-center gap-2">
            <Input value="aspora_pk_•••••••••••••••••••" readOnly className="font-mono text-xs" />
            <Button variant="outline" disabled>
              Reveal
            </Button>
            <Button variant="outline" disabled>
              Rotate
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-6 space-y-3">
          <h3 className="font-semibold">Webhook endpoints</h3>
          <EmptyState
            icon={<Key className="h-5 w-5" />}
            title="No webhooks configured"
            description="Add a webhook URL to get a POST whenever an obligation changes status or a rule is promoted."
            action={
              <Button variant="outline" disabled>
                <Plus className="h-3.5 w-3.5" />
                Add webhook
              </Button>
            }
          />
        </CardContent>
      </Card>
    </div>
  );
}
