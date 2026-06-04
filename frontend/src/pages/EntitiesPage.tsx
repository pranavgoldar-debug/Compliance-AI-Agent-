// Entities — every Aspora legal entity. Table + Card grid toggle, multi-select
// filters, search by name/type/reg #.
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ChevronDown,
  LayoutGrid,
  List,
  Lock,
  Plus,
  Search,
  Building2,
  Trash2,
} from "lucide-react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent } from "@/components/ui/card";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { EmptyState } from "@/components/EmptyState";
import { ExportMenu } from "@/components/ExportMenu";
import { PageHeader } from "@/components/PageHeader";
import { fmtRelative, userInitials, JURISDICTIONS, jurisdiction } from "@/lib/format";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";
import type { Entity } from "@/types/api";


type ViewMode = "table" | "grid";


export function EntitiesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const queryClient = useQueryClient();
  const deleteMany = useMutation({
    mutationFn: (ids: number[]) =>
      Promise.all(ids.map((id) => api.delete(`/api/entities/${id}`))),
    onSuccess: (_r, ids) => {
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      window.alert(`Deleted ${ids.length} entity(ies).`);
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });
  const [q, setQ] = useState("");
  const [jurisdictions, setJurisdictions] = useState<string[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [view, setView] = useState<ViewMode>("table");

  const { data, isLoading } = useQuery({
    queryKey: ["entities"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
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
    return arr;
  }, [data, q, jurisdictions, types]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Entities"
        description="Every Aspora legal entity, with active obligation counts."
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
        <TableView
          entities={filtered}
          isAdmin={isAdmin}
          deleting={deleteMany.isPending}
          onDeleteMany={(ids) => {
            if (
              window.confirm(
                `Permanently delete ${ids.length} selected entity(ies) and everything tied to them (licenses, filings)? This can't be undone.`,
              )
            ) {
              deleteMany.mutate(ids);
            }
          }}
        />
      ) : (
        <GridView entities={filtered} />
      )}
    </div>
  );
}


type SortKey =
  | "jurisdiction"
  | "name"
  | "type"
  | "active"
  | "overdue"
  | "due_soon"
  | "last";

function TableView({
  entities,
  isAdmin,
  deleting,
  onDeleteMany,
}: {
  entities: Entity[];
  isAdmin: boolean;
  deleting: boolean;
  onDeleteMany: (ids: number[]) => void;
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  // Click a column header to sort; click again to flip direction. Defaults to
  // jurisdiction so you can eyeball all entities of one country together.
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({
    key: "jurisdiction",
    dir: "asc",
  });
  const toggleSort = (key: SortKey) =>
    setSort((s) =>
      s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" },
    );

  const sorted = useMemo(() => {
    const dir = sort.dir === "asc" ? 1 : -1;
    const val = (e: Entity): string | number => {
      switch (sort.key) {
        case "jurisdiction":
          return jurisdiction(e.jurisdiction_code).name;
        case "name":
          return e.name.toLowerCase();
        case "type":
          return e.legal_type.toLowerCase();
        case "active":
          return e.active_obligations_count;
        case "overdue":
          return e.overdue_obligations_count;
        case "due_soon":
          return e.in_alert_window_count;
        case "last":
          return e.last_filed_at ? new Date(e.last_filed_at).getTime() : 0;
      }
    };
    return [...entities].sort((a, b) => {
      const av = val(a);
      const bv = val(b);
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return a.name.localeCompare(b.name);
    });
  }, [entities, sort]);

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  const allSelected = entities.length > 0 && entities.every((e) => selected.has(e.id));
  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(entities.map((e) => e.id)));
  const selectedIds = entities.filter((e) => selected.has(e.id)).map((e) => e.id);

  const SortTh = ({
    label,
    sortKey,
    align = "left",
    title,
  }: {
    label: string;
    sortKey: SortKey;
    align?: "left" | "right";
    title?: string;
  }) => (
    <th
      className={cn(
        "px-4 py-2.5 font-medium cursor-pointer select-none hover:text-foreground",
        align === "right" ? "text-right" : "text-left",
      )}
      onClick={() => toggleSort(sortKey)}
      title={title}
    >
      <span className={cn("inline-flex items-center gap-1", align === "right" && "flex-row-reverse")}>
        {label}
        {sort.key === sortKey && (
          <ChevronDown
            className={cn("h-3 w-3 transition-transform", sort.dir === "asc" && "rotate-180")}
          />
        )}
      </span>
    </th>
  );

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      {isAdmin && selectedIds.length > 0 && (
        <div className="flex items-center justify-between gap-2 px-4 py-2 border-b border-border bg-secondary/30">
          <span className="text-sm">{selectedIds.length} selected</span>
          <Button
            size="sm"
            variant="outline"
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
            disabled={deleting}
            onClick={() => onDeleteMany(selectedIds)}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete selected
          </Button>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[900px]">
          <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              {isAdmin && (
                <th className="px-3 py-2.5 w-8">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    className="accent-aspora-600"
                  />
                </th>
              )}
              <SortTh label="Jurisdiction" sortKey="jurisdiction" />
              <SortTh label="Entity" sortKey="name" />
              <SortTh label="Type" sortKey="type" />
              <th className="px-4 py-2.5 text-left font-medium">Fiscal YE</th>
              <SortTh label="Active" sortKey="active" align="right" />
              <SortTh label="Overdue" sortKey="overdue" align="right" />
              <SortTh
                label="Due soon"
                sortKey="due_soon"
                align="right"
                title="Obligations due within the next few weeks (approaching their deadline)."
              />
              <SortTh label="Last activity" sortKey="last" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sorted.map((e) => (
              <tr
                key={e.id}
                className="hover:bg-secondary/30 cursor-pointer"
                onClick={() => {
                  window.location.href = `/entities/${e.id}`;
                }}
              >
                {isAdmin && (
                  <td
                    className="px-3 py-2.5"
                    onClick={(ev) => ev.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(e.id)}
                      onChange={() => toggle(e.id)}
                      className="accent-aspora-600"
                    />
                  </td>
                )}
                <td className="px-4 py-2.5">
                  <JurisdictionBadge code={e.jurisdiction_code} />
                </td>
                <td className="px-4 py-2.5">
                  <Link
                    to={`/entities/${e.id}`}
                    className="flex items-center gap-3 min-w-0 hover:text-aspora-700"
                  >
                    <div className="h-8 w-8 rounded-lg bg-aspora-100 grid place-items-center text-aspora-700 font-semibold text-[10px] shrink-0">
                      {e.short_code || userInitials(e.name)}
                    </div>
                    <div className="font-medium truncate">{e.name}</div>
                  </Link>
                </td>
                <td className="px-4 py-2.5 text-muted-foreground">{e.legal_type}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{e.fiscal_year_end || "—"}</td>
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
                <dt className="text-muted-foreground">FYE</dt>
                <dd>{e.fiscal_year_end || "—"}</dd>
              </dl>

              <div className="flex items-center gap-1.5 pt-1 border-t border-border">
                <Badge variant="neutral">{e.active_obligations_count} active</Badge>
                {e.overdue_obligations_count > 0 && (
                  <Badge variant="overdue">{e.overdue_obligations_count} overdue</Badge>
                )}
                {e.in_alert_window_count > 0 && (
                  <Badge variant="alert">{e.in_alert_window_count} due soon</Badge>
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
