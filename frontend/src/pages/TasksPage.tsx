// Tasks — personal work inbox. Urgency-grouped, sub-tabbed scope, filter bar,
// sort dropdown, hover quick actions.
import { useMemo, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Coffee, ChevronDown, MoreHorizontal, CheckCircle2, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { StatusPill } from "@/components/StatusPill";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { EffortBandBadge } from "@/components/EffortBandBadge";
import { AssigneeChip } from "@/components/AssigneeChip";
import { EmptyState } from "@/components/EmptyState";
import { ExportMenu } from "@/components/ExportMenu";
import { PageHeader } from "@/components/PageHeader";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";
import { useAuth } from "@/contexts/AuthContext";
import { fmtShortDate } from "@/lib/format";
import { jurisdictionOptionsInUse } from "@/lib/countries";
import { cn } from "@/lib/utils";
import type { Entity, Obligation, ObligationStatus, UserBrief } from "@/types/api";

type Scope = "assigned" | "unassigned" | "watching" | "completed" | "all";
type SortKey = "due_date" | "recently_updated" | "priority";

const SCOPES: { key: Scope; label: string }[] = [
  { key: "assigned", label: "Assigned to me" },
  { key: "unassigned", label: "Unassigned" },
  { key: "completed", label: "Completed" },
  { key: "all", label: "All" },
];

// Open work nobody owns yet — the slice the dashboard's Unassigned tile
// deep-links to (/tasks?scope=unassigned). Derived client-side from scope=all.
const isUnassigned = (o: Obligation) =>
  !o.assignee && o.status !== "completed" && o.status !== "not_applicable";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "due_date", label: "Due date (default)" },
  { key: "recently_updated", label: "Recently updated" },
  { key: "priority", label: "Priority" },
];


// Priority order — overdue first, then alert window, then by due date.
function priorityScore(o: Obligation): number {
  if (o.is_overdue) return -10000 + o.days_remaining; // more negative = more urgent
  if (o.is_in_alert_window) return -5000 + o.days_remaining;
  if (o.status === "completed") return 100000;
  return o.days_remaining;
}


interface Filters {
  entityIds: number[];
  jurisdictions: string[];
  statuses: ObligationStatus[];
  dueWithinDays: number | null;
}

function emptyFilters(): Filters {
  return { entityIds: [], jurisdictions: [], statuses: [], dueWithinDays: null };
}


function groupByUrgency(tasks: Obligation[]): Record<string, Obligation[]> {
  const groups: Record<string, Obligation[]> = {
    Overdue: [],
    "In alert window": [],
    "In progress": [],
    Upcoming: [],
    Completed: [],
  };
  for (const t of tasks) {
    if (t.status === "completed") groups.Completed.push(t);
    else if (t.is_overdue) groups.Overdue.push(t);
    else if (t.is_in_alert_window) groups["In alert window"].push(t);
    else if (t.status === "in_progress" || t.status === "pending_review")
      groups["In progress"].push(t);
    else groups.Upcoming.push(t);
  }
  return groups;
}


function TaskRow({ ob }: { ob: Obligation }) {
  const { openObligation } = useObligationDrawer();
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => openObligation(ob.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter") openObligation(ob.id);
      }}
      className="group w-full grid grid-cols-[1.4fr_2fr_120px_140px_minmax(150px,1fr)] gap-4 px-4 py-3 items-center hover:bg-secondary/40 transition-colors text-sm cursor-pointer"
    >
      <div className="flex items-center gap-2 min-w-0">
        <JurisdictionBadge code={ob.entity_jurisdiction_code} showName={false} />
        <div className="min-w-0">
          <div className="font-medium truncate">{ob.entity_name}</div>
          <div className="text-xs text-muted-foreground truncate">{ob.rule_authority}</div>
        </div>
      </div>
      <div className="min-w-0">
        <div className="truncate font-medium">{ob.rule_form_name}</div>
        <div className="text-xs text-muted-foreground truncate">
          {ob.rule_category} · {ob.period_label || ob.rule_frequency}
        </div>
      </div>
      <div className="tabular-nums">{fmtShortDate(ob.due_date)}</div>
      <StatusPill
        status={ob.status}
        isOverdue={ob.is_overdue}
        daysRemaining={ob.days_remaining}
        showDays
      />

      <div className="flex items-center justify-end gap-1.5 min-w-0">
        <AssigneeChip user={ob.assignee} size="sm" showName />
        <RowQuickActions ob={ob} />
      </div>
    </div>
  );
}


function RowQuickActions({ ob }: { ob: Obligation }) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserBrief[]>("/api/users"),
    enabled: isAdmin,
  });

  const mutation = useMutation({
    mutationFn: (patch: Partial<Obligation>) =>
      api.patch<Obligation>(`/api/obligations/${ob.id}`, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["entity-obligations"] });
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      queryClient.invalidateQueries({ queryKey: ["sidebar-task-count"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  return (
    <div onClick={(e) => e.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className="h-7 w-7 grid place-items-center rounded-md hover:bg-secondary text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <MoreHorizontal className="h-3.5 w-3.5" />
            )}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            onClick={() => mutation.mutate({ status: "completed" } as Partial<Obligation>)}
            disabled={ob.status === "completed"}
          >
            <CheckCircle2 className="h-3.5 w-3.5 mr-2" />
            Mark as filed
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() =>
              mutation.mutate({ status: "in_progress" } as Partial<Obligation>)
            }
            disabled={ob.status === "in_progress"}
          >
            Mark in progress
          </DropdownMenuItem>
          {isAdmin && (
            <>
              <DropdownMenuLabel className="mt-1 text-[10px] uppercase tracking-wider">
                Reassign to
              </DropdownMenuLabel>
              {users.slice(0, 6).map((u) => (
                <DropdownMenuItem
                  key={u.id}
                  onClick={() =>
                    mutation.mutate({ assignee_id: u.id } as unknown as Partial<Obligation>)
                  }
                  disabled={ob.assignee?.id === u.id}
                >
                  {u.full_name || u.email}
                </DropdownMenuItem>
              ))}
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}


function GroupSection({ title, items }: { title: string; items: Obligation[] }) {
  if (items.length === 0) return null;
  const tone =
    title === "Overdue"
      ? "overdue"
      : title === "In alert window"
        ? "alert"
        : title === "Completed"
          ? "completed"
          : title === "In progress"
            ? "progress"
            : "neutral";
  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-secondary/30">
        <Badge variant={tone as never}>{title}</Badge>
        <span className="text-xs text-muted-foreground tabular-nums">
          {items.length} item{items.length === 1 ? "" : "s"}
        </span>
      </div>
      {/* Column headers — same grid template as TaskRow. */}
      <div className="grid grid-cols-[1.4fr_2fr_120px_140px_minmax(150px,1fr)] gap-4 px-4 py-2 items-center text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border bg-secondary/10">
        <div>Entity / Authority</div>
        <div>Obligation</div>
        <div>Due</div>
        <div>Status</div>
        <div className="text-right">Assignee</div>
      </div>
      <div className="divide-y divide-border">
        {items.map((ob) => (
          <TaskRow key={ob.id} ob={ob} />
        ))}
      </div>
    </div>
  );
}


// The Department enum on the backend still includes legal / risk / operations
// for future use, but the only two we surface today are compliance + finance
// since that's where the actual hand-off happens.
type DepartmentFilter = "all" | "compliance" | "finance";

const DEPT_LABEL: Record<DepartmentFilter, string> = {
  all: "All departments",
  compliance: "Compliance",
  finance: "Finance",
};

interface TasksPageProps {
  /** When set, the page opens pre-filtered to that department. The /compliance
      route renders TasksPage with defaultDepartment="compliance". */
  defaultDepartment?: DepartmentFilter;
  /** When true, the page opens with the Awaiting payment filter on. The
      /finance route renders TasksPage with defaultAwaitingPayment=true. */
  defaultAwaitingPayment?: boolean;
}

export function TasksPage({
  defaultDepartment,
  defaultAwaitingPayment,
}: TasksPageProps = {}) {
  const { user: me } = useAuth();
  const userId = me?.id ?? null;
  const [department, setDepartment] = useState<DepartmentFilter>(
    defaultDepartment ?? "all",
  );
  // Initial Awaiting-payment state: prop wins, then ?awaiting_payment=1
  // query param (for old links), else off.
  const initialAwaitingPayment =
    defaultAwaitingPayment ??
    (typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("awaiting_payment") === "1");
  const [awaitingPayment, setAwaitingPayment] = useState<boolean>(
    Boolean(initialAwaitingPayment),
  );
  // ?status=pending_review (etc) pre-seeds the status filter so dashboard
  // tile links land users in the right slice.
  const initialFilters: Filters = (() => {
    const base = emptyFilters();
    if (typeof window === "undefined") return base;
    const raw = new URLSearchParams(window.location.search).get("status");
    if (!raw) return base;
    const valid: ObligationStatus[] = [
      "not_started",
      "in_progress",
      "pending_review",
      "completed",
      "not_applicable",
    ];
    const seeded = raw
      .split(",")
      .filter((s): s is ObligationStatus =>
        valid.includes(s as ObligationStatus),
      );
    return { ...base, statuses: seeded };
  })();
  // ?scope=<tab> deep-links straight to that tab — the dashboard's Unassigned
  // tile uses ?scope=unassigned, the "needs attention" banner uses ?scope=all.
  // Otherwise, when the user arrives with a URL pre-filter (status or
  // awaiting-payment), default scope to "all" so they see every match, not just
  // their own assignments.
  const initialScope: Scope = (() => {
    const s =
      typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("scope")
        : null;
    if (s === "assigned" || s === "unassigned" || s === "completed" || s === "all")
      return s;
    return initialFilters.statuses.length > 0 || initialAwaitingPayment ? "all" : "assigned";
  })();
  const [scope, setScope] = useState<Scope>(initialScope);
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [sortKey, setSortKey] = useState<SortKey>("due_date");

  const { data: rawData, isLoading, isFetching } = useQuery({
    queryKey: ["tasks", scope, department, awaitingPayment],
    queryFn: () => {
      // The API has no unassigned scope — fetch everything and slice client-side.
      const qs = new URLSearchParams({ scope: scope === "unassigned" ? "all" : scope });
      if (department !== "all") qs.set("department", department);
      if (awaitingPayment) qs.set("awaiting_payment", "1");
      return api.get<Obligation[]>(`/api/tasks?${qs.toString()}`);
    },
    // Poll every 30s so admins see employee status changes (submit-for-
    // review, in-progress) without manually refreshing.
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    // Keep the previously-loaded list visible while the new query runs.
    // Switching tabs (Assigned to me → Completed) no longer blanks the
    // page to a skeleton — the old list stays put with a subtle "fetching"
    // indicator instead.
    placeholderData: keepPreviousData,
  });
  // Unassigned scope slices the all-fetch down to ownerless open work.
  const data = useMemo(
    () => (scope === "unassigned" ? rawData?.filter(isUnassigned) : rawData),
    [rawData, scope],
  );
  const { data: entities = [] } = useQuery({
    queryKey: ["entities"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
  });

  // Always-on counts for the 4 scope tabs (Assigned / Watching / Completed
  // / All). Single fetch of scope=all + a derive — way cheaper than 4
  // parallel queries and the numbers stay consistent. Falls back to the
  // currently-loaded data while the all-fetch is in flight.
  const allTasksQuery = useQuery({
    queryKey: ["tasks", "all", "counts"],
    queryFn: () => api.get<Obligation[]>("/api/tasks?scope=all"),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    staleTime: 15_000,
  });
  const scopeCounts: Record<Scope, number | null> = useMemo(() => {
    const all = allTasksQuery.data;
    if (!all) {
      // Pre-fill the active scope from `data` so the user sees at least
      // one number immediately on first load.
      return {
        assigned: scope === "assigned" ? data?.length ?? null : null,
        unassigned: scope === "unassigned" ? data?.length ?? null : null,
        watching: scope === "watching" ? data?.length ?? null : null,
        completed: scope === "completed" ? data?.length ?? null : null,
        all: scope === "all" ? data?.length ?? null : null,
      };
    }
    const meId = userId;
    return {
      assigned: all.filter(
        (o) =>
          o.assignee?.id === meId &&
          o.status !== "completed" &&
          o.status !== "not_applicable",
      ).length,
      unassigned: all.filter(isUnassigned).length,
      // Watching needs the comment-author list — we don't have that on
      // the client. Best approximation: items where I'm the assignee OR
      // I'm tagged in payment_reference (rare). Leave as the active fetch.
      watching: scope === "watching" ? data?.length ?? null : null,
      completed: all.filter((o) => o.status === "completed").length,
      all: all.length,
    };
  }, [allTasksQuery.data, data, scope, userId]);

  // Apply filters + sort.
  const visible = useMemo(() => {
    let arr = data ?? [];
    if (filters.entityIds.length)
      arr = arr.filter((o) => filters.entityIds.includes(o.entity_id));
    if (filters.jurisdictions.length)
      arr = arr.filter((o) => filters.jurisdictions.includes(o.entity_jurisdiction_code));
    if (filters.statuses.length)
      arr = arr.filter((o) => filters.statuses.includes(o.status));
    if (filters.dueWithinDays != null)
      arr = arr.filter(
        (o) => o.days_remaining <= (filters.dueWithinDays as number) && o.days_remaining >= 0,
      );

    const dir = 1;
    arr = [...arr].sort((a, b) => {
      switch (sortKey) {
        case "recently_updated":
          return dir * b.updated_at.localeCompare(a.updated_at);
        case "priority":
          return dir * (priorityScore(a) - priorityScore(b));
        default:
          return dir * a.due_date.localeCompare(b.due_date);
      }
    });
    return arr;
  }, [data, filters, sortKey]);

  const groups = visible ? groupByUrgency(visible) : null;
  const activeFilterCount =
    filters.entityIds.length +
    filters.jurisdictions.length +
    filters.statuses.length +
    (filters.dueWithinDays != null ? 1 : 0);

  // Header copy. The page is a single combined "Compliance & Finance"
  // queue — scope tabs + filters are how teams slice their own work
  // without us splitting them into separate pages.
  const pageTitle = "Filings";
  const pageDescription =
    "Your filing queue — every obligation generated from the licenses you track.";

  return (
    <div className="space-y-5">
      <PageHeader
        title={pageTitle}
        description={pageDescription}
        actions={<ExportMenu kind="obligations" />}
      />

      <Tabs value={scope} onValueChange={(v) => setScope(v as Scope)}>
        <TabsList>
          {SCOPES.map((s) => {
            const n = scopeCounts[s.key];
            return (
              <TabsTrigger key={s.key} value={s.key}>
                {s.label}
                {n != null && (
                  <span className="ml-1.5 text-xs text-muted-foreground tabular-nums">
                    ({n})
                  </span>
                )}
              </TabsTrigger>
            );
          })}
        </TabsList>
      </Tabs>

      {/* Filter + sort bar */}
      <div className="flex flex-wrap items-center gap-2">
        <FilterPopover
          label="Entity"
          options={entities.map((e) => ({ value: String(e.id), label: e.name }))}
          selected={filters.entityIds.map(String)}
          onChange={(vals) =>
            setFilters((f) => ({ ...f, entityIds: vals.map((v) => Number(v)) }))
          }
          searchable
        />
        <FilterPopover
          label="Jurisdiction"
          options={jurisdictionOptionsInUse(entities.map((e) => e.jurisdiction_code)).map(
            (o) => ({ value: o.value, label: o.name }),
          )}
          selected={filters.jurisdictions}
          onChange={(vals) => setFilters((f) => ({ ...f, jurisdictions: vals }))}
        />
        <FilterPopover
          label="Status"
          options={[
            { value: "not_started", label: "Not started" },
            { value: "in_progress", label: "In progress" },
            { value: "pending_review", label: "Pending review" },
            { value: "completed", label: "Completed" },
          ]}
          selected={filters.statuses}
          onChange={(vals) => setFilters((f) => ({ ...f, statuses: vals as ObligationStatus[] }))}
        />
        <DueRangePopover
          value={filters.dueWithinDays}
          onChange={(v) => setFilters((f) => ({ ...f, dueWithinDays: v }))}
        />
        {/* The Awaiting-payment chip is gone, but ?awaiting_payment=1 links
            (legacy /finance redirect) still pre-filter; surface an off
            switch only while that hidden filter is active. */}
        {awaitingPayment && (
          <button
            type="button"
            onClick={() => setAwaitingPayment(false)}
            className="inline-flex items-center gap-1.5 rounded-full border px-3 h-8 text-xs transition-colors border-amber-300 bg-amber-50 text-amber-800 font-medium"
            title="Showing only filings whose payment leg is still open — click to clear"
          >
            Awaiting payment ✕
          </button>
        )}
        {activeFilterCount > 0 && (
          <button
            onClick={() => setFilters(emptyFilters())}
            className="text-xs text-aspora-700 hover:underline ml-1"
          >
            Clear ({activeFilterCount})
          </button>
        )}

        <div className="ml-auto inline-flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Sort:</span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                {SORTS.find((s) => s.key === sortKey)!.label}
                <ChevronDown className="h-3.5 w-3.5 ml-1" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {SORTS.map((s) => (
                <DropdownMenuItem
                  key={s.key}
                  onClick={() => setSortKey(s.key)}
                  className={cn(sortKey === s.key && "bg-aspora-50")}
                >
                  {s.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : !visible || visible.length === 0 ? (
        <Card>
          <div className="p-10">
            <EmptyState
              icon={<Coffee className="h-6 w-6" />}
              title={
                scope === "assigned"
                  ? "Nothing on your plate"
                  : scope === "unassigned"
                    ? "Everything has an owner"
                    : scope === "completed"
                      ? "No completed items yet"
                      : "All caught up"
              }
              description={
                scope === "assigned"
                  ? "All caught up. Time for a coffee."
                  : scope === "unassigned"
                    ? "Every open filing is assigned to someone."
                    : scope === "watching"
                      ? "Comment on or open an obligation to start watching it."
                      : "No tasks match the current filters."
              }
            />
          </div>
        </Card>
      ) : (
        <div className="space-y-4">
          {groups &&
            ["Overdue", "In alert window", "In progress", "Upcoming", "Completed"].map((g) => (
              <GroupSection key={g} title={g} items={groups[g]} />
            ))}
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Filter popover helpers
// ---------------------------------------------------------------------------
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
          {visible.map((o) => {
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
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}


function DueRangePopover({
  value,
  onChange,
}: {
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  const PRESETS = [
    { v: 7, label: "Next 7 days" },
    { v: 14, label: "Next 14 days" },
    { v: 30, label: "Next 30 days" },
    { v: 90, label: "Next 90 days" },
  ];
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn(value != null && "bg-aspora-50 border-aspora-200 text-aspora-800")}
        >
          Due date
          {value != null && (
            <Badge variant="default" className="ml-1.5 -mr-1">
              {value}d
            </Badge>
          )}
          <ChevronDown className="h-3.5 w-3.5 ml-1" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-44 p-1">
        {PRESETS.map((p) => (
          <button
            key={p.v}
            onClick={() => onChange(p.v === value ? null : p.v)}
            className={cn(
              "w-full text-left px-2 py-1.5 rounded-md text-sm hover:bg-secondary",
              value === p.v && "bg-aspora-50 text-aspora-700",
            )}
          >
            {p.label}
          </button>
        ))}
        {value != null && (
          <button
            onClick={() => onChange(null)}
            className="w-full text-left px-2 py-1.5 rounded-md text-xs text-aspora-700 hover:underline mt-1"
          >
            Clear
          </button>
        )}
      </PopoverContent>
    </Popover>
  );
}
