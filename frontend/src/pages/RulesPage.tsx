import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { PageHeader } from "@/components/PageHeader";
import { JURISDICTIONS } from "@/lib/format";
import type { Rule, RuleStatus } from "@/types/api";

export function RulesPage() {
  const [tab, setTab] = useState<RuleStatus>("production");
  const [q, setQ] = useState("");
  const [jurisdictionCode, setJurisdictionCode] = useState<string>("");
  const [category, setCategory] = useState<string>("");

  const { data: rules, isLoading } = useQuery({
    queryKey: ["rules", tab, jurisdictionCode, category],
    queryFn: () => {
      const params = new URLSearchParams({ status: tab });
      if (jurisdictionCode) params.set("jurisdiction_code", jurisdictionCode);
      if (category) params.set("category", category);
      return api.get<Rule[]>(`/api/rules?${params.toString()}`);
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
    <div className="space-y-6">
      <PageHeader
        title="Compliance Rules"
        description="Rule templates that generate per-entity obligations. Admins manage these; everyone reads."
      />

      <Tabs value={tab} onValueChange={(v) => setTab(v as RuleStatus)}>
        <TabsList>
          <TabsTrigger value="production">Production</TabsTrigger>
          <TabsTrigger value="staging">Staging</TabsTrigger>
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

      <Card className="overflow-hidden">
        <div className="grid grid-cols-[2fr_1.5fr_1fr_1fr_120px_100px] gap-3 px-4 py-3 bg-secondary/50 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          <div>Form / Report</div>
          <div>Authority</div>
          <div>Category</div>
          <div>Jurisdiction</div>
          <div>Frequency</div>
          <div className="text-right">Entities</div>
        </div>

        {isLoading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-10 text-center text-sm text-muted-foreground">
            No rules matched your filters.
          </div>
        ) : (
          <div className="divide-y divide-border">
            {filtered.slice(0, 200).map((r) => (
              <div
                key={r.id}
                className="grid grid-cols-[2fr_1.5fr_1fr_1fr_120px_100px] gap-3 px-4 py-3 items-center text-sm"
              >
                <div className="min-w-0">
                  <div className="font-medium truncate">{r.form_name}</div>
                  {r.area && (
                    <div className="text-xs text-muted-foreground truncate">{r.area}</div>
                  )}
                </div>
                <div className="text-muted-foreground truncate">{r.authority}</div>
                <div>
                  <Badge variant="neutral">{r.category}</Badge>
                </div>
                <div>
                  <JurisdictionBadge code={r.jurisdiction_code} />
                </div>
                <div className="text-xs text-muted-foreground">{r.frequency}</div>
                <div className="text-right text-xs tabular-nums">{r.entity_ids.length}</div>
              </div>
            ))}
            {filtered.length > 200 && (
              <div className="p-3 text-center text-xs text-muted-foreground">
                Showing first 200 of {filtered.length}.
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
