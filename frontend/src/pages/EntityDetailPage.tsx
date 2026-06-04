// Entity Detail — one specific legal entity with tabs: Overview, Registrations,
// Compliance Items, Documents, Key Persons, Activity / Audit Log. Most tabs
// are filled with realistic demo content; real CRUD lands in Phase 5+.
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Archive,
  Edit,
  Loader2,
  Lock,
  History,
  UserCheck,
  KeyRound,
  Plus,
  Trash2,
  ChevronUp,
  ChevronDown,
  ArrowDown,
} from "lucide-react";
import { api } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/StatusPill";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { EffortBandBadge } from "@/components/EffortBandBadge";
import { AssigneeChip } from "@/components/AssigneeChip";
import { EmptyState } from "@/components/EmptyState";
import { DocumentList } from "@/components/DocumentList";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";
import { useAuth } from "@/contexts/AuthContext";
import { fmtDate, fmtRelative, fmtShortDate, userInitials } from "@/lib/format";
import { gatesForJurisdiction } from "@/lib/financeGates";
import { cn } from "@/lib/utils";
import type { ActivityOut, Entity, License, Obligation } from "@/types/api";


function StatTile({
  value,
  label,
  tone = "neutral",
}: {
  value: number | string;
  label: string;
  tone?: "neutral" | "overdue" | "alert" | "completed";
}) {
  const toneClasses = {
    neutral: "text-foreground",
    overdue: "text-red-600",
    alert: "text-amber-600",
    completed: "text-emerald-600",
  }[tone];
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3 min-w-[110px]">
      <div className={cn("text-2xl font-semibold tabular-nums leading-tight", toneClasses)}>
        {value}
      </div>
      <div className="text-[11px] text-muted-foreground uppercase tracking-wide mt-0.5">{label}</div>
    </div>
  );
}


export function EntityDetailPage() {
  const { entityId } = useParams();
  const [tab, setTab] = useState("overview");
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const { data: entity, isLoading: loadingEntity } = useQuery({
    queryKey: ["entity", entityId],
    queryFn: () => api.get<Entity>(`/api/entities/${entityId}`),
    enabled: !!entityId,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });

  const { data: obligations, isLoading: loadingObs } = useQuery({
    queryKey: ["entity-obligations", entityId],
    queryFn: () => api.get<Obligation[]>(`/api/obligations?entity_id=${entityId}&limit=200`),
    enabled: !!entityId,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });

  const { data: entityLicenses = [] } = useQuery({
    queryKey: ["entity-licenses", entityId],
    queryFn: () => api.get<License[]>(`/api/licenses?entity_id=${entityId}`),
    enabled: !!entityId,
    refetchInterval: 30_000,
  });

  if (loadingEntity) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-32" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!entity) {
    return (
      <div className="space-y-4">
        <Link to="/entities" className="text-sm text-aspora-600 hover:underline">
          ← Back to entities
        </Link>
        <div className="rounded-xl border border-border bg-card p-10 text-center text-muted-foreground">
          Entity not found.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link
        to="/entities"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to entities
      </Link>

      <EntityHero entity={entity} isAdmin={isAdmin} />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="profile">Activity Profile</TabsTrigger>
          <TabsTrigger value="registrations">Registrations</TabsTrigger>
          <TabsTrigger value="licenses">
            Licenses
            {entityLicenses.length > 0 && (
              <Badge variant="neutral" className="ml-1">
                {entityLicenses.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="documents">Documents</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab
            entity={entity}
            obligations={obligations ?? []}
            licenses={entityLicenses}
          />
        </TabsContent>

        <TabsContent value="profile">
          <ActivityProfileTab entity={entity} isAdmin={isAdmin} />
        </TabsContent>

        <TabsContent value="registrations">
          <RegistrationsTab entity={entity} isAdmin={isAdmin} />
        </TabsContent>

        <TabsContent value="licenses">
          <LicensesTab entity={entity} />
        </TabsContent>

        <TabsContent value="documents">
          <DocumentsTab entity={entity} />
        </TabsContent>
      </Tabs>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Activity Profile — Yes / No / TBC flags (drives Find Regulations) + ownership
// ---------------------------------------------------------------------------
function ActivityProfileTab({ entity, isAdmin }: { entity: Entity; isAdmin: boolean }) {
  const queryClient = useQueryClient();
  const gates = gatesForJurisdiction(entity.jurisdiction_code);
  const profile = entity.finance_profile ?? {};

  const saveProfile = useMutation({
    mutationFn: (next: Record<string, string>) =>
      api.patch<Entity>(`/api/entities/${entity.id}`, { finance_profile: next }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["entity"] }),
  });
  const setFlag = (key: string, value: "yes" | "no" | "tbc") => {
    const next = { ...profile };
    if (value === "tbc") delete next[key];
    else next[key] = value;
    saveProfile.mutate(next);
  };

  const FLAG_OPTIONS: { value: "yes" | "no" | "tbc"; label: string }[] = [
    { value: "yes", label: "Yes" },
    { value: "no", label: "No" },
    { value: "tbc", label: "TBC" },
  ];

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-5 space-y-3">
          <div>
            <h3 className="font-semibold">Activity profile</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              What this entity does. These answers drive which filings{" "}
              <strong>Find Regulations</strong> marks mandatory vs conditional.
              TBC = awaiting confirmation (doesn't switch anything on).
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {gates.map((g) => {
              const val = profile[g.key];
              const current = val === "yes" ? "yes" : val === "no" ? "no" : "tbc";
              return (
                <div
                  key={g.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background/60 px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="text-sm truncate">{g.question}</div>
                    <div className="text-[11px] text-muted-foreground truncate">
                      {g.drives}
                    </div>
                  </div>
                  <div className="inline-flex rounded-md border border-input overflow-hidden shrink-0">
                    {FLAG_OPTIONS.map((o) => (
                      <button
                        key={o.value}
                        type="button"
                        disabled={!isAdmin || saveProfile.isPending}
                        onClick={() => setFlag(g.key, o.value)}
                        className={cn(
                          "px-2.5 py-1 text-xs transition-colors disabled:opacity-60",
                          current === o.value
                            ? o.value === "yes"
                              ? "bg-emerald-500 text-white"
                              : o.value === "no"
                                ? "bg-slate-700 text-white"
                                : "bg-secondary text-foreground"
                            : "bg-background hover:bg-secondary text-muted-foreground",
                          o.value !== "yes" && "border-l border-input",
                        )}
                      >
                        {o.label}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------
function EntityHero({ entity, isAdmin }: { entity: Entity; isAdmin: boolean }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [editOpen, setEditOpen] = useState(false);

  const archiveMutation = useMutation({
    mutationFn: () => api.post<Entity>(`/api/entities/${entity.id}/archive`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      queryClient.invalidateQueries({ queryKey: ["entity", entity.id] });
      // Entity is now hidden from the list — bounce back to /entities.
      navigate("/entities");
    },
    onError: (e) => {
      window.alert(
        `Couldn't archive:\n\n${e instanceof Error ? e.message : String(e)}`,
      );
    },
  });

  return (
    <>
    <Card>
      <CardContent className="p-6">
        <div className="flex items-start justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="h-14 w-14 rounded-xl bg-aspora-100 grid place-items-center text-aspora-700 font-bold text-xl shrink-0">
              {userInitials(entity.name)}
            </div>
            <div>
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-2xl font-semibold tracking-tight">{entity.name}</h1>
                <JurisdictionBadge code={entity.jurisdiction_code} />
                <Badge variant="default">{entity.legal_type}</Badge>
              </div>
              <div className="text-sm text-muted-foreground mt-1 flex items-center gap-4 flex-wrap">
                <span>
                  Reg # <span className="font-mono text-foreground">{entity.registration_number || "—"}</span>
                </span>
                <span>·</span>
                <span>Formed {fmtDate(entity.incorporation_date)}</span>
                <span>·</span>
                <span>FYE {entity.fiscal_year_end || "—"}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!isAdmin}
              title={isAdmin ? undefined : "Admin only"}
              onClick={() => isAdmin && setEditOpen(true)}
            >
              {isAdmin ? <Edit className="h-4 w-4" /> : <Lock className="h-3.5 w-3.5" />}
              Edit
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!isAdmin || archiveMutation.isPending}
              title={isAdmin ? undefined : "Admin only"}
              onClick={() => {
                if (!isAdmin) return;
                if (
                  window.confirm(
                    `Archive "${entity.name}"? It'll be hidden from the entities list. Existing obligations and licenses stay intact.`,
                  )
                ) {
                  archiveMutation.mutate();
                }
              }}
            >
              {archiveMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Archive className="h-4 w-4" />
              )}
              Archive
            </Button>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          <StatTile value={entity.active_obligations_count} label="Total active" />
          <StatTile value={entity.overdue_obligations_count} label="Overdue" tone="overdue" />
          <StatTile value={entity.in_alert_window_count} label="In alert window" tone="alert" />
          <StatTile
            value={entity.last_filed_at ? fmtShortDate(entity.last_filed_at) : "—"}
            label="Last filed"
            tone="completed"
          />
        </div>
      </CardContent>
    </Card>
    <EditEntityDialog
      open={editOpen}
      onOpenChange={setEditOpen}
      entity={entity}
    />
    </>
  );
}


// ---------------------------------------------------------------------------
// Edit entity dialog
// ---------------------------------------------------------------------------
function EditEntityDialog({
  open,
  onOpenChange,
  entity,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  entity: Entity;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(entity.name);
  const [legalType, setLegalType] = useState(entity.legal_type);
  const [regNumber, setRegNumber] = useState(entity.registration_number ?? "");
  const [fye, setFye] = useState(entity.fiscal_year_end ?? "");
  const [incDate, setIncDate] = useState(entity.incorporation_date ?? "");
  const [shortCode, setShortCode] = useState(entity.short_code ?? "");
  const [countryLeadId, setCountryLeadId] = useState<number | "">(
    entity.country_lead?.id ?? "",
  );
  const [error, setError] = useState<string | null>(null);

  // Users list for the country-lead picker. Admin-only endpoint covers
  // every user incl. inactive ones; if non-admin somehow opens this
  // dialog the call returns 403 and the dropdown stays empty (which is
  // fine — only admins can hit the Edit button anyway).
  const { data: users = [] } = useQuery({
    queryKey: ["users", "admin"],
    queryFn: () => api.get<{ id: number; full_name: string; email: string }[]>("/api/users/admin"),
    enabled: open,
  });

  // Re-sync the form when the entity object changes (e.g. polling refresh).
  useEffect(() => {
    if (open) {
      setName(entity.name);
      setLegalType(entity.legal_type);
      setRegNumber(entity.registration_number ?? "");
      setFye(entity.fiscal_year_end ?? "");
      setIncDate(entity.incorporation_date ?? "");
      setShortCode(entity.short_code ?? "");
      setCountryLeadId(entity.country_lead?.id ?? "");
      setError(null);
    }
  }, [open, entity]);

  const mutation = useMutation({
    mutationFn: () =>
      api.patch<Entity>(`/api/entities/${entity.id}`, {
        name: name.trim(),
        legal_type: legalType.trim(),
        registration_number: regNumber.trim() || null,
        fiscal_year_end: fye.trim() || null,
        incorporation_date: incDate || null,
        short_code: shortCode.trim() || null,
        country_lead_id: countryLeadId === "" ? null : Number(countryLeadId),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["entity", entity.id] });
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      onOpenChange(false);
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>Edit entity</DialogTitle>
        </DialogHeader>
        <div className="p-6 space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium">Legal name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium">Legal type</label>
              <Input
                value={legalType}
                placeholder="Private Limited / LLC / FZE…"
                onChange={(e) => setLegalType(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">Short code</label>
              <Input
                value={shortCode}
                placeholder="VINC, NESS…"
                onChange={(e) => setShortCode(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">Registration number</label>
            <Input
              value={regNumber}
              onChange={(e) => setRegNumber(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium">Incorporation date</label>
              <Input
                type="date"
                value={incDate}
                onChange={(e) => setIncDate(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">Fiscal year end</label>
              <Input
                value={fye}
                placeholder="31-Mar"
                onChange={(e) => setFye(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium">Country lead</label>
            <select
              value={countryLeadId}
              onChange={(e) =>
                setCountryLeadId(e.target.value === "" ? "" : Number(e.target.value))
              }
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">— None —</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name || u.email}
                </option>
              ))}
            </select>
            <p className="text-[11px] text-muted-foreground">
              Single owner for this entity — they get pinged first on
              regulator changes + escalations.
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
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !name.trim()}
          >
            {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


// ---------------------------------------------------------------------------
// Overview tab
// ---------------------------------------------------------------------------
function OverviewTab({
  entity,
  obligations,
  licenses,
}: {
  entity: Entity;
  obligations: Obligation[];
  licenses: License[];
}) {
  // Recent 5 obligation changes — fake "recent activity" feed sourced from
  // updated_at on this entity's obligations. Real activity feed lands in P5.
  const recent = [...obligations]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, 5);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card className="md:col-span-2">
        <CardContent className="p-6 space-y-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Business Information
          </h3>
          <dl className="grid grid-cols-2 gap-y-3 text-sm">
            <dt className="text-muted-foreground">Legal name</dt>
            <dd className="font-medium">{entity.name}</dd>
            <dt className="text-muted-foreground">Legal type</dt>
            <dd>{entity.legal_type || "—"}</dd>
            <dt className="text-muted-foreground">Registration #</dt>
            <dd className="font-mono text-xs">{entity.registration_number || "—"}</dd>
            <dt className="text-muted-foreground">Incorporation date</dt>
            <dd>{fmtDate(entity.incorporation_date)}</dd>
            <dt className="text-muted-foreground">Fiscal year end</dt>
            <dd>{entity.fiscal_year_end || "—"}</dd>
            <dt className="text-muted-foreground">Jurisdiction</dt>
            <dd>
              <JurisdictionBadge code={entity.jurisdiction_code} />
            </dd>
            <dt className="text-muted-foreground">Created</dt>
            <dd className="text-xs text-muted-foreground">{fmtRelative(entity.created_at)}</dd>
          </dl>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardContent className="p-6 space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Country lead
            </h3>
            {entity.country_lead ? (
              <div className="flex items-center gap-3">
                <Avatar className="h-11 w-11">
                  <AvatarFallback>{userInitials(entity.country_lead.full_name)}</AvatarFallback>
                </Avatar>
                <div className="min-w-0">
                  <div className="font-medium truncate">{entity.country_lead.full_name}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {entity.country_lead.email}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground italic">Unassigned</div>
            )}
            <div className="text-xs text-muted-foreground pt-2 border-t border-border">
              Backup: <span className="italic">Unassigned</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Licenses held
              </h3>
              <Link to="/licenses" className="text-xs text-aspora-700 hover:underline">
                Manage
              </Link>
            </div>
            {licenses.length === 0 ? (
              <div className="text-sm text-muted-foreground italic">
                No licenses on record.
              </div>
            ) : (
              <ul className="space-y-2 text-sm">
                {licenses.map((l) => (
                  <li
                    key={l.id}
                    className="flex items-start justify-between gap-2 border-b border-border/60 pb-2 last:border-0 last:pb-0"
                  >
                    <div className="min-w-0">
                      <div className="font-medium truncate">{l.name}</div>
                      <div className="text-[11px] text-muted-foreground truncate">
                        {l.authority}
                        {l.license_number ? ` · ${l.license_number}` : ""}
                      </div>
                    </div>
                    <span className="text-[11px] text-muted-foreground whitespace-nowrap">
                      {l.expiry_date || "No expiry"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Linked key persons
              </h3>
              <button className="text-xs text-aspora-700 hover:underline" disabled>
                View all
              </button>
            </div>
            <ul className="space-y-2 text-sm">
              {entity.country_lead && (
                <li className="flex items-center gap-2">
                  <Avatar className="h-7 w-7">
                    <AvatarFallback className="text-[10px]">
                      {userInitials(entity.country_lead.full_name)}
                    </AvatarFallback>
                  </Avatar>
                  <div>
                    <div className="font-medium">{entity.country_lead.full_name}</div>
                    <div className="text-xs text-muted-foreground">Authorised signatory</div>
                  </div>
                </li>
              )}
              <li className="text-xs text-muted-foreground italic pl-1 pt-1">
                Add directors and signatories from the Key Persons tab.
              </li>
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card className="md:col-span-3">
        <CardContent className="p-6 space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Recent activity
          </h3>
          {recent.length === 0 ? (
            <EmptyState
              icon={<History className="h-5 w-5" />}
              title="No activity yet"
              description="Once obligations get updated or filed, the latest changes show up here."
            />
          ) : (
            <ul className="space-y-2">
              {recent.map((ob) => (
                <li
                  key={ob.id}
                  className="flex items-center gap-3 text-sm hover:bg-secondary/30 rounded-lg px-2 py-1.5 -mx-2"
                >
                  <Avatar className="h-7 w-7">
                    <AvatarFallback className="text-[10px]">
                      {userInitials(ob.assignee?.full_name || "Aspora")}
                    </AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <span className="font-medium">{ob.assignee?.full_name?.split(" ")[0] || "Someone"}</span>{" "}
                    <span className="text-muted-foreground">updated</span>{" "}
                    <span className="font-medium">{ob.rule_form_name}</span>{" "}
                    <span className="text-muted-foreground">→ </span>
                    <StatusPill status={ob.status} isOverdue={ob.is_overdue} />
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {fmtRelative(ob.updated_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Registrations tab — demo data, real CRUD in Phase 5
// ---------------------------------------------------------------------------
const DEMO_REGISTRATIONS_PER_JURISDICTION: Record<
  string,
  { type: string; number: string; status: string; frequency: string }[]
> = {
  uk: [
    { type: "Corporation Tax (CT)", number: "1234567890", status: "Active", frequency: "Annual" },
    { type: "VAT", number: "GB 123 4567 89", status: "Active", frequency: "Quarterly" },
    { type: "PAYE", number: "120/AB12345", status: "Active", frequency: "Monthly" },
  ],
  us: [
    { type: "EIN", number: "12-3456789", status: "Active", frequency: "Annual" },
    { type: "Delaware Annual Report", number: "—", status: "Active", frequency: "Annual" },
    { type: "State Sales Tax (CA)", number: "SR-XX-12345", status: "Active", frequency: "Monthly" },
  ],
  india: [
    { type: "GSTIN", number: "29AAAAA0000A1Z5", status: "Active", frequency: "Monthly" },
    { type: "PAN", number: "AAAAA1234A", status: "Active", frequency: "—" },
    { type: "TAN", number: "ABCD12345E", status: "Active", frequency: "Quarterly" },
  ],
};


function RegistrationsTab({ entity, isAdmin }: { entity: Entity; isAdmin: boolean }) {
  const rows = DEMO_REGISTRATIONS_PER_JURISDICTION[entity.jurisdiction_code] ?? [];
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-secondary/30">
        <h3 className="text-sm font-semibold">Tax & legal registrations</h3>
        <Button size="sm" disabled={!isAdmin} title={isAdmin ? undefined : "Admin only"}>
          {isAdmin ? <Plus className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
          Add registration
        </Button>
      </div>
      {rows.length === 0 ? (
        <div className="p-10">
          <EmptyState
            icon={<KeyRound className="h-5 w-5" />}
            title="No registrations captured yet"
            description="Add VAT, EIN, Corporation Tax and other registrations so they generate compliance items automatically."
          />
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-secondary/20 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Type</th>
              <th className="px-4 py-2 text-left font-medium">Number</th>
              <th className="px-4 py-2 text-left font-medium">Status</th>
              <th className="px-4 py-2 text-left font-medium">Frequency</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((r) => (
              <tr key={r.type} className="hover:bg-secondary/30">
                <td className="px-4 py-2.5 font-medium">{r.type}</td>
                <td className="px-4 py-2.5 font-mono text-xs">{r.number}</td>
                <td className="px-4 py-2.5">
                  <Badge variant="completed">{r.status}</Badge>
                </td>
                <td className="px-4 py-2.5 text-muted-foreground">{r.frequency}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Compliance Items tab
// ---------------------------------------------------------------------------
function ObligationsTab({
  obligations,
  loading,
}: {
  obligations: Obligation[] | undefined;
  loading: boolean;
}) {
  const { openObligation } = useObligationDrawer();
  if (loading) {
    return (
      <Card>
        <div className="p-6 space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      </Card>
    );
  }
  if (!obligations || obligations.length === 0) {
    return (
      <EmptyState
        title="Rules are still being applied to this entity"
        description="Items will appear within a minute. Refresh if you've just added a rule."
      />
    );
  }
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[900px]">
          <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 text-left font-medium">Form / Report</th>
              <th className="px-3 py-2.5 text-left font-medium">Authority · Category</th>
              <th className="px-3 py-2.5 text-left font-medium">Period</th>
              <th className="px-3 py-2.5 text-left font-medium">Due date</th>
              <th className="px-3 py-2.5 text-left font-medium">Status</th>
              <th className="px-3 py-2.5 text-left font-medium">Effort</th>
              <th className="px-3 py-2.5 text-left font-medium">Assignee</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {obligations.slice(0, 100).map((ob) => (
              <tr
                key={ob.id}
                className="hover:bg-secondary/30 cursor-pointer"
                onClick={() => openObligation(ob.id)}
              >
                <td className="px-3 py-2.5">
                  <div className="font-medium truncate">{ob.rule_form_name}</div>
                  <div className="text-xs text-muted-foreground truncate">{ob.rule_name}</div>
                </td>
                <td className="px-3 py-2.5 text-muted-foreground">
                  <span className="truncate">{ob.rule_authority}</span>
                  <span className="opacity-60"> · {ob.rule_category}</span>
                </td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground">
                  {ob.period_label || "—"}
                </td>
                <td className="px-3 py-2.5 tabular-nums">{fmtShortDate(ob.due_date)}</td>
                <td className="px-3 py-2.5">
                  <div className="flex flex-col gap-1">
                    <StatusPill status={ob.status} isOverdue={ob.is_overdue} />
                    <StatusPill
                      status={ob.status}
                      isOverdue={ob.is_overdue}
                      daysRemaining={ob.days_remaining}
                      showDays
                    />
                  </div>
                </td>
                <td className="px-3 py-2.5">
                  <EffortBandBadge band={ob.effort_band} />
                </td>
                <td className="px-3 py-2.5">
                  <AssigneeChip user={ob.assignee} size="sm" showName />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {obligations.length > 100 && (
        <div className="p-3 text-center text-xs text-muted-foreground border-t border-border">
          Showing first 100 of {obligations.length}. Open the calendar to filter further.
        </div>
      )}
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Documents tab — wired to /api/documents via DocumentList.
// ---------------------------------------------------------------------------
function LicensesTab({ entity }: { entity: Entity }) {
  const { data: licenses = [], isLoading } = useQuery({
    queryKey: ["entity-licenses", entity.id],
    queryFn: () => api.get<License[]>(`/api/licenses?entity_id=${entity.id}`),
    refetchInterval: 30_000,
  });
  return (
    <Card>
      <CardContent className="p-5">
        <div className="text-sm font-medium mb-3">
          Licenses held by {entity.name}
        </div>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : licenses.length === 0 ? (
          <div className="text-sm text-muted-foreground">
            No licenses yet. Upload one on the Licenses page (admin) — it’ll
            show here and surface the filings this entity owes.
          </div>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-secondary/40 text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">License</th>
                  <th className="text-left px-3 py-2 font-medium">Authority</th>
                  <th className="text-left px-3 py-2 font-medium">No.</th>
                  <th className="text-left px-3 py-2 font-medium">Expiry</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {licenses.map((l) => (
                  <tr key={l.id} className="hover:bg-secondary/20">
                    <td className="px-3 py-2 font-medium">
                      <Link to="/licenses" className="hover:underline">
                        {l.name}
                      </Link>
                      {l.license_type && (
                        <div className="text-[11px] text-muted-foreground">
                          {l.license_type}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{l.authority}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {l.license_number || "—"}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {l.expiry_date || "No expiry"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DocumentsTab({ entity }: { entity: Entity }) {
  return (
    <Card>
      <CardContent className="p-5">
        <DocumentList
          scope={{ kind: "entity", entityId: entity.id }}
          title="All documents for this entity"
          hint="Upload formation papers, prior filings, contracts, or expert notes. Max 25 MB per file."
        />
      </CardContent>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Key Persons tab (demo)
// ---------------------------------------------------------------------------
function KeyPersonsTab({ entity, isAdmin }: { entity: Entity; isAdmin: boolean }) {
  const demoPeople: { name: string; role: string; email: string }[] = entity.country_lead
    ? [
        {
          name: entity.country_lead.full_name,
          role: "Authorised signatory",
          email: entity.country_lead.email,
        },
        { name: "—", role: "Director", email: "Add via Settings" },
      ]
    : [];
  return (
    <Card>
      <CardContent className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Directors, officers, signatories</h3>
          <Button size="sm" disabled={!isAdmin} title={isAdmin ? undefined : "Admin only"}>
            {isAdmin ? <Plus className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
            Add person
          </Button>
        </div>
        {demoPeople.length === 0 ? (
          <EmptyState
            icon={<UserCheck className="h-5 w-5" />}
            title="No key persons linked"
            description="Add directors, signatories, and officers so the right people get pinged on each filing."
          />
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {demoPeople.map((p, i) => (
              <li key={i} className="rounded-lg border border-border p-3 flex items-start gap-3">
                <Avatar className="h-10 w-10">
                  <AvatarFallback>{userInitials(p.name)}</AvatarFallback>
                </Avatar>
                <div className="min-w-0">
                  <div className="font-medium truncate">{p.name}</div>
                  <div className="text-xs text-muted-foreground">{p.role}</div>
                  <div className="text-xs text-muted-foreground mt-0.5 truncate">{p.email}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Activity / Audit log tab — wired to /api/activities scoped to this entity.
// ---------------------------------------------------------------------------
function ActivityTab({ entity }: { entity: Entity }) {
  const { data: activities = [], isLoading } = useQuery({
    queryKey: ["activities", "entity", entity.id],
    queryFn: () =>
      api.get<ActivityOut[]>(`/api/activities?entity_id=${entity.id}&limit=100`),
  });

  return (
    <Card>
      <CardContent className="p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Activity log</h3>
          <span className="text-xs text-muted-foreground tabular-nums">
            {activities.length} event{activities.length === 1 ? "" : "s"}
          </span>
        </div>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </div>
        ) : activities.length === 0 ? (
          <EmptyState
            icon={<History className="h-5 w-5" />}
            title="No activity in the selected range"
            description="Update an obligation or upload a document to see the audit trail here."
          />
        ) : (
          <ul className="space-y-2">
            {activities.map((a) => (
              <li
                key={a.id}
                className="flex items-start gap-3 text-sm rounded-lg px-2 py-1.5 hover:bg-secondary/30"
              >
                <Avatar className="h-7 w-7 shrink-0 mt-0.5">
                  <AvatarFallback className="text-[10px]">
                    {userInitials(a.actor?.full_name || "—")}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <div className="leading-snug">
                    <span className="font-medium">
                      {a.actor?.full_name || "System"}
                    </span>{" "}
                    <span className="text-muted-foreground">{a.action.replace(/\./g, " ")}</span>
                    {a.target_label && (
                      <>
                        <span className="text-muted-foreground"> · </span>
                        <span className="font-medium">{a.target_label}</span>
                      </>
                    )}
                  </div>
                </div>
                <span className="text-xs text-muted-foreground whitespace-nowrap mt-1">
                  {fmtRelative(a.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}


