// Compliance Obligations — the system of record for human-approved obligations.
// One row per obligation instance (quarterly filings show up as 4 separate
// rows, each with its own due date + status). Powers the same data the
// calendar reads. Approved-only: obligations are generated from Production
// (Approved) rules, so nothing here is an AI proposal awaiting review.
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search, ExternalLink, ClipboardCheck } from "lucide-react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { StatusPill } from "@/components/StatusPill";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { ExportMenu } from "@/components/ExportMenu";
import { fmtDate, userInitials, JURISDICTIONS } from "@/lib/format";
import type { Obligation, ObligationStatus } from "@/types/api";

const STATUS_OPTIONS: { value: ObligationStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "not_applicable", label: "Not applicable" },
];

export function ComplianceObligationsPage() {
  const [q, setQ] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [status, setStatus] = useState<ObligationStatus | "">("");

  const { data, isLoading } = useQuery({
    queryKey: ["compliance-obligations"],
    queryFn: () => api.get<Obligation[]>("/api/obligations?limit=1000"),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });

  const filtered = useMemo(() => {
    let arr = data ?? [];
    if (jurisdiction) arr = arr.filter((o) => o.entity_jurisdiction_code === jurisdiction);
    if (status) arr = arr.filter((o) => o.status === status);
    if (q.trim()) {
      const n = q.trim().toLowerCase();
      arr = arr.filter(
        (o) =>
          o.rule_name.toLowerCase().includes(n) ||
          o.entity_name.toLowerCase().includes(n) ||
          o.rule_authority.toLowerCase().includes(n),
      );
    }
    return [...arr].sort((a, b) => a.due_date.localeCompare(b.due_date));
  }, [data, jurisdiction, status, q]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Compliance Obligations"
        description="Human-approved obligations — every filing instance with its own due date, owner and status. This is the system of record that powers the calendar."
        actions={<ExportMenu kind="obligations" params={{ jurisdiction_code: jurisdiction || undefined }} />}
      />

      {/* Filters — jurisdiction always available */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-[260px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by obligation, entity, authority…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9 h-10"
          />
        </div>
        <select
          value={jurisdiction}
          onChange={(e) => setJurisdiction(e.target.value)}
          className="h-10 rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="">All jurisdictions</option>
          {Object.entries(JURISDICTIONS).map(([code, j]) => (
            <option key={code} value={code}>
              {j.flag} {j.name}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as ObligationStatus | "")}
          className="h-10 rounded-md border border-input bg-background px-3 text-sm"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<ClipboardCheck className="h-6 w-6" />}
          title={
            data && data.length === 0
              ? "No approved obligations yet"
              : "No obligations match the filters"
          }
          description={
            data && data.length === 0
              ? "Approve obligations under Review & Assign — they'll appear here with their due dates."
              : "Try clearing the jurisdiction or status filter."
          }
        />
      ) : (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[980px]">
              <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium">Obligation</th>
                  <th className="px-4 py-2.5 text-left font-medium">Entity</th>
                  <th className="px-4 py-2.5 text-left font-medium">Jurisdiction</th>
                  <th className="px-4 py-2.5 text-left font-medium">Due date</th>
                  <th className="px-4 py-2.5 text-left font-medium">Owner</th>
                  <th className="px-4 py-2.5 text-left font-medium">Status</th>
                  <th className="px-4 py-2.5 text-left font-medium">Frequency</th>
                  <th className="px-4 py-2.5 text-left font-medium">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((o) => (
                  <tr key={o.id} className="hover:bg-secondary/30">
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/obligations/${o.id}`}
                        className="font-medium hover:text-aspora-700"
                      >
                        {o.rule_name}
                      </Link>
                      {o.period_label && (
                        <div className="text-[11px] text-muted-foreground">{o.period_label}</div>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">{o.entity_name}</td>
                    <td className="px-4 py-2.5">
                      <JurisdictionBadge code={o.entity_jurisdiction_code} />
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={o.is_overdue ? "text-red-600 font-medium" : ""}>
                        {fmtDate(o.due_date)}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      {o.assignee ? (
                        <span className="inline-flex items-center gap-1.5">
                          <span className="h-5 w-5 rounded-full bg-aspora-100 grid place-items-center text-[9px] font-semibold text-aspora-700">
                            {userInitials(o.assignee.full_name)}
                          </span>
                          <span className="truncate">{o.assignee.full_name}</span>
                        </span>
                      ) : (
                        <span className="text-muted-foreground italic text-xs">Unassigned</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <StatusPill status={o.status} />
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{o.rule_frequency}</td>
                    <td className="px-4 py-2.5 text-xs">
                      {o.rule_source_url ? (
                        <a
                          href={o.rule_source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-aspora-700 hover:underline"
                        >
                          Source
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
