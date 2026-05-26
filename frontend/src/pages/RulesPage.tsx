// Compliance Rules — admin manages the rule templates that generate per-entity
// obligations. Two tabs: Production (flat table) and Staging (side-by-side
// review cards with confidence indicators).
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  ChevronDown,
  ChevronRight,
  CircleCheck,
  CircleAlert,
  CircleHelp,
  ExternalLink,
  FileText,
  Search,
  Sparkles,
  Upload,
} from "lucide-react";
import { api } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { EmptyState } from "@/components/EmptyState";
import { ExportMenu } from "@/components/ExportMenu";
import { PageHeader } from "@/components/PageHeader";
import { AddRuleFromTextDialog } from "@/components/AddRuleFromTextDialog";
import { fmtRelative, JURISDICTIONS } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Rule, RuleStatus } from "@/types/api";

export function RulesPage() {
  const [tab, setTab] = useState<RuleStatus>("production");
  const [q, setQ] = useState("");
  const [jurisdictionCode, setJurisdictionCode] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  const [aiDialogOpen, setAiDialogOpen] = useState(false);
  const navigate = useNavigate();

  const { data: rules, isLoading } = useQuery({
    queryKey: ["rules", tab, jurisdictionCode, category],
    queryFn: () => {
      const params = new URLSearchParams({ status: tab });
      if (jurisdictionCode) params.set("jurisdiction_code", jurisdictionCode);
      if (category) params.set("category", category);
      return api.get<Rule[]>(`/api/rules?${params.toString()}`);
    },
  });

  // Counts for tab badges (kept cheap: separate small queries).
  const { data: stagingCount } = useQuery({
    queryKey: ["rules-staging-count"],
    queryFn: async () => {
      const rs = await api.get<Rule[]>("/api/rules?status=staging");
      return rs.length;
    },
  });

  const filtered = useMemo(() => {
    if (!rules) return [];
    if (!q.trim()) return rules;
    const needle = q.trim().toLowerCase();
    return rules.filter(
      (r) =>
        r.name.toLowerCase().includes(needle) ||
        r.form_name.toLowerCase().includes(needle) ||
        r.authority.toLowerCase().includes(needle) ||
        r.area.toLowerCase().includes(needle),
    );
  }, [rules, q]);

  const categories = useMemo(() => {
    if (!rules) return [];
    return Array.from(new Set(rules.map((r) => r.category))).sort();
  }, [rules]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Compliance Rules"
        description="Templates that generate per-entity obligations. The most critical data asset in the product."
        actions={
          <div className="flex items-center gap-2">
            <ExportMenu
              kind="rules"
              params={{
                status: tab,
                jurisdiction_code: jurisdictionCode || undefined,
              }}
            />
            <Button variant="outline" disabled title="Coming later">
              <Upload className="h-4 w-4" />
              Import template
            </Button>
            <Button onClick={() => setAiDialogOpen(true)}>
              <Sparkles className="h-4 w-4" />
              Add from text
            </Button>
          </div>
        }
      />
      <AddRuleFromTextDialog open={aiDialogOpen} onOpenChange={setAiDialogOpen} />

      <Tabs value={tab} onValueChange={(v) => setTab(v as RuleStatus)}>
        <TabsList>
          <TabsTrigger value="production">
            In Production
            {tab === "production" && rules && (
              <Badge variant="neutral" className="ml-1">
                {rules.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="staging">
            Staging
            {typeof stagingCount === "number" && stagingCount > 0 && (
              <Badge variant="alert" className="ml-1">
                {stagingCount}
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
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
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
          {filtered.map((r) => (
            <StagingCard key={r.id} rule={r} />
          ))}
        </div>
      ) : (
        <ProductionTable rules={filtered} />
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Production table
// ---------------------------------------------------------------------------
function ProductionTable({ rules }: { rules: Rule[] }) {
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[1100px]">
          <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 text-left font-medium">Jurisdiction</th>
              <th className="px-3 py-2.5 text-left font-medium">Form / Report</th>
              <th className="px-3 py-2.5 text-left font-medium">Authority</th>
              <th className="px-3 py-2.5 text-left font-medium">Category</th>
              <th className="px-3 py-2.5 text-left font-medium">Frequency</th>
              <th className="px-3 py-2.5 text-left font-medium">Due-date rule</th>
              <th className="px-3 py-2.5 text-right font-medium">Entities</th>
              <th className="px-3 py-2.5 text-left font-medium">Last update</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rules.slice(0, 200).map((r) => (
              <tr key={r.id} className="hover:bg-secondary/30">
                <td className="px-3 py-2.5">
                  <JurisdictionBadge code={r.jurisdiction_code} />
                </td>
                <td className="px-3 py-2.5">
                  <div className="font-medium">{r.form_name}</div>
                  {r.area && <div className="text-xs text-muted-foreground truncate">{r.area}</div>}
                </td>
                <td className="px-3 py-2.5 text-muted-foreground">{r.authority}</td>
                <td className="px-3 py-2.5">
                  <Badge variant="neutral">{r.category}</Badge>
                </td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground">{r.frequency}</td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground max-w-[260px] truncate">
                  {r.due_date_rule}
                </td>
                <td className="px-3 py-2.5 text-right text-xs tabular-nums">
                  {r.entity_ids.length}
                </td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground">
                  {fmtRelative(r.updated_at)}
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


function StagingCard({ rule }: { rule: Rule }) {
  const [open, setOpen] = useState(false);
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
          <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-border">
            {/* Left — editable extracted fields */}
            <div className="p-5 space-y-3">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-2">
                AI-extracted fields
              </div>
              <ExtractedField label="Form name" value={rule.form_name} />
              <ExtractedField label="Authority" value={rule.authority} />
              <ExtractedField label="Category" value={rule.category} />
              <ExtractedField label="Area / Sub-area" value={rule.area} />
              <ExtractedField label="Frequency" value={rule.frequency} />
              <ExtractedField label="Due-date rule" value={rule.due_date_rule} multiline />
              <ExtractedField label="Payment rule" value={rule.payment_rule} multiline />
              <ExtractedField
                label="Applicability"
                value={`${rule.applicability}${rule.applicability_note ? " — " + rule.applicability_note : ""}`}
              />
            </div>

            {/* Right — original source text proxy */}
            <div className="p-5 space-y-2 bg-secondary/20">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium flex items-center justify-between mb-2">
                <span>Source — original regulation</span>
                <a
                  href="#"
                  onClick={(e) => e.preventDefault()}
                  className="inline-flex items-center gap-1 text-xs text-aspora-700 hover:underline"
                >
                  Open in tab
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <div className="rounded-lg border border-border bg-background px-3 py-3 text-xs leading-relaxed font-mono whitespace-pre-wrap text-muted-foreground max-h-[320px] overflow-auto scrollbar-thin">
                {rule.due_date_rule || "—"}
                {"\n\n"}
                {rule.applicability_note || "(no applicability note)"}
                {"\n\n"}
                <span className="italic text-muted-foreground/70">
                  When this rule was extracted by Claude, the full source text was the regulatory excerpt above. Per-field provenance + side-by-side diff vs an existing rule lands in Phase 5.
                </span>
              </div>
            </div>
          </div>

          {/* Action bar */}
          <div className="border-t border-border bg-secondary/30 px-5 py-3 flex items-center justify-between flex-wrap gap-2">
            <div className="text-xs text-muted-foreground">
              <span className="font-medium">Diff vs existing rule</span> — none detected
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled>
                Request more info
              </Button>
              <Button variant="outline" size="sm" disabled>
                Edit
              </Button>
              <Button variant="outline" size="sm" disabled className="text-red-600">
                Reject
              </Button>
              <Button size="sm" disabled>
                Approve &amp; promote
              </Button>
            </div>
          </div>
        </CardContent>
      )}
    </Card>
  );
}


function ExtractedField({
  label,
  value,
  multiline = false,
}: {
  label: string;
  value: string | null;
  multiline?: boolean;
}) {
  const conf = pseudoConfidence(value);
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-[11px] font-medium text-muted-foreground">{label}</label>
        <ConfidenceDot level={conf} />
      </div>
      {multiline ? (
        <textarea
          rows={3}
          defaultValue={value ?? ""}
          className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm font-mono"
          readOnly
        />
      ) : (
        <input
          type="text"
          defaultValue={value ?? ""}
          className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm"
          readOnly
        />
      )}
    </div>
  );
}
