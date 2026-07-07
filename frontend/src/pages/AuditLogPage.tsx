// Audit Log — admin-only chronological feed of every state change.
// Wired to /api/activities with filter bar (date range, entity, actor, action),
// grouped by date (sticky date headers), with CSV export.

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  Download,
  History,
  Loader2,
  Search,
  Trash2,
} from "lucide-react";
import { api, apiUrl } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DateField } from "@/components/DateField";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { fieldLabel, fmtRelative, fmtTime, parseBackendDate, userInitials } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ActivityOut, Entity, UserBrief } from "@/types/api";


const ACTION_BUCKETS: { label: string; prefixes: string[] }[] = [
  { label: "Obligation changes", prefixes: ["obligation."] },
  { label: "Comments", prefixes: ["comment."] },
  { label: "Documents", prefixes: ["document."] },
  { label: "Users", prefixes: ["user."] },
];


export function AuditLogPage() {
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [actorIds, setActorIds] = useState<number[]>([]);
  const [entityIds, setEntityIds] = useState<number[]>([]);
  const [actionLabels, setActionLabels] = useState<string[]>([]);
  const [since, setSince] = useState<string>("");
  const [until, setUntil] = useState<string>("");

  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserBrief[]>("/api/users"),
  });

  const clearMutation = useMutation({
    mutationFn: () => api.delete<{ deleted: number }>("/api/activities"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["audit-log"] }),
  });
  const { data: entities = [] } = useQuery({
    queryKey: ["entities"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
  });

  const { data: activities = [], isLoading } = useQuery({
    queryKey: ["audit-log", actorIds, entityIds, since, until],
    queryFn: () => {
      // The API accepts ONE actor / ONE entity at a time; for multi-select we
      // do client-side filtering on the largest superset.
      const params = new URLSearchParams({ limit: "500" });
      if (since) params.set("since", new Date(since).toISOString());
      if (until) params.set("until", new Date(until).toISOString());
      return api.get<ActivityOut[]>(`/api/activities?${params.toString()}`);
    },
  });

  // ----------------------------------------------------------------
  // Client-side filters layered on top of date-range fetch
  // ----------------------------------------------------------------
  const filtered = useMemo(() => {
    let arr = activities;
    if (actorIds.length)
      arr = arr.filter((a) => a.actor && actorIds.includes(a.actor.id));
    if (entityIds.length) {
      const wanted = new Set(entityIds);
      arr = arr.filter((a) => {
        if (a.target_type === "entity" && a.target_id && wanted.has(a.target_id)) return true;
        // Entity-scoped events on obligations / documents already filtered
        // server-side when entity_id is passed; here we only loosely match
        // on target_label containing the entity name (best-effort).
        if (a.target_label) {
          for (const e of entities) {
            if (wanted.has(e.id) && a.target_label.includes(e.name)) return true;
          }
        }
        return false;
      });
    }
    if (actionLabels.length) {
      const prefixes = ACTION_BUCKETS.filter((b) => actionLabels.includes(b.label)).flatMap(
        (b) => b.prefixes,
      );
      arr = arr.filter((a) => prefixes.some((p) => a.action.startsWith(p)));
    }
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      arr = arr.filter(
        (a) =>
          a.action.toLowerCase().includes(needle) ||
          (a.target_label?.toLowerCase().includes(needle) ?? false) ||
          (a.actor?.full_name?.toLowerCase().includes(needle) ?? false) ||
          (a.actor?.email?.toLowerCase().includes(needle) ?? false),
      );
    }
    return arr;
  }, [activities, actorIds, entityIds, actionLabels, q, entities]);

  // Group by calendar day for sticky date headers.
  const groupedByDay = useMemo(() => {
    const groups = new Map<string, ActivityOut[]>();
    for (const a of filtered) {
      const day = parseBackendDate(a.created_at).toDateString();
      if (!groups.has(day)) groups.set(day, []);
      groups.get(day)!.push(a);
    }
    return Array.from(groups.entries());
  }, [filtered]);

  const activeFilterCount =
    actorIds.length + entityIds.length + actionLabels.length + (since ? 1 : 0) + (until ? 1 : 0);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Audit Log"
        description="Immutable record of every state change. Admin only."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" asChild>
              <a href={apiUrl("/api/activities/export")} download>
                <Download className="h-4 w-4" />
                Export CSV
              </a>
            </Button>
            <Button
              variant="outline"
              className="text-red-600"
              disabled={clearMutation.isPending}
              onClick={() => {
                if (
                  window.confirm(
                    "Clear the entire activity log? This is irreversible. Export a CSV first if you want a copy.",
                  )
                ) {
                  clearMutation.mutate();
                }
              }}
            >
              {clearMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Clear log
            </Button>
          </div>
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-[280px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search actions, names, items…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9 h-10"
          />
        </div>
        <FilterPopover
          label="Actor"
          options={users.map((u) => ({ value: String(u.id), label: u.full_name || u.email }))}
          selected={actorIds.map(String)}
          onChange={(vals) => setActorIds(vals.map(Number))}
          searchable
        />
        <FilterPopover
          label="Entity"
          options={entities.map((e) => ({ value: String(e.id), label: e.name }))}
          selected={entityIds.map(String)}
          onChange={(vals) => setEntityIds(vals.map(Number))}
          searchable
        />
        <FilterPopover
          label="Action type"
          options={ACTION_BUCKETS.map((b) => ({ value: b.label, label: b.label }))}
          selected={actionLabels}
          onChange={setActionLabels}
        />
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className={cn(
                "h-10",
                (since || until) && "bg-aspora-50 border-aspora-200 text-aspora-800",
              )}
            >
              Date range
              {(since || until) && (
                <Badge variant="default" className="ml-1.5 -mr-1">
                  1
                </Badge>
              )}
              <ChevronDown className="h-3.5 w-3.5 ml-1" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-72 p-3 space-y-2">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Since</div>
            <DateField value={since} onChange={setSince} />
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Until</div>
            <DateField value={until} onChange={setUntil} />
            {(since || until) && (
              <button
                onClick={() => {
                  setSince("");
                  setUntil("");
                }}
                className="text-xs text-aspora-700 hover:underline"
              >
                Clear range
              </button>
            )}
          </PopoverContent>
        </Popover>
        {activeFilterCount > 0 && (
          <button
            onClick={() => {
              setActorIds([]);
              setEntityIds([]);
              setActionLabels([]);
              setSince("");
              setUntil("");
            }}
            className="text-xs text-aspora-700 hover:underline"
          >
            Clear ({activeFilterCount})
          </button>
        )}
        <div className="ml-auto text-xs text-muted-foreground tabular-nums">
          {filtered.length} event{filtered.length === 1 ? "" : "s"}
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : groupedByDay.length === 0 ? (
        <EmptyState
          icon={<History className="h-6 w-6" />}
          title="No activity in the selected range"
          description="Try widening the date window or clearing some filters."
        />
      ) : (
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            {groupedByDay.map(([day, items]) => (
              <div key={day}>
                <div className="sticky top-0 z-10 bg-secondary border-b border-border px-4 py-2 text-xs uppercase tracking-wider text-muted-foreground font-semibold shadow-sm">
                  {day}
                </div>
                <ul className="divide-y divide-border">
                  {items.map((a) => (
                    <ActivityRow key={a.id} activity={a} />
                  ))}
                </ul>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}


function ActivityRow({ activity }: { activity: ActivityOut }) {
  return (
    <li className="px-4 py-3 flex items-start gap-3 hover:bg-secondary/30">
      <span className="text-xs tabular-nums text-muted-foreground w-20 shrink-0 mt-1">
        {fmtTime(activity.created_at)}
      </span>
      <Avatar className="h-7 w-7 shrink-0 mt-0.5">
        <AvatarFallback className="text-[10px]">
          {userInitials(activity.actor?.full_name || activity.actor?.email || "—")}
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1 text-sm">
        <div className="leading-snug">
          <span className="font-medium">
            {activity.actor?.full_name || activity.actor?.email || "System"}
          </span>{" "}
          <span className="text-muted-foreground">{humaniseAction(activity.action)}</span>
          {activity.target_label && (
            <>
              {" "}
              <span className="font-medium">{activity.target_label}</span>
            </>
          )}
        </div>
        {activity.payload && Object.keys(activity.payload).length > 0 && (
          <div className="mt-1.5 flex items-center gap-1 flex-wrap">
            {renderPayload(activity.payload)}
          </div>
        )}
      </div>
      <span className="text-xs text-muted-foreground whitespace-nowrap mt-1">
        {fmtRelative(activity.created_at)}
      </span>
    </li>
  );
}


function humaniseAction(action: string): string {
  switch (action) {
    case "obligation.updated":
      return "updated";
    case "obligation.due_date_changed":
      return "changed the due date of";
    case "obligation.due_date_change_requested":
      return "requested a due-date change on";
    case "obligation.due_date_request_declined":
      return "declined a due-date request on";
    case "comment.added":
      return "commented on";
    case "document.uploaded":
      return "uploaded";
    case "document.updated":
      return "renamed";
    case "document.deleted":
      return "deleted";
    case "user.created":
      return "created user";
    case "user.updated":
      return "updated user";
    case "user.deactivated":
      return "deactivated user";
    default:
      return action;
  }
}


// User-facing labels for the internal rule lifecycle, matching the Review &
// Assign tabs — so the audit log reads "For Action" / "Approved" instead of the
// raw "staging" / "production".
const STATUS_LABELS: Record<string, string> = {
  staging: "For Action",
  production: "Approved",
  archived: "Archived",
  retired: "Retired",
};
const STATUS_KEYS = new Set(["from", "to", "status", "from_status", "to_status"]);

function payloadValue(key: string, value: string): string {
  return STATUS_KEYS.has(key) && value in STATUS_LABELS ? STATUS_LABELS[value] : value;
}

function renderPayload(payload: Record<string, unknown>) {
  // Rich entity-update diff: "Field: old → new" (sensitive fields show only
  // "updated" — see _entity_change_log on the backend).
  const changes = payload.changes as
    | Record<string, { from?: unknown; to?: unknown; updated?: boolean }>
    | undefined;
  if (changes && typeof changes === "object" && Object.keys(changes).length > 0) {
    return Object.entries(changes)
      .slice(0, 6)
      .map(([field, c]) => {
        const hasValues = !!c && typeof c === "object" && ("from" in c || "to" in c);
        const fmt = (v: unknown) =>
          v == null || v === "" ? "—" : payloadValue("from", String(v));
        return (
          <Badge key={field} variant="neutral" className="text-[10px]">
            {fieldLabel(field)}:{" "}
            {hasValues ? (
              <span className="font-mono ml-1">
                {fmt(c.from)} → {fmt(c.to)}
              </span>
            ) : (
              <span className="ml-1">updated</span>
            )}
          </Badge>
        );
      });
  }
  const fields = (payload.changed_fields ?? payload.fields) as string[] | undefined;
  if (Array.isArray(fields) && fields.length > 0) {
    return fields.slice(0, 6).map((f) => (
      <Badge key={f} variant="neutral" className="text-[10px]">
        {fieldLabel(f)}
      </Badge>
    ));
  }
  // Generic display of {key: value} pairs (filename, role, email…)
  return Object.entries(payload)
    .slice(0, 4)
    .map(([k, v]) => {
      if (v === null || typeof v === "object") return null;
      return (
        <Badge key={k} variant="neutral" className="text-[10px]">
          {k}: <span className="font-mono ml-1">{payloadValue(k, String(v))}</span>
        </Badge>
      );
    });
}


// ---------------------------------------------------------------------------
// Filter popover (multi-select with optional search)
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
