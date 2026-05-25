import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Archive, Edit, MoreHorizontal } from "lucide-react";
import { api } from "@/lib/api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/StatusPill";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { fmtDate, fmtRelative, fmtShortDate, userInitials } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Entity, Obligation } from "@/types/api";

function StatTile({
  value,
  label,
  tone = "neutral",
}: {
  value: number | string;
  label: string;
  tone?: "neutral" | "overdue" | "alert" | "completed";
}) {
  const toneClasses = {
    neutral: "text-foreground",
    overdue: "text-red-600",
    alert: "text-amber-600",
    completed: "text-emerald-600",
  }[tone];
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3 min-w-[100px]">
      <div className={cn("text-2xl font-semibold tabular-nums leading-tight", toneClasses)}>
        {value}
      </div>
      <div className="text-xs text-muted-foreground uppercase tracking-wide mt-0.5">
        {label}
      </div>
    </div>
  );
}

export function EntityDetailPage() {
  const { entityId } = useParams();
  const [tab, setTab] = useState("overview");

  const { data: entity, isLoading: loadingEntity } = useQuery({
    queryKey: ["entity", entityId],
    queryFn: () => api.get<Entity>(`/api/entities/${entityId}`),
    enabled: !!entityId,
  });

  const { data: obligations, isLoading: loadingObs } = useQuery({
    queryKey: ["entity-obligations", entityId],
    queryFn: () => api.get<Obligation[]>(`/api/obligations?entity_id=${entityId}&limit=200`),
    enabled: !!entityId,
  });

  if (loadingEntity) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-32" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!entity) {
    return (
      <div className="space-y-4">
        <Link to="/entities" className="text-sm text-aspora-600 hover:underline">
          ← Back to entities
        </Link>
        <div className="rounded-xl border border-border bg-card p-10 text-center text-muted-foreground">
          Entity not found.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link
        to="/entities"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to entities
      </Link>

      {/* Hero */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-start justify-between gap-6">
            <div className="flex items-center gap-4">
              <div className="h-14 w-14 rounded-xl bg-aspora-100 grid place-items-center text-aspora-700 font-bold text-xl shrink-0">
                {userInitials(entity.name)}
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-semibold tracking-tight">{entity.name}</h1>
                  <JurisdictionBadge code={entity.jurisdiction_code} />
                </div>
                <div className="text-sm text-muted-foreground mt-1">
                  {entity.legal_type}
                  {entity.registration_number && ` · ${entity.registration_number}`}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm">
                <Edit className="h-4 w-4" />
                Edit
              </Button>
              <Button variant="outline" size="sm">
                <Archive className="h-4 w-4" />
                Archive
              </Button>
              <Button variant="ghost" size="icon">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Stat row */}
          <div className="mt-6 flex flex-wrap gap-3">
            <StatTile value={entity.active_obligations_count} label="Total active" />
            <StatTile value={entity.overdue_obligations_count} label="Overdue" tone="overdue" />
            <StatTile
              value={entity.in_alert_window_count}
              label="In alert window"
              tone="alert"
            />
            <StatTile
              value={entity.last_filed_at ? fmtShortDate(entity.last_filed_at) : "—"}
              label="Last filed"
            />
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="obligations">
            Compliance Items
            <Badge variant="neutral" className="ml-1">
              {obligations?.length ?? 0}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="documents">Documents</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="md:col-span-2">
              <CardContent className="p-6 space-y-4">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Business Information
                </h3>
                <dl className="grid grid-cols-2 gap-y-3 text-sm">
                  <dt className="text-muted-foreground">Legal name</dt>
                  <dd className="font-medium">{entity.name}</dd>
                  <dt className="text-muted-foreground">Legal type</dt>
                  <dd>{entity.legal_type || "—"}</dd>
                  <dt className="text-muted-foreground">Registration #</dt>
                  <dd className="font-mono text-xs">{entity.registration_number || "—"}</dd>
                  <dt className="text-muted-foreground">Incorporation date</dt>
                  <dd>{fmtDate(entity.incorporation_date)}</dd>
                  <dt className="text-muted-foreground">Fiscal year end</dt>
                  <dd>{entity.fiscal_year_end || "—"}</dd>
                  <dt className="text-muted-foreground">Jurisdiction</dt>
                  <dd>
                    <JurisdictionBadge code={entity.jurisdiction_code} />
                  </dd>
                </dl>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6 space-y-4">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Country Lead
                </h3>
                {entity.country_lead ? (
                  <div className="flex items-center gap-3">
                    <Avatar className="h-12 w-12">
                      <AvatarFallback>
                        {userInitials(entity.country_lead.full_name)}
                      </AvatarFallback>
                    </Avatar>
                    <div>
                      <div className="font-medium">{entity.country_lead.full_name}</div>
                      <div className="text-xs text-muted-foreground">
                        {entity.country_lead.email}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground italic">Unassigned</div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="obligations">
          <Card className="overflow-hidden">
            {loadingObs ? (
              <div className="p-6 space-y-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-10" />
                ))}
              </div>
            ) : !obligations || obligations.length === 0 ? (
              <div className="p-10 text-center text-sm text-muted-foreground">
                No obligations for this entity yet.
              </div>
            ) : (
              <div className="divide-y divide-border">
                <div className="grid grid-cols-[2fr_1.5fr_1fr_120px_120px_120px] gap-3 px-4 py-3 bg-secondary/50 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  <div>Form / Report</div>
                  <div>Authority · Category</div>
                  <div>Period</div>
                  <div>Due date</div>
                  <div>Status</div>
                  <div>Assignee</div>
                </div>
                {obligations.slice(0, 100).map((ob) => (
                  <div
                    key={ob.id}
                    className="grid grid-cols-[2fr_1.5fr_1fr_120px_120px_120px] gap-3 px-4 py-3 items-center text-sm"
                  >
                    <div>
                      <div className="font-medium truncate">{ob.rule_form_name}</div>
                      <div className="text-xs text-muted-foreground truncate">{ob.rule_name}</div>
                    </div>
                    <div className="text-muted-foreground truncate">
                      {ob.rule_authority}
                      <span className="opacity-60"> · {ob.rule_category}</span>
                    </div>
                    <div className="text-xs text-muted-foreground">{ob.period_label || "—"}</div>
                    <div className="tabular-nums text-sm">{fmtShortDate(ob.due_date)}</div>
                    <div className="flex flex-col gap-1">
                      <StatusPill status={ob.status} isOverdue={ob.is_overdue} />
                      <StatusPill
                        status={ob.status}
                        isOverdue={ob.is_overdue}
                        daysRemaining={ob.days_remaining}
                        showDays
                      />
                    </div>
                    <div>
                      {ob.assignee ? (
                        <div className="flex items-center gap-2">
                          <Avatar className="h-6 w-6">
                            <AvatarFallback className="text-[10px]">
                              {userInitials(ob.assignee.full_name)}
                            </AvatarFallback>
                          </Avatar>
                          <span className="text-xs truncate">
                            {ob.assignee.full_name.split(" ")[0]}
                          </span>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground italic">Unassigned</span>
                      )}
                    </div>
                  </div>
                ))}
                {obligations.length > 100 && (
                  <div className="p-3 text-center text-xs text-muted-foreground">
                    Showing first 100 of {obligations.length}. Use filters to narrow further.
                  </div>
                )}
              </div>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="documents">
          <Card>
            <CardContent className="p-10 text-center text-sm text-muted-foreground">
              Document storage lands in Phase 4. Upload filings, certificates, and audit
              artifacts here.
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="activity">
          <Card>
            <CardContent className="p-10 text-center text-sm text-muted-foreground">
              The audit log of who-did-what for this entity lands in Phase 4.
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
