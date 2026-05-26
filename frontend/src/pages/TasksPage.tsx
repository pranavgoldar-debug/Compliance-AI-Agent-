import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/StatusPill";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { PageHeader } from "@/components/PageHeader";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";
import { fmtShortDate } from "@/lib/format";
import type { Obligation } from "@/types/api";

type Scope = "assigned" | "watching" | "completed" | "all";

const SCOPES: { key: Scope; label: string }[] = [
  { key: "assigned", label: "Assigned to me" },
  { key: "watching", label: "Watching" },
  { key: "completed", label: "Completed" },
  { key: "all", label: "All" },
];

function groupTasks(tasks: Obligation[]) {
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
    <button
      type="button"
      onClick={() => openObligation(ob.id)}
      className="w-full text-left grid grid-cols-[1.4fr_2fr_140px_140px_140px] gap-4 px-4 py-3 items-center hover:bg-secondary/40 transition-colors text-sm"
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
      <StatusPill status={ob.status} isOverdue={ob.is_overdue} />
    </button>
  );
}

function Section({ title, items }: { title: string; items: Obligation[] }) {
  if (items.length === 0) return null;
  const variant =
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
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Badge variant={variant as never}>{title}</Badge>
        <span className="text-xs text-muted-foreground">
          {items.length} item{items.length === 1 ? "" : "s"}
        </span>
      </div>
      <div className="divide-y divide-border">
        {items.map((ob) => (
          <TaskRow key={ob.id} ob={ob} />
        ))}
      </div>
    </div>
  );
}

export function TasksPage() {
  const [scope, setScope] = useState<Scope>("assigned");
  const { data, isLoading } = useQuery({
    queryKey: ["tasks", scope],
    queryFn: () => api.get<Obligation[]>(`/api/tasks?scope=${scope}`),
  });

  const groups = data ? groupTasks(data) : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tasks"
        description="What you owe today, this week, and beyond. Assigned to you, watched, completed, or everything."
      />

      <Tabs value={scope} onValueChange={(v) => setScope(v as Scope)}>
        <TabsList>
          {SCOPES.map((s) => (
            <TabsTrigger key={s.key} value={s.key}>
              {s.label}
              {data && scope === s.key && (
                <Badge variant="neutral" className="ml-1">
                  {data.length}
                </Badge>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : !data || data.length === 0 ? (
        <Card>
          <div className="p-10 text-center text-sm text-muted-foreground">
            {scope === "assigned"
              ? "Nothing assigned to you right now. 🌴"
              : scope === "watching"
                ? "You're not watching any obligations yet — comment on one to start."
                : scope === "completed"
                  ? "No completed tasks in your queue."
                  : "No tasks found."}
          </div>
        </Card>
      ) : (
        <div className="space-y-4">
          {groups &&
            ["Overdue", "In alert window", "In progress", "Upcoming", "Completed"].map((g) => (
              <Section key={g} title={g} items={groups[g]} />
            ))}
        </div>
      )}
    </div>
  );
}
