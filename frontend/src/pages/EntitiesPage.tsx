// Entities — every Aspora legal entity. Table + Card grid toggle, multi-select
// filters, search by name/type/reg #.
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ChevronDown,
  LayoutGrid,
  List,
  Lock,
  Plus,
  Search,
  Building2,
} from "lucide-react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent } from "@/components/ui/card";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { EmptyState } from "@/components/EmptyState";
import { ExportMenu } from "@/components/ExportMenu";
import { PageHeader } from "@/components/PageHeader";
import { fmtRelative, userInitials, JURISDICTIONS } from "@/lib/format";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";
import type { Entity, UserBrief } from "@/types/api";


type ViewMode = "table" | "grid";


export function EntitiesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [q, setQ] = useState("");
  const [jurisdictions, setJurisdictions] = useState<string[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [leadIds, setLeadIds] = useState<string[]>([]);
  const [view, setView] = useState<ViewMode>("table");

  const { data, isLoading } = useQuery({
    queryKey: ["entities"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
  });
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserBrief[]>("/api/users"),
  });

  const allTypes = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.map((e) => e.legal_type).filter(Boolean))).sort();
  }, [data]);

  const filtered = useMemo(() => {
    if (!data) return [];
    let arr = data;
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      arr = arr.filter(
        (e) =>
          e.name.toLowerCase().includes(needle) ||
          e.legal_type.toLowerCase().includes(needle) ||
          (e.registration_number?.toLowerCase().includes(needle) ?? false),
      );
    }
    if (jurisdictions.length) arr = arr.filter((e) => jurisdictions.includes(e.jurisdiction_code));
    if (types.length) arr = arr.filter((e) => types.includes(e.legal_type));
    if (leadIds.length)
      arr = arr.filter((e) => e.country_lead && leadIds.includes(String(e.country_lead.id)));
    return arr;
  }, [data, q, jurisdictions, types, leadIds]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Entities"
        description="Every Aspora legal entity, with active obligation counts and country leads."
        actions={
          <div className="flex items-center gap-2">
            <ExportMenu
              kind="entities"
              params={{
                jurisdiction_code: jurisdictions.length === 1 ? jurisdictions[0] : undefined,
              }}
            />
            {isAdmin ? (
              <Button>
                <Plus className="h-4 w-4" />
                Add entity
              </Button>
            ) : (
              <Button variant="outline" disabled title="Admin only">
                <Lock className="h-3.5 w-3.5" />
                Add entity
              </Button>
            )}
          </div>
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
        <FilterPopover
          label="Jurisdiction"
          options={Object.entries(JURISDICTIONS).map(([code, j]) => ({
            value: code,
            label: `${j.flag} ${j.name}`,
          }))}
          selected={jurisdictions}
          onChange={setJurisdictions}
        />
        <FilterPopover
          label="Type"
          options={allTypes.map((t) => ({ value: t, label: t }))}
          selected={types}
          onChange={setTypes}
          searchable
        />
        <FilterPopover
          label="Country lead"
          options={users.map((u) => ({ value: String(u.id), label: u.full_name }))}
          selected={leadIds}
          onChange={setLeadIds}
          searchable
        />

        <div className="ml-auto inline-flex rounded-lg border border-input overflow-hidden">
          <button
            onClick={() => setView("table")}
            className={cn(
              "h-9 px-3 text-sm inline-flex items-center gap-1.5",
              view === "table" ? "bg-aspora-600 text-white" : "bg-background hover:bg-secondary",
            )}
          >
            <List className="h-3.5 w-3.5" />
            Table
          </button>
          <button
            onClick={() => setView("grid")}
            className={cn(
              "h-9 px-3 text-sm inline-flex items-center gap-1.5 border-l border-input",
              view === "grid" ? "bg-aspora-600 text-white" : "bg-background hover:bg-secondary",
            )}
          >
            <LayoutGrid className="h-3.5 w-3.5" />
            Card grid
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<Building2 className="h-6 w-6" />}
          title={data && data.length === 0 ? "Add your first entity to get started" : "No entities match the filters"}
          description={
            data && data.length === 0
              ? "Aspora UK Ltd, Aspora DMCC, Aspora India Pvt Ltd — track them all from one place."
              : "Try clearing some filters or searching for a different name."
          }
          action={
            isAdmin && data && data.length === 0 ? (
              <Button>
                <Plus className="h-4 w-4" />
                Add entity
              </Button>
            ) : undefined
          }
        />
      ) : view === "table" ? (
        <TableView entities={filtered} />
      ) : (
        <GridView entities={filtered} />
      )}
    </div>
  );
}


function TableView({ entities }: { entities: Entity[] }) {
  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[1000px]">
          <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 text-left font-medium">Entity</th>
              <th className="px-4 py-2.5 text-left font-medium">Type</th>
              <th className="px-4 py-2.5 text-left font-medium">Jurisdiction</th>
              <th className="px-4 py-2.5 text-left font-medium">Fiscal YE</th>
              <th className="px-4 py-2.5 text-left font-medium">Country lead</th>
              <th className="px-4 py-2.5 text-right font-medium">Active</th>
              <th className="px-4 py-2.5 text-right font-medium">Overdue</th>
              <th className="px-4 py-2.5 text-right font-medium">In alert</th>
              <th className="px-4 py-2.5 text-left font-medium">Last activity</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {entities.map((e) => (
              <tr
                key={e.id}
                className="hover:bg-secondary/30 cursor-pointer"
                onClick={() => {
                  window.location.href = `/entities/${e.id}`;
                }}
              >
                <td className="px-4 py-2.5">
                  <Link
                    to={`/entities/${e.id}`}
                    className="flex items-center gap-3 min-w-0 hover:text-aspora-700"
                  >
                    <div className="h-8 w-8 rounded-lg bg-aspora-100 grid place-items-center text-aspora-700 font-semibold text-[10px] shrink-0">
                      {e.short_code || userInitials(e.name)}
                    </div>
                    <div className="min-w-0">
                      <div className="font-medium truncate">{e.name}</div>
                      <div className="text-xs text-muted-foreground truncate font-mono">
                        {e.short_code
                          ? e.registration_number || `Code: ${e.short_code}`
                          : e.registration_number || "No reg #"}
                      </div>
                    </div>
                  </Link>
                </td>
                <td className="px-4 py-2.5 text-muted-foreground">{e.legal_type}</td>
                <td className="px-4 py-2.5">
                  <JurisdictionBadge code={e.jurisdiction_code} />
                </td>
                <td className="px-4 py-2.5 text-muted-foreground">{e.fiscal_year_end || "—"}</td>
                <td className="px-4 py-2.5">
                  {e.country_lead ? (
                    <div className="flex items-center gap-2 min-w-0">
                      <Avatar className="h-6 w-6">
                        <AvatarFallback className="text-[10px]">
                          {userInitials(e.country_lead.full_name)}
                        </AvatarFallback>
                      </Avatar>
                      <span className="truncate">{e.country_lead.full_name}</span>
                    </div>
                  ) : (
                    <span className="text-muted-foreground italic text-xs">Unassigned</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums font-medium">
                  {e.active_obligations_count}
                </td>
                <td className="px-4 py-2.5 text-right">
                  {e.overdue_obligations_count > 0 ? (
                    <Badge variant="overdue">{e.overdue_obligations_count}</Badge>
                  ) : (
                    <span className="text-muted-foreground">0</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right">
                  {e.in_alert_window_count > 0 ? (
                    <Badge variant="alert">{e.in_alert_window_count}</Badge>
                  ) : (
                    <span className="text-muted-foreground">0</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-xs text-muted-foreground">
                  {e.last_filed_at ? fmtRelative(e.last_filed_at) : "No filings yet"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


function GridView({ entities }: { entities: Entity[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
      {entities.map((e) => (
        <Link key={e.id} to={`/entities/${e.id}`} className="group">
          <Card className="overflow-hidden h-full group-hover:shadow-md transition-shadow">
            <CardContent className="p-4 space-y-3">
              <div className="flex items-start gap-3">
                <div className="h-11 w-11 rounded-lg bg-aspora-100 grid place-items-center text-aspora-700 font-bold text-sm shrink-0">
                  {userInitials(e.name)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold truncate group-hover:text-aspora-700">{e.name}</div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                    <JurisdictionBadge code={e.jurisdiction_code} />
                    <span>·</span>
                    <span className="truncate">{e.legal_type}</span>
                  </div>
                </div>
              </div>

              <dl className="grid grid-cols-2 gap-y-1 text-xs">
                <dt className="text-muted-foreground">Reg #</dt>
                <dd className="font-mono text-[11px] truncate">
                  {e.registration_number || "—"}
                </dd>
                <dt className="text-muted-foreground">FYE</dt>
                <dd>{e.fiscal_year_end || "—"}</dd>
                <dt className="text-muted-foreground">Country lead</dt>
                <dd className="truncate">
                  {e.country_lead?.full_name?.split(" ")[0] || "—"}
                </dd>
              </dl>

              <div className="flex items-center gap-1.5 pt-1 border-t border-border">
                <Badge variant="neutral">{e.active_obligations_count} active</Badge>
                {e.overdue_obligations_count > 0 && (
                  <Badge variant="overdue">{e.overdue_obligations_count} overdue</Badge>
                )}
                {e.in_alert_window_count > 0 && (
                  <Badge variant="alert">{e.in_alert_window_count} alert</Badge>
                )}
              </div>
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}


function FilterPopover({
  label,
  options,
  selected,
  onChange,
  searchable,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (next: string[]) => void;
  searchable?: boolean;
}) {
  const [q, setQ] = useState("");
  const visible = q
    ? options.filter((o) => o.label.toLowerCase().includes(q.toLowerCase()))
    : options;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn(
            "h-10",
            selected.length > 0 && "bg-aspora-50 border-aspora-200 text-aspora-800",
          )}
        >
          {label}
          {selected.length > 0 && (
            <Badge variant="default" className="ml-1.5 -mr-1">
              {selected.length}
            </Badge>
          )}
          <ChevronDown className="h-3.5 w-3.5 ml-1" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-60 p-0">
        {searchable && (
          <div className="border-b border-border p-2">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search…"
              className="h-8"
              autoFocus
            />
          </div>
        )}
        <div className="max-h-60 overflow-auto scrollbar-thin py-1">
          {visible.length === 0 ? (
            <div className="px-3 py-3 text-xs text-muted-foreground text-center">No matches</div>
          ) : (
            visible.map((o) => {
              const checked = selected.includes(o.value);
              return (
                <button
                  key={o.value}
                  onClick={() =>
                    onChange(
                      checked ? selected.filter((v) => v !== o.value) : [...selected, o.value],
                    )
                  }
                  className="w-full text-left px-2 py-1.5 hover:bg-secondary flex items-center gap-2 text-sm"
                >
                  <Checkbox checked={checked} readOnly />
                  <span className="truncate">{o.label}</span>
                </button>
              );
            })
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
