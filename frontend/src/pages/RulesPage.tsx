// Compliance Rules — admin manages the rule templates that generate per-entity
// obligations. Two tabs: Production (flat table) and Staging (side-by-side
// review cards with confidence indicators).
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  ChevronDown,
  ChevronRight,
  CircleCheck,
  CircleAlert,
  CircleHelp,
  Archive,
  AlertTriangle,
  ExternalLink,
  FileText,
  LayoutList,
  Loader2,
  Table2,
  Search,
  Sparkles,
  Upload,
} from "lucide-react";
import { RuleChangeCheckDialog } from "@/components/RuleChangeCheckDialog";
import { ImportRulesDialog } from "@/components/ImportRulesDialog";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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
import { PageHeader } from "@/components/PageHeader";
import { fmtRelative, JURISDICTIONS } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Rule, RuleStatus, UserBrief, Obligation } from "@/types/api";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";

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
  const [stagingView, setStagingView] = useState<"card" | "table">("card");
  const [q, setQ] = useState("");
  const [jurisdictionCode, setJurisdictionCode] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  const [dateOrder, setDateOrder] = useState<"latest" | "oldest">("latest");
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const navigate = useNavigate();

  const { data: rules, isLoading } = useQuery({
    queryKey: ["rules", tab, jurisdictionCode, category],
    queryFn: () => {
      const params = new URLSearchParams({ status: tab });
      if (jurisdictionCode) params.set("jurisdiction_code", jurisdictionCode);
      if (category) params.set("category", category);
      // For Action only shows items a human sent here; hide discovered drafts.
      if (tab === "staging") params.set("in_review", "true");
      return api.get<Rule[]>(`/api/rules?${params.toString()}`);
    },
  });

  // Counts for tab badges (kept cheap: separate small queries).
  const { data: stagingCount } = useQuery({
    queryKey: ["rules-staging-count"],
    queryFn: async () => {
      const rs = await api.get<Rule[]>("/api/rules?status=staging&in_review=true");
      return rs.length;
    },
  });

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
    // Sort by when the item was added (created_at) — latest or oldest first.
    return [...arr].sort((a, b) => {
      const cmp = a.created_at.localeCompare(b.created_at);
      return dateOrder === "latest" ? -cmp : cmp;
    });
  }, [rules, q, dateOrder]);

  const categories = useMemo(() => {
    if (!rules) return [];
    return Array.from(new Set(rules.map((r) => r.category))).sort();
  }, [rules]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Review & Assign"
        description="AI-proposed obligations and regulatory changes awaiting your approval. Review, assign ownership, and confirm applicability before they become active compliance obligations."
        actions={
          <div className="flex items-center gap-2">
            <ExportMenu
              kind="rules"
              params={{
                status: tab,
                jurisdiction_code: jurisdictionCode || undefined,
              }}
            />
            <Button
              variant="outline"
              onClick={() => setImportDialogOpen(true)}
              title="Bulk import rules from a CSV or Excel file"
            >
              <Upload className="h-4 w-4" />
              Import template
            </Button>
          </div>
        }
      />
      <ImportRulesDialog open={importDialogOpen} onOpenChange={setImportDialogOpen} />

      <Tabs value={tab} onValueChange={(v) => setTab(v as RuleStatus)}>
        <TabsList>
          <TabsTrigger value="staging">
            For Action
            {typeof stagingCount === "number" && stagingCount > 0 && (
              <Badge variant="alert" className="ml-1">
                {stagingCount}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="production">
            Approved
            {tab === "production" && rules && (
              <Badge variant="neutral" className="ml-1">
                {rules.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="archived">Archived</TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-[260px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by form, authority, area…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9"
          />
        </div>
        <select
          value={jurisdictionCode}
          onChange={(e) => setJurisdictionCode(e.target.value)}
          className="h-10 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="">All jurisdictions</option>
          {Object.entries(JURISDICTIONS).map(([code, j]) => (
            <option key={code} value={code}>
              {j.flag} {j.name}
            </option>
          ))}
        </select>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="h-10 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          value={dateOrder}
          onChange={(e) => setDateOrder(e.target.value as "latest" | "oldest")}
          className="h-10 rounded-lg border border-input bg-background px-3 text-sm"
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
              : tab === "archived"
                ? "No archived rules"
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
        <ProductionTable rules={filtered} />
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
function ProductionTable({ rules }: { rules: Rule[] }) {
  const openFiling = useOpenFiling();
  const [checking, setChecking] = useState<Rule | null>(null);
  const [editingUrlRule, setEditingUrlRule] = useState<Rule | null>(null);
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
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

  const cleanupMutation = useMutation({
    mutationFn: () =>
      api.post<{ deleted_rules: number; deleted_obligations: number }>(
        "/api/rules/cleanup-recent-production?hours=24&mine_only=true",
      ),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      window.alert(
        `Removed ${r.deleted_rules} draft rule(s) and ${r.deleted_obligations} filing(s) you added in the last 24 hours. Production catalogue rules were left untouched.`,
      );
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  // Mark an approved obligation inactive (archive it) when it no longer applies.
  const archiveMutation = useMutation({
    mutationFn: (id: number) =>
      api.patch<Rule>(`/api/rules/${id}`, { status: "archived" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      queryClient.invalidateQueries({ queryKey: ["obligations"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  const backfillMutation = useMutation({
    mutationFn: () =>
      api.post<{
        checked: number;
        source_filled: number;
        submission_filled: number;
        skipped_no_match: number;
      }>("/api/rules/backfill-source-urls"),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      queryClient.invalidateQueries({ queryKey: ["obligations"] });
      window.alert(
        `Regulator URLs filled.\nChecked: ${r.checked}\nSource links added: ${r.source_filled}\nSubmission links added: ${r.submission_filled}\nNo authority match: ${r.skipped_no_match}`,
      );
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  const wipeMutation = useMutation({
    mutationFn: () =>
      api.post<{ rules: number; obligations: number }>(
        "/api/rules/wipe-catalogue",
      ),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      queryClient.invalidateQueries({ queryKey: ["license-rules"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["obligations"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      window.alert(
        `Catalogue cleared. Deleted ${r.rules} rule(s) and ${r.obligations} calendar filing(s). Users, entities and licenses are untouched.\n\nNow open a license and use "Find Regulations" to rebuild the catalogue.`,
      );
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  return (
    <Card className="overflow-hidden">
      {isAdmin && (
        <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-border bg-secondary/20">
          <span className="text-xs text-muted-foreground">
            Backfill regulator links, or clean up rules you added recently.
          </span>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:text-destructive hover:bg-destructive/10"
              disabled={wipeMutation.isPending}
              onClick={() => {
                if (
                  window.confirm(
                    "Clear the ENTIRE catalogue? This deletes every rule and every calendar filing (obligations). Users, entities and licenses stay.\n\nThis is for starting clean with the AI-first flow — rebuild via 'Find Regulations'. Cannot be undone.",
                  )
                ) {
                  wipeMutation.mutate();
                }
              }}
              title="Delete all rules + calendar entries. Users/entities/licenses stay."
            >
              {wipeMutation.isPending && (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              )}
              Clear all rules
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={backfillMutation.isPending}
              onClick={() => backfillMutation.mutate()}
              title="Fill every rule's regulator 'View regulation' + 'Submit & pay' links from the authority table"
            >
              {backfillMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Backfill regulator URLs
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:text-destructive hover:bg-destructive/10"
              disabled={cleanupMutation.isPending}
              onClick={() => {
                if (
                  window.confirm(
                    "Delete the DRAFT (staging / AI-extracted) rules you created in the last 24 hours, and any filings scheduled from them? Production catalogue rules are NOT touched. Uploaded documents are kept. This can't be undone.",
                  )
                ) {
                  cleanupMutation.mutate();
                }
              }}
            >
              {cleanupMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Clean up draft rules I added (last 24h)
            </Button>
          </div>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[1200px]">
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
              <th className="px-3 py-2.5 w-8" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rules.slice(0, 200).map((r) => (
              <tr key={r.id} className="hover:bg-secondary/30">
                <td className="px-3 py-2.5">
                  <JurisdictionBadge code={r.jurisdiction_code} />
                </td>
                <td className="px-3 py-2.5">
                  <button
                    type="button"
                    onClick={() => openFiling(r)}
                    className="font-medium text-left hover:text-aspora-700 hover:underline"
                  >
                    {r.form_name}
                  </button>
                  {r.area && <div className="text-xs text-muted-foreground truncate">{r.area}</div>}
                </td>
                <td className="px-3 py-2.5 text-muted-foreground">{r.authority}</td>
                <td className="px-3 py-2.5">
                  <Badge variant="neutral">{r.category}</Badge>
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
                <td className="px-3 py-2.5 text-right whitespace-nowrap">
                  {isAdmin && r.status === "production" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-muted-foreground hover:text-destructive"
                      title="Mark inactive — archive this obligation (no longer applies)"
                      disabled={archiveMutation.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Mark "${r.form_name}" inactive? It will be archived and stop generating filings.`,
                          )
                        ) {
                          archiveMutation.mutate(r.id);
                        }
                      }}
                    >
                      <Archive className="h-3.5 w-3.5" />
                    </Button>
                  )}
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

function StagingCard({ rule }: { rule: Rule }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const queryClient = useQueryClient();

  const initialDraft = () => ({
    form_name: rule.form_name,
    authority: rule.authority,
    category: rule.category,
    area: rule.area,
    frequency: rule.frequency,
    due_date_rule: rule.due_date_rule ?? "",
    payment_rule: rule.payment_rule ?? "",
    applicability: rule.applicability as string,
    applicability_note: rule.applicability_note ?? "",
    tax_type: rule.tax_type as string,
  });
  const [draft, setDraft] = useState(initialDraft);
  const set = (k: keyof ReturnType<typeof initialDraft>, v: string) =>
    setDraft((d) => ({ ...d, [k]: v }));

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
    queryClient.invalidateQueries({ queryKey: ["rules-staging-count"] });
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
  const rejectMutation = useMutation({
    mutationFn: () => api.patch<Rule>(`/api/rules/${rule.id}`, { status: "archived" }),
    onSuccess: refresh,
  });
  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/api/rules/${rule.id}`),
    onSuccess: refresh,
  });
  const busy =
    saveMutation.isPending ||
    promoteMutation.isPending ||
    rejectMutation.isPending ||
    deleteMutation.isPending;
  const err =
    saveMutation.error ||
    promoteMutation.error ||
    rejectMutation.error ||
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
        <Badge variant="alert">Awaiting review</Badge>
      </button>

      {open && (
        <CardContent className="p-0 border-t border-border">
          <div>
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
                    View original regulation
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
              <ExtractedField label="Form name" value={draft.form_name} editing={editing} onChange={(v) => set("form_name", v)} />
              <ExtractedField label="Authority" value={draft.authority} editing={editing} onChange={(v) => set("authority", v)} />
              <ExtractedField label="Category" value={draft.category} editing={editing} onChange={(v) => set("category", v)} />
              <ExtractedField label="Area / Sub-area" value={draft.area} editing={editing} onChange={(v) => set("area", v)} />
              <ExtractedField label="Frequency" value={draft.frequency} editing={editing} onChange={(v) => set("frequency", v)} />
              <ExtractedField label="Due-date rule" value={draft.due_date_rule} multiline editing={editing} onChange={(v) => set("due_date_rule", v)} />
              <ExtractedField label="Payment rule" value={draft.payment_rule} multiline editing={editing} onChange={(v) => set("payment_rule", v)} />
              <ExtractedField label="Applicability" value={draft.applicability} options={APPLICABILITY_OPTIONS} editing={editing} onChange={(v) => set("applicability", v)} />
              <ExtractedField label="Applicability note" value={draft.applicability_note} multiline editing={editing} onChange={(v) => set("applicability_note", v)} />
              <ExtractedField label="Tax type" value={draft.tax_type} options={TAX_TYPE_OPTIONS} editing={editing} onChange={(v) => set("tax_type", v)} />
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
                <AssignSelect label="Approver" value={approver} users={users} onChange={setApprover} />
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
                    className="text-red-600"
                    disabled={busy}
                    onClick={() => {
                      if (window.confirm("Reject this rule? It will be archived (not deleted).")) {
                        rejectMutation.mutate();
                      }
                    }}
                  >
                    {rejectMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Reject
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
  const openFiling = useOpenFiling();
  const [editingUrlRule, setEditingUrlRule] = useState<Rule | null>(null);
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["rules"] });
    queryClient.invalidateQueries({ queryKey: ["rules-staging-count"] });
    queryClient.invalidateQueries({ queryKey: ["calendar"] });
    queryClient.invalidateQueries({ queryKey: ["obligations"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const approve = useMutation({
    mutationFn: (id: number) => api.patch<Rule>(`/api/rules/${id}`, { status: "production" }),
    onSuccess: refresh,
  });
  const reject = useMutation({
    mutationFn: (id: number) => api.patch<Rule>(`/api/rules/${id}`, { status: "archived" }),
    onSuccess: refresh,
  });
  const busy = approve.isPending || reject.isPending;

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[900px]">
          <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 text-left font-medium">Jurisdiction</th>
              <th className="px-3 py-2.5 text-left font-medium">Obligation</th>
              <th className="px-3 py-2.5 text-left font-medium">Authority</th>
              <th className="px-3 py-2.5 text-left font-medium">Category</th>
              <th className="px-3 py-2.5 text-left font-medium">Frequency</th>
              <th className="px-3 py-2.5 text-left font-medium">Due date</th>
              <th className="px-3 py-2.5 text-left font-medium">Source</th>
              <th className="px-3 py-2.5 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rules.map((r) => (
              <tr key={r.id} className="hover:bg-secondary/30">
                <td className="px-3 py-2.5">
                  <JurisdictionBadge code={r.jurisdiction_code} />
                </td>
                <td className="px-3 py-2.5 font-medium">
                  <button
                    type="button"
                    onClick={() => openFiling(r)}
                    className="text-left hover:text-aspora-700 hover:underline"
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
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-red-600 ml-1"
                    disabled={busy}
                    onClick={() => reject.mutate(r.id)}
                  >
                    Reject
                  </Button>
                </td>
              </tr>
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
}: {
  label: string;
  value: string | null;
  multiline?: boolean;
  editing?: boolean;
  onChange?: (v: string) => void;
  options?: string[];
}) {
  const conf = pseudoConfidence(value);
  const editable = editing && !!onChange;
  const base = editable
    ? "border-aspora-300 bg-background"
    : "border-input bg-secondary/30 text-muted-foreground";
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-[11px] font-medium text-muted-foreground">{label}</label>
        <ConfidenceDot level={conf} />
      </div>
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
