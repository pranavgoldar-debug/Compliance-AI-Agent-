import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  addMonths,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { JURISDICTIONS, fmtDate } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";
import { cn } from "@/lib/utils";
import type { CalendarObligation, ObligationStatus } from "@/types/api";

function statusDotClass(status: ObligationStatus, isOverdue: boolean): string {
  if (isOverdue) return "bg-red-500";
  switch (status) {
    case "completed":
      return "bg-emerald-500";
    case "in_progress":
      return "bg-blue-500";
    case "pending_review":
      return "bg-purple-500";
    default:
      return "bg-amber-500";
  }
}

export function CalendarPage() {
  const [cursor, setCursor] = useState(new Date());
  const [jurisdictionCode, setJurisdictionCode] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [selected, setSelected] = useState<Date>(new Date());
  const { openObligation } = useObligationDrawer();

  // Calendar grid range — fill out the surrounding weeks.
  const monthStart = startOfMonth(cursor);
  const monthEnd = endOfMonth(cursor);
  const gridStart = startOfWeek(monthStart, { weekStartsOn: 1 });
  const gridEnd = endOfWeek(monthEnd, { weekStartsOn: 1 });

  const { data, isLoading } = useQuery({
    queryKey: [
      "calendar",
      format(gridStart, "yyyy-MM-dd"),
      format(gridEnd, "yyyy-MM-dd"),
      jurisdictionCode,
      statusFilter,
    ],
    queryFn: () => {
      const params = new URLSearchParams({
        start: format(gridStart, "yyyy-MM-dd"),
        end: format(gridEnd, "yyyy-MM-dd"),
      });
      if (jurisdictionCode) params.set("jurisdiction_code", jurisdictionCode);
      if (statusFilter) params.set("status", statusFilter);
      return api.get<CalendarObligation[]>(`/api/calendar?${params.toString()}`);
    },
  });

  // Build a date -> obligations map.
  const byDate = useMemo(() => {
    const map = new Map<string, CalendarObligation[]>();
    for (const ob of data ?? []) {
      const key = ob.due_date;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(ob);
    }
    return map;
  }, [data]);

  // Build the days array
  const days: Date[] = [];
  {
    const day = new Date(gridStart);
    while (day <= gridEnd) {
      days.push(new Date(day));
      day.setDate(day.getDate() + 1);
    }
  }

  const selectedKey = format(selected, "yyyy-MM-dd");
  const selectedItems = byDate.get(selectedKey) ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Compliance Calendar"
        description="Every obligation across every entity, on one month grid. Click a day for detail."
        actions={
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon" onClick={() => setCursor(subMonths(cursor, 1))}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <div className="px-3 text-sm font-medium min-w-[140px] text-center">
              {format(cursor, "MMMM yyyy")}
            </div>
            <Button variant="outline" size="icon" onClick={() => setCursor(addMonths(cursor, 1))}>
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setCursor(new Date())}>
              Today
            </Button>
          </div>
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <select
          value={jurisdictionCode}
          onChange={(e) => setJurisdictionCode(e.target.value)}
          className="h-9 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="">All jurisdictions</option>
          {Object.entries(JURISDICTIONS).map(([code, j]) => (
            <option key={code} value={code}>
              {j.flag} {j.name}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="">All statuses</option>
          <option value="not_started">Not started</option>
          <option value="in_progress">In progress</option>
          <option value="pending_review">Pending review</option>
          <option value="completed">Completed</option>
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        {/* Month grid */}
        <Card className="overflow-hidden">
          {/* Day-of-week header */}
          <div className="grid grid-cols-7 border-b border-border bg-secondary/40">
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
            <div className="grid grid-cols-7 grid-rows-6 min-h-[480px]">
              {days.map((day) => {
                const key = format(day, "yyyy-MM-dd");
                const items = byDate.get(key) ?? [];
                const inMonth = isSameMonth(day, cursor);
                const isToday = isSameDay(day, new Date());
                const isSelected = isSameDay(day, selected);
                const hasOverdue = items.some((i) => i.is_overdue);
                return (
                  <button
                    key={key}
                    onClick={() => setSelected(day)}
                    className={cn(
                      "text-left px-2 py-2 border-r border-b border-border last:border-r-0 transition-colors",
                      !inMonth && "bg-secondary/20 text-muted-foreground",
                      inMonth && "hover:bg-secondary/40",
                      isSelected && "bg-aspora-50 hover:bg-aspora-50",
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
                      {hasOverdue && (
                        <span className="h-1.5 w-1.5 rounded-full bg-red-500" aria-hidden />
                      )}
                    </div>
                    <div className="space-y-1">
                      {items.slice(0, 3).map((ob) => (
                        <div
                          key={ob.id}
                          className="flex items-center gap-1.5 text-[11px] leading-tight"
                          title={`${ob.entity_name} — ${ob.rule_form_name}`}
                        >
                          <span
                            className={cn(
                              "h-1.5 w-1.5 rounded-full shrink-0",
                              statusDotClass(ob.status, ob.is_overdue),
                            )}
                          />
                          <span className="truncate">{ob.rule_form_name}</span>
                        </div>
                      ))}
                      {items.length > 3 && (
                        <div className="text-[10px] text-muted-foreground">
                          +{items.length - 3} more
                        </div>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </Card>

        {/* Right rail — selected day */}
        <Card className="overflow-hidden h-fit">
          <div className="px-4 py-3 border-b border-border">
            <div className="text-xs uppercase tracking-wider text-muted-foreground">
              {format(selected, "EEEE")}
            </div>
            <div className="text-lg font-semibold">{fmtDate(selectedKey, "d MMMM yyyy")}</div>
            <div className="text-xs text-muted-foreground mt-1">
              {selectedItems.length} obligation{selectedItems.length === 1 ? "" : "s"}
            </div>
          </div>
          <div className="max-h-[460px] overflow-auto scrollbar-thin divide-y divide-border">
            {selectedItems.length === 0 ? (
              <div className="p-6 text-center text-sm text-muted-foreground">
                Nothing due on this day.
              </div>
            ) : (
              selectedItems.map((ob) => (
                <button
                  key={ob.id}
                  type="button"
                  onClick={() => openObligation(ob.id)}
                  className="block w-full text-left px-4 py-3 hover:bg-secondary/40"
                >
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="text-xs text-muted-foreground truncate">
                        {ob.entity_name}
                      </div>
                      <div className="font-medium text-sm leading-tight truncate">
                        {ob.rule_form_name}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge
                          variant={ob.is_overdue ? "overdue" : ob.days_remaining <= 14 ? "alert" : "neutral"}
                        >
                          {ob.is_overdue
                            ? `${Math.abs(ob.days_remaining)}d overdue`
                            : ob.days_remaining === 0
                              ? "Due today"
                              : `${ob.days_remaining}d`}
                        </Badge>
                        <span className="text-xs text-muted-foreground truncate">
                          {ob.rule_authority}
                        </span>
                      </div>
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
