// Compliance Calendar — heatmap month grid OR flat list view, with sticky
// multi-select filter bar, date-range picker (month / quarter / custom up to
// 92 days), bulk actions, and a right-rail detail panel.
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addDays,
  addMonths,
  differenceInCalendarDays,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  parseISO,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import {
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  LayoutGrid,
  List,
  Loader2,
  Search,
  UserCheck,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { StatusPill } from "@/components/StatusPill";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { AssigneeChip } from "@/components/AssigneeChip";
import { EmptyState } from "@/components/EmptyState";
import { ExportMenu } from "@/components/ExportMenu";
import { InlineStatusMenu } from "@/components/InlineStatusMenu";
import { PageHeader } from "@/components/PageHeader";
import { JURISDICTIONS, fmtDate, cleanFilingName } from "@/lib/format";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";
import { cn } from "@/lib/utils";
import type {
  BulkUpdateResult,
  CalendarObligation,
  Entity,
  ObligationStatus,
  UserBrief,
} from "@/types/api";


// ---------------------------------------------------------------------------
// Filter state types + constants
// ---------------------------------------------------------------------------
type RangeKind = "month" | "quarter" | "custom";
type ViewMode = "heatmap" | "list";

const STATUS_OPTIONS: { value: ObligationStatus; label: string }[] = [
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "pending_review", label: "Pending review" },
  { value: "completed", label: "Completed" },
  { value: "not_applicable", label: "N/A" },
];

const TAX_TYPES = ["Direct Tax", "Indirect Tax", "Not a Tax"];
const APPLICABILITIES = ["Mandatory", "Conditional", "Sector-specific"];


interface Filters {
  entityIds: number[];
  jurisdictions: string[];
  taxTypes: string[];
  applicabilities: string[];
  authorities: string[];
  categories: string[];
  statuses: ObligationStatus[];
  assigneeIds: number[];
}


function emptyFilters(): Filters {
  return {
    entityIds: [],
    jurisdictions: [],
    taxTypes: [],
    applicabilities: [],
    authorities: [],
    categories: [],
    statuses: [],
    assigneeIds: [],
  };
}


// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export function CalendarPage() {
  const [rangeKind, setRangeKind] = useState<RangeKind>("month");
  const [cursor, setCursor] = useState(new Date());
  const [customStart, setCustomStart] = useState<Date>(new Date());
  const [customEnd, setCustomEnd] = useState<Date>(addDays(new Date(), 30));
  const [filters, setFilters] = useState<Filters>(emptyFilters());
  const [viewMode, setViewMode] = useState<ViewMode>("heatmap");
  const [selected, setSelected] = useState<Date>(new Date());

  // Resolve current range.
  const { start, end } = useMemo(() => {
    if (rangeKind === "custom") {
      const span = differenceInCalendarDays(customEnd, customStart);
      const cappedEnd = span > 92 ? addDays(customStart, 92) : customEnd;
      return { start: customStart, end: cappedEnd };
    }
    if (rangeKind === "quarter") {
      const s = startOfMonth(cursor);
      return { start: s, end: addDays(s, 90) };
    }
    // Month — show grid-aligned weeks for visual coherence.
    const ms = startOfMonth(cursor);
    const me = endOfMonth(cursor);
    return {
      start: startOfWeek(ms, { weekStartsOn: 1 }),
      end: endOfWeek(me, { weekStartsOn: 1 }),
    };
  }, [rangeKind, cursor, customStart, customEnd]);

  // ---------------------------------------------------------------------
  // Data — calendar + supporting lookups for filters
  // ---------------------------------------------------------------------
  const { data: entities = [] } = useQuery({
    queryKey: ["entities"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
  });
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserBrief[]>("/api/users"),
  });

  const { data: items = [], isLoading } = useQuery({
    queryKey: [
      "calendar",
      format(start, "yyyy-MM-dd"),
      format(end, "yyyy-MM-dd"),
      filters,
    ],
    queryFn: () => {
      const params = new URLSearchParams({
        start: format(start, "yyyy-MM-dd"),
        end: format(end, "yyyy-MM-dd"),
      });
      filters.entityIds.forEach((id) => params.append("entity_ids", String(id)));
      filters.jurisdictions.forEach((j) => params.append("jurisdiction_codes", j));
      filters.taxTypes.forEach((t) => params.append("tax_types", t));
      filters.statuses.forEach((s) => params.append("statuses", s));
      filters.assigneeIds.forEach((id) => params.append("assignee_ids", String(id)));
      return api.get<CalendarObligation[]>(`/api/calendar?${params.toString()}`);
    },
    refetchOnWindowFocus: true,
    refetchInterval: 60_000,
  });

  const activeFilterCount =
    filters.entityIds.length +
    filters.jurisdictions.length +
    filters.taxTypes.length +
    filters.applicabilities.length +
    filters.authorities.length +
    filters.categories.length +
    filters.statuses.length +
    filters.assigneeIds.length;

  // Distinct authorities + categories present in the loaded range — drive the
  // Authority / Category filter options. Derived from the server-fetched items
  // (before client-side filtering) so options never disappear as you select.
  const authorityOptions = useMemo(() => {
    const set = new Set<string>();
    for (const o of items) if (o.rule_authority) set.add(o.rule_authority);
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [items]);

  const categoryOptions = useMemo(() => {
    const set = new Set<string>();
    for (const o of items) if (o.rule_category) set.add(o.rule_category);
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [items]);

  // Applicability + Authority + Category filters, applied client-side on
  // already-loaded data. Empty = show all.
  const filteredItems = useMemo(() => {
    let out = items;
    if (filters.applicabilities.length > 0) {
      const set = new Set(filters.applicabilities);
      out = out.filter((o) => set.has(o.rule_applicability));
    }
    if (filters.authorities.length > 0) {
      const set = new Set(filters.authorities);
      out = out.filter((o) => set.has(o.rule_authority));
    }
    if (filters.categories.length > 0) {
      const set = new Set(filters.categories);
      out = out.filter((o) => set.has(o.rule_category));
    }
    return out;
  }, [items, filters.applicabilities, filters.authorities, filters.categories]);

  // Build a date -> obligations map for the heatmap.
  const byDate = useMemo(() => {
    const map = new Map<string, CalendarObligation[]>();
    for (const ob of filteredItems) {
      if (!map.has(ob.due_date)) map.set(ob.due_date, []);
      map.get(ob.due_date)!.push(ob);
    }
    return map;
  }, [filteredItems]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Compliance Calendar"
        description="Every obligation across every entity. Heatmap to triage, list to scan."
        actions={
          <div className="flex items-center gap-2">
            <DateRangeControl
              rangeKind={rangeKind}
              onChangeRangeKind={setRangeKind}
              cursor={cursor}
              onCursorChange={setCursor}
              customStart={customStart}
              customEnd={customEnd}
              onCustomChange={(s, e) => {
                setCustomStart(s);
                setCustomEnd(e);
              }}
            />
            <div className="inline-flex rounded-lg border border-input overflow-hidden">
              <button
                onClick={() => setViewMode("heatmap")}
                className={cn(
                  "h-9 px-3 text-sm inline-flex items-center gap-1.5",
                  viewMode === "heatmap"
                    ? "bg-aspora-600 text-white"
                    : "bg-background hover:bg-secondary",
                )}
              >
                <LayoutGrid className="h-3.5 w-3.5" />
                Heatmap
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={cn(
                  "h-9 px-3 text-sm inline-flex items-center gap-1.5 border-l border-input",
                  viewMode === "list"
                    ? "bg-aspora-600 text-white"
                    : "bg-background hover:bg-secondary",
                )}
              >
                <List className="h-3.5 w-3.5" />
                List
              </button>
            </div>
            <ExportMenu
              kind="obligations"
              params={{
                due_from: format(start, "yyyy-MM-dd"),
                due_to: format(end, "yyyy-MM-dd"),
                jurisdiction_code:
                  filters.jurisdictions.length === 1 ? filters.jurisdictions[0] : undefined,
              }}
            />
          </div>
        }
      />

      {/* Sticky filter bar */}
      <div className="sticky top-0 z-20 bg-secondary -mx-8 px-8 py-3 border-b border-border shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          <MultiSelectFilter
            label="Entity"
            options={entities.map((e) => ({ value: String(e.id), label: e.name }))}
            selected={filters.entityIds.map(String)}
            onChange={(vals) =>
              setFilters((f) => ({ ...f, entityIds: vals.map((v) => Number(v)) }))
            }
            searchable
          />
          <MultiSelectFilter
            label="Jurisdiction"
            options={Object.entries(JURISDICTIONS).map(([code, j]) => ({
              value: code,
              label: `${j.flag} ${j.name}`,
            }))}
            selected={filters.jurisdictions}
            onChange={(vals) => setFilters((f) => ({ ...f, jurisdictions: vals }))}
          />
          <MultiSelectFilter
            label="Tax type"
            options={TAX_TYPES.map((t) => ({ value: t, label: t }))}
            selected={filters.taxTypes}
            onChange={(vals) => setFilters((f) => ({ ...f, taxTypes: vals }))}
          />
          <MultiSelectFilter
            label="Applicability"
            options={APPLICABILITIES.map((a) => ({ value: a, label: a }))}
            selected={filters.applicabilities}
            onChange={(vals) => setFilters((f) => ({ ...f, applicabilities: vals }))}
          />
          <MultiSelectFilter
            label="Authority"
            options={authorityOptions.map((a) => ({ value: a, label: a }))}
            selected={filters.authorities}
            onChange={(vals) => setFilters((f) => ({ ...f, authorities: vals }))}
            searchable
          />
          <MultiSelectFilter
            label="Category"
            options={categoryOptions.map((c) => ({ value: c, label: c }))}
            selected={filters.categories}
            onChange={(vals) => setFilters((f) => ({ ...f, categories: vals }))}
            searchable
          />
          <MultiSelectFilter
            label="Status"
            options={STATUS_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            selected={filters.statuses}
            onChange={(vals) =>
              setFilters((f) => ({ ...f, statuses: vals as ObligationStatus[] }))
            }
          />
          <MultiSelectFilter
            label="Assignee"
            options={users.map((u) => ({ value: String(u.id), label: u.full_name }))}
            selected={filters.assigneeIds.map(String)}
            onChange={(vals) =>
              setFilters((f) => ({ ...f, assigneeIds: vals.map((v) => Number(v)) }))
            }
            searchable
          />
          {activeFilterCount > 0 && (
            <>
              <Badge variant="default" className="ml-1">
                {activeFilterCount} filter{activeFilterCount === 1 ? "" : "s"}
              </Badge>
              <button
                onClick={() => setFilters(emptyFilters())}
                className="text-xs text-aspora-700 hover:underline ml-1 inline-flex items-center gap-1"
              >
                <X className="h-3 w-3" />
                Clear
              </button>
            </>
          )}
          <div className="ml-auto text-xs text-muted-foreground tabular-nums">
            {filteredItems.length} item{filteredItems.length === 1 ? "" : "s"} in range
          </div>
        </div>
      </div>

      {viewMode === "heatmap" ? (
        <HeatmapView
          cursor={cursor}
          rangeStart={start}
          rangeEnd={end}
          byDate={byDate}
          isLoading={isLoading}
          selected={selected}
          onSelect={setSelected}
          onPrev={() => setCursor(subMonths(cursor, 1))}
          onNext={() => setCursor(addMonths(cursor, 1))}
        />
      ) : (
        <ListView items={filteredItems} isLoading={isLoading} />
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Date range control — popover with month / quarter / custom + nav arrows
// ---------------------------------------------------------------------------
function DateRangeControl({
  rangeKind,
  onChangeRangeKind,
  cursor,
  onCursorChange,
  customStart,
  customEnd,
  onCustomChange,
}: {
  rangeKind: RangeKind;
  onChangeRangeKind: (k: RangeKind) => void;
  cursor: Date;
  onCursorChange: (d: Date) => void;
  customStart: Date;
  customEnd: Date;
  onCustomChange: (s: Date, e: Date) => void;
}) {
  return (
    <div className="flex items-center gap-1">
      {rangeKind !== "custom" && (
        <Button
          variant="outline"
          size="icon"
          onClick={() => onCursorChange(subMonths(cursor, 1))}
          aria-label="Previous"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
      )}
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="min-w-[180px] justify-between">
            {rangeKind === "month"
              ? format(cursor, "MMMM yyyy")
              : rangeKind === "quarter"
                ? `${format(cursor, "MMM yyyy")} → ${format(addDays(cursor, 90), "MMM yyyy")}`
                : `${format(customStart, "d MMM")} → ${format(customEnd, "d MMM")}`}
            <ChevronDown className="h-3.5 w-3.5 ml-1" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-64 p-3 space-y-3">
          <div className="space-y-1">
            <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mb-1">
              Range
            </div>
            {(["month", "quarter", "custom"] as RangeKind[]).map((k) => (
              <button
                key={k}
                onClick={() => onChangeRangeKind(k)}
                className={cn(
                  "block w-full text-left px-2 py-1.5 rounded-md text-sm capitalize",
                  rangeKind === k ? "bg-aspora-50 text-aspora-700" : "hover:bg-secondary",
                )}
              >
                {k}
              </button>
            ))}
          </div>
          {rangeKind === "custom" && (
            <div className="space-y-2 border-t border-border pt-3">
              <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                Custom (max 92 days)
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">Start</label>
                <Input
                  type="date"
                  value={format(customStart, "yyyy-MM-dd")}
                  onChange={(e) =>
                    e.target.value &&
                    onCustomChange(parseISO(e.target.value), customEnd)
                  }
                />
                <label className="text-xs text-muted-foreground mt-1">End</label>
                <Input
                  type="date"
                  value={format(customEnd, "yyyy-MM-dd")}
                  onChange={(e) =>
                    e.target.value &&
                    onCustomChange(customStart, parseISO(e.target.value))
                  }
                />
              </div>
            </div>
          )}
        </PopoverContent>
      </Popover>
      {rangeKind !== "custom" && (
        <>
          <Button
            variant="outline"
            size="icon"
            onClick={() => onCursorChange(addMonths(cursor, 1))}
            aria-label="Next"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onCursorChange(new Date())}>
            Today
          </Button>
        </>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Multi-select filter — simple Popover + checkbox list
// ---------------------------------------------------------------------------
interface MSOption {
  value: string;
  label: string;
}
function MultiSelectFilter({
  label,
  options,
  selected,
  onChange,
  searchable,
}: {
  label: string;
  options: MSOption[];
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
            "h-9",
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
      <PopoverContent className="w-64 p-0">
        {searchable && (
          <div className="border-b border-border p-2">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search…"
                className="w-full h-8 rounded-md border border-input bg-background pl-7 pr-2 text-sm"
                autoFocus
              />
            </div>
          </div>
        )}
        <div className="max-h-64 overflow-auto scrollbar-thin py-1">
          {visible.length === 0 ? (
            <div className="px-3 py-4 text-xs text-muted-foreground text-center">
              No matches.
            </div>
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
        {selected.length > 0 && (
          <div className="border-t border-border p-2">
            <button
              onClick={() => onChange([])}
              className="text-xs text-aspora-700 hover:underline"
            >
              Clear {selected.length} selected
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}


// ---------------------------------------------------------------------------
// Heatmap view
// ---------------------------------------------------------------------------
function dayBadgeTone(items: CalendarObligation[]): string {
  if (items.some((i) => i.is_overdue)) return "bg-red-600 text-white";
  if (items.some((i) => i.is_in_alert_window)) return "bg-amber-500 text-white";
  if (items.some((i) => i.status === "in_progress" || i.status === "pending_review"))
    return "bg-blue-500 text-white";
  if (items.every((i) => i.status === "completed")) return "bg-emerald-500 text-white";
  return "bg-slate-300 text-slate-800";
}


function HeatmapView({
  cursor,
  rangeStart,
  rangeEnd,
  byDate,
  isLoading,
  selected,
  onSelect,
  onPrev,
  onNext,
}: {
  cursor: Date;
  rangeStart: Date;
  rangeEnd: Date;
  byDate: Map<string, CalendarObligation[]>;
  isLoading: boolean;
  selected: Date;
  onSelect: (d: Date) => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  const days: Date[] = [];
  {
    const day = new Date(rangeStart);
    while (day <= rangeEnd) {
      days.push(new Date(day));
      day.setDate(day.getDate() + 1);
    }
  }

  const selectedKey = format(selected, "yyyy-MM-dd");
  const selectedItems = byDate.get(selectedKey) ?? [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
      <Card className="overflow-hidden">
        {/* Inline month switcher header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-secondary/30">
          <button
            onClick={onPrev}
            className="p-1 rounded hover:bg-secondary text-muted-foreground"
            aria-label="Previous month"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <div className="font-semibold text-sm">{format(cursor, "MMMM yyyy")}</div>
          <button
            onClick={onNext}
            className="p-1 rounded hover:bg-secondary text-muted-foreground"
            aria-label="Next month"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        {/* Day-of-week header */}
        <div className="grid grid-cols-7 border-b border-border bg-secondary/20">
          {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
            <div
              key={d}
              className="px-2 py-2 text-[11px] uppercase tracking-wider text-muted-foreground"
            >
              {d}
            </div>
          ))}
        </div>

        {isLoading ? (
          <div className="p-4">
            <Skeleton className="h-96" />
          </div>
        ) : (
          <div
            className="grid grid-cols-7"
            style={{ gridAutoRows: "minmax(96px, 1fr)" }}
          >
            {days.map((day) => {
              const key = format(day, "yyyy-MM-dd");
              const items = byDate.get(key) ?? [];
              const inMonth = isSameMonth(day, cursor);
              const isToday = isSameDay(day, new Date());
              const isSelected = isSameDay(day, selected);
              const tone = items.length ? dayBadgeTone(items) : "";
              return (
                <Tooltip key={key}>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => onSelect(day)}
                      className={cn(
                        "text-left px-2 py-2 border-r border-b border-border transition-colors relative",
                        !inMonth && "bg-secondary/10 text-muted-foreground/70",
                        inMonth && "hover:bg-secondary/40",
                        isSelected && "ring-2 ring-aspora-500 ring-inset",
                      )}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span
                          className={cn(
                            "text-xs font-medium",
                            isToday &&
                              "inline-flex h-5 w-5 items-center justify-center rounded-full bg-aspora-600 text-white",
                          )}
                        >
                          {format(day, "d")}
                        </span>
                        {items.length > 0 && (
                          <span
                            className={cn(
                              "inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-semibold tabular-nums",
                              tone,
                            )}
                          >
                            {items.length}
                          </span>
                        )}
                      </div>
                      <div className="space-y-0.5">
                        {items.slice(0, 2).map((ob) => (
                          <div
                            key={ob.id}
                            className="text-[10px] leading-tight truncate text-muted-foreground"
                          >
                            {ob.entity_name.replace(/^Aspora\s+/, "")} · {cleanFilingName(ob.rule_form_name)}
                          </div>
                        ))}
                        {items.length > 2 && (
                          <div className="text-[10px] text-muted-foreground italic">
                            +{items.length - 2} more
                          </div>
                        )}
                      </div>
                    </button>
                  </TooltipTrigger>
                  {items.length > 0 && (
                    <TooltipContent>
                      <div className="font-semibold mb-1">{format(day, "EEE, d MMM")}</div>
                      {items.slice(0, 5).map((ob) => (
                        <div key={ob.id} className="opacity-90">
                          • {ob.entity_name} — {cleanFilingName(ob.rule_form_name)}
                        </div>
                      ))}
                      {items.length > 5 && (
                        <div className="opacity-70 italic">+{items.length - 5} more</div>
                      )}
                    </TooltipContent>
                  )}
                </Tooltip>
              );
            })}
          </div>
        )}
      </Card>

      <DayDetailPanel date={selected} items={selectedItems} />
    </div>
  );
}


function DayDetailPanel({ date, items }: { date: Date; items: CalendarObligation[] }) {
  const { openObligation } = useObligationDrawer();
  return (
    <Card className="overflow-hidden h-fit sticky top-20">
      <div className="px-4 py-3 border-b border-border">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">
          {format(date, "EEEE")}
        </div>
        <div className="text-lg font-semibold">{format(date, "d MMMM yyyy")}</div>
        <div className="text-xs text-muted-foreground mt-1">
          {items.length} obligation{items.length === 1 ? "" : "s"}
        </div>
      </div>
      <div className="max-h-[520px] overflow-auto scrollbar-thin divide-y divide-border">
        {items.length === 0 ? (
          <div className="p-6 text-center text-sm text-muted-foreground">
            Nothing due on this day.
          </div>
        ) : (
          items.map((ob) => (
            <button
              key={ob.id}
              type="button"
              onClick={() => openObligation(ob.id)}
              className="block w-full text-left px-4 py-3 hover:bg-secondary/40"
            >
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-0.5">
                <JurisdictionBadge code={ob.entity_jurisdiction_code} showName={false} />
                <span className="truncate">{ob.entity_name}</span>
              </div>
              <div className="font-medium text-sm leading-tight truncate">{cleanFilingName(ob.rule_form_name)}</div>
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                <Badge
                  variant={
                    ob.is_overdue ? "overdue" : ob.is_in_alert_window ? "alert" : "neutral"
                  }
                >
                  {ob.is_overdue
                    ? `${Math.abs(ob.days_remaining)}d overdue`
                    : ob.days_remaining === 0
                      ? "Due today"
                      : `${ob.days_remaining}d`}
                </Badge>
                <AssigneeChip user={ob.assignee} size="xs" />
              </div>
            </button>
          ))
        )}
      </div>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// List view — sortable table with bulk select
// ---------------------------------------------------------------------------
type SortKey = "due_date" | "entity" | "rule" | "status" | "days";

function ListView({
  items,
  isLoading,
}: {
  items: CalendarObligation[];
  isLoading: boolean;
}) {
  const { openObligation } = useObligationDrawer();
  const [sortKey, setSortKey] = useState<SortKey>("due_date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [selected, setSelected] = useState<Set<number>>(new Set());

  // Reset selection when the underlying items change identity.
  const itemsRef = useRef(items);
  useEffect(() => {
    if (itemsRef.current !== items) {
      setSelected(new Set());
      itemsRef.current = items;
    }
  }, [items]);

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    return [...items].sort((a, b) => {
      switch (sortKey) {
        case "due_date":
          return dir * a.due_date.localeCompare(b.due_date);
        case "entity":
          return dir * a.entity_name.localeCompare(b.entity_name);
        case "rule":
          return dir * a.rule_form_name.localeCompare(b.rule_form_name);
        case "status":
          return dir * a.status.localeCompare(b.status);
        case "days":
          return dir * (a.days_remaining - b.days_remaining);
      }
    });
  }, [items, sortKey, sortDir]);

  const toggleSort = (k: SortKey) => {
    if (sortKey === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir("asc");
    }
  };

  const allChecked = sorted.length > 0 && sorted.every((o) => selected.has(o.id));
  const someChecked = !allChecked && sorted.some((o) => selected.has(o.id));

  return (
    <>
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[1100px]">
            <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-3 py-2.5 w-8">
                  <Checkbox
                    checked={allChecked}
                    indeterminate={someChecked}
                    onChange={(e) => {
                      const next = new Set(selected);
                      if (e.target.checked) sorted.forEach((o) => next.add(o.id));
                      else sorted.forEach((o) => next.delete(o.id));
                      setSelected(next);
                    }}
                  />
                </th>
                <SortHeader label="Due date" k="due_date" current={sortKey} dir={sortDir} onClick={toggleSort} />
                <SortHeader label="Entity" k="entity" current={sortKey} dir={sortDir} onClick={toggleSort} />
                <SortHeader label="Obligation" k="rule" current={sortKey} dir={sortDir} onClick={toggleSort} />
                <th className="px-3 py-2.5 text-left font-medium">Category</th>
                <SortHeader label="Status" k="status" current={sortKey} dir={sortDir} onClick={toggleSort} />
                <th className="px-3 py-2.5 text-left font-medium">Assignee</th>
                <SortHeader label="Days" k="days" current={sortKey} dir={sortDir} onClick={toggleSort} />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={9} className="p-2">
                      <Skeleton className="h-8" />
                    </td>
                  </tr>
                ))
              ) : sorted.length === 0 ? (
                <tr>
                  <td colSpan={9} className="p-10">
                    <EmptyState
                      title="No filings in selected range"
                      description="Try widening the date range or clearing some filters."
                    />
                  </td>
                </tr>
              ) : (
                sorted.map((ob) => (
                  <tr
                    key={ob.id}
                    className="hover:bg-secondary/30 cursor-pointer"
                    onClick={() => openObligation(ob.id)}
                  >
                    <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selected.has(ob.id)}
                        onChange={(e) => {
                          const next = new Set(selected);
                          if (e.target.checked) next.add(ob.id);
                          else next.delete(ob.id);
                          setSelected(next);
                        }}
                      />
                    </td>
                    <td className="px-3 py-2.5 tabular-nums whitespace-nowrap">
                      {fmtDate(ob.due_date, "d MMM yyyy")}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2 min-w-0">
                        <JurisdictionBadge code={ob.entity_jurisdiction_code} showName={false} />
                        <span className="truncate font-medium">{ob.entity_name}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="font-medium">{cleanFilingName(ob.rule_form_name)}</div>
                      <div className="text-xs text-muted-foreground truncate">{ob.rule_authority}</div>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-wrap items-center gap-1">
                        <Badge variant="neutral">{ob.rule_category}</Badge>
                        {(ob.rule_tax_type === "Direct Tax" ||
                          ob.rule_tax_type === "Indirect Tax") && (
                          <Badge
                            variant={
                              ob.rule_tax_type === "Direct Tax"
                                ? "progress"
                                : "review"
                            }
                          >
                            {ob.rule_tax_type}
                          </Badge>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                          </td>
                    <td className="px-3 py-2.5">
                      <InlineStatusMenu
                        obligationId={ob.id}
                        status={ob.status}
                        isOverdue={ob.is_overdue}
                      />
                    </td>
                    <td className="px-3 py-2.5">
                      <AssigneeChip user={ob.assignee} size="sm" showName />
                    </td>
                    <td className="px-3 py-2.5">
                      <Badge
                        variant={
                          ob.is_overdue ? "overdue" : ob.is_in_alert_window ? "alert" : "neutral"
                        }
                      >
                        {ob.is_overdue
                          ? `${Math.abs(ob.days_remaining)}d overdue`
                          : ob.days_remaining === 0
                            ? "Due today"
                            : `${ob.days_remaining}d`}
                      </Badge>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {selected.size > 0 && (
        <BulkActionBar selected={selected} onClear={() => setSelected(new Set())} />
      )}
    </>
  );
}


// ---------------------------------------------------------------------------
// Bulk action bar — wired to /api/obligations/bulk-update
// ---------------------------------------------------------------------------
function BulkActionBar({
  selected,
  onClear,
}: {
  selected: Set<number>;
  onClear: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserBrief[]>("/api/users"),
  });

  const mutation = useMutation({
    mutationFn: (body: {
      obligation_ids: number[];
      status?: ObligationStatus;
      assignee_id?: number | null;
      clear_assignee?: boolean;
    }) => api.post<BulkUpdateResult>("/api/obligations/bulk-update", body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["entity-obligations"] });
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      queryClient.invalidateQueries({ queryKey: ["sidebar-task-count"] });
      onClear();
    },
  });

  const ids = Array.from(selected);

  function setStatus(status: ObligationStatus) {
    mutation.mutate({ obligation_ids: ids, status });
  }
  function assignTo(userId: number | null) {
    if (userId === null) {
      mutation.mutate({ obligation_ids: ids, clear_assignee: true });
    } else {
      mutation.mutate({ obligation_ids: ids, assignee_id: userId });
    }
  }

  return (
    <div className="sticky bottom-4 z-30 flex justify-center">
      <div className="bg-foreground text-background rounded-full shadow-xl px-4 py-2 flex items-center gap-3 text-sm">
        <span className="font-medium">
          {selected.size} selected
          {mutation.isPending && <Loader2 className="inline-block h-3 w-3 ml-2 animate-spin" />}
        </span>
        <span className="opacity-30">|</span>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="hover:underline inline-flex items-center gap-1" disabled={mutation.isPending}>
              <UserCheck className="h-3.5 w-3.5" />
              Assign…
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuLabel>Assign all to…</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => assignTo(null)}>Unassigned</DropdownMenuItem>
            {users.map((u) => (
              <DropdownMenuItem key={u.id} onClick={() => assignTo(u.id)}>
                {u.full_name || u.email}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="hover:underline inline-flex items-center gap-1" disabled={mutation.isPending}>
              <CheckCircle2 className="h-3.5 w-3.5" />
              Change status…
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuLabel>Change all to…</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setStatus("not_started")}>Not started</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setStatus("in_progress")}>In progress</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setStatus("pending_review")}>Pending review</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setStatus("completed")}>Completed</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <button
          onClick={onClear}
          className="opacity-70 hover:opacity-100"
          aria-label="Clear selection"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}


function SortHeader({
  label,
  k,
  current,
  dir,
  onClick,
}: {
  label: string;
  k: SortKey;
  current: SortKey;
  dir: "asc" | "desc";
  onClick: (k: SortKey) => void;
}) {
  const active = k === current;
  return (
    <th className="px-3 py-2.5 text-left font-medium">
      <button
        onClick={() => onClick(k)}
        className={cn(
          "inline-flex items-center gap-1 hover:text-foreground",
          active && "text-foreground",
        )}
      >
        {label}
        {active && (dir === "asc" ? "↑" : "↓")}
      </button>
    </th>
  );
}
