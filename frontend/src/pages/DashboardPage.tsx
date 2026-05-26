import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  AlertCircle,
  BellRing,
  CalendarClock,
  CalendarDays,
  UserPlus,
  Sun,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";
import { StatusPill } from "@/components/StatusPill";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { AssigneeChip } from "@/components/AssigneeChip";
import { EffortBandBadge } from "@/components/EffortBandBadge";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { fmtShortDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DashboardStats, Obligation } from "@/types/api";

function greetingFor(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function formatToday(): string {
  return new Date().toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}


// ---------------------------------------------------------------------------
// Metric cards — Overdue / Due this week / Due this month / Unassigned
// ---------------------------------------------------------------------------
function MetricCard({
  value,
  label,
  tone,
  icon: Icon,
  href,
}: {
  value: number;
  label: string;
  tone: "overdue" | "alert" | "neutral" | "muted";
  icon: React.ComponentType<{ className?: string }>;
  href: string;
}) {
  const toneClasses = {
    overdue: "border-red-200 bg-red-50",
    alert: "border-amber-200 bg-amber-50",
    neutral: "border-aspora-200 bg-aspora-50/60",
    muted: "border-slate-200 bg-slate-50",
  }[tone];
  const valueColor = {
    overdue: "text-red-700",
    alert: "text-amber-700",
    neutral: "text-aspora-800",
    muted: "text-slate-700",
  }[tone];
  return (
    <Link
      to={href}
      className={cn(
        "rounded-xl border px-4 py-3 flex items-center gap-3 transition-shadow hover:shadow-sm",
        toneClasses,
      )}
    >
      <Icon className={cn("h-5 w-5 shrink-0", valueColor)} />
      <div className="flex flex-col leading-tight min-w-0">
        <span className={cn("text-2xl font-semibold tabular-nums", valueColor)}>{value}</span>
        <span className="text-xs uppercase tracking-wide text-muted-foreground truncate">
          {label}
        </span>
      </div>
      <ArrowUpRight className="ml-auto h-4 w-4 text-muted-foreground/50 shrink-0" />
    </Link>
  );
}


// ---------------------------------------------------------------------------
// Stacked banners — red overdue + amber alert
// ---------------------------------------------------------------------------
function AlertBanners({ overdue, inAlert }: { overdue: number; inAlert: number }) {
  if (overdue === 0 && inAlert === 0) return null;
  return (
    <div className="space-y-2">
      {overdue > 0 && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-3 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-red-600 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-red-800">
              {overdue} item{overdue === 1 ? "" : "s"} overdue — immediate action required
            </div>
            <div className="text-xs text-red-700/80">
              These items missed their due date. Filter to Overdue in the calendar to triage.
            </div>
          </div>
          <Link
            to="/calendar"
            className="text-sm font-medium text-red-700 hover:underline whitespace-nowrap"
          >
            View →
          </Link>
        </div>
      )}
      {inAlert > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-3 flex items-center gap-3">
          <BellRing className="h-5 w-5 text-amber-600 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-amber-800">
              {inAlert} item{inAlert === 1 ? "" : "s"} need attention this week
            </div>
            <div className="text-xs text-amber-700/80">
              Inside the alert window — file or push them along before they slip.
            </div>
          </div>
          <Link
            to="/tasks"
            className="text-sm font-medium text-amber-700 hover:underline whitespace-nowrap"
          >
            View →
          </Link>
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// My open tasks row
// ---------------------------------------------------------------------------
function MyTaskRow({ ob }: { ob: Obligation }) {
  const { openObligation } = useObligationDrawer();
  return (
    <button
      type="button"
      onClick={() => openObligation(ob.id)}
      className="w-full text-left grid grid-cols-[1fr_2fr_110px_110px_110px_44px] gap-3 items-center px-4 py-2.5 hover:bg-secondary/50 transition-colors text-sm"
    >
      <div className="flex items-center gap-2 min-w-0">
        <JurisdictionBadge code={ob.entity_jurisdiction_code} showName={false} />
        <span className="truncate font-medium">{ob.entity_name}</span>
      </div>
      <div className="truncate">
        <div className="truncate">{ob.rule_form_name}</div>
        <div className="text-xs text-muted-foreground truncate">{ob.rule_category}</div>
      </div>
      <div className="tabular-nums">{fmtShortDate(ob.due_date)}</div>
      <StatusPill
        status={ob.status}
        isOverdue={ob.is_overdue}
        daysRemaining={ob.days_remaining}
        showDays
      />
      <StatusPill status={ob.status} isOverdue={ob.is_overdue} />
      <QuickActionMenu />
    </button>
  );
}


function QuickActionMenu() {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          onClick={(e) => e.stopPropagation()}
          className="grid place-items-center h-7 w-7 rounded-md hover:bg-secondary text-muted-foreground"
        >
          ⋯
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem disabled>Mark as filed</DropdownMenuItem>
        <DropdownMenuItem disabled>Reassign…</DropdownMenuItem>
        <DropdownMenuItem disabled>Snooze 1 day</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}


function SectionHeader({
  title,
  count,
  href,
}: {
  title: string;
  count: number;
  href?: string;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="text-xs text-muted-foreground tabular-nums">({count})</span>
      </div>
      {href && (
        <Link
          to={href}
          className="text-xs font-medium text-aspora-700 hover:text-aspora-800 inline-flex items-center gap-1"
        >
          View all <ArrowUpRight className="h-3 w-3" />
        </Link>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// This week's filings — grouped by weekday with assignee avatars
// ---------------------------------------------------------------------------
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

function ThisWeekStrip({ items }: { items: Obligation[] }) {
  const { openObligation } = useObligationDrawer();

  // Build {weekday: items} for the next 5 weekdays starting today.
  const byDay = new Map<string, { date: Date; items: Obligation[] }>();
  const today = new Date();
  const dayIndex = today.getDay() === 0 ? 6 : today.getDay() - 1; // Mon=0…Sun=6
  for (let i = 0; i < 5; i++) {
    const d = new Date(today);
    const target = dayIndex + i;
    if (target >= WEEKDAYS.length) break;
    d.setDate(today.getDate() + i);
    byDay.set(WEEKDAYS[target], { date: d, items: [] });
  }
  for (const ob of items) {
    const due = new Date(ob.due_date);
    const wd = due.getDay() === 0 ? 6 : due.getDay() - 1;
    const key = WEEKDAYS[wd];
    if (byDay.has(key)) byDay.get(key)!.items.push(ob);
  }

  const entries = Array.from(byDay.entries());
  if (entries.length === 0) {
    return (
      <EmptyState
        icon={<Sun className="h-5 w-5" />}
        title="You're clear this week"
        description="Nothing falls due in the next 5 working days."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-5 divide-y md:divide-y-0 md:divide-x divide-border">
      {entries.map(([weekday, { date, items: dayItems }]) => (
        <div key={weekday} className="p-4 min-w-0">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-foreground">
              {weekday}
            </span>
            <span className="text-[10px] text-muted-foreground">
              {date.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </span>
          </div>
          {dayItems.length === 0 ? (
            <div className="text-xs text-muted-foreground italic">—</div>
          ) : (
            <div className="space-y-2">
              {dayItems.slice(0, 4).map((ob) => (
                <button
                  key={ob.id}
                  type="button"
                  onClick={() => openObligation(ob.id)}
                  className="block w-full text-left group"
                >
                  <div className="text-sm font-medium truncate group-hover:text-aspora-700">
                    {ob.rule_form_name}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-muted-foreground truncate flex-1">
                      {ob.entity_name}
                    </span>
                    <AssigneeChip user={ob.assignee} size="xs" />
                  </div>
                </button>
              ))}
              {dayItems.length > 4 && (
                <div className="text-xs text-muted-foreground">+{dayItems.length - 4} more</div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Items in alert window (all entities)
// ---------------------------------------------------------------------------
function AlertRow({ ob }: { ob: Obligation }) {
  const { openObligation } = useObligationDrawer();
  return (
    <button
      type="button"
      onClick={() => openObligation(ob.id)}
      className="w-full text-left grid grid-cols-[1fr_1.6fr_110px_110px_110px_60px] gap-3 items-center px-4 py-2.5 hover:bg-secondary/50 transition-colors text-sm"
    >
      <div className="flex items-center gap-2 min-w-0">
        <JurisdictionBadge code={ob.entity_jurisdiction_code} showName={false} />
        <span className="truncate font-medium">{ob.entity_name}</span>
      </div>
      <div className="truncate">{ob.rule_form_name}</div>
      <div className="tabular-nums">{fmtShortDate(ob.due_date)}</div>
      <StatusPill
        status={ob.status}
        isOverdue={ob.is_overdue}
        daysRemaining={ob.days_remaining}
        showDays
      />
      <EffortBandBadge band={ob.effort_band} />
      <AssigneeChip user={ob.assignee} size="sm" />
    </button>
  );
}


export function DashboardPage() {
  const { user } = useAuth();
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardStats>("/api/dashboard"),
  });

  const firstName = (user?.full_name || user?.email || "there").split(" ")[0];
  const greeting = greetingFor(new Date().getHours());

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {greeting}, {firstName}
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">{formatToday()}</p>
        </div>
        <div className="hidden lg:block text-right text-xs text-muted-foreground">
          Aspora Compliance OS<br />
          <span className="text-muted-foreground/70">{user?.role === "admin" ? "Admin workspace" : "Operator workspace"}</span>
        </div>
      </div>

      {/* Alert banners */}
      {!isLoading && data && <AlertBanners overdue={data.overdue} inAlert={data.in_alert_window} />}

      {/* Metric strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {isLoading || !data ? (
          <>
            <Skeleton className="h-[70px]" />
            <Skeleton className="h-[70px]" />
            <Skeleton className="h-[70px]" />
            <Skeleton className="h-[70px]" />
          </>
        ) : (
          <>
            <MetricCard
              value={data.overdue}
              label="Overdue"
              tone={data.overdue > 0 ? "overdue" : "muted"}
              icon={AlertCircle}
              href="/calendar"
            />
            <MetricCard
              value={data.due_this_week}
              label="Due this week"
              tone={data.due_this_week > 0 ? "alert" : "muted"}
              icon={CalendarClock}
              href="/tasks"
            />
            <MetricCard
              value={data.due_this_month}
              label="Due this month"
              tone="neutral"
              icon={CalendarDays}
              href="/calendar"
            />
            <MetricCard
              value={data.unassigned}
              label="Unassigned"
              tone={data.unassigned > 0 ? "alert" : "muted"}
              icon={UserPlus}
              href="/calendar"
            />
          </>
        )}
      </div>

      {/* Open tasks */}
      <Card className="overflow-hidden">
        <SectionHeader
          title="Open tasks assigned to you"
          count={data?.open_tasks.length ?? 0}
          href="/tasks"
        />
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          ) : data && data.open_tasks.length > 0 ? (
            <div className="divide-y divide-border">
              <div className="grid grid-cols-[1fr_2fr_110px_110px_110px_44px] gap-3 px-4 py-2.5 bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
                <div>Entity</div>
                <div>Obligation</div>
                <div>Due date</div>
                <div>Days remaining</div>
                <div>Status</div>
                <div />
              </div>
              {data.open_tasks.slice(0, 8).map((ob) => (
                <MyTaskRow key={ob.id} ob={ob} />
              ))}
            </div>
          ) : (
            <div className="p-8">
              <EmptyState
                icon={<Sun className="h-5 w-5" />}
                title="Nothing on your plate"
                description="No tasks assigned to you right now. Time for a coffee."
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Items in alert window */}
      <Card className="overflow-hidden">
        <SectionHeader
          title="Items in alert window (all entities)"
          count={data?.items_in_alert_window.length ?? 0}
          href="/calendar"
        />
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          ) : data && data.items_in_alert_window.length > 0 ? (
            <div className="divide-y divide-border">
              <div className="grid grid-cols-[1fr_1.6fr_110px_110px_110px_60px] gap-3 px-4 py-2.5 bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
                <div>Entity</div>
                <div>Obligation</div>
                <div>Due date</div>
                <div>Days remaining</div>
                <div>Effort</div>
                <div>Assignee</div>
              </div>
              {data.items_in_alert_window.slice(0, 10).map((ob) => (
                <AlertRow key={ob.id} ob={ob} />
              ))}
            </div>
          ) : (
            <div className="p-8">
              <EmptyState
                title="Clean horizon"
                description="Nothing in the alert window across the whole organisation."
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* This week's filings */}
      <Card className="overflow-hidden">
        <SectionHeader title="This week's filings" count={data?.this_week.length ?? 0} />
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6">
              <Skeleton className="h-24" />
            </div>
          ) : (
            <ThisWeekStrip items={data?.this_week ?? []} />
          )}
        </CardContent>
      </Card>

    </div>
  );
}
