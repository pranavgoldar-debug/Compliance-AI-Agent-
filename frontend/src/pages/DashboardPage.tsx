import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  AlertCircle,
  BellRing,
  Building2,
  CalendarClock,
  CalendarDays,
  CheckCircle2,
  FileBadge,
  UserPlus,
  Sun,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";
import { StatusPill } from "@/components/StatusPill";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { AssigneeChip } from "@/components/AssigneeChip";
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
import type { DashboardStats, Entity, Obligation } from "@/types/api";

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
  sublabel,
  tone,
  icon: Icon,
  href,
}: {
  value: number;
  label: string;
  sublabel?: string;
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
        {sublabel && (
          <span className="text-[10px] text-muted-foreground/80 truncate">
            {sublabel}
          </span>
        )}
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
// This week's filings — next 7 days from today, grouped by exact date so no
// item gets dropped because of weekend / cross-week edges.
// ---------------------------------------------------------------------------
const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function ymdLocal(d: Date): string {
  // Render the local Y-M-D so we match the YYYY-MM-DD strings the API hands
  // back (which are naive dates — no TZ in them).
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function ThisWeekStrip({ items }: { items: Obligation[] }) {
  const { openObligation } = useObligationDrawer();

  // Build 7 buckets keyed by YYYY-MM-DD, starting today.
  const buckets: { key: string; date: Date; items: Obligation[] }[] = [];
  const today = new Date();
  for (let i = 0; i < 7; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() + i);
    buckets.push({ key: ymdLocal(d), date: d, items: [] });
  }
  const byKey = new Map(buckets.map((b) => [b.key, b]));

  for (const ob of items) {
    // API returns "YYYY-MM-DD" strings — match directly, no TZ wrangling.
    const bucket = byKey.get(ob.due_date);
    if (bucket) bucket.items.push(ob);
  }

  const totalShown = buckets.reduce((n, b) => n + b.items.length, 0);
  if (totalShown === 0) {
    return (
      <EmptyState
        icon={<Sun className="h-5 w-5" />}
        title="You're clear this week"
        description="Nothing falls due in the next 7 days."
      />
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 divide-y md:divide-y-0 md:divide-x divide-border">
      {buckets.map((b, i) => (
        <div key={b.key} className="p-4 min-w-0">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-foreground">
              {i === 0 ? "Today" : i === 1 ? "Tomorrow" : DAY_NAMES[b.date.getDay()]}
            </span>
            <span className="text-[10px] text-muted-foreground">
              {b.date.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </span>
          </div>
          {b.items.length === 0 ? (
            <div className="text-xs text-muted-foreground italic">—</div>
          ) : (
            <div className="space-y-2">
              {b.items.slice(0, 4).map((ob) => (
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
              {b.items.length > 4 && (
                <div className="text-xs text-muted-foreground">+{b.items.length - 4} more</div>
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
      className="w-full text-left grid grid-cols-[1fr_1.6fr_110px_110px_60px] gap-3 items-center px-4 py-2.5 hover:bg-secondary/50 transition-colors text-sm"
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
      <AssigneeChip user={ob.assignee} size="sm" />
    </button>
  );
}


export function DashboardPage() {
  const { user } = useAuth();
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardStats>("/api/dashboard"),
    // Poll every minute — keeps the Awaiting review / Overdue tiles live
    // so an admin sees a new "submit for review" without manual refresh.
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
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
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        {isLoading || !data ? (
          <>
            {Array.from({ length: 7 }).map((_, i) => (
              <Skeleton key={i} className="h-[70px]" />
            ))}
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
              value={data.awaiting_review}
              label="Pending verification"
              tone={data.awaiting_review > 0 ? "alert" : "muted"}
              icon={CheckCircle2}
              href="/tasks?status=pending_review"
            />
            <MetricCard
              value={data.awaiting_payment}
              label="Awaiting payment"
              tone={data.awaiting_payment > 0 ? "alert" : "muted"}
              icon={CheckCircle2}
              href="/tasks?awaiting_payment=1"
            />
            <MetricCard
              value={data.unassigned}
              label="Unassigned"
              tone={data.unassigned > 0 ? "alert" : "muted"}
              icon={UserPlus}
              href="/tasks?scope=unassigned"
            />
            <MetricCard
              value={data.entity_count}
              label="Entities"
              tone="neutral"
              icon={Building2}
              href="/entities"
            />
            <MetricCard
              value={data.license_count}
              label="Licenses"
              tone="neutral"
              icon={FileBadge}
              href="/licenses"
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
              <div className="grid grid-cols-[1fr_1.6fr_110px_110px_60px] gap-3 px-4 py-2.5 bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
                <div>Entity</div>
                <div>Obligation</div>
                <div>Due date</div>
                <div>Days remaining</div>
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


