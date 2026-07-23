// Compliance Rules — admin manages the rule templates that generate per-entity
// obligations. Two tabs: Production (flat table) and Staging (side-by-side
// review cards with confidence indicators).
import { Fragment, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  ChevronDown,
  ChevronRight,
  CircleCheck,
  CircleAlert,
  CircleHelp,
  AlertTriangle,
  ExternalLink,
  FileText,
  LayoutList,
  Loader2,
  Table2,
  Search,
  Sparkles,
} from "lucide-react";
import { RuleChangeCheckDialog } from "@/components/RuleChangeCheckDialog";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { EmptyState } from "@/components/EmptyState";
import { ExportMenu } from "@/components/ExportMenu";
import { DueDateRuleBuilder } from "@/components/DueDateRuleBuilder";
import type { DueDateSpec } from "@/lib/dueDateSpec";
import { PageHeader } from "@/components/PageHeader";
import { fmtRelative, deriveFunction, parseBackendDate } from "@/lib/format";
import { jurisdictionOptionsInUse } from "@/lib/countries";
import { cn } from "@/lib/utils";
import type { Rule, RuleStatus, UserBrief, Obligation, Entity } from "@/types/api";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";

// Higher-level category groups for the filter. Each rule's free-text `category`
// is bucketed into one of these (case-insensitive exact-or-contains match);
// anything that fits none lands in "Other" so nothing is hidden.
const CATEGORY_GROUPS: { label: string; cats: string[] }[] = [
  { label: "AML/CFT (financial crime)", cats: ["aml / cft", "aml/cft", "aml", "cft"] },
  { label: "Corporate filings", cats: ["corporate & statutory", "corporate and statutory", "statutory", "corporate filing"] },
  { label: "Direct tax", cats: ["corporate tax", "corporation tax", "income tax", "direct tax"] },
  { label: "Indirect tax", cats: ["vat", "gst", "sales/use tax", "sales tax", "excise", "indirect tax", "customs"] },
  { label: "Payroll / employment tax", cats: ["payroll", "pension", "social security", "workers compensation", "employment tax"] },
  { label: "Prudential/conduct returns", cats: ["regulatory", "prudential", "conduct"] },
  { label: "Transfer pricing / information return", cats: ["information return", "forex", "cross-border", "transfer pricing", "cbcr"] },
];
const OTHER_GROUP = "Other";
const CATEGORY_GROUP_LABELS = [...CATEGORY_GROUPS.map((g) => g.label), OTHER_GROUP];

function categoryGroup(category: string | null | undefined): string {
  const c = (category || "").toLowerCase().trim();
  for (const g of CATEGORY_GROUPS) {
    if (g.cats.some((k) => c === k || c.includes(k))) return g.label;
  }
  return OTHER_GROUP;
}

// Checkbox multi-select used for the category-group filter (Select All + ticks).
function GroupMultiSelect({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const allSelected = selected.length === 0 || selected.length === options.length;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            "h-10 rounded-lg font-normal shrink-0",
            selected.length > 0 && "bg-aspora-50 border-aspora-200 text-aspora-800",
          )}
        >
          {selected.length > 0 ? `${label} · ${selected.length}` : label}
          <ChevronDown className="h-3.5 w-3.5 ml-1" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0" align="start">
        <div className="max-h-72 overflow-auto scrollbar-thin py-1">
          <button
            onClick={() => onChange([])}
            className="w-full text-left px-2 py-1.5 hover:bg-secondary flex items-center gap-2 text-sm font-medium"
          >
            <Checkbox checked={allSelected} readOnly />
            <span>(Select all)</span>
          </button>
          {options.map((o) => {
            const checked = selected.includes(o);
            return (
              <button
                key={o}
                onClick={() =>
                  onChange(
                    checked ? selected.filter((v) => v !== o) : [...selected, o],
                  )
                }
                className="w-full text-left px-2 py-1.5 hover:bg-secondary flex items-center gap-2 text-sm"
              >
                <Checkbox checked={checked} readOnly />
                <span className="truncate">{o}</span>
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// Open the obligation (filing) generated from a rule — looks it up by the
// rule's first entity and opens the same detail drawer used on Filings.
function useOpenFiling() {
  const { openObligation } = useObligationDrawer();
  return async (rule: Rule) => {
    const eid = rule.entity_ids[0];
    if (!eid) {
      window.alert("No entity linked to this rule yet.");
      return;
    }
    try {
      const obs = await api.get<Obligation[]>(
        `/api/obligations?entity_id=${eid}&limit=300`,
      );
      const match = obs.find((o) => o.rule_id === rule.id);
      if (match) openObligation(match.id);
      else window.alert("No filing generated for this rule yet — approve it first.");
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  };
}

export function RulesPage() {
  const [tab, setTab] = useState<RuleStatus>("staging");
  const [stagingView, setStagingView] = useState<"card" | "table">("table");
  const [q, setQ] = useState("");
  const [jurisdictionCode, setJurisdictionCode] = useState<string>("");
  const [groupSel, setGroupSel] = useState<string[]>([]);
  const [fn, setFn] = useState<string>("");
  const [applic, setApplic] = useState<string>("");
  const [freq, setFreq] = useState<string>("");
  const [entityId, setEntityId] = useState<string>("");
  const [dateOrder, setDateOrder] = useState<"latest" | "oldest">("latest");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  // On-demand cleanup for duplicates that already reached For Action (the
  // discovery-time pass leaves reviewed items alone). Dedupes per entity via AI.
  const dedupe = useMutation({
    mutationFn: () =>
      api.post<{ removed: number }>("/api/rules/dedupe?status=staging&in_review=true"),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      window.alert(
        r.removed
          ? `Removed ${r.removed} duplicate${r.removed === 1 ? "" : "s"} from For Action.`
          : "No duplicates found in For Action.",
      );
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  const { data: rules, isLoading } = useQuery({
    queryKey: ["rules", tab, jurisdictionCode],
    queryFn: () => {
      const params = new URLSearchParams({ status: tab });
      if (jurisdictionCode) params.set("jurisdiction_code", jurisdictionCode);
      // Category is filtered client-side (below) so its dropdown always shows
      // the full set of categories present, instead of collapsing to the one
      // that's selected.
      // For Action only shows items a human sent here; hide discovered drafts.
      if (tab === "staging") params.set("in_review", "true");
      // Hide rules orphaned by a deleted entity (or only owned by archived
      // entities).
      params.set("active_entity_only", "true");
      return api.get<Rule[]>(`/api/rules?${params.toString()}`);
    },
  });

  // Entities — fuels the Entity filter; any entity you add shows up here.
  const { data: entities = [] } = useQuery({
    queryKey: ["entities"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
  });

  // Always-on counts for both tab badges (For Action / Approved) — one
  // consolidated query, refreshed by the same invalidation that mutations fire.
  const { data: counts } = useQuery({
    queryKey: ["rules-count"],
    queryFn: async () => {
      const [s, p] = await Promise.all([
        api.get<Rule[]>("/api/rules?status=staging&in_review=true&active_entity_only=true"),
        api.get<Rule[]>("/api/rules?status=production&active_entity_only=true"),
      ]);
      return { staging: s.length, production: p.length };
    },
  });
  const stagingCount = counts?.staging;
  const productionCount = counts?.production;

  // On open, make sure every For Action / Approved rule has its calendar
  // obligation — so items show on the calendar automatically.
  useEffect(() => {
    api.post("/api/rules/ensure-calendar").catch(() => {});
  }, []);

  // Regulatory changes detected by monitoring (source_changed_at set on a live
  // rule). These surface in For Action for human review alongside new rules.
  const { data: changedRules = [] } = useQuery({
    queryKey: ["rules-changes"],
    queryFn: async () => {
      const rs = await api.get<Rule[]>("/api/rules?status=production");
      return rs.filter((r) => r.source_changed_at);
    },
    enabled: tab === "staging",
  });
  const changes = jurisdictionCode
    ? changedRules.filter((r) => r.jurisdiction_code === jurisdictionCode)
    : changedRules;

  const fnOf = (r: Rule) => r.responsible_function || deriveFunction(r.category, r.area);

  const filtered = useMemo(() => {
    if (!rules) return [];
    let arr = rules;
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      arr = arr.filter(
        (r) =>
          r.name.toLowerCase().includes(needle) ||
          r.form_name.toLowerCase().includes(needle) ||
          r.authority.toLowerCase().includes(needle) ||
          r.area.toLowerCase().includes(needle),
      );
    }
    if (fn) arr = arr.filter((r) => fnOf(r) === fn);
    if (groupSel.length)
      arr = arr.filter((r) => groupSel.includes(categoryGroup(r.category)));
    if (applic) arr = arr.filter((r) => r.applicability === applic);
    if (freq) arr = arr.filter((r) => r.frequency === freq);
    if (entityId)
      arr = arr.filter((r) => r.entity_ids.includes(Number(entityId)));
    // Sort by when the item was added (created_at) — latest or oldest first.
    return [...arr].sort((a, b) => {
      const cmp = a.created_at.localeCompare(b.created_at);
      return dateOrder === "latest" ? -cmp : cmp;
    });
  }, [rules, q, fn, groupSel, applic, freq, entityId, dateOrder]);

  const freqOptions = useMemo(
    () =>
      Array.from(new Set((rules ?? []).map((r) => r.frequency).filter(Boolean))).sort(),
    [rules],
  );

  const functions = useMemo(() => {
    // Always offer the four canonical teams (in order) so Compliance is
    // selectable even when no loaded row currently resolves to it.
    const CANON = ["Finance", "Compliance", "Legal", "HR"];
    const extras = Array.from(new Set((rules ?? []).map(fnOf)))
      .filter((f) => f && !CANON.includes(f))
      .sort();
    return [...CANON, ...extras];
  }, [rules]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Review & Assign"
        description="AI-proposed obligations and regulatory changes awaiting your approval. Review, assign ownership, and confirm applicability before they become active compliance obligations."
        actions={
          <div className="flex items-center gap-2">
            {isAdmin && tab === "staging" && (
              <Button
                variant="outline"
                onClick={() => dedupe.mutate()}
                disabled={dedupe.isPending}
                title="Use AI to merge duplicate / near-duplicate filings in For Action"
              >
                {dedupe.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                Remove duplicates
              </Button>
            )}
            <ExportMenu
              kind="rules"
              params={{
                status: tab,
                jurisdiction_code: jurisdictionCode || undefined,
                // For Action shows only items sent to review — match that here,
                // so the export excludes freshly-discovered drafts (otherwise it
                // dumps the whole staging catalog instead of the visible rows).
                in_review: tab === "staging" ? "true" : undefined,
              }}
            />
          </div>
        }
      />

      <div className="flex items-center justify-between gap-3 flex-wrap">
      <Tabs value={tab} onValueChange={(v) => setTab(v as RuleStatus)}>
        <TabsList>
          <TabsTrigger value="staging">
            For Action
            {typeof stagingCount === "number" && (
              <Badge variant={stagingCount > 0 ? "alert" : "neutral"} className="ml-1">
                {stagingCount}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="production">
            Approved
            {typeof productionCount === "number" && (
              <Badge variant="neutral" className="ml-1">
                {productionCount}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>
      </Tabs>
        <div className="relative w-full sm:w-auto sm:min-w-[280px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by form, authority, area…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-nowrap gap-2 items-center overflow-x-auto pb-1">
        <select
          value={entityId}
          onChange={(e) => setEntityId(e.target.value)}
          className="h-10 min-w-[180px] shrink-0 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="">All entities</option>
          {entities.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name}
            </option>
          ))}
        </select>
        <select
          value={jurisdictionCode}
          onChange={(e) => setJurisdictionCode(e.target.value)}
          className="h-10 shrink-0 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="">All jurisdictions</option>
          {jurisdictionOptionsInUse(entities.map((e) => e.jurisdiction_code)).map((o) => (
            <option key={o.value} value={o.value}>
              {o.name}
            </option>
          ))}
        </select>
        <GroupMultiSelect
          label="All categories"
          options={CATEGORY_GROUP_LABELS}
          selected={groupSel}
          onChange={setGroupSel}
        />
        <select
          value={fn}
          onChange={(e) => setFn(e.target.value)}
          className="h-10 shrink-0 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="">All functions</option>
          {functions.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
        <select
          value={applic}
          onChange={(e) => setApplic(e.target.value)}
          className="h-10 shrink-0 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="">All applicability</option>
          <option value="Mandatory">Mandatory</option>
          <option value="Conditional">Conditional</option>
          <option value="Sector-specific">Sector-specific</option>
        </select>
        <select
          value={freq}
          onChange={(e) => setFreq(e.target.value)}
          className="h-10 shrink-0 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="">All frequencies</option>
          {freqOptions.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
        <select
          value={dateOrder}
          onChange={(e) => setDateOrder(e.target.value as "latest" | "oldest")}
          className="h-10 shrink-0 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="latest">Latest first</option>
          <option value="oldest">Oldest first</option>
        </select>
      </div>

      {tab === "staging" && changes.length > 0 && <ChangesPanel rules={changes} />}

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : filtered.length === 0 && !(tab === "staging" && changes.length > 0) ? (
        <EmptyState
          icon={<FileText className="h-6 w-6" />}
          title={
            tab === "staging"
              ? "Inbox zero — no rules awaiting review"
              : "No rules match the filters"
          }
          description={
            tab === "staging"
              ? "When a country expert submits a new filing template, it lands here for review before going live."
              : "Try clearing filters, or invite a country expert to submit rules for this jurisdiction."
          }
          action={
            tab === "production" && (
              <Button onClick={() => navigate("/rules")} variant="outline">
                Clear filters
              </Button>
            )
          }
        />
      ) : tab === "staging" ? (
        <div className="space-y-3">
          <div className="flex justify-end">
            <div className="inline-flex rounded-lg border border-input overflow-hidden text-sm">
              <button
                onClick={() => setStagingView("card")}
                className={cn(
                  "px-3 h-8 inline-flex items-center gap-1.5",
                  stagingView === "card"
                    ? "bg-aspora-600 text-white"
                    : "bg-background hover:bg-secondary",
                )}
              >
                <LayoutList className="h-3.5 w-3.5" />
                Cards
              </button>
              <button
                onClick={() => setStagingView("table")}
                className={cn(
                  "px-3 h-8 inline-flex items-center gap-1.5 border-l border-input",
                  stagingView === "table"
                    ? "bg-aspora-600 text-white"
                    : "bg-background hover:bg-secondary",
                )}
              >
                <Table2 className="h-3.5 w-3.5" />
                Table
              </button>
            </div>
          </div>
          {stagingView === "table" ? (
            <StagingTable rules={filtered} />
          ) : (
            filtered.map((r) => <StagingCard key={r.id} rule={r} />)
          )}
        </div>
      ) : (
        <ProductionTable rules={filtered} tab={tab} />
      )}
    </div>
  );
}


// Shows the most recent change summary (what changed) for a rule, pulled from
// its monitoring snapshots.
function LatestChange({ ruleId }: { ruleId: number }) {
  const { data } = useQuery({
    queryKey: ["rule-snapshots", ruleId],
    queryFn: () =>
      api.get<{ change_summary: string | null; fetched_at: string }[]>(
        `/api/rules/${ruleId}/snapshots`,
      ),
  });
  const summary = data?.find((s) => s.change_summary)?.change_summary;
  if (!summary) return null;
  return (
    <div className="text-xs text-amber-900 mt-1">
      <span className="font-medium">What changed: </span>
      {summary}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Detected regulatory changes — surfaced in For Action for human review.
// ---------------------------------------------------------------------------
function ChangesPanel({ rules }: { rules: Rule[] }) {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        <h3 className="text-sm font-semibold text-amber-900">
          Regulatory changes detected ({rules.length})
        </h3>
      </div>
      <p className="text-xs text-amber-800/80">
        Weekly monitoring flagged updates on these live obligations. Review the
        source, then edit or re-approve the rule under Approved.
      </p>
      <div className="space-y-2">
        {rules.map((r) => (
          <div
            key={r.id}
            className="flex items-start justify-between gap-3 rounded-lg border border-amber-200 bg-background px-3 py-2"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <JurisdictionBadge code={r.jurisdiction_code} showName={false} />
                <span className="font-medium text-sm truncate">{r.form_name}</span>
                <Badge variant="alert">Change detected</Badge>
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {r.authority} · {r.category} · detected{" "}
                {r.source_changed_at ? fmtRelative(r.source_changed_at) : "—"}
              </div>
              <LatestChange ruleId={r.id} />
            </div>
            {r.source_url && (
              <a
                href={r.source_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-aspora-700 hover:underline inline-flex items-center gap-1 shrink-0"
              >
                View source <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Production table
// ---------------------------------------------------------------------------
// Maps entity id → name. Two entities in the same jurisdiction filing the same
// form are otherwise indistinguishable in the table (both rows just show e.g.
// "United Kingdom"), which reads like one was skipped — so each row names the
// entity/entities it belongs to under the jurisdiction badge.
function useEntityNameMap(): Map<number, string> {
  const { data: entities = [] } = useQuery({
    queryKey: ["entities"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
    staleTime: 300_000,
  });
  return useMemo(() => {
    const m = new Map<number, string>();
    for (const e of entities) m.set(e.id, e.name);
    return m;
  }, [entities]);
}

function EntityNamesLine({ ids, byId }: { ids: number[]; byId: Map<number, string> }) {
  const names = (ids ?? [])
    .map((id) => byId.get(id))
    .filter(Boolean)
    .join(", ");
  if (!names) return null;
  return (
    <div className="mt-0.5 text-xs text-muted-foreground truncate max-w-[180px]" title={names}>
      {names}
    </div>
  );
}

function ProductionTable({ rules, tab }: { rules: Rule[]; tab: string }) {
  const openFiling = useOpenFiling();
  const [checking, setChecking] = useState<Rule | null>(null);
  const [editingUrlRule, setEditingUrlRule] = useState<Rule | null>(null);
  // Row selection for per-row bulk-delete (admin) — reset on section change.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  useEffect(() => setSelected(new Set()), [tab]);
  const pageRules = rules.slice(0, 200);
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const entityById = useEntityNameMap();
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserBrief[]>("/api/users"),
    staleTime: 300_000,
  });
  const userName = (id: number | null) => {
    if (!id) return "—";
    const u = users.find((x) => x.id === id);
    return u ? u.full_name || u.email : "—";
  };
  const fmtApproved = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })
      : "—";

  // Change the assignee on an approved rule — syncs onto its obligation too.
  const assignMutation = useMutation({
    mutationFn: (args: { id: number; ownerId: number | null }) =>
      api.patch(`/api/rules/${args.id}`, { owner_id: args.ownerId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      queryClient.invalidateQueries({ queryKey: ["obligations"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  // Clear ONLY the section you're viewing — delete just this tab's rule ids,
  // so clearing For Action never touches Approved and vice versa.
  const sectionLabel = tab === "staging" ? "For Action" : "Approved";
  const clearSection = useMutation({
    mutationFn: (ids: number[]) =>
      api.post<{ deleted: number }>("/api/rules/bulk-delete", { ids }),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      queryClient.invalidateQueries({ queryKey: ["rules-count"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["obligations"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      window.alert(
        `Cleared ${r.deleted} rule(s) from the ${sectionLabel} section. Other sections are untouched.`,
      );
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  // Delete only the rows the admin ticked (per-row checkboxes) — same
  // bulk-delete endpoint, just the selected ids.
  const deleteSelected = useMutation({
    mutationFn: (ids: number[]) =>
      api.post<{ deleted: number }>("/api/rules/bulk-delete", { ids }),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      queryClient.invalidateQueries({ queryKey: ["rules-count"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["obligations"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      setSelected(new Set());
      window.alert(`Deleted ${r.deleted} filing(s).`);
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  // Permanently remove rules orphaned by a deleted entity (no live entity left).
  // The sections already HIDE these; this clears them from the DB too.
  const orphanCleanup = useMutation({
    mutationFn: () =>
      api.post<{ deleted_rules: number; deleted_obligations: number }>(
        "/api/rules/cleanup-orphans",
      ),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      queryClient.invalidateQueries({ queryKey: ["rules-count"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["obligations"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      window.alert(
        r.deleted_rules
          ? `Removed ${r.deleted_rules} orphaned rule(s) and ${r.deleted_obligations} filing(s) left behind by deleted entities.`
          : "No orphaned rules found.",
      );
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  return (
    <Card className="overflow-hidden">
      {isAdmin && (
        <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-border bg-secondary/20">
          <span className="text-xs text-muted-foreground">
            Delete filings you no longer need, or remove rules left by deleted entities.
          </span>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:text-destructive hover:bg-destructive/10"
              disabled={clearSection.isPending || !(rules && rules.length)}
              onClick={() => {
                const ids = (rules ?? []).map((r) => r.id);
                if (!ids.length) return;
                if (
                  window.confirm(
                    `Clear the ${sectionLabel} section? This permanently deletes the ${ids.length} rule(s) in THIS section (and their calendar filings). The other sections are untouched. Cannot be undone.`,
                  )
                ) {
                  clearSection.mutate(ids);
                }
              }}
              title={`Delete only the rules in the ${sectionLabel} section`}
            >
              {clearSection.isPending && (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              )}
              Clear {sectionLabel}
            </Button>
            {selected.size > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:text-destructive hover:bg-destructive/10"
                disabled={deleteSelected.isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      `Permanently delete the ${selected.size} selected filing(s) and their calendar obligations? This can't be undone.`,
                    )
                  ) {
                    deleteSelected.mutate([...selected]);
                  }
                }}
                title="Delete only the rows you've ticked"
              >
                {deleteSelected.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Delete selected ({selected.size})
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:text-destructive hover:bg-destructive/10"
              disabled={orphanCleanup.isPending}
              onClick={() => {
                if (
                  window.confirm(
                    "Permanently delete rules left with no live entity (orphaned by a deleted entity), plus any filings off them? The Library catalogue is NOT touched. This can't be undone.",
                  )
                ) {
                  orphanCleanup.mutate();
                }
              }}
              title="Remove approved/for-action rules whose entity was deleted"
            >
              {orphanCleanup.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Remove orphaned rules
            </Button>
          </div>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[1200px]">
          <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              {isAdmin && (
                <th className="px-3 py-2.5 w-8">
                  <input
                    type="checkbox"
                    className="accent-aspora-600"
                    checked={pageRules.length > 0 && pageRules.every((r) => selected.has(r.id))}
                    onChange={(e) =>
                      setSelected(e.target.checked ? new Set(pageRules.map((r) => r.id)) : new Set())
                    }
                    title="Select all"
                  />
                </th>
              )}
              <th className="px-3 py-2.5 text-left font-medium">Jurisdiction</th>
              <th className="px-3 py-2.5 text-left font-medium">Form / Report</th>
              <th className="px-3 py-2.5 text-left font-medium">Authority</th>
              <th className="px-3 py-2.5 text-left font-medium">Category</th>
              <th className="px-3 py-2.5 text-left font-medium">Frequency</th>
              <th className="px-3 py-2.5 text-left font-medium">Due-date rule</th>
              <th className="px-3 py-2.5 text-left font-medium">Assignee</th>
              {tab === "production" && (
                <>
                  <th className="px-3 py-2.5 text-left font-medium">Approved by</th>
                  <th className="px-3 py-2.5 text-left font-medium">Approved on</th>
                </>
              )}
              <th className="px-3 py-2.5 text-left font-medium">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {pageRules.map((r) => (
              <tr key={r.id} className="hover:bg-secondary/30">
                {isAdmin && (
                  <td className="px-3 py-2.5">
                    <input
                      type="checkbox"
                      className="accent-aspora-600"
                      checked={selected.has(r.id)}
                      onChange={(e) =>
                        setSelected((prev) => {
                          const next = new Set(prev);
                          if (e.target.checked) next.add(r.id);
                          else next.delete(r.id);
                          return next;
                        })
                      }
                    />
                  </td>
                )}
                <td className="px-3 py-2.5">
                  <JurisdictionBadge code={r.jurisdiction_code} />
                  <EntityNamesLine ids={r.entity_ids} byId={entityById} />
                </td>
                <td className="px-3 py-2.5">
                  <button
                    type="button"
                    onClick={() => openFiling(r)}
                    className="font-medium text-left text-blue-600 hover:text-blue-700 hover:underline"
                  >
                    {r.form_name}
                  </button>
                  {r.area && <div className="text-xs text-muted-foreground truncate">{r.area}</div>}
                </td>
                <td className="px-3 py-2.5 text-muted-foreground">{r.authority}</td>
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-1.5">
                    <Badge variant="neutral">{r.category}</Badge>
                    {r.applicability && (
                      <Badge variant={r.applicability === "Mandatory" ? "alert" : "neutral"}>
                        {r.applicability}
                      </Badge>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground">{r.frequency}</td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground max-w-[240px] truncate">
                  {r.due_date_rule}
                </td>
                <td className="px-3 py-2.5 text-xs">
                  {isAdmin ? (
                    <select
                      value={r.owner_id ?? ""}
                      disabled={assignMutation.isPending}
                      onChange={(e) =>
                        assignMutation.mutate({
                          id: r.id,
                          ownerId: e.target.value ? Number(e.target.value) : null,
                        })
                      }
                      className="h-8 rounded border border-input bg-background px-1.5 text-xs max-w-[140px]"
                    >
                      <option value="">— Unassigned —</option>
                      {users.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.full_name || u.email}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-muted-foreground">{userName(r.owner_id)}</span>
                  )}
                </td>
                {tab === "production" && (
                  <>
                    <td className="px-3 py-2.5 text-xs text-muted-foreground">
                      {userName(r.approver_id)}
                    </td>
                    <td
                      className="px-3 py-2.5 text-xs text-muted-foreground whitespace-nowrap"
                      title={r.approved_at ? parseBackendDate(r.approved_at).toLocaleString() : undefined}
                    >
                      {fmtApproved(r.approved_at)}
                    </td>
                  </>
                )}
                <td className="px-3 py-2.5 text-xs">
                  <button
                    type="button"
                    onClick={() => setEditingUrlRule(r)}
                    className="text-left hover:underline"
                    title="Click to set or edit the regulator portal URL"
                  >
                    {r.source_changed_at ? (
                      <Badge variant="alert" title={`Source changed ${fmtRelative(r.source_changed_at)}`}>
                        Changed
                      </Badge>
                    ) : r.source_url ? (
                      <span className="text-aspora-700">tracked ✎</span>
                    ) : (
                      <span className="text-amber-700 italic">+ add URL</span>
                    )}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rules.length > 200 && (
        <div className="p-3 text-center text-xs text-muted-foreground border-t border-border">
          Showing first 200 of {rules.length}.
        </div>
      )}
      {checking && (
        <RuleChangeCheckDialog
          rule={checking}
          open={!!checking}
          onOpenChange={(v) => !v && setChecking(null)}
        />
      )}
      {editingUrlRule && (
        <EditRuleUrlDialog
          rule={editingUrlRule}
          open={!!editingUrlRule}
          onOpenChange={(v) => !v && setEditingUrlRule(null)}
        />
      )}
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Staging review card — side-by-side editable fields + source text
// ---------------------------------------------------------------------------
type Confidence = "high" | "medium" | "low";

// We don't have a per-field confidence stored yet — synthesize from rule data.
// (Real per-field confidence ships with the rule extractor when we surface it
// from the extractor metadata in a later phase.)
function pseudoConfidence(value: string | null | undefined): Confidence {
  if (!value || value.trim().length === 0) return "low";
  if (value.length < 16) return "medium";
  return "high";
}

function ConfidenceDot({ level }: { level: Confidence }) {
  const colour = {
    high: "bg-emerald-500",
    medium: "bg-amber-500",
    low: "bg-red-500",
  }[level];
  const Icon =
    level === "high" ? CircleCheck : level === "medium" ? CircleAlert : CircleHelp;
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground"
      title={`AI confidence: ${level}`}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", colour)} />
      <Icon className="h-3 w-3" />
      {level}
    </span>
  );
}


const TAX_TYPE_OPTIONS = ["Direct Tax", "Indirect Tax", "Not a Tax"];
const APPLICABILITY_OPTIONS = ["Mandatory", "Conditional", "Sector-specific"];

function StagingCard({ rule, defaultOpen = false }: { rule: Rule; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [editing, setEditing] = useState(false);
  const queryClient = useQueryClient();

  const initialDraft = () => ({
    form_name: rule.form_name,
    authority: rule.authority,
    category: rule.category,
    area: rule.area,
    frequency: rule.frequency,
    due_date_rule: rule.due_date_rule ?? "",
    due_date_spec: (rule.due_date_spec as unknown as DueDateSpec | null) ?? null,
    payment_rule: rule.payment_rule ?? "",
    applicability: rule.applicability as string,
    applicability_note: rule.applicability_note ?? "",
    tax_type: rule.tax_type as string,
  });
  const [draft, setDraft] = useState(initialDraft);
  const set = (k: keyof ReturnType<typeof initialDraft>, v: string) =>
    setDraft((d) => ({ ...d, [k]: v }) as ReturnType<typeof initialDraft>);
  const setSpec = (spec: DueDateSpec) => setDraft((d) => ({ ...d, due_date_spec: spec }));

  // Owner / Reviewer / Approver assignment (Review & Assign workflow).
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserBrief[]>("/api/users"),
    staleTime: 300_000,
  });
  const [owner, setOwner] = useState(rule.owner_id ? String(rule.owner_id) : "");
  const [approver, setApprover] = useState(rule.approver_id ? String(rule.approver_id) : "");

  // Smart assignment: map the rule's function to a team and suggest a person
  // from it. Admins can override via the dropdown.
  const suggestedDept = suggestDepartment(rule);
  const suggested = users.find((u) => u.department === suggestedDept);
  useEffect(() => {
    if (!rule.owner_id && !owner && suggested) setOwner(String(suggested.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggested?.id]);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["rules"] });
    queryClient.invalidateQueries({ queryKey: ["rules-count"] });
    queryClient.invalidateQueries({ queryKey: ["calendar"] });
    queryClient.invalidateQueries({ queryKey: ["obligations"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const saveMutation = useMutation({
    mutationFn: () => api.patch<Rule>(`/api/rules/${rule.id}`, draft),
    onSuccess: () => {
      setEditing(false);
      refresh();
    },
  });
  const promoteMutation = useMutation({
    mutationFn: () =>
      api.patch<Rule>(`/api/rules/${rule.id}`, {
        status: "production",
        owner_id: owner ? Number(owner) : null,
        approver_id: approver ? Number(approver) : null,
      }),
    onSuccess: refresh,
  });
  // Send the rule back to the entity's Compliance tab: it stays a staging
  // draft, just no longer flagged for review — so it reappears on the
  // discovered list and can be re-sent later.
  const returnMutation = useMutation({
    mutationFn: () => api.patch<Rule>(`/api/rules/${rule.id}`, { sent_to_review: false }),
    onSuccess: refresh,
  });
  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/api/rules/${rule.id}`),
    onSuccess: refresh,
  });
  // Apply the deterministic routing-engine's owner-team suggestion when it
  // disagrees with the stored team (LLM-vs-engine reconciliation).
  const applyOwnerMutation = useMutation({
    mutationFn: () =>
      api.patch<Rule>(`/api/rules/${rule.id}`, {
        responsible_function: rule.owner_team_suggested,
      }),
    onSuccess: refresh,
  });
  const busy =
    saveMutation.isPending ||
    promoteMutation.isPending ||
    returnMutation.isPending ||
    deleteMutation.isPending;
  const err =
    saveMutation.error ||
    promoteMutation.error ||
    returnMutation.error ||
    deleteMutation.error;

  return (
    <Card className="overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left px-5 py-4 flex items-center gap-4 hover:bg-secondary/30"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
        <JurisdictionBadge code={rule.jurisdiction_code} showName={false} />
        <div className="min-w-0 flex-1">
          <div className="font-semibold truncate">{rule.form_name}</div>
          <div className="text-xs text-muted-foreground truncate">
            {rule.authority} · {rule.category} · {rule.frequency}
          </div>
        </div>
        <div className="hidden md:flex items-center gap-2 text-xs text-muted-foreground">
          <span>Submitted</span>
          <span className="font-medium">{fmtRelative(rule.created_at)}</span>
        </div>
        {rule.applicability && (
          <Badge variant={rule.applicability === "Mandatory" ? "alert" : "neutral"}>
            {rule.applicability}
          </Badge>
        )}
        <Badge variant="alert">Awaiting review</Badge>
      </button>

      {open && (
        <CardContent className="p-0 border-t border-border">
          <div>
            {rule.owner_team_suggested && (
              <div className="mx-5 mt-4 rounded-lg border border-aspora-300 bg-aspora-50/40 px-3 py-2 text-xs flex items-center justify-between gap-3">
                <span>
                  Owner team is <strong>{rule.responsible_function}</strong> — the routing
                  engine suggests <strong>{rule.owner_team_suggested}</strong>.
                </span>
                <button
                  type="button"
                  disabled={applyOwnerMutation.isPending}
                  onClick={() => applyOwnerMutation.mutate()}
                  className="rounded-md border border-aspora-400 bg-white px-2.5 py-1 font-medium text-aspora-700 hover:bg-aspora-50 disabled:opacity-60"
                >
                  Apply
                </button>
              </div>
            )}
            {/* Editable extracted fields (full width) */}
            <div className="p-5 space-y-3">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-2 flex items-center justify-between">
                <span>
                  AI-extracted fields {editing && <span className="text-aspora-600">(editing)</span>}
                </span>
                {rule.source_url && (
                  <a
                    href={rule.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-aspora-700 hover:underline normal-case tracking-normal"
                  >
                    View source
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
              <ExtractedField label="Form name" value={draft.form_name} editing={editing} onChange={(v) => set("form_name", v)} hint="The official form / report code — e.g. GSTR-3B, Form 22." />
              <ExtractedField label="Authority" value={draft.authority} editing={editing} onChange={(v) => set("authority", v)} hint="Who receives this filing — the regulator, registry or recipient." />
              <ExtractedField label="Category" value={draft.category} editing={editing} onChange={(v) => set("category", v)} hint="High-level bucket used for grouping and filtering." />
              <ExtractedField label="Area / Sub-area" value={draft.area} editing={editing} onChange={(v) => set("area", v)} hint="A short sub-topic within the category." />
              {editing ? (
                <div className="rounded-lg border border-border p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-medium text-muted-foreground">
                      Due date — when this filing falls due; the preview below
                      shows the schedule it produces
                    </span>
                    <Link
                      to="/settings?tab=playbook"
                      className="text-[11px] text-aspora-700 hover:underline whitespace-nowrap"
                    >
                      Full guide →
                    </Link>
                  </div>
                  <DueDateRuleBuilder value={draft.due_date_spec} onChange={setSpec} />
                </div>
              ) : (
                <ExtractedField
                  label="Due date"
                  value={`${draft.frequency}${draft.due_date_rule ? ` — ${draft.due_date_rule}` : ""}`}
                  editing={false}
                  onChange={() => {}}
                />
              )}
              <ExtractedField label="Payment rule" value={draft.payment_rule} multiline editing={editing} onChange={(v) => set("payment_rule", v)} hint="Any fee or tax paid with this filing — amount, %, late fees. Leave blank if nothing is paid." />
              <ExtractedField label="Applicability" value={draft.applicability} options={APPLICABILITY_OPTIONS} editing={editing} onChange={(v) => set("applicability", v)} hint="Mandatory = always applies · Conditional = only when a trigger is met · Sector-specific = only for certain licence types." />
              <ExtractedField label="Applicability note" value={draft.applicability_note} multiline editing={editing} onChange={(v) => set("applicability_note", v)} hint="If Conditional / Sector-specific — what triggers it." />
              <ExtractedField label="Tax type" value={draft.tax_type} options={TAX_TYPE_OPTIONS} editing={editing} onChange={(v) => set("tax_type", v)} hint="Direct = tax on income / profits · Indirect = VAT/GST-style tax collected on the authority's behalf · Not a Tax = everything else." />
            </div>

            {/* Assignment — Owner / Reviewer / Approver */}
            <div className="px-5 pb-5 pt-1">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-2 flex items-center gap-2">
                <span>Assign ownership</span>
                {suggested && (
                  <span className="normal-case tracking-normal text-aspora-700 font-normal">
                    · auto-suggested {suggestedDept} team
                  </span>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <AssignSelect label="Assignee" value={owner} users={users} onChange={setOwner} />
                {/* Approver = the admin who signs off — only admins are offered. */}
                <AssignSelect
                  label="Approver"
                  value={approver}
                  users={users.filter((u) => u.role === "admin")}
                  onChange={setApprover}
                />
              </div>
            </div>
          </div>

          {/* Action bar */}
          <div className="border-t border-border bg-secondary/30 px-5 py-3 flex items-center justify-between flex-wrap gap-2">
            <div className="text-xs text-destructive">
              {err ? (err as Error).message : ""}
            </div>
            <div className="flex items-center gap-2">
              {editing ? (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => {
                      setDraft(initialDraft());
                      setEditing(false);
                      saveMutation.reset();
                    }}
                  >
                    Cancel
                  </Button>
                  <Button size="sm" disabled={busy} onClick={() => saveMutation.mutate()}>
                    {saveMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Save changes
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="outline" size="sm" disabled={busy} onClick={() => setEditing(true)}>
                    Edit
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Move "${rule.form_name}" back to the entity's Compliance tab? It returns to the discovered list as a draft — you can send it to Review & Assign again anytime.`,
                        )
                      ) {
                        returnMutation.mutate();
                      }
                    }}
                    title="Return to the entity's discovered list (not a delete)"
                  >
                    {returnMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Move back to Compliance
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive hover:bg-destructive/10"
                    disabled={busy}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Permanently delete "${rule.form_name}"?\n\nThis also removes any filings scheduled from it. Uploaded documents are kept. This can't be undone.`,
                        )
                      ) {
                        deleteMutation.mutate();
                      }
                    }}
                  >
                    {deleteMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Delete
                  </Button>
                  <Button size="sm" disabled={busy} onClick={() => promoteMutation.mutate()}>
                    {promoteMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Approve &amp; assign
                  </Button>
                </>
              )}
            </div>
          </div>
        </CardContent>
      )}
    </Card>
  );
}


// Compact table view for For Action — quick triage. Full review + assignment
// lives in the card view.
function StagingTable({ rules }: { rules: Rule[] }) {
  const queryClient = useQueryClient();
  // Clicking a row expands it to the SAME inline review panel the card view
  // shows (uniform behaviour across table + cards), not a separate drawer.
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [editingUrlRule, setEditingUrlRule] = useState<Rule | null>(null);
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserBrief[]>("/api/users"),
    staleTime: 300_000,
  });
  const userName = (id: number | null) => {
    if (!id) return "—";
    const u = users.find((x) => x.id === id);
    return u ? u.full_name || u.email : "—";
  };
  const entityById = useEntityNameMap();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["rules"] });
    queryClient.invalidateQueries({ queryKey: ["rules-count"] });
    queryClient.invalidateQueries({ queryKey: ["calendar"] });
    queryClient.invalidateQueries({ queryKey: ["obligations"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const approve = useMutation({
    mutationFn: (id: number) => api.patch<Rule>(`/api/rules/${id}`, { status: "production" }),
    onSuccess: refresh,
  });
  const busy = approve.isPending;

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[900px]">
          <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 text-left font-medium">Jurisdiction</th>
              <th className="px-3 py-2.5 text-left font-medium">Form / Report</th>
              <th className="px-3 py-2.5 text-left font-medium">Authority</th>
              <th className="px-3 py-2.5 text-left font-medium">Category</th>
              <th className="px-3 py-2.5 text-left font-medium">Frequency</th>
              <th className="px-3 py-2.5 text-left font-medium">Due-date rule</th>
              <th className="px-3 py-2.5 text-left font-medium">Assignee</th>
              <th className="px-3 py-2.5 text-left font-medium">Source</th>
              <th className="px-3 py-2.5 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rules.map((r) => (
              <Fragment key={r.id}>
              <tr className="hover:bg-secondary/30">
                <td className="px-3 py-2.5">
                  <JurisdictionBadge code={r.jurisdiction_code} />
                  <EntityNamesLine ids={r.entity_ids} byId={entityById} />
                </td>
                <td className="px-3 py-2.5 font-medium">
                  <button
                    type="button"
                    onClick={() => setExpandedId((id) => (id === r.id ? null : r.id))}
                    className="text-left text-blue-600 hover:text-blue-700 hover:underline"
                  >
                    {r.form_name}
                  </button>
                </td>
                <td className="px-3 py-2.5 text-muted-foreground">{r.authority}</td>
                <td className="px-3 py-2.5">
                  <Badge variant="neutral">{r.category}</Badge>
                </td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground">{r.frequency}</td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground max-w-[220px] truncate" title={r.due_date_rule}>
                  {r.due_date_rule || "—"}
                </td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground">{userName(r.owner_id)}</td>
                <td className="px-3 py-2.5 text-xs">
                  <button
                    type="button"
                    onClick={() => setEditingUrlRule(r)}
                    className="text-left hover:underline"
                    title="Set the regulation + government filing (submission) URLs"
                  >
                    {r.submission_url || r.source_url ? (
                      <span className="text-aspora-700 inline-flex items-center gap-1">
                        Filing URL ✎
                      </span>
                    ) : (
                      <span className="text-amber-700 italic">+ add URL</span>
                    )}
                  </button>
                </td>
                <td className="px-3 py-2.5 text-right whitespace-nowrap">
                  <Button size="sm" disabled={busy} onClick={() => approve.mutate(r.id)}>
                    Approve
                  </Button>
                </td>
              </tr>
              {expandedId === r.id && (
                <tr>
                  <td colSpan={9} className="p-3 bg-secondary/20">
                    <StagingCard rule={r} defaultOpen />
                  </td>
                </tr>
              )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      {editingUrlRule && (
        <EditRuleUrlDialog
          rule={editingUrlRule}
          open={!!editingUrlRule}
          onOpenChange={(v) => !v && setEditingUrlRule(null)}
        />
      )}
    </div>
  );
}


// Map a rule's responsible function / category to the team that should own it.
function suggestDepartment(rule: Rule): string {
  const f = `${rule.responsible_function ?? ""} ${rule.category}`.toLowerCase();
  if (f.includes("legal")) return "legal";
  if (f.includes("compliance") || f.includes("aml")) return "compliance";
  if (f.includes("risk")) return "risk";
  // Finance / tax / accounting → finance team (default).
  return "finance";
}

function AssignSelect({
  label,
  value,
  users,
  onChange,
}: {
  label: string;
  value: string;
  users: UserBrief[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
      >
        <option value="">— Unassigned —</option>
        {users.map((u) => (
          <option key={u.id} value={u.id}>
            {u.full_name || u.email}
          </option>
        ))}
      </select>
    </div>
  );
}


function ExtractedField({
  label,
  value,
  multiline = false,
  editing = false,
  onChange,
  options,
  hint,
}: {
  label: string;
  value: string | null;
  multiline?: boolean;
  editing?: boolean;
  onChange?: (v: string) => void;
  options?: string[];
  /** Plain-language one-liner shown under the label while editing. */
  hint?: string;
}) {
  const editable = editing && !!onChange;
  const base = editable
    ? "border-aspora-300 bg-background"
    : "border-input bg-secondary/30 text-muted-foreground";
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-[11px] font-medium text-muted-foreground">{label}</label>
      </div>
      {editable && hint && (
        <div className="text-[11px] text-muted-foreground mb-1">{hint}</div>
      )}
      {options ? (
        <select
          value={value ?? ""}
          disabled={!editable}
          onChange={(e) => onChange?.(e.target.value)}
          className={cn("h-8 w-full rounded-md border px-2 text-sm", base)}
        >
          {options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : multiline ? (
        <textarea
          rows={3}
          value={value ?? ""}
          readOnly={!editable}
          onChange={(e) => onChange?.(e.target.value)}
          className={cn("w-full rounded-md border px-2 py-1.5 text-sm font-mono", base)}
        />
      ) : (
        <input
          type="text"
          value={value ?? ""}
          readOnly={!editable}
          onChange={(e) => onChange?.(e.target.value)}
          className={cn("h-8 w-full rounded-md border px-2 text-sm", base)}
        />
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// EditRuleUrlDialog — small inline editor for the source_url on a Rule.
// Lets admins capture the regulator's portal / template page so the
// "Submit on regulator's portal →" button on every obligation deep-
// links somewhere useful.
// ---------------------------------------------------------------------------
function EditRuleUrlDialog({
  rule,
  open,
  onOpenChange,
}: {
  rule: Rule;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState(rule.source_url ?? "");
  const [submitUrl, setSubmitUrl] = useState(rule.submission_url ?? "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setUrl(rule.source_url ?? "");
      setSubmitUrl(rule.submission_url ?? "");
      setError(null);
    }
  }, [open, rule]);

  const mutation = useMutation({
    mutationFn: () =>
      api.patch<Rule>(`/api/rules/${rule.id}`, {
        source_url: url.trim() || null,
        submission_url: submitUrl.trim() || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      queryClient.invalidateQueries({ queryKey: ["obligations"] });
      onOpenChange(false);
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  });

  const okUrl = (v: string) => !v.trim() || /^https?:\/\//i.test(v.trim());
  const valid = okUrl(url) && okUrl(submitUrl);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>Regulator links for {rule.form_name}</DialogTitle>
        </DialogHeader>
        <div className="p-6 space-y-4">
          <div className="text-sm text-muted-foreground">
            These two links appear on every obligation generated from this
            rule (filed with <strong>{rule.authority}</strong>).
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium">
              Regulation / template page
            </label>
            <Input
              autoFocus
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.incometax.gov.in/iec/foportal/"
              className="font-mono text-xs"
            />
            {!okUrl(url) && (
              <div className="text-[11px] text-red-700">
                URL must start with http:// or https://
              </div>
            )}
            <p className="text-[11px] text-muted-foreground">
              Everyone sees this as <strong>“View regulation &amp; template”</strong>.
              Read the rules + grab the filing template here.
            </p>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium">
              Government submission portal (where you actually file + pay)
            </label>
            <Input
              value={submitUrl}
              onChange={(e) => setSubmitUrl(e.target.value)}
              placeholder="https://eportal.incometax.gov.in/iec/foservices/"
              className="font-mono text-xs"
            />
            {!okUrl(submitUrl) && (
              <div className="text-[11px] text-red-700">
                URL must start with http:// or https://
              </div>
            )}
            <p className="text-[11px] text-muted-foreground">
              Admins see this as <strong>“Submit &amp; pay on regulator’s portal →”</strong>.
              This is your actual government e-filing link. Leave empty and the
              submit button falls back to the regulation page above.
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
            disabled={mutation.isPending || !valid}
          >
            {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Save links
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
