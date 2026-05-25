import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowUpRight, AlertCircle, BellRing, ShieldCheck, UserPlus } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { StatusPill } from "@/components/StatusPill";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { fmtShortDate, userInitials } from "@/lib/format";
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

function CountPill({
  value,
  label,
  tone,
  icon: Icon,
}: {
  value: number;
  label: string;
  tone: "overdue" | "alert" | "safe" | "neutral";
  icon: React.ComponentType<{ className?: string }>;
}) {
  const toneClasses = {
    overdue: "bg-red-50 border-red-200 text-red-700",
    alert: "bg-amber-50 border-amber-200 text-amber-700",
    safe: "bg-emerald-50 border-emerald-200 text-emerald-700",
    neutral: "bg-slate-50 border-slate-200 text-slate-700",
  }[tone];
  const valueColor = {
    overdue: "text-red-600",
    alert: "text-amber-600",
    safe: "text-emerald-600",
    neutral: "text-slate-700",
  }[tone];
  return (
    <div className={cn("rounded-xl border px-4 py-3 flex items-center gap-3", toneClasses)}>
      <Icon className="h-5 w-5 shrink-0" />
      <div className="flex flex-col leading-tight">
        <span className={cn("text-2xl font-semibold tabular-nums", valueColor)}>{value}</span>
        <span className="text-xs uppercase tracking-wide opacity-80">{label}</span>
      </div>
    </div>
  );
}

function AlertBanner({ overdue }: { overdue: number }) {
  if (overdue === 0) return null;
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4 flex items-center gap-4">
      <AlertCircle className="h-5 w-5 text-red-600 shrink-0" />
      <div className="flex-1">
        <div className="text-sm font-semibold text-red-800">
          {overdue} obligation{overdue === 1 ? "" : "s"} overdue — immediate action required
        </div>
        <div className="text-xs text-red-700/80 mt-0.5">
          These items missed their due date. Filter to overdue in the calendar to triage.
        </div>
      </div>
      <Link
        to="/calendar"
        className="text-sm font-medium text-red-700 hover:underline whitespace-nowrap"
      >
        View overdue →
      </Link>
    </div>
  );
}

function ObligationRow({ ob, showAssignee = true }: { ob: Obligation; showAssignee?: boolean }) {
  return (
    <Link
      to={`/entities/${ob.entity_id}`}
      className="grid grid-cols-[1fr_2fr_120px_110px_110px_auto] gap-4 items-center px-4 py-3 hover:bg-secondary/50 transition-colors text-sm"
    >
      <div className="flex items-center gap-2 min-w-0">
        <JurisdictionBadge code={ob.entity_jurisdiction_code} showName={false} />
        <span className="truncate font-medium">{ob.entity_name}</span>
      </div>
      <div className="truncate text-muted-foreground">{ob.rule_form_name}</div>
      <div className="tabular-nums">{fmtShortDate(ob.due_date)}</div>
      <StatusPill
        status={ob.status}
        isOverdue={ob.is_overdue}
        daysRemaining={ob.days_remaining}
        showDays
      />
      <StatusPill status={ob.status} isOverdue={ob.is_overdue} />
      {showAssignee && (
        <div className="flex justify-end">
          {ob.assignee ? (
            <Avatar className="h-7 w-7">
              <AvatarFallback className="text-[10px]">
                {userInitials(ob.assignee.full_name)}
              </AvatarFallback>
            </Avatar>
          ) : (
            <span className="text-muted-foreground" title="Unassigned">
              <UserPlus className="h-4 w-4" />
            </span>
          )}
        </div>
      )}
    </Link>
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
        <span className="text-xs text-muted-foreground">({count})</span>
      </div>
      {href && (
        <Link
          to={href}
          className="text-xs font-medium text-aspora-600 hover:text-aspora-700 inline-flex items-center gap-1"
        >
          View all <ArrowUpRight className="h-3 w-3" />
        </Link>
      )}
    </div>
  );
}

function ThisWeekStrip({ items }: { items: Obligation[] }) {
  // Group obligations by date label.
  const byDay = new Map<string, Obligation[]>();
  for (const ob of items) {
    const key = fmtShortDate(ob.due_date);
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key)!.push(ob);
  }
  const days = Array.from(byDay.entries()).slice(0, 5);

  if (days.length === 0) {
    return (
      <div className="px-4 py-6 text-center text-sm text-muted-foreground">
        Nothing on the calendar in the next 7 days. 🌴
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-5 divide-y md:divide-y-0 md:divide-x divide-border">
      {days.map(([day, dayItems]) => (
        <div key={day} className="p-4 min-w-0">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-2">
            {day}
          </div>
          <div className="space-y-2">
            {dayItems.slice(0, 4).map((ob) => (
              <Link
                key={ob.id}
                to={`/entities/${ob.entity_id}`}
                className="block group"
              >
                <div className="text-sm font-medium truncate group-hover:text-aspora-700">
                  {ob.rule_form_name}
                </div>
                <div className="text-xs text-muted-foreground truncate">{ob.entity_name}</div>
              </Link>
            ))}
            {dayItems.length > 4 && (
              <div className="text-xs text-muted-foreground">+{dayItems.length - 4} more</div>
            )}
          </div>
        </div>
      ))}
    </div>
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
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {greeting}, {firstName}
        </h1>
        <p className="text-muted-foreground mt-1">{formatToday()}</p>
      </div>

      {/* Count strip */}
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
            <CountPill value={data.overdue} label="Overdue" tone="overdue" icon={AlertCircle} />
            <CountPill
              value={data.in_alert_window}
              label="In alert window"
              tone="alert"
              icon={BellRing}
            />
            <CountPill value={data.in_safe_zone} label="In safe zone" tone="safe" icon={ShieldCheck} />
            <CountPill
              value={data.completed_this_month}
              label="Completed this month"
              tone="neutral"
              icon={ShieldCheck}
            />
          </>
        )}
      </div>

      {/* Alert banner */}
      {!isLoading && data && <AlertBanner overdue={data.overdue} />}

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
              {data.open_tasks.slice(0, 8).map((ob) => (
                <ObligationRow key={ob.id} ob={ob} showAssignee={false} />
              ))}
            </div>
          ) : (
            <div className="p-6 text-sm text-muted-foreground">
              No tasks assigned to you right now. Nice.
            </div>
          )}
        </CardContent>
      </Card>

      {/* In alert window */}
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
              {data.items_in_alert_window.slice(0, 10).map((ob) => (
                <ObligationRow key={ob.id} ob={ob} />
              ))}
            </div>
          ) : (
            <div className="p-6 text-sm text-muted-foreground">
              No items in the alert window. Clean horizon.
            </div>
          )}
        </CardContent>
      </Card>

      {/* This week */}
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
