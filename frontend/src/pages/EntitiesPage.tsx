import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { PageHeader } from "@/components/PageHeader";
import { fmtRelative, userInitials, JURISDICTIONS } from "@/lib/format";
import { useAuth } from "@/contexts/AuthContext";
import type { Entity } from "@/types/api";

export function EntitiesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [q, setQ] = useState("");
  const [jurisdiction, setJurisdiction] = useState<string>("");

  const { data, isLoading } = useQuery({
    queryKey: ["entities", jurisdiction],
    queryFn: () =>
      api.get<Entity[]>(
        "/api/entities" + (jurisdiction ? `?jurisdiction_code=${jurisdiction}` : ""),
      ),
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    if (!q.trim()) return data;
    const needle = q.trim().toLowerCase();
    return data.filter(
      (e) =>
        e.name.toLowerCase().includes(needle) ||
        e.legal_type.toLowerCase().includes(needle) ||
        e.registration_number?.toLowerCase().includes(needle),
    );
  }, [data, q]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Entities"
        description="Every Aspora legal entity, with active obligation counts and country leads."
        actions={
          isAdmin && (
            <Button>
              <Plus className="h-4 w-4" />
              Add entity
            </Button>
          )
        }
      />

      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-[280px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by name, type, registration #…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9 h-10"
          />
        </div>
        <select
          value={jurisdiction}
          onChange={(e) => setJurisdiction(e.target.value)}
          className="h-10 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="">All jurisdictions</option>
          {Object.entries(JURISDICTIONS).map(([code, j]) => (
            <option key={code} value={code}>
              {j.flag} {j.name}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="grid grid-cols-[2fr_1.2fr_1fr_1fr_1fr_0.6fr_0.6fr_1fr] gap-4 px-4 py-3 bg-secondary/50 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          <div>Entity</div>
          <div>Type</div>
          <div>Jurisdiction</div>
          <div>Fiscal Year End</div>
          <div>Country Lead</div>
          <div className="text-right">Active</div>
          <div className="text-right">In Alert</div>
          <div>Last Activity</div>
        </div>

        {isLoading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-10 text-center text-sm text-muted-foreground">
            No entities matched your filters.
          </div>
        ) : (
          <div className="divide-y divide-border">
            {filtered.map((e) => (
              <Link
                key={e.id}
                to={`/entities/${e.id}`}
                className="grid grid-cols-[2fr_1.2fr_1fr_1fr_1fr_0.6fr_0.6fr_1fr] gap-4 px-4 py-3 items-center hover:bg-secondary/40 transition-colors text-sm"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="h-9 w-9 rounded-lg bg-aspora-100 grid place-items-center text-aspora-700 font-semibold text-xs shrink-0">
                    {userInitials(e.name)}
                  </div>
                  <div className="min-w-0">
                    <div className="font-medium truncate">{e.name}</div>
                    <div className="text-xs text-muted-foreground truncate">
                      {e.registration_number || "No reg #"}
                    </div>
                  </div>
                </div>
                <div className="text-muted-foreground truncate">{e.legal_type}</div>
                <div>
                  <JurisdictionBadge code={e.jurisdiction_code} />
                </div>
                <div className="text-muted-foreground">{e.fiscal_year_end || "—"}</div>
                <div className="flex items-center gap-2 min-w-0">
                  {e.country_lead ? (
                    <>
                      <Avatar className="h-6 w-6">
                        <AvatarFallback className="text-[10px]">
                          {userInitials(e.country_lead.full_name)}
                        </AvatarFallback>
                      </Avatar>
                      <span className="truncate">{e.country_lead.full_name}</span>
                    </>
                  ) : (
                    <span className="text-muted-foreground italic">Unassigned</span>
                  )}
                </div>
                <div className="text-right tabular-nums font-medium">
                  {e.active_obligations_count}
                </div>
                <div className="text-right tabular-nums">
                  {e.overdue_obligations_count > 0 ? (
                    <Badge variant="overdue">{e.overdue_obligations_count} overdue</Badge>
                  ) : e.in_alert_window_count > 0 ? (
                    <Badge variant="alert">{e.in_alert_window_count}</Badge>
                  ) : (
                    <span className="text-muted-foreground">0</span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground">
                  {e.last_filed_at ? fmtRelative(e.last_filed_at) : "No filings yet"}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
