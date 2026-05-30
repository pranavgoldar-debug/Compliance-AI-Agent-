import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Download } from "lucide-react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/PageHeader";
import { JURISDICTIONS, jurisdiction } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Rule } from "@/types/api";

/**
 * Filings Catalog — the exact original Compliance Calendar table you spec'd
 * early on. 274 filings across 8 jurisdictions, listed in the format your
 * Aspora ops team uses for the master tracker:
 *
 *   S No · Geo · Category · Area · Form/Report · Authority · Frequency ·
 *   Standard Due Date Rule (CY) · Payment · Applicability · Reason if N/A
 *
 * Reads from /api/rules (no backend change needed). Client-side filters +
 * CSV export. Same data as the Compliance Rules admin page, just in your
 * original column layout for at-a-glance reading.
 */
export function FilingsCatalogPage() {
  const [search, setSearch] = useState("");
  const [jurisdictionCode, setJurisdictionCode] = useState<string>("");
  const [category, setCategory] = useState<string>("");

  const { data: rules = [], isLoading } = useQuery({
    queryKey: ["catalog-rules"],
    queryFn: () => api.get<Rule[]>("/api/rules?status=production"),
  });

  // Pull the unique categories for the filter dropdown.
  const categories = useMemo(() => {
    return Array.from(new Set(rules.map((r) => r.category))).sort();
  }, [rules]);

  // Apply all filters together so the visible count + CSV export agree.
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return rules.filter((r) => {
      if (jurisdictionCode && r.jurisdiction_code !== jurisdictionCode) return false;
      if (category && r.category !== category) return false;
      if (
        needle &&
        !(
          r.form_name.toLowerCase().includes(needle) ||
          r.authority.toLowerCase().includes(needle) ||
          r.area.toLowerCase().includes(needle) ||
          r.name.toLowerCase().includes(needle)
        )
      ) {
        return false;
      }
      return true;
    });
  }, [rules, jurisdictionCode, category, search]);

  // Sort by jurisdiction then category then form name for a stable order
  // matching how the original table was grouped.
  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      if (a.jurisdiction_code !== b.jurisdiction_code)
        return a.jurisdiction_code.localeCompare(b.jurisdiction_code);
      if (a.category !== b.category) return a.category.localeCompare(b.category);
      return a.form_name.localeCompare(b.form_name);
    });
  }, [filtered]);

  function downloadCsv() {
    const headers = [
      "S No",
      "Geo",
      "Country",
      "Category",
      "Area",
      "Form / Report",
      "Authority",
      "Frequency",
      "Standard Due Date Rule (CY)",
      "Payment",
      "Applicability",
      "Tax Type",
      "Reason if N/A",
    ];
    const rows = sorted.map((r, i) => [
      String(i + 1),
      jurisdiction(r.jurisdiction_code).flag,
      jurisdiction(r.jurisdiction_code).name,
      r.category,
      r.area,
      r.form_name,
      r.authority,
      r.frequency,
      r.due_date_rule,
      r.payment_rule ?? "",
      r.applicability,
      r.tax_type,
      r.applicability_note ?? "",
    ]);
    const escape = (cell: string) => {
      const needsQuote = /[",\n]/.test(cell);
      const safe = cell.replace(/"/g, '""');
      return needsQuote ? `"${safe}"` : safe;
    };
    const csv = [headers, ...rows]
      .map((row) => row.map(escape).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const stamp = new Date().toISOString().slice(0, 10);
    a.download = `aspora-filings-catalog-${stamp}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function applicabilityClass(value: string): string {
    switch (value) {
      case "Mandatory":
        return "text-red-700 border-red-200 bg-red-50";
      case "Conditional":
        return "text-amber-700 border-amber-200 bg-amber-50";
      case "Sector-specific":
        return "text-slate-700 border-slate-200 bg-slate-50";
      default:
        return "text-muted-foreground border-border bg-secondary";
    }
  }

  function taxTypeClass(value: string): string {
    switch (value) {
      case "Direct Tax":
        return "text-blue-700 border-blue-200 bg-blue-50";
      case "Indirect Tax":
        return "text-purple-700 border-purple-200 bg-purple-50";
      default:
        return "text-muted-foreground border-border bg-secondary";
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Filings Catalog"
        description="Every recurring filing, return, report and notification a remittance fintech tracks — 274 across 8 jurisdictions, in your original column format."
        actions={
          <Button onClick={downloadCsv} disabled={sorted.length === 0}>
            <Download className="h-4 w-4" />
            Export CSV
          </Button>
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-[280px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by form, authority, area…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 h-10"
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
          className="h-10 rounded-lg border border-input bg-background px-3 text-sm min-w-[180px]"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <span className="text-sm text-muted-foreground ml-auto">
          {isLoading ? "…" : `${sorted.length} of ${rules.length} filings`}
        </span>
      </div>

      {/* Table */}
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-secondary/60 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              <tr>
                <Th className="w-[60px] text-right pr-3">S No</Th>
                <Th className="w-[150px]">Geo</Th>
                <Th className="w-[160px]">Category</Th>
                <Th className="w-[160px]">Area</Th>
                <Th className="min-w-[240px]">Form / Report</Th>
                <Th className="w-[180px]">Authority</Th>
                <Th className="w-[130px]">Frequency</Th>
                <Th className="min-w-[280px]">Standard Due Date Rule (CY)</Th>
                <Th className="min-w-[200px]">Payment</Th>
                <Th className="w-[120px]">Applicability</Th>
                <Th className="w-[120px]">Tax type</Th>
                <Th className="min-w-[220px]">Reason if N/A</Th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={12} className="px-3 py-2">
                      <Skeleton className="h-8" />
                    </td>
                  </tr>
                ))
              ) : sorted.length === 0 ? (
                <tr>
                  <td
                    colSpan={12}
                    className="px-3 py-10 text-center text-muted-foreground"
                  >
                    No filings matched your filters.
                  </td>
                </tr>
              ) : (
                sorted.map((r, i) => {
                  const j = jurisdiction(r.jurisdiction_code);
                  return (
                    <tr
                      key={r.id}
                      className="border-t border-border hover:bg-secondary/30 align-top"
                    >
                      <Td className="text-right pr-3 tabular-nums text-muted-foreground">
                        {i + 1}
                      </Td>
                      <Td>
                        <span className="inline-flex items-center gap-1.5">
                          <span aria-hidden className="text-base leading-none">
                            {j.flag}
                          </span>
                          {j.name}
                        </span>
                      </Td>
                      <Td>
                        <Badge variant="neutral">{r.category}</Badge>
                      </Td>
                      <Td className="text-muted-foreground">{r.area || "—"}</Td>
                      <Td className="font-medium">{r.form_name}</Td>
                      <Td className="text-muted-foreground">{r.authority}</Td>
                      <Td>{r.frequency}</Td>
                      <Td className="text-muted-foreground whitespace-pre-line">
                        {r.due_date_rule}
                      </Td>
                      <Td className="text-muted-foreground whitespace-pre-line">
                        {r.payment_rule || "—"}
                      </Td>
                      <Td>
                        <span
                          className={cn(
                            "inline-block rounded-full border px-2 py-0.5 text-xs font-medium",
                            applicabilityClass(r.applicability),
                          )}
                        >
                          {r.applicability}
                        </span>
                      </Td>
                      <Td>
                        <span
                          className={cn(
                            "inline-block rounded-full border px-2 py-0.5 text-xs font-medium",
                            taxTypeClass(r.tax_type),
                          )}
                        >
                          {r.tax_type}
                        </span>
                      </Td>
                      <Td className="text-muted-foreground">
                        {r.applicability_note || "—"}
                      </Td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}


// Cell helpers keep the table markup tight and the wrapping consistent.
function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th className={cn("text-left px-3 py-2.5 align-bottom border-b border-border", className)}>
      {children}
    </th>
  );
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={cn("px-3 py-2.5 align-top", className)}>{children}</td>;
}
