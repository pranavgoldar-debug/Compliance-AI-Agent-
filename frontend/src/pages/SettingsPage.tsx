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
  | "profile"
  | "users"
  | "integrations"
  | "jurisdictions"
  | "alerts"
  | "retention"
  | "api";


const TABS: { key: TabKey; label: string; adminOnly?: boolean; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: "profile", label: "Profile", icon: Bell },
  { key: "users", label: "Users & Roles", adminOnly: true, icon: Building2 },
  { key: "integrations", label: "Integrations", adminOnly: true, icon: Slack },
  { key: "jurisdictions", label: "Jurisdictions", adminOnly: true, icon: Globe },
  { key: "alerts", label: "Alert policies", adminOnly: true, icon: ListChecks },
  { key: "retention", label: "Audit retention", adminOnly: true, icon: Trash2 },
  { key: "api", label: "API & Webhooks", adminOnly: true, icon: Key },
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
          {tab === "profile" && <ProfileTab user={user} />}
          {tab === "users" && isAdmin && <UsersTab />}
          {tab === "integrations" && isAdmin && <IntegrationsTab />}
          {tab === "jurisdictions" && isAdmin && <JurisdictionsTab />}
          {tab === "alerts" && isAdmin && <AlertPoliciesTab />}
          {tab === "retention" && isAdmin && <RetentionTab />}
          {tab === "api" && isAdmin && <ApiTab />}
        </div>
      </div>
    </div>
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

  const [calOn, setCalOn] = useState(false);  // cosmetic — calendar integration not yet wired
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
            description="Channel-wide pings on overdue / assignment / mention. Requires workspace Slack to be connected."
            checked={prefs?.notify_slack ?? true}
            onChange={(v) => patchPrefs.mutate({ notify_slack: v })}
          />
          <ToggleRow
            icon={<Mail className="h-4 w-4" />}
            label="Email"
            description="Password resets + (when configured) overdue + assignment emails to your inbox."
            checked={prefs?.notify_email ?? true}
            onChange={(v) => patchPrefs.mutate({ notify_email: v })}
          />
          <ToggleRow
            icon={<CalendarIcon className="h-4 w-4" />}
            label="Google Calendar events"
            description="Adds an all-day event on each due date. Coming next round."
            checked={calOn}
            onChange={setCalOn}
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
            <p className="text-[11px] text-muted-foreground mt-1">
              When set, Slack alerts ping you with a real <code className="font-mono">@</code>{" "}
              mention. Find it in Slack → your profile → "Copy member ID".
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
            the assignee at each offset below for the relevant effort band.
            Each (person, filing, offset) fires exactly once.
          </p>
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Effort band</th>
                  <th className="px-3 py-2 text-left font-medium">Typical cadence</th>
                  <th className="px-3 py-2 text-left font-medium">Reminders sent</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {[
                  { band: "1w", cadence: "Monthly", offsets: "7 days before" },
                  { band: "2w", cadence: "Quarterly", offsets: "25 + 15 days before" },
                  { band: "4w", cadence: "Half-yearly", offsets: "30 + 15 days before" },
                  { band: "8w", cadence: "Annual", offsets: "45 + 30 days before" },
                  { band: "12w", cadence: "Multi-year / long-form", offsets: "60 + 30 days before" },
                ].map((r) => (
                  <tr key={r.band}>
                    <td className="px-3 py-2 font-mono text-xs">{r.band}</td>
                    <td className="px-3 py-2 text-muted-foreground">{r.cadence}</td>
                    <td className="px-3 py-2">{r.offsets}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-muted-foreground">
            To change the policy, edit{" "}
            <code className="font-mono">_REMINDER_OFFSETS</code> in{" "}
            <code className="font-mono">src/compliance_agent/api/_helpers.py</code>.
          </p>
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
          <table className="w-full text-sm">
            <thead className="bg-secondary/30 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-5 py-2.5 text-left font-medium">Name</th>
                <th className="px-5 py-2.5 text-left font-medium">Email</th>
                <th className="px-5 py-2.5 text-left font-medium">Role</th>
                <th className="px-5 py-2.5 text-left font-medium">Last active</th>
                <th className="px-5 py-2.5 text-left font-medium">Status</th>
                <th className="px-5 py-2.5 text-right font-medium">Actions</th>
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
                  <td className="px-5 py-3 text-right">
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
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);

  // Reset state when the dialog opens with a new user.
  useEffect(() => {
    if (user) {
      setFullName(user.full_name);
      setRole(user.role);
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
      <DialogContent size="sm">
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
}

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
  const [result, setResult] = useState<{ ok: boolean; detail: string | null } | null>(null);

  useEffect(() => {
    if (cfg) setChannel(cfg.default_channel || "");
  }, [cfg]);

  const saveMutation = useMutation({
    mutationFn: (body: { webhook_url?: string; default_channel?: string; enabled?: boolean }) =>
      api.post<SlackConfig>("/api/admin/integrations/slack", body),
    onSuccess: (fresh) => {
      queryClient.setQueryData(["integrations", "slack"], fresh);
      setEditing(false);
      setWebhook("");
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
              <p className="text-[11px] text-muted-foreground mt-1">
                Slack → your workspace → Apps → search "Incoming Webhooks" → Add Configuration →
                pick a channel → copy the Webhook URL.
              </p>
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
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setEditing(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() =>
                  saveMutation.mutate({
                    webhook_url: webhook.trim() || undefined,
                    default_channel: channel.trim() || undefined,
                    enabled: true,
                  })
                }
                disabled={saveMutation.isPending || (!webhook.trim() && !cfg.configured)}
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
              <div className="font-semibold">Email (Gmail / any SMTP)</div>
              <Badge variant="neutral">Config via .env</Badge>
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">
              Sends password-reset emails today; assignment + overdue emails when notification
              prefs are on.
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-secondary/30 px-4 py-3 text-sm space-y-2">
          <div className="font-medium">Connect Gmail in three steps</div>
          <ol className="list-decimal list-inside text-xs text-muted-foreground space-y-1">
            <li>
              Turn on 2-Step Verification on the Google account that will send the mail.
            </li>
            <li>
              Visit <span className="font-mono">myaccount.google.com/apppasswords</span> →
              generate an App Password for "Mail / Other → Aspora".
            </li>
            <li>
              Drop the password into your <span className="font-mono">.env</span>:
              <pre className="mt-1 bg-background border border-border rounded p-2 text-[11px] font-mono whitespace-pre-wrap">
{`SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@aspora.com
SMTP_PASSWORD=<the 16-char app password>
SMTP_FROM="Aspora Compliance <you@aspora.com>"`}
              </pre>
              Restart the server. That's it.
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


function ComingSoonGrid() {
  const items: { name: string; description: string; icon: React.ReactNode }[] = [
    {
      name: "Google Calendar",
      description: "Per-user OAuth — drops events on each due date",
      icon: <CalendarIcon className="h-5 w-5" />,
    },
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
