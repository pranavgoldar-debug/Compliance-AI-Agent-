// Entity Detail — one specific legal entity with tabs: Overview, Registrations,
// Compliance Items, Documents, Key Persons, Activity / Audit Log. Most tabs
// are filled with realistic demo content; real CRUD lands in Phase 5+.
import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Archive,
  Edit,
  Loader2,
  Lock,
  History,
  UserCheck,
  KeyRound,
  Plus,
  Trash2,
  Sparkles,
  ExternalLink,
} from "lucide-react";
import { AIExtractDialog, UploadDialog } from "@/pages/LicensesPage";
import { api } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { DateField } from "@/components/DateField";
import { FiscalYearEndPicker } from "@/components/FiscalYearEndPicker";
import { AddRegulationModal } from "@/components/AddRegulationModal";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/StatusPill";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { AssigneeChip } from "@/components/AssigneeChip";
import { EmptyState } from "@/components/EmptyState";
import { DocumentList } from "@/components/DocumentList";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";
import { useAuth } from "@/contexts/AuthContext";
import { deriveFunction, fmtDate, fmtRelative, fmtShortDate, userInitials } from "@/lib/format";
import { CountrySelect } from "@/components/CountrySelect";
import { gatesForJurisdiction, followupsForJurisdiction, thresholdForJurisdiction } from "@/lib/financeGates";
import { cn } from "@/lib/utils";
import type { ActivityOut, BankDetails, DocumentOut, Entity, GeneratedQuestion, License, Obligation, OwnershipStage, Rule } from "@/types/api";


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
    <div className="rounded-lg border border-border bg-card px-4 py-3 min-w-[110px]">
      <div className={cn("text-2xl font-semibold tabular-nums leading-tight", toneClasses)}>
        {value}
      </div>
      <div className="text-[11px] text-muted-foreground uppercase tracking-wide mt-0.5">{label}</div>
    </div>
  );
}


export function EntityDetailPage() {
  const { entityId } = useParams();
  const [tab, setTab] = useState("overview");
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const { data: entity, isLoading: loadingEntity } = useQuery({
    queryKey: ["entity", entityId],
    queryFn: () => api.get<Entity>(`/api/entities/${entityId}`),
    enabled: !!entityId,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });

  const { data: obligations, isLoading: loadingObs } = useQuery({
    queryKey: ["entity-obligations", entityId],
    queryFn: () => api.get<Obligation[]>(`/api/obligations?entity_id=${entityId}&limit=200`),
    enabled: !!entityId,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });

  const { data: entityLicenses = [] } = useQuery({
    queryKey: ["entity-licenses", entityId],
    queryFn: () => api.get<License[]>(`/api/licenses?entity_id=${entityId}`),
    enabled: !!entityId,
    refetchInterval: 30_000,
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

      <EntityHero entity={entity} isAdmin={isAdmin} />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="licenses">
            Licenses
            {entityLicenses.length > 0 && (
              <Badge variant="neutral" className="ml-1">
                {entityLicenses.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="primary-activity">Primary Activity</TabsTrigger>
          <TabsTrigger value="compliance">Compliance</TabsTrigger>
          <TabsTrigger value="documents">Documents</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab
            entity={entity}
            obligations={obligations ?? []}
            licenses={entityLicenses}
            onManageLicenses={() => setTab("licenses")}
            isAdmin={isAdmin}
          />
        </TabsContent>

        <TabsContent value="compliance">
          <RegulatoryAssessmentTab
            entity={entity}
            licenses={entityLicenses}
            isAdmin={isAdmin}
          />
        </TabsContent>

        <TabsContent value="licenses">
          <LicensesTab entity={entity} isAdmin={isAdmin} />
        </TabsContent>

        <TabsContent value="primary-activity">
          <ActivityProfileTab entity={entity} isAdmin={isAdmin} />
        </TabsContent>

        <TabsContent value="documents">
          <EntityDocumentsTab entity={entity} isAdmin={isAdmin} />
        </TabsContent>
      </Tabs>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Primary Activity — Yes / No / TBD flags, each revealing its follow-ups on
// "Yes". Questions start UNANSWERED; the answers only gate the follow-ups and
// drive the mandatory-vs-conditional assessment. They do NOT change what
// "Refresh Regulations" discovers — discovery always assumes every activity.
// ---------------------------------------------------------------------------
function ActivityProfileTab({ entity, isAdmin }: { entity: Entity; isAdmin: boolean }) {
  const queryClient = useQueryClient();
  const juris = entity.jurisdiction_code;
  const gates = gatesForJurisdiction(juris);
  const profile = entity.finance_profile ?? {};

  const saveProfile = useMutation({
    mutationFn: (next: Record<string, string>) =>
      api.patch<Entity>(`/api/entities/${entity.id}`, { finance_profile: next }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["entity"] }),
  });

  // Primary answers start UNANSWERED (TBD, "to be decided") — nothing is
  // pre-selected. They only
  // gate which follow-ups appear (those, plus the operation-specific questions,
  // are asked in the Compliance tab under Activities) and feed the
  // mandatory-vs-conditional assessment. They never change what "Refresh
  // Regulations" discovers — discovery always assumes every activity is present.
  const flagOf = (key: string): "yes" | "no" | "tbc" =>
    profile[key] === "yes" ? "yes" : profile[key] === "no" ? "no" : "tbc";
  const setFlag = (key: string, value: "yes" | "no" | "tbc") => {
    const next = { ...profile };
    if (value === "tbc") delete next[key];
    else next[key] = value;
    saveProfile.mutate(next);
  };

  const FLAG_OPTIONS: { value: "yes" | "no" | "tbc"; label: string; hint?: string }[] = [
    { value: "yes", label: "Yes" },
    { value: "no", label: "No" },
    { value: "tbc", label: "TBD", hint: "To be decided — not answered yet" },
  ];

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-5 space-y-3">
          <div>
            <h3 className="font-semibold">Primary activity</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              What this entity does. Answer <strong>Yes</strong> to the
              activities that apply; <strong>TBD</strong> ("to be decided")
              means it hasn't been answered yet. The follow-up and
              operation-specific questions are asked under{" "}
              <strong>Compliance → Activities</strong> and decide which
              discovered filings are mandatory vs conditional.
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              These answers do <strong>not</strong> change what{" "}
              <strong>Refresh Regulations</strong> discovers — that list always
              assumes every activity is present.
            </p>
            <p className="text-xs text-red-600 mt-1 font-medium">
              ⚠️ Don't change an answer unless the entity's actual activity has
              changed. It saves immediately and feeds the mandatory-vs-conditional
              assessment, so filings can flip between mandatory, conditional and
              not-applicable, and different follow-up questions apply. (It will
              not delete confirmed filings or change what Refresh Regulations
              discovers.)
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {gates.map((g) => {
              const current = flagOf(g.key);
              return (
                <div
                  key={g.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background/60 px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="text-sm truncate">{g.question}</div>
                    <div className="text-[11px] text-muted-foreground truncate">
                      {g.drives}
                    </div>
                  </div>
                  <div className="inline-flex rounded-md border border-input overflow-hidden shrink-0">
                    {FLAG_OPTIONS.map((o) => (
                      <button
                        key={o.value}
                        type="button"
                        title={o.hint}
                        disabled={!isAdmin || saveProfile.isPending}
                        onClick={() => setFlag(g.key, o.value)}
                        className={cn(
                          "px-2.5 py-1 text-xs transition-colors disabled:opacity-60",
                          current === o.value
                            ? o.value === "yes"
                              ? "bg-emerald-500 text-white"
                              : o.value === "no"
                                ? "bg-slate-700 text-white"
                                : "bg-secondary text-foreground"
                            : "bg-background hover:bg-secondary text-muted-foreground",
                          o.value !== "yes" && "border-l border-input",
                        )}
                      >
                        {o.label}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Detailed Questions — country/entity-specific scoping, AFTER AI discovery.
// Narrows the generated filings down to what's actually mandatory.
// ---------------------------------------------------------------------------
function DetailedQuestionsTab({ entity, isAdmin }: { entity: Entity; isAdmin: boolean }) {
  const queryClient = useQueryClient();
  const juris = entity.jurisdiction_code;
  const gates = gatesForJurisdiction(juris);
  // Local optimistic copy so clicks update instantly; saved in the background.
  const [profile, setProfile] = useState<Record<string, string>>(
    entity.finance_profile ?? {},
  );
  useEffect(() => {
    setProfile(entity.finance_profile ?? {});
  }, [entity.finance_profile]);
  const saveProfile = useMutation({
    mutationFn: (next: Record<string, string>) =>
      api.patch<Entity>(`/api/entities/${entity.id}`, { finance_profile: next }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["entity"] }),
  });
  const setAnswer = (key: string, value: string) => {
    const next = { ...profile, [key]: value };
    setProfile(next);
    saveProfile.mutate(next);
  };

  // Only show follow-ups for activities that apply (answered "Yes") and that
  // exist for this jurisdiction — so the set changes per entity/country.
  const detailGates = gates.filter(
    (g) => profile[g.key] === "yes" && followupsForJurisdiction(g, juris).length > 0,
  );

  return (
    <Card>
      <CardContent className="p-5 space-y-3">
        <div>
          <h3 className="font-semibold">Secondary activity</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Jurisdiction- and threshold-specific questions used to{" "}
            <strong>filter out</strong> what doesn't apply. Once you've run{" "}
            <strong>Refresh Regulations</strong> under Compliance Rules, your
            answers here decide which of the discovered filings stay mandatory,
            which become conditional, and which are dropped. See the outcome
            under Registrations.
          </p>
        </div>
        {detailGates.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No detailed questions yet. Set the Activity Profile (mark the
            relevant activities "Yes") and the jurisdiction-specific questions
            will appear here.
          </p>
        ) : (
          <div className="space-y-3">
            {detailGates.map((g) => (
              <div key={g.id} className="rounded-lg border border-border bg-background/60 px-3 py-2.5">
                <div className="text-xs font-medium text-aspora-700 mb-2">{g.drives}</div>
                <div className="space-y-2.5">
                  {followupsForJurisdiction(g, juris).map((f) => {
                    const threshold = thresholdForJurisdiction(f, juris);
                    return (
                    <div
                      key={f.key}
                      className="flex items-center justify-between gap-3 flex-wrap"
                    >
                      <div className="min-w-0">
                        <div className="text-sm">{f.question}</div>
                        {threshold && (
                          <div className="text-[11px] text-muted-foreground mt-0.5">
                            {threshold}
                          </div>
                        )}
                      </div>
                      <div className="inline-flex flex-wrap gap-1">
                        {f.options.map((o) => (
                          <button
                            key={o.value}
                            type="button"
                            disabled={!isAdmin}
                            onClick={() => setAnswer(f.key, o.value)}
                            className={cn(
                              "rounded-md border px-2.5 py-1 text-xs transition-colors disabled:opacity-60",
                              profile[f.key] === o.value
                                ? "border-aspora-500 bg-aspora-50 text-aspora-700 font-medium"
                                : "border-input bg-background hover:bg-secondary text-muted-foreground",
                            )}
                          >
                            {o.label}
                          </button>
                        ))}
                      </div>
                    </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Regulatory assessment — the unified Compliance tab. One page, top to bottom:
//   1. Refresh Regulations (exhaustive discovery)        — ComplianceRulesTab
//   2. Primary activity questions (fixed 12)             — ActivityProfileTab
//   3. Adaptive qualification questions (AI-generated)   — DynamicQuestionsCard
//   4. Reassess → final inventory → Add to Review&Assign — ApplicabilitySection
// ---------------------------------------------------------------------------
function RegulatoryAssessmentTab({
  entity,
  licenses,
  isAdmin,
}: {
  entity: Entity;
  licenses: License[];
  isAdmin: boolean;
}) {
  // Shared so the same Function/Category filter applies to the discovered list
  // AND the applicable-regulations inventory below.
  const [fnFilter, setFnFilter] = useState("");
  const [catFilter, setCatFilter] = useState("");
  return (
    <div className="space-y-4">
      <ComplianceRulesTab
        entity={entity}
        licenses={licenses}
        isAdmin={isAdmin}
        fnFilter={fnFilter}
        setFnFilter={setFnFilter}
        catFilter={catFilter}
        setCatFilter={setCatFilter}
        afterHeader={
          <ApplicabilitySection
            entity={entity}
            isAdmin={isAdmin}
            fnFilter={fnFilter}
            catFilter={catFilter}
          />
        }
      />
    </div>
  );
}


// One generated (secondary) question rendered as an option row.
function GeneratedQuestionRow({
  q,
  value,
  onPick,
  disabled,
}: {
  q: GeneratedQuestion;
  value: string | undefined;
  onPick: (v: string) => void;
  disabled: boolean;
}) {
  // Multi-select answers are stored as a comma-joined string, so a single value
  // type still covers both single- and multi-select questions.
  const multi = !!q.multi_select;
  const selected = multi ? (value ? value.split(",").filter(Boolean) : []) : [];
  const isOn = (v: string) => (multi ? selected.includes(v) : value === v);
  const pick = (v: string) => {
    if (!multi) return onPick(v);
    const next = selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v];
    onPick(next.join(","));
  };
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="min-w-0">
        <div className="text-sm">
          {q.question}
          {multi && (
            <span className="text-[11px] text-muted-foreground"> · select all that apply</span>
          )}
        </div>
        {q.drives && <div className="text-[11px] text-muted-foreground">{q.drives}</div>}
      </div>
      <div className="inline-flex flex-wrap gap-1">
        {q.options.map((o) => (
          <button
            key={o.value}
            type="button"
            disabled={disabled}
            onClick={() => pick(o.value)}
            className={cn(
              "rounded-md border px-2.5 py-1 text-xs transition-colors disabled:opacity-60",
              isOn(o.value)
                ? "border-aspora-500 bg-aspora-50 text-aspora-700 font-medium"
                : "border-input bg-background hover:bg-secondary text-muted-foreground",
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}


// Mirror the backend dedupe signature (normalized name/form + cadence) so the
// "Add to Review" action never promotes a discovered draft that already exists
// in Review or Confirmed.
const _STOP_WORDS = ["the", "a", "an", "of", "for", "to", "and", "filing", "form"];
function _normName(s?: string | null): string {
  return (s || "")
    .toLowerCase()
    .replace(/\([^)]*\)/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .split(" ")
    .filter((w) => w && !_STOP_WORDS.includes(w))
    .map((w) => (w.length >= 4 && w.endsWith("s") ? w.slice(0, -1) : w))
    .sort()
    .join(" ");
}
function ruleSigs(name?: string | null, form?: string | null, freq?: string | null): string[] {
  const f = (freq || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  return [_normName(name), _normName(form)].filter(Boolean).map((k) => `${k}|${f}`);
}


// "Activities" → a pop-up questionnaire (fixed primary questions, each
// revealing its AI-generated follow-ups when set to "Yes", plus operation-
// specific questions). On "Find applicable regulations" the AI reads the
// answers + discovered list and returns the inventory shown below.
function ApplicabilitySection({
  entity,
  isAdmin,
  fnFilter = "",
  catFilter = "",
}: {
  entity: Entity;
  isAdmin: boolean;
  fnFilter?: string;
  catFilter?: string;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  // Only show this section once discovery has produced items for the entity.
  const { data: staging = [] } = useQuery({
    queryKey: ["rules", "staging", entity.id],
    queryFn: () => api.get<Rule[]>(`/api/rules?status=staging&entity_id=${entity.id}`),
  });
  const { data: production = [] } = useQuery({
    queryKey: ["rules", "production", entity.id],
    queryFn: () => api.get<Rule[]>(`/api/rules?status=production&entity_id=${entity.id}`),
  });
  const hasDiscovered = [...staging, ...production].some((r) =>
    r.entity_ids.includes(entity.id),
  );
  const gates = gatesForJurisdiction(entity.jurisdiction_code);
  const qual = entity.qualification ?? {};
  const questions = qual.questions ?? [];
  const secAnswers = qual.answers ?? {};
  const profile = entity.finance_profile ?? {};

  const generate = useMutation({
    mutationFn: () => api.post(`/api/entities/${entity.id}/generate-questions`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["entity"] }),
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });
  const savePrimary = useMutation({
    mutationFn: (next: Record<string, string>) =>
      api.patch<Entity>(`/api/entities/${entity.id}`, { finance_profile: next }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["entity"] });
      queryClient.invalidateQueries({ queryKey: ["gaps", entity.id] });
    },
  });
  const saveSecondary = useMutation({
    mutationFn: (next: Record<string, string>) =>
      api.patch<Entity>(`/api/entities/${entity.id}`, {
        qualification: { ...qual, answers: next },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["entity"] }),
  });
  const setAnswer = (key: string, value: string) =>
    saveSecondary.mutate({ ...secAnswers, [key]: value });
  // Standard primary follow-ups (VAT frequency, TP threshold, …) save onto the
  // finance_profile, like the primary flags.
  const setProfileAnswer = (key: string, value: string) =>
    savePrimary.mutate({ ...profile, [key]: value });

  // The result the server has already persisted for this entity. The assess
  // endpoint saves it in TWO places — last_assessment and qualification.assessment
  // — so read both: whichever the deployed backend wrote restores the inventory.
  // It comes back on every entity fetch, so it survives navigation, reload, and
  // new sessions; the AI only re-runs on an explicit click.
  const laItems = (entity.last_assessment?.items as AssessItem[] | undefined) ?? undefined;
  const qaItems =
    (entity.qualification as unknown as { assessment?: AssessItem[] } | null)?.assessment ??
    undefined;
  const persistedItems = laItems ?? qaItems;
  const persisted: AssessResp | undefined = persistedItems
    ? {
        available: true,
        items: persistedItems,
        notes: entity.last_assessment?.notes ?? null,
      }
    : undefined;
  // Find applicable regulations — AI reads answers + discovered list. Seeded from
  // the persisted result so the inventory shows on every mount even if the
  // in-memory cache was dropped; only re-runs the AI on an explicit click.
  const assess = useQuery<AssessResp>({
    queryKey: ["assess", entity.id],
    queryFn: () => api.post<AssessResp>(`/api/entities/${entity.id}/assess-obligations`),
    enabled: false,
    staleTime: Infinity,
    gcTime: Infinity,
    initialData: persisted,
    retry: false,
  });
  useEffect(() => {
    if (assess.isError && assess.error) {
      window.alert(assess.error instanceof Error ? assess.error.message : String(assess.error));
    }
  }, [assess.isError, assess.error]);
  // Fresh run wins; otherwise fall back to the persisted result. Either way it
  // only recomputes (and spends tokens) when the user re-runs explicitly.
  const result = assess.data ?? persisted;
  // Apply the shared Function/Category filter to the inventory too.
  const items = (result?.items ?? []).filter(
    (i) =>
      (!fnFilter || (i.function || "") === fnFilter) &&
      (!catFilter || (i.category || "") === catFilter),
  );
  const grp = (v: string) => items.filter((i) => i.verdict === v);
  const mandatory = grp("mandatory");
  const conditional = grp("conditional");
  const notApplicable = grp("not_applicable");

  const [picked, setPicked] = useState<Set<string>>(new Set());
  // Default-tick mandatory + conditional. Keyed on the result's form names (a
  // stable string) so the selection also initializes when the result is
  // restored from the persisted entity.last_assessment after navigation — not
  // only on a fresh run (which the old [assess.data] dependency missed).
  const resultKey = (result?.items ?? []).map((i) => i.form_name).join("|");
  useEffect(() => {
    if (result) {
      setPicked(
        new Set(
          (result.items ?? [])
            // Default-tick ONLY mandatory; conditional + not-applicable start
            // unticked so the user opts those into Review & Assign deliberately.
            .filter((i) => i.verdict === "mandatory")
            .map((i) => i.form_name),
        ),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultKey]);
  const toggle = (form: string) =>
    setPicked((p) => {
      const n = new Set(p);
      n.has(form) ? n.delete(form) : n.add(form);
      return n;
    });

  const addToReview = useMutation({
    mutationFn: async () => {
      // Only the TICKED items move to Review & Assign. Unticked items (incl.
      // the not-applicable column) are LEFT AS-IS as discovered drafts — never
      // auto-archived. Archiving is a manual action only.
      const itemRuleIds = new Set(items.map((i) => i.rule_id));
      const existing = new Set<string>();
      for (const r of [...staging.filter((r) => r.sent_to_review), ...production]) {
        if (itemRuleIds.has(r.id)) continue;
        ruleSigs(r.name, r.form_name, r.frequency).forEach((s) => existing.add(s));
      }
      let skipped = 0;
      await Promise.all(
        items
          .filter((i) => i.rule_id && picked.has(i.form_name))
          .map((i) => {
            const dup = ruleSigs(i.name, i.form_name, i.frequency).some((s) => existing.has(s));
            if (dup) {
              // Already in Review & Assign — skip (leave the draft as-is, don't
              // archive it).
              skipped++;
              return Promise.resolve();
            }
            return api.patch(`/api/rules/${i.rule_id}`, {
              status: "staging",
              sent_to_review: true,
              applicability: i.verdict === "mandatory" ? "Mandatory" : "Conditional",
            });
          }),
      );
      return skipped;
    },
    onSuccess: (skipped) => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["obligations"] });
      const note = skipped ? ` ${skipped} skipped — already in Review & Assign.` : "";
      window.alert(`${picked.size - skipped} obligation(s) sent to Review & Assign.${note}`);
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  // Hidden until "Refresh Regulations" has produced discovered items. But once
  // an assessment has been run, keep showing it even if the staging/production
  // rule queries momentarily report nothing on remount (tab switch) — otherwise
  // the result would vanish until the user re-runs "Find applicable regulations".
  if (!hasDiscovered && !result) return null;

  const gateKeys = new Set(gates.map((g) => g.key));
  const followupsFor = (primaryKey: string) =>
    questions.filter((q) => q.primary_key === primaryKey);
  const generalQuestions = questions.filter(
    (q) => !q.primary_key || !gateKeys.has(q.primary_key),
  );

  // Dedupe follow-ups: the AI often regenerates a question that already exists
  // as a static follow-up (e.g. pension/social security), so the same question
  // can show twice. Normalize the text (drop parenthetical examples + casing)
  // and keep the first occurrence only, sweeping static → AI → general in the
  // same order they render so the static/canonical copy wins.
  const norm = (s: string) =>
    s.toLowerCase().replace(/\([^)]*\)/g, "").replace(/[^a-z0-9]+/g, " ").trim();
  const seen = new Set<string>();
  const take = (text: string) => {
    const k = norm(text);
    if (!k || seen.has(k)) return false;
    seen.add(k);
    return true;
  };
  const gateFollowups: Record<
    string,
    {
      staticFups: ReturnType<typeof followupsForJurisdiction>;
      aiFups: GeneratedQuestion[];
    }
  > = {};
  for (const g of gates) {
    const isYes = profile[g.key] === "yes";
    const staticFups = (
      isYes ? followupsForJurisdiction(g, entity.jurisdiction_code) : []
    ).filter((f) => take(f.question));
    const aiFups = (isYes ? followupsFor(g.key) : []).filter((q) =>
      take(q.question),
    );
    gateFollowups[g.key] = { staticFups, aiFups };
  }
  const generalToShow = generalQuestions.filter((q) => take(q.question));

  // Primary answers are set in the Primary Activity tab — the popup asks ONLY
  // the follow-ups (for activities marked "Yes" there) and the operation-
  // specific questions. The verdict still reads BOTH primary and follow-up
  // answers server-side.
  const gatesWithFollowups = gates.filter((g) => {
    const { staticFups, aiFups } = gateFollowups[g.key];
    return staticFups.length > 0 || aiFups.length > 0;
  });

  const openActivities = () => {
    if (questions.length === 0 && isAdmin) generate.mutate();
    setOpen(true);
  };
  const findApplicable = async () => {
    setOpen(false);
    await assess.refetch();
    // Refresh the entity so its server-persisted `last_assessment` (saved by the
    // assess endpoint) is loaded into the entity cache immediately. That makes
    // `entity.last_assessment` the durable source for the result, so it survives
    // left-sidebar navigation and full reloads — not just in-page tab switches
    // (which were the only thing the volatile assess.data cache covered).
    // Navigation never re-runs the AI (the query stays enabled:false), so no
    // tokens are spent on revisits.
    queryClient.invalidateQueries({ queryKey: ["entity"] });
  };

  const Col = ({ title, list, tone }: { title: string; list: AssessItem[]; tone: "alert" | "neutral" | "muted" }) => (
    <div
      className={cn(
        "rounded-lg border p-3",
        tone === "alert"
          ? "border-amber-200 bg-amber-50/50"
          : tone === "neutral"
            ? "border-emerald-200 bg-emerald-50/40"
            : "border-border bg-secondary/30",
      )}
    >
      <div className="flex items-center gap-2 mb-2">
        <Badge variant={tone === "alert" ? "alert" : tone === "neutral" ? "completed" : "neutral"}>
          {list.length}
        </Badge>
        <span className="text-sm font-medium">{title}</span>
      </div>
      {list.length === 0 ? (
        <p className="text-xs text-muted-foreground">None.</p>
      ) : (
        <ul className="space-y-1.5 text-sm">
          {list.map((i) => (
            <li key={i.form_name} className="flex items-start gap-2">
              <input
                type="checkbox"
                className="mt-1 accent-aspora-600 shrink-0"
                checked={picked.has(i.form_name)}
                onChange={() => toggle(i.form_name)}
              />
              <div className="min-w-0">
                <div className="font-medium">
                  {i.name}
                  {i.frequency && (
                    <span className="text-[11px] text-muted-foreground"> · {i.frequency}</span>
                  )}
                </div>
                {i.reason && <div className="text-[11px] text-muted-foreground">{i.reason}</div>}
                {i.next_due && (
                  <div className="text-[11px] font-medium text-foreground">
                    Next due: {fmtDate(i.next_due)}
                  </div>
                )}
                {i.due && <div className="text-[11px] text-muted-foreground">{i.due}</div>}
                {i.source_url && /^https?:\/\//i.test(i.source_url) && (
                  <a
                    href={i.source_url}
                    target="_blank"
                    rel="noreferrer"
                    title="Official authority website — verify the filing here."
                    className="text-[11px] text-aspora-600 hover:underline inline-flex items-center gap-1"
                  >
                    <ExternalLink className="h-3 w-3" />
                    Verify at source
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  const renderQuestion = (q: GeneratedQuestion) => (
    <GeneratedQuestionRow
      key={q.key}
      q={q}
      value={secAnswers[q.key]}
      onPick={(v) => setAnswer(q.key, v)}
      disabled={!isAdmin || saveSecondary.isPending}
    />
  );

  // Standard follow-up for a primary gate (e.g. VAT → monthly/quarterly/annual),
  // with the jurisdiction threshold shown where relevant.
  const renderStaticFollowup = (f: ReturnType<typeof followupsForJurisdiction>[number]) => {
    const th = thresholdForJurisdiction(f, entity.jurisdiction_code);
    return (
      <div key={f.key} className="flex items-center justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <div className="text-sm">{f.question}</div>
          {th && <div className="text-[11px] text-muted-foreground">{th}</div>}
        </div>
        <div className="inline-flex flex-wrap gap-1">
          {f.options.map((o) => (
            <button
              key={o.value}
              type="button"
              disabled={!isAdmin || savePrimary.isPending}
              onClick={() => setProfileAnswer(f.key, o.value)}
              className={cn(
                "rounded-md border px-2.5 py-1 text-xs transition-colors disabled:opacity-60",
                profile[f.key] === o.value
                  ? "border-aspora-500 bg-aspora-50 text-aspora-700 font-medium"
                  : "border-input bg-background hover:bg-secondary text-muted-foreground",
              )}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>
    );
  };

  return (
    <>
      {/* Call-to-action: open the Activities questionnaire */}
      <Card>
        <CardContent className="p-5 flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h3 className="font-semibold">See what's required</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Answer a few questions about this entity to filter the discovered
              list down to what's mandatory and applicable.
            </p>
          </div>
          {isAdmin && (
            <Button onClick={openActivities}>
              <Sparkles className="h-4 w-4" />
              Activities
            </Button>
          )}
        </CardContent>
      </Card>

      {assess.isFetching && (
        <Card>
          <CardContent className="p-5 flex items-center gap-3 text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin text-aspora-600" />
            Finding applicable regulations… (~15–25s)
          </CardContent>
        </Card>
      )}

      {!assess.isFetching && result && items.length > 0 && (
        <Card>
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2 text-xs flex-wrap">
                <span className="rounded-full bg-secondary px-2.5 py-1 font-medium">
                  {items.length} identified
                </span>
                <span className="text-muted-foreground">→</span>
                <span className="rounded-full bg-amber-100 text-amber-800 px-2.5 py-1 font-medium">
                  {mandatory.length} mandatory
                </span>
                <span className="rounded-full bg-emerald-100 text-emerald-800 px-2.5 py-1 font-medium">
                  {conditional.length} conditional
                </span>
                <span className="rounded-full bg-slate-100 text-slate-700 px-2.5 py-1 font-medium">
                  {notApplicable.length} not applicable
                </span>
              </div>
              {isAdmin && (
                <Button size="sm" onClick={() => addToReview.mutate()} disabled={addToReview.isPending}>
                  {addToReview.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Add {picked.size} to Review &amp; Assign
                </Button>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground">
              <strong>Mandatory</strong> — required for this entity now.{" "}
              <strong>Conditional</strong> — applies only if a threshold or
              trigger is met; confirm via the follow-up questions.{" "}
              <strong>Not applicable</strong> — ruled out by this entity's
              activity answers, so it won't be filed.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Col title="Mandatory" list={mandatory} tone="alert" />
              <Col title="Conditional" list={conditional} tone="neutral" />
              <Col title="Not applicable" list={notApplicable} tone="muted" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Activities pop-up */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>Activities</DialogTitle>
          </DialogHeader>
          <div className="p-6 space-y-3 max-h-[65vh] overflow-y-auto">
            <p className="text-xs text-muted-foreground">
              Follow-up and operation-specific questions — tailored to this
              entity's nature of operations and jurisdiction — that refine the
              discovered list. Set the entity's activities under{" "}
              <strong>Primary Activity</strong> first, then answer these and
              click <strong>Find applicable regulations</strong>.
            </p>
            {generate.isPending ? (
              <div className="flex items-center gap-3 py-4 text-sm text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin text-aspora-600" />
                Generating questions… (~15–25s)
              </div>
            ) : (
              <>
                {gatesWithFollowups.length === 0 && generalToShow.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No follow-up questions yet. Mark the relevant activities{" "}
                    <strong>Yes</strong> under <strong>Primary Activity</strong>{" "}
                    and their follow-ups will appear here.
                  </p>
                ) : (
                  <>
                    {gatesWithFollowups.length > 0 && (
                      <div className="space-y-2">
                        {gatesWithFollowups.map((g) => {
                          const { staticFups, aiFups: fups } = gateFollowups[g.key];
                          return (
                            <div
                              key={g.id}
                              className="rounded-lg border border-border bg-background/60 px-3 py-2.5"
                            >
                              <div className="text-xs font-medium text-aspora-700 mb-2">
                                {g.drives}
                              </div>
                              <div className="space-y-2.5">
                                {staticFups.map(renderStaticFollowup)}
                                {fups.map(renderQuestion)}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {generalToShow.length > 0 && (
                      <div className="space-y-2.5 pt-1">
                        <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                          Operation-specific
                        </div>
                        {generalToShow.map(renderQuestion)}
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Close
            </Button>
            <Button onClick={findApplicable} disabled={generate.isPending}>
              <Sparkles className="h-4 w-4" />
              Find applicable regulations
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}


// ---------------------------------------------------------------------------
// Compliance Rules — AI-generated obligations awaiting review + confirmed ones
// ---------------------------------------------------------------------------
function ComplianceRulesTab({
  entity,
  licenses,
  isAdmin,
  afterHeader,
  fnFilter,
  setFnFilter,
  catFilter,
  setCatFilter,
}: {
  entity: Entity;
  licenses: License[];
  isAdmin: boolean;
  afterHeader?: ReactNode;
  fnFilter: string;
  setFnFilter: (v: string) => void;
  catFilter: string;
  setCatFilter: (v: string) => void;
}) {
  const queryClient = useQueryClient();

  const { data: staging = [], isLoading: loadingStaging } = useQuery({
    queryKey: ["rules", "staging", entity.id],
    queryFn: () => api.get<Rule[]>(`/api/rules?status=staging&entity_id=${entity.id}`),
  });
  const { data: production = [], isLoading: loadingProd } = useQuery({
    queryKey: ["rules", "production", entity.id],
    queryFn: () => api.get<Rule[]>(`/api/rules?status=production&entity_id=${entity.id}`),
  });

  const review = staging.filter((r) => r.entity_ids.includes(entity.id));
  const confirmed = production.filter((r) => r.entity_ids.includes(entity.id));

  // Regulatory-body filter for the discovered list. Options derive from the
  // discovered rules' authorities — which are this entity's jurisdiction's
  // regulators — so the list changes with the jurisdiction.
  const [regFilter, setRegFilter] = useState("");

  // Filters for the discovered list — by function and category. Fall back to a
  // client-side derive when the server hasn't set responsible_function.
  const allDiscovered = [...review, ...confirmed];
  const fnOf = (r: Rule) => r.responsible_function || deriveFunction(r.category, r.area);
  // Always offer the four canonical teams (in order), plus any unexpected extra
  // the data carries — so Compliance is selectable even when, on first load, no
  // row currently resolves to it.
  const CANON_FUNCTIONS = ["Finance", "Compliance", "Legal", "HR"];
  const extraFns = Array.from(new Set(allDiscovered.map(fnOf)))
    .filter((f) => f && !CANON_FUNCTIONS.includes(f))
    .sort();
  const functions = [...CANON_FUNCTIONS, ...extraFns];
  const categories = Array.from(
    new Set(allDiscovered.map((r) => r.category).filter(Boolean)),
  ).sort();
  const regulators = Array.from(
    new Set(allDiscovered.map((r) => r.authority).filter(Boolean)),
  ).sort();
  const matchFilter = (r: Rule) =>
    (!fnFilter || fnOf(r) === fnFilter) &&
    (!catFilter || r.category === catFilter) &&
    (!regFilter || r.authority === regFilter);
  const reviewShown = review.filter(matchFilter);
  const confirmedShown = confirmed.filter(matchFilter);
  const [addManualOpen, setAddManualOpen] = useState(false);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["rules"] });
    queryClient.invalidateQueries({ queryKey: ["calendar"] });
    queryClient.invalidateQueries({ queryKey: ["obligations"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["gaps", entity.id] });
  };

  const reject = useMutation({
    mutationFn: (id: number) => api.delete(`/api/rules/${id}`),
    onSuccess: refresh,
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  // Entity-level discovery — driven by Nature of Operations + jurisdiction +
  // ALL licenses. Requires at least one license AND a nature of operations
  // (gated below + enforced by the backend with a 400).
  const discover = useMutation<{ available: boolean; created: number; added?: string[]; already_present?: number; duplicates_removed?: number; notes?: string | null }>({
    mutationFn: () => api.post(`/api/entities/${entity.id}/discover-regulations`),
    onSuccess: (r) => {
      refresh();
      if (r && r.available === false) {
        window.alert(r.notes || "AI is off in this deployment.");
      } else if (r) {
        // Only NEW filings (not already in this entity's list) get added; show
        // exactly which ones, plus how many were already present, so a second
        // run — or a different function's owner — sees just what's missing.
        const present = r.already_present
          ? ` ${r.already_present} were already in your list.`
          : "";
        const removed = r.duplicates_removed
          ? ` ${r.duplicates_removed} duplicate(s) removed.`
          : "";
        if (r.created === 0) {
          window.alert(
            `Nothing new to add — everything discovered is already in your list.${present}${removed}`,
          );
        } else {
          const names = (r.added ?? []).map((n) => `• ${n}`).join("\n");
          window.alert(
            `${r.created} new regulation(s) added:\n${names}\n${present}${removed}\n\n` +
              `Review them below, run "Activities" → "Find applicable regulations", then send the ones you want to Review & Assign.`,
          );
        }
      }
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  // Hard gate: discovery requires BOTH a license on file AND a stated nature
  // of operations (the backend enforces this with a 400). Reflect it in the UI
  // so the action is disabled with a reason rather than failing on click.
  const hasLicense = (licenses?.length ?? 0) > 0;
  const hasNature = Boolean(entity.nature_of_operation && entity.nature_of_operation.trim());
  const canDiscover = hasLicense && hasNature;
  const discoverBlockedReason = !hasLicense
    ? "Upload at least one license for this entity first."
    : !hasNature
      ? "Set the entity's nature of operations first."
      : "";
  // Both staging + confirmed forms, so a re-run doesn't duplicate what's
  // already in Review or Confirmed.
  const confirmedForms = [...confirmed, ...review].map((r) => r.form_name || r.name);

  const RuleRow = ({ r, mode }: { r: Rule; mode: "review" | "confirmed" }) => {
    // Applicability is only signalled on the CONFIRMED list (dimmed = ruled out
    // by this entity's activity answers). The discovered/draft list is the raw
    // candidate set — every row renders identically; applicability is decided by
    // "Find applicable regulations", not pre-judged here with the keyword gate.
    const na = mode === "confirmed" && r.entity_applicability === "not_applicable";
    return (
    <div
      title={na ? "Not applicable to this entity based on its activity answers." : undefined}
      className={cn(
        "flex items-start justify-between gap-3 rounded-lg border border-border bg-background/60 px-3 py-2.5",
        na && "opacity-60",
      )}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm">{r.name}</span>
          {/* Discovered list is the exhaustive candidate set (assume all
              activities present) — no applicability label here; that's decided
              by "Find applicable regulations" below. */}
          {mode === "confirmed" && !na && (
            <Badge variant={r.applicability === "Mandatory" ? "alert" : "neutral"}>
              {r.applicability}
            </Badge>
          )}
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">
          {r.authority} · {r.category} · {r.frequency}
        </div>
      </div>
      {isAdmin && mode === "confirmed" && (
        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            size="sm"
            variant="ghost"
            className="text-muted-foreground hover:text-destructive"
            onClick={() => {
              if (window.confirm(`Remove "${r.name}" from this entity's confirmed rules?`)) {
                reject.mutate(r.id);
              }
            }}
            disabled={reject.isPending}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
    </div>
    );
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-5 space-y-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <h3 className="font-semibold">Compliance rules</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                AI discovers the regulations this entity could owe — from its
                Nature of Operations, jurisdiction and any uploaded licenses.
              </p>
            </div>
            {isAdmin && (
              <div className="flex flex-wrap items-center gap-2 shrink-0">
                <Button variant="outline" onClick={() => setAddManualOpen(true)}>
                  <Plus className="h-4 w-4" />
                  Add regulation
                </Button>
                <Button
                  onClick={() => discover.mutate()}
                  disabled={discover.isPending || !canDiscover}
                  title={discoverBlockedReason || undefined}
                >
                  {discover.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4" />
                  )}
                  Refresh Regulations
                </Button>
              </div>
            )}
          </div>
          {discover.isPending && (
            <p className="text-xs text-muted-foreground pt-1 flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin text-aspora-600" />
              Finding all applicable regulations for this entity… (~20–30s)
            </p>
          )}
          {/* Discovery funnel: discovered → in review → confirmed. Reflects the
              active filter. */}
          {(review.length > 0 || confirmed.length > 0) && (
            <div className="flex items-center gap-2 pt-2 text-xs flex-wrap">
              <span className="rounded-full bg-secondary px-2.5 py-1 font-medium">
                {reviewShown.length + confirmedShown.length} discovered
              </span>
              <span className="text-muted-foreground">→</span>
              <span className="rounded-full bg-amber-100 text-amber-800 px-2.5 py-1 font-medium">
                {reviewShown.length} draft
              </span>
              <span className="text-muted-foreground">→</span>
              <span className="rounded-full bg-emerald-100 text-emerald-800 px-2.5 py-1 font-medium">
                {confirmedShown.length} confirmed
              </span>
              {confirmedShown.length > 0 && (
                <span className="text-muted-foreground">
                  ({confirmedShown.filter((r) => r.applicability === "Mandatory").length} mandatory ·{" "}
                  {confirmedShown.filter((r) => r.applicability !== "Mandatory").length} conditional)
                </span>
              )}
            </div>
          )}
          {allDiscovered.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 pt-2">
              <select
                value={fnFilter}
                onChange={(e) => setFnFilter(e.target.value)}
                className="h-8 min-w-[140px] rounded-md border border-input bg-background px-2 text-xs"
              >
                <option value="">All functions</option>
                {functions.map((f) => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
              <select
                value={catFilter}
                onChange={(e) => setCatFilter(e.target.value)}
                className="h-8 min-w-[150px] rounded-md border border-input bg-background px-2 text-xs"
              >
                <option value="">All categories</option>
                {categories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <select
                value={regFilter}
                onChange={(e) => setRegFilter(e.target.value)}
                className="h-8 min-w-[160px] rounded-md border border-input bg-background px-2 text-xs"
              >
                <option value="">All regulatory bodies</option>
                {regulators.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
              {(fnFilter || catFilter || regFilter) && (
                <button
                  onClick={() => {
                    setFnFilter("");
                    setCatFilter("");
                    setRegFilter("");
                  }}
                  className="text-xs text-aspora-700 hover:underline"
                >
                  Clear
                </button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Activities / applicability flow — sits right under the header. */}
      {afterHeader}

      {/* Review (AI Generated) */}
      <Card>
        <CardContent className="p-5 space-y-3">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-sm">Discovered (AI generated)</h3>
            <Badge variant="alert">{reviewShown.length}</Badge>
            {(fnFilter || catFilter) && (
              <span className="text-xs text-muted-foreground">
                · {[fnFilter, catFilter].filter(Boolean).join(" · ")} (of {review.length})
              </span>
            )}
          </div>
          {loadingStaging ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
              <Loader2 className="h-4 w-4 animate-spin text-aspora-600" /> Loading…
            </div>
          ) : reviewShown.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {review.length === 0
                ? "Nothing awaiting review. Use “Refresh Regulations” to find obligations."
                : "No items match the current filter."}
            </p>
          ) : (
            <div className="space-y-2">
              {reviewShown.map((r) => (
                <RuleRow key={r.id} r={r} mode="review" />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Confirmed */}
      <Card>
        <CardContent className="p-5 space-y-3">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-sm">Confirmed</h3>
            <Badge variant="completed">{confirmedShown.length}</Badge>
          </div>
          {loadingProd ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
              <Loader2 className="h-4 w-4 animate-spin text-aspora-600" /> Loading…
            </div>
          ) : confirmedShown.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {confirmed.length === 0
                ? "No confirmed rules yet. Approve items from Review to add them here."
                : "No items match the current filter."}
            </p>
          ) : (
            <div className="space-y-2">
              {confirmedShown.map((r) => (
                <RuleRow key={r.id} r={r} mode="confirmed" />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <AddRegulationDialog
        entity={entity}
        open={addManualOpen}
        onOpenChange={setAddManualOpen}
        onAdded={refresh}
      />
    </div>
  );
}


// Manually add a regulation the AI missed — created as a draft on the entity
// (sent_to_review=false), so it joins the discovered list.
function AddRegulationDialog({
  entity,
  open,
  onOpenChange,
  onAdded,
}: {
  entity: Entity;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onAdded: () => void;
}) {
  // Map the modal's frequency ids + structured due-rule onto the backend schema.
  const FREQ_LABEL: Record<string, string> = {
    ANNUAL: "Annual", SEMI_ANNUAL: "Semi-annual", QUARTERLY: "Quarterly",
    MONTHLY: "Monthly", ONE_TIME: "One-time",
  };
  const FREQ_SPEC: Record<string, string> = {
    ANNUAL: "annual", SEMI_ANNUAL: "semiannual", QUARTERLY: "quarterly",
    MONTHLY: "monthly", ONE_TIME: "onetime",
  };
  const toSpec = (dr: any, freqId: string): Record<string, unknown> | null => {
    const f = FREQ_SPEC[freqId] || "annual";
    if (!dr) return null;
    if (dr.type === "SPECIFIC_DATE") return dr.date ? { frequency: "onetime", date: dr.date } : null;
    if (dr.type === "FIXED_DATE") return { frequency: f, basis: "fixed", day: dr.day, month: dr.month };
    if (dr.type === "OFFSET_FROM_FY_END" || dr.type === "OFFSET_FROM_PERIOD_END") {
      let unit = String(dr.offset_unit || "MONTHS").toLowerCase();
      let offset = dr.offset_value || 0;
      if (unit === "weeks") { unit = "days"; offset = offset * 7; }
      if (unit !== "days") unit = "months";
      return { frequency: f, basis: "after_period", offset, unit, snap_last: dr.day_anchor === "LAST_DAY_OF_MONTH" };
    }
    return null;
  };
  const mapTeam = (t: any): string | null => {
    const v = String(t || "").trim();
    if (v === "HR / Payroll") return "HR";
    return ["Finance", "Compliance", "Legal", "HR"].includes(v) ? v : null;
  };
  const toPayload = (rec: any) => {
    const nm = String(rec.filingName || "").trim() || "Untitled filing";
    return {
      name: nm,
      jurisdiction_code: entity.jurisdiction_code,
      category: String(rec.type || "").trim() || "Other",
      area: String(rec.subtype || "").trim(),
      form_name: nm,
      authority: String(rec.regulator || "").trim() || "—",
      frequency: FREQ_LABEL[rec.frequency as string] || String(rec.frequency || "Annual"),
      due_date_rule: String(rec.deadlineRuleText || "").trim() || "—",
      due_date_spec: toSpec(rec.dueRule, rec.frequency),
      applicability: "Mandatory",
      applicability_note: String(rec.applicability || "").trim() || null,
      responsible_function: mapTeam(rec.ownerTeam),
      plain_description: String(rec.description || "").trim() || null,
      source_url: String(rec.sourceUrl || "").trim() || null,
      status: "staging",
      sent_to_review: false,
      entity_ids: [entity.id],
    };
  };

  // Added regulations are DRAFTS on the discovered list (sent_to_review=false) —
  // they don't go to Review & Assign until a human sends them.
  const create = useMutation({
    mutationFn: (payloads: ReturnType<typeof toPayload>[]) =>
      Promise.all(payloads.map((p) => api.post("/api/rules", p))),
    onSuccess: () => {
      onAdded();
      onOpenChange(false);
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  return (
    <AddRegulationModal
      open={open}
      onClose={() => onOpenChange(false)}
      onSubmit={(rec) => create.mutate([toPayload(rec)])}
      onImport={(recs) => create.mutate(recs.map(toPayload))}
      jurisdiction={entity.jurisdiction_code}
    />
  );
}


// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------
function EntityHero({ entity, isAdmin }: { entity: Entity; isAdmin: boolean }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [editOpen, setEditOpen] = useState(false);

  const archiveMutation = useMutation({
    mutationFn: () => api.post<Entity>(`/api/entities/${entity.id}/archive`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      queryClient.invalidateQueries({ queryKey: ["entity", entity.id] });
      // Entity is now hidden from the list — bounce back to /entities.
      navigate("/entities");
    },
    onError: (e) => {
      window.alert(
        `Couldn't archive:\n\n${e instanceof Error ? e.message : String(e)}`,
      );
    },
  });

  return (
    <>
    <Card>
      <CardContent className="p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-4 min-w-0">
            <div
              className={cn(
                "h-14 w-14 rounded-xl bg-aspora-100 grid place-items-center text-aspora-700 font-bold shrink-0 leading-none text-center px-1",
                entity.short_code ? "text-base" : "text-xl",
              )}
            >
              {entity.short_code || userInitials(entity.name)}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-2xl font-semibold tracking-tight break-words">{entity.name}</h1>
                <JurisdictionBadge code={entity.jurisdiction_code} />
                <Badge variant="default">{entity.legal_type}</Badge>
              </div>
              <div className="text-sm text-muted-foreground mt-1 flex items-center gap-4 flex-wrap">
                <span>
                  Reg # <span className="font-mono text-foreground">{entity.registration_number || "—"}</span>
                </span>
                <span>·</span>
                <span>Formed {fmtDate(entity.incorporation_date)}</span>
                <span>·</span>
                <span>FYE {entity.fiscal_year_end || "—"}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              disabled={!isAdmin}
              title={isAdmin ? undefined : "Admin only"}
              onClick={() => isAdmin && setEditOpen(true)}
            >
              {isAdmin ? <Edit className="h-4 w-4" /> : <Lock className="h-3.5 w-3.5" />}
              Edit
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!isAdmin || archiveMutation.isPending}
              title={isAdmin ? undefined : "Admin only"}
              onClick={() => {
                if (!isAdmin) return;
                if (
                  window.confirm(
                    `Archive "${entity.name}"? It'll be hidden from the entities list. Existing obligations and licenses stay intact.`,
                  )
                ) {
                  archiveMutation.mutate();
                }
              }}
            >
              {archiveMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Archive className="h-4 w-4" />
              )}
              Archive
            </Button>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          <StatTile value={entity.active_obligations_count} label="Total active" />
          <StatTile value={entity.overdue_obligations_count} label="Overdue" tone="overdue" />
          <StatTile value={entity.in_alert_window_count} label="In alert window" tone="alert" />
        </div>
      </CardContent>
    </Card>
    <EditEntityDialog
      open={editOpen}
      onOpenChange={setEditOpen}
      entity={entity}
    />
    </>
  );
}


// ---------------------------------------------------------------------------
// Edit entity dialog
// ---------------------------------------------------------------------------
function EditEntityDialog({
  open,
  onOpenChange,
  entity,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  entity: Entity;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(entity.name);
  const [legalType, setLegalType] = useState(entity.legal_type);
  const [jurisdictionCode, setJurisdictionCode] = useState(entity.jurisdiction_code ?? "");
  const [regNumber, setRegNumber] = useState(entity.registration_number ?? "");
  const [taxId, setTaxId] = useState(entity.tax_id ?? "");
  const [address, setAddress] = useState(entity.address ?? "");
  const [fye, setFye] = useState(entity.fiscal_year_end ?? "");
  // ARD = Annual Return Date. Same as FYE unless an explicit one is stored.
  const [ardSame, setArdSame] = useState(!entity.annual_return_date);
  const [ard, setArd] = useState(entity.annual_return_date ?? "");
  const [incDate, setIncDate] = useState(entity.incorporation_date ?? "");
  const [shortCode, setShortCode] = useState(entity.short_code ?? "");
  const [nature, setNature] = useState(entity.nature_of_operation ?? "");
  const [ownership, setOwnership] = useState<OwnershipStage[]>(entity.ownership ?? []);
  const [error, setError] = useState<string | null>(null);

  // Re-sync the form when the entity object changes (e.g. polling refresh).
  useEffect(() => {
    if (open) {
      setName(entity.name);
      setLegalType(entity.legal_type);
      setJurisdictionCode(entity.jurisdiction_code ?? "");
      setRegNumber(entity.registration_number ?? "");
      setTaxId(entity.tax_id ?? "");
      setAddress(entity.address ?? "");
      setFye(entity.fiscal_year_end ?? "");
      setArdSame(!entity.annual_return_date);
      setArd(entity.annual_return_date ?? "");
      setIncDate(entity.incorporation_date ?? "");
      setShortCode(entity.short_code ?? "");
      setNature(entity.nature_of_operation ?? "");
      setOwnership(entity.ownership ?? []);
      setError(null);
    }
  }, [open, entity]);

  const setStage = (i: number, patch: Partial<OwnershipStage>) =>
    setOwnership((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const addStage = () => setOwnership((rows) => [...rows, { name: "", role: "" }]);
  const removeStage = (i: number) =>
    setOwnership((rows) => rows.filter((_, idx) => idx !== i));

  const mutation = useMutation({
    mutationFn: () => {
      const cleaned = ownership
        .map((o) => ({ name: o.name.trim(), role: o.role.trim() }))
        .filter((o) => o.name);
      return api.patch<Entity>(`/api/entities/${entity.id}`, {
        name: name.trim(),
        legal_type: legalType.trim(),
        jurisdiction_code: jurisdictionCode || null,
        registration_number: regNumber.trim() || null,
        tax_id: taxId.trim() || null,
        address: address.trim() || null,
        fiscal_year_end: fye.trim() || null,
        annual_return_date: ardSame ? null : (ard.trim() || null),
        incorporation_date: incDate || null,
        short_code: shortCode.trim() || null,
        nature_of_operation: nature.trim() || null,
        ownership: cleaned.length ? cleaned : null,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["entity", entity.id] });
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      onOpenChange(false);
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>Edit entity</DialogTitle>
        </DialogHeader>
        <div className="p-6 space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium">Legal name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">Jurisdiction</label>
            <CountrySelect value={jurisdictionCode} onChange={setJurisdictionCode} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium">Legal type</label>
              <Input
                value={legalType}
                placeholder="Private Limited / LLC / FZE…"
                onChange={(e) => setLegalType(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">Short code</label>
              <Input
                value={shortCode}
                placeholder="VINC, NESS…"
                onChange={(e) => setShortCode(e.target.value)}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium">Registration number</label>
              <Input
                value={regNumber}
                onChange={(e) => setRegNumber(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">GST / Tax No</label>
              <Input
                value={taxId}
                placeholder="GSTIN / VAT / TRN…"
                onChange={(e) => setTaxId(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">Address</label>
            <textarea
              value={address}
              placeholder="Registered office address"
              onChange={(e) => setAddress(e.target.value)}
              rows={2}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-y"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">Nature of operation</label>
            <textarea
              value={nature}
              placeholder="What the entity does — e.g. cross-border remittance & payments."
              onChange={(e) => setNature(e.target.value)}
              rows={2}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-y"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium">Incorporation date</label>
              <DateField value={incDate} onChange={setIncDate} />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">Fiscal year end</label>
              <FiscalYearEndPicker value={fye} onChange={setFye} />
            </div>
          </div>
          <div className="space-y-1">
            <label className="flex items-center gap-2 text-xs font-medium">
              <input
                type="checkbox"
                className="accent-aspora-600"
                checked={ardSame}
                onChange={(e) => setArdSame(e.target.checked)}
              />
              Annual Return Date (ARD) is the same as the fiscal year end
            </label>
            {!ardSame && (
              <div className="pt-1 space-y-1">
                <label className="text-xs font-medium">Annual Return Date (ARD)</label>
                <FiscalYearEndPicker value={ard} onChange={setArd} />
              </div>
            )}
          </div>

          <div className="space-y-2 pt-1">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium">Ownership</label>
              <span className="text-[11px] text-muted-foreground">
                Ultimate parent → … → this entity
              </span>
            </div>
            {ownership.length > 0 && (
              <div className="space-y-2">
                {ownership.map((stage, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Input
                      value={stage.name}
                      placeholder="Owner / parent name"
                      className="flex-1"
                      onChange={(e) => setStage(i, { name: e.target.value })}
                    />
                    <Input
                      value={stage.role}
                      placeholder="Stake % (e.g. 100)"
                      className="w-28 shrink-0"
                      onChange={(e) => setStage(i, { role: e.target.value })}
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeStage(i)}
                      aria-label="Remove owner"
                    >
                      <Trash2 className="h-4 w-4 text-muted-foreground" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
            <Button variant="outline" size="sm" onClick={addStage}>
              <Plus className="h-4 w-4" />
              Add owner
            </Button>
          </div>

          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !name.trim()}
          >
            {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


// ---------------------------------------------------------------------------
// Overview tab
// ---------------------------------------------------------------------------
// Format an ownership stake: a bare number gets a "%" suffix automatically, so
// the user only types "100". Values that already include "%" (or free text)
// are shown as-is.
function fmtStake(role: string | undefined): string | null {
  const v = (role ?? "").trim();
  if (!v) return null;
  if (v.includes("%")) return v;
  return /^\d+(\.\d+)?$/.test(v) ? `${v}%` : v;
}

type BankField =
  | "account_name"
  | "bank_name"
  | "account_type"
  | "account_number"
  | "sort_code"
  | "iban"
  | "swift"
  | "currency";
const BANK_FIELDS: { key: BankField; label: string; placeholder: string }[] = [
  { key: "account_name", label: "Account name", placeholder: "Account holder" },
  { key: "bank_name", label: "Bank", placeholder: "Bank name" },
  { key: "account_type", label: "Account type", placeholder: "e.g. Current / Savings" },
  { key: "account_number", label: "Account number", placeholder: "Account no." },
  { key: "sort_code", label: "Sort code / Routing", placeholder: "Sort code / routing no." },
  { key: "iban", label: "IBAN", placeholder: "IBAN" },
  { key: "swift", label: "SWIFT / BIC", placeholder: "SWIFT" },
  { key: "currency", label: "Currency", placeholder: "e.g. GBP" },
];

// Normalise stored bank_details into a list of accounts. New shape is
// { accounts: [...] }; a legacy single account is the flat fields.
function bankAccountsOf(bd: BankDetails | null | undefined): BankDetails[] {
  if (!bd) return [];
  if (Array.isArray(bd.accounts)) return bd.accounts;
  const flat: BankDetails = { ...bd };
  delete flat.accounts;
  return Object.values(flat).some((v) => v && String(v).trim()) ? [flat] : [];
}

function BankDetailsCard({
  entity,
  isAdmin,
  fullWidth,
}: {
  entity: Entity;
  isAdmin: boolean;
  fullWidth?: boolean;
}) {
  const queryClient = useQueryClient();
  const accounts = bankAccountsOf(entity.bank_details);
  // editIdx: an EXISTING account being edited on its own (null = none).
  const [editIdx, setEditIdx] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<BankDetails>({});
  // newDrafts: bulk-ADD mode — a list of new blank accounts (null = not adding).
  const [newDrafts, setNewDrafts] = useState<BankDetails[] | null>(null);
  const adding = newDrafts !== null;
  const idle = editIdx === null && !adding;

  const flatten = (a: BankDetails) => {
    const { accounts: _drop, ...flat } = a;
    return flat;
  };
  const nonEmpty = (a: BankDetails) =>
    Object.values(flatten(a)).some((v) => v && String(v).trim());
  const persist = (next: BankDetails[]) =>
    api.patch<Entity>(`/api/entities/${entity.id}`, {
      bank_details: { accounts: next.map(flatten).filter(nonEmpty) },
    });

  const saveEdit = useMutation({
    mutationFn: () => {
      const next = [...accounts];
      if (editIdx != null) next[editIdx] = editDraft;
      return persist(next);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["entity"] });
      setEditIdx(null);
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });
  const saveNew = useMutation({
    mutationFn: () => persist([...accounts, ...(newDrafts ?? [])]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["entity"] });
      setNewDrafts(null);
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });
  const del = useMutation({
    mutationFn: (i: number) => persist(accounts.filter((_, idx) => idx !== i)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["entity"] }),
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  // Field inputs bound to an arbitrary draft + onChange.
  const fields = (val: BankDetails, onChange: (k: BankField, v: string) => void) =>
    BANK_FIELDS.map((f) => (
      <div key={f.key} className="space-y-1">
        <label className="text-[11px] text-muted-foreground">{f.label}</label>
        <Input
          value={val[f.key] ?? ""}
          placeholder={f.placeholder}
          onChange={(e) => onChange(f.key, e.target.value)}
          className="h-9"
        />
      </div>
    ));

  return (
    <Card>
      <CardContent className="p-6 space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Bank accounts
        </h3>

        {accounts.length === 0 && !adding ? (
          <div className="text-sm text-muted-foreground italic">
            No bank accounts recorded{isAdmin ? " — click Add account." : "."}
          </div>
        ) : (
          <div
            className={cn(
              fullWidth ? "grid sm:grid-cols-2 lg:grid-cols-3 gap-3 items-start" : "space-y-3",
            )}
          >
            {accounts.map((acct, i) =>
              editIdx === i ? (
                <div
                  key={i}
                  className="rounded-lg border border-aspora-200 bg-aspora-50/30 p-3 space-y-2"
                >
                  <div className="text-[11px] font-medium text-muted-foreground">
                    Account {i + 1}
                  </div>
                  {fields(editDraft, (k, v) => setEditDraft((d) => ({ ...d, [k]: v })))}
                  <div className="flex justify-end gap-2 pt-1">
                    <Button variant="outline" size="sm" onClick={() => setEditIdx(null)}>
                      Cancel
                    </Button>
                    <Button size="sm" onClick={() => saveEdit.mutate()} disabled={saveEdit.isPending}>
                      {saveEdit.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                      Save
                    </Button>
                  </div>
                </div>
              ) : (
                <div key={i} className="rounded-lg border border-border p-3">
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <span className="text-[11px] font-medium text-muted-foreground">
                      {accounts.length > 1 ? `Account ${i + 1}` : ""}
                    </span>
                    {isAdmin && idle && (
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={() => { setEditDraft({ ...acct }); setEditIdx(i); }}
                          className="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground"
                          title="Edit this account"
                        >
                          <Edit className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => {
                            if (window.confirm("Delete this bank account?")) del.mutate(i);
                          }}
                          className="p-1 rounded hover:bg-red-50 text-muted-foreground hover:text-red-600"
                          title="Delete this account"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                  <dl className="grid grid-cols-3 gap-y-1.5 text-sm">
                    {BANK_FIELDS.filter((f) => acct[f.key]).map((f) => (
                      <div key={f.key} className="contents">
                        <dt className="text-muted-foreground col-span-1">{f.label}</dt>
                        <dd className="col-span-2 font-medium break-all">{acct[f.key]}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ),
            )}
          </div>
        )}

        {/* Bulk add: one or more NEW accounts entered together, then saved. */}
        {adding && (
          <div className="space-y-3">
            {newDrafts!.map((acc, i) => (
              <div
                key={i}
                className="rounded-lg border border-aspora-200 bg-aspora-50/30 p-3 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-muted-foreground">
                    New account {i + 1}
                  </span>
                  {newDrafts!.length > 1 && (
                    <button
                      onClick={() => setNewDrafts((d) => (d ?? []).filter((_, idx) => idx !== i))}
                      className="p-1 rounded hover:bg-red-50 text-muted-foreground hover:text-red-600"
                      title="Remove"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
                {fields(acc, (k, v) =>
                  setNewDrafts((d) => (d ?? []).map((r, idx) => (idx === i ? { ...r, [k]: v } : r))),
                )}
              </div>
            ))}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setNewDrafts((d) => [...(d ?? []), {}])}
            >
              <Plus className="h-4 w-4" />
              Add another
            </Button>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" size="sm" onClick={() => setNewDrafts(null)}>
                Cancel
              </Button>
              <Button size="sm" onClick={() => saveNew.mutate()} disabled={saveNew.isPending}>
                {saveNew.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                Save
              </Button>
            </div>
          </div>
        )}

        {isAdmin && idle && (
          <Button variant="outline" size="sm" onClick={() => setNewDrafts([{}])}>
            <Plus className="h-4 w-4" />
            Add account
          </Button>
        )}
      </CardContent>
    </Card>
  );
}


// Turn an audit action id into a readable verb for the activity feed.
function humaniseAction(action: string): string {
  const map: Record<string, string> = {
    "obligation.updated": "updated",
    "comment.added": "commented on",
    "document.uploaded": "uploaded a document",
    "document.deleted": "deleted a document",
    "entity.updated": "updated the entity",
    "entity.created": "created the entity",
    "entity.discovered_regulations": "ran Refresh Regulations",
    "entity.generated_questions": "generated questions",
    "entity.assessed_obligations": "found applicable regulations",
    "rule.bulk_created": "added regulations",
    "rule.updated": "updated a rule",
    "rule.created": "created a rule",
  };
  return map[action] || action.replace(/[._]/g, " ");
}

function OverviewTab({
  entity,
  obligations,
  licenses,
  onManageLicenses,
  isAdmin,
}: {
  entity: Entity;
  obligations: Obligation[];
  licenses: License[];
  onManageLicenses: () => void;
  isAdmin: boolean;
}) {
  // Recent 5 obligation changes — fake "recent activity" feed sourced from
  // updated_at on this entity's obligations. Real activity feed lands in P5.
  const { data: activityFeed = [] } = useQuery({
    queryKey: ["activities", entity.id],
    queryFn: () => api.get<ActivityOut[]>(`/api/activities?entity_id=${entity.id}&limit=8`),
    refetchInterval: 60_000,
  });

  return (
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
            <dt className="text-muted-foreground">Registration number</dt>
            <dd className="font-mono text-xs">{entity.registration_number || "—"}</dd>
            <dt className="text-muted-foreground">GST / Tax No</dt>
            <dd className="font-mono text-xs">{entity.tax_id || "—"}</dd>
            <dt className="text-muted-foreground">Address</dt>
            <dd className="whitespace-pre-line">{entity.address || "—"}</dd>
            <dt className="text-muted-foreground">Incorporation date</dt>
            <dd>{fmtDate(entity.incorporation_date)}</dd>
            <dt className="text-muted-foreground">Fiscal year end</dt>
            <dd>{entity.fiscal_year_end || "—"}</dd>
            <dt className="text-muted-foreground">Annual Return Date</dt>
            <dd>{entity.annual_return_date || "Same as fiscal year end"}</dd>
            <dt className="text-muted-foreground">Nature of operation</dt>
            <dd>{entity.nature_of_operation || "—"}</dd>
            <dt className="text-muted-foreground">Jurisdiction</dt>
            <dd>
              <JurisdictionBadge code={entity.jurisdiction_code} />
            </dd>
          </dl>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardContent className="p-6 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Licenses held
              </h3>
              <button
                onClick={onManageLicenses}
                className="text-xs text-aspora-700 hover:underline"
              >
                Manage
              </button>
            </div>
            {licenses.length === 0 ? (
              <div className="text-sm text-muted-foreground italic">
                No licenses on record.
              </div>
            ) : (
              <ul className="space-y-2 text-sm">
                {licenses.map((l) => (
                  <li
                    key={l.id}
                    className="flex items-start justify-between gap-2 border-b border-border/60 pb-2 last:border-0 last:pb-0"
                  >
                    <div className="min-w-0">
                      <div className="font-medium truncate">{l.name}</div>
                      <div className="text-[11px] text-muted-foreground truncate">
                        {l.authority}
                        {l.license_number ? ` · ${l.license_number}` : ""}
                      </div>
                    </div>
                    <span className="text-[11px] text-muted-foreground whitespace-nowrap">
                      {l.expiry_date || "No expiry"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6 space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Ownership
            </h3>
            {!entity.ownership || entity.ownership.length === 0 ? (
              <div className="text-sm text-muted-foreground italic">
                No ownership recorded{isAdmin ? " — add it under Edit." : "."}
              </div>
            ) : (
              <ul className="space-y-2 text-sm">
                {entity.ownership.map((stage, i) => {
                  const stake = fmtStake(stage.role);
                  return (
                    <li
                      key={i}
                      className="border-b border-border/60 pb-2 last:border-0 last:pb-0"
                    >
                      <div className="font-medium">
                        {stake && (
                          <span className="text-aspora-700">{stake}</span>
                        )}{" "}
                        {stage.name}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="md:col-span-3">
        <BankDetailsCard entity={entity} isAdmin={isAdmin} fullWidth />
      </div>

      <Card className="md:col-span-3">
        <CardContent className="p-6 space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Recent activity
          </h3>
          {activityFeed.length === 0 ? (
            <EmptyState
              icon={<History className="h-5 w-5" />}
              title="No activity yet"
              description="Actions on this entity — discovery, edits, filings — show up here with who did them."
            />
          ) : (
            <ul className="space-y-2">
              {activityFeed.map((a) => (
                <li
                  key={a.id}
                  className="flex items-center gap-3 text-sm hover:bg-secondary/30 rounded-lg px-2 py-1.5 -mx-2"
                >
                  <Avatar className="h-7 w-7">
                    <AvatarFallback className="text-[10px]">
                      {userInitials(a.actor?.full_name || "System")}
                    </AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <span className="font-medium">{a.actor?.full_name || "System"}</span>{" "}
                    <span className="text-muted-foreground">{humaniseAction(a.action)}</span>
                    {a.target_label && (
                      <>
                        {" "}
                        <span className="font-medium">{a.target_label}</span>
                      </>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {fmtRelative(a.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Registrations tab — demo data, real CRUD in Phase 5
// ---------------------------------------------------------------------------
const DEMO_REGISTRATIONS_PER_JURISDICTION: Record<
  string,
  { type: string; number: string; status: string; frequency: string }[]
> = {
  uk: [
    { type: "Corporation Tax (CT)", number: "1234567890", status: "Active", frequency: "Annual" },
    { type: "VAT", number: "GB 123 4567 89", status: "Active", frequency: "Quarterly" },
    { type: "PAYE", number: "120/AB12345", status: "Active", frequency: "Monthly" },
  ],
  us: [
    { type: "EIN", number: "12-3456789", status: "Active", frequency: "Annual" },
    { type: "Delaware Annual Report", number: "—", status: "Active", frequency: "Annual" },
    { type: "State Sales Tax (CA)", number: "SR-XX-12345", status: "Active", frequency: "Monthly" },
  ],
  india: [
    { type: "GSTIN", number: "29AAAAA0000A1Z5", status: "Active", frequency: "Monthly" },
    { type: "PAN", number: "AAAAA1234A", status: "Active", frequency: "—" },
    { type: "TAN", number: "ABCD12345E", status: "Active", frequency: "Quarterly" },
  ],
};


type AssessItem = {
  rule_id: number | null;
  name: string;
  form_name: string;
  category: string | null;
  function?: string | null;
  frequency: string | null;
  verdict: string;
  reason: string;
  triggering_factors?: string | null;
  due?: string | null;
  next_due?: string | null;
  basis?: string | null;
  source_url?: string | null;
  jurisdiction?: string | null;
};
type AssessResp = { available: boolean; items: AssessItem[]; notes?: string | null };


// ---------------------------------------------------------------------------
// Compliance Items tab
// ---------------------------------------------------------------------------
function ObligationsTab({
  obligations,
  loading,
}: {
  obligations: Obligation[] | undefined;
  loading: boolean;
}) {
  const { openObligation } = useObligationDrawer();
  if (loading) {
    return (
      <Card>
        <div className="p-6 space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      </Card>
    );
  }
  if (!obligations || obligations.length === 0) {
    return (
      <EmptyState
        title="Rules are still being applied to this entity"
        description="Items will appear within a minute. Refresh if you've just added a rule."
      />
    );
  }
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[900px]">
          <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 text-left font-medium">Form / Report</th>
              <th className="px-3 py-2.5 text-left font-medium">Authority · Category</th>
              <th className="px-3 py-2.5 text-left font-medium">Period</th>
              <th className="px-3 py-2.5 text-left font-medium">Due date</th>
              <th className="px-3 py-2.5 text-left font-medium">Status</th>
              <th className="px-3 py-2.5 text-left font-medium">Assignee</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {obligations.slice(0, 100).map((ob) => (
              <tr
                key={ob.id}
                className="hover:bg-secondary/30 cursor-pointer"
                onClick={() => openObligation(ob.id)}
              >
                <td className="px-3 py-2.5">
                  <div className="font-medium truncate">{ob.rule_form_name}</div>
                  <div className="text-xs text-muted-foreground truncate">{ob.rule_name}</div>
                </td>
                <td className="px-3 py-2.5 text-muted-foreground">
                  <span className="truncate">{ob.rule_authority}</span>
                  <span className="opacity-60"> · {ob.rule_category}</span>
                </td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground">
                  {ob.period_label || "—"}
                </td>
                <td className="px-3 py-2.5 tabular-nums">{fmtShortDate(ob.due_date)}</td>
                <td className="px-3 py-2.5">
                  <div className="flex flex-col gap-1">
                    <StatusPill status={ob.status} isOverdue={ob.is_overdue} />
                    <StatusPill
                      status={ob.status}
                      isOverdue={ob.is_overdue}
                      daysRemaining={ob.days_remaining}
                      showDays
                    />
                  </div>
                </td>
                <td className="px-3 py-2.5">
                  <AssigneeChip user={ob.assignee} size="sm" showName />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {obligations.length > 100 && (
        <div className="p-3 text-center text-xs text-muted-foreground border-t border-border">
          Showing first 100 of {obligations.length}. Open the calendar to filter further.
        </div>
      )}
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Documents tab — wired to /api/documents via DocumentList.
// ---------------------------------------------------------------------------
function LicensesTab({ entity, isAdmin }: { entity: Entity; isAdmin: boolean }) {
  const queryClient = useQueryClient();
  const [uploadOpen, setUploadOpen] = useState(false);
  const { data: licenses = [], isLoading } = useQuery({
    queryKey: ["entity-licenses", entity.id],
    queryFn: () => api.get<License[]>(`/api/licenses?entity_id=${entity.id}`),
    refetchInterval: 30_000,
  });
  const refreshLicenses = () =>
    queryClient.invalidateQueries({ queryKey: ["entity-licenses", entity.id] });
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/api/licenses/${id}`),
    onSuccess: refreshLicenses,
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-medium">Licenses held by {entity.name}</div>
          {isAdmin && (
            <Button size="sm" onClick={() => setUploadOpen(true)}>
              <Plus className="h-3.5 w-3.5" />
              Upload license
            </Button>
          )}
        </div>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : licenses.length === 0 ? (
          <div className="text-sm text-muted-foreground">
            No licenses yet.{" "}
            {isAdmin
              ? "Upload one — Claude reads it and surfaces the filings this entity owes."
              : "An admin can upload one here."}
          </div>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-secondary/40 text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">License</th>
                  <th className="text-left px-3 py-2 font-medium">Authority</th>
                  <th className="text-left px-3 py-2 font-medium">No.</th>
                  <th className="text-left px-3 py-2 font-medium">Expiry</th>
                  {isAdmin && <th className="px-3 py-2 w-24" />}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {licenses.map((l) => (
                  <tr key={l.id} className="hover:bg-secondary/20">
                    <td className="px-3 py-2 font-medium">
                      <Link to={`/licenses/${l.id}`} className="hover:underline">
                        {l.name}
                      </Link>
                      {l.license_type && (
                        <div className="text-[11px] text-muted-foreground">
                          {l.license_type}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{l.authority}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {l.license_number || "—"}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {l.expiry_date || "No expiry"}
                    </td>
                    {isAdmin && (
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-muted-foreground hover:text-destructive"
                          title="Delete license"
                          disabled={deleteMutation.isPending}
                          onClick={() => {
                            if (
                              window.confirm(
                                `Delete "${l.name}"? This removes the license and its file. This can't be undone.`,
                              )
                            ) {
                              deleteMutation.mutate(l.id);
                            }
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        presetEntityId={entity.id}
        onUploaded={() => {
          refreshLicenses();
          setUploadOpen(false);
        }}
      />
    </Card>
  );
}

// Folder-based documents view for the entity — mirrors the standalone
// Documents page (folder cards → open a folder → upload/list), scoped here.
const ENTITY_DEFAULT_FOLDERS = ["Filings", "Templates", "Incorporation Documents"];

function EntityDocumentsTab({ entity, isAdmin }: { entity: Entity; isAdmin: boolean }) {
  const queryClient = useQueryClient();
  const [folder, setFolder] = useState<string | null>(null);
  const [q, setQ] = useState("");

  const { data: docs = [] } = useQuery({
    queryKey: ["entity-docs", entity.id],
    queryFn: () => api.get<DocumentOut[]>(`/api/documents?entity_id=${entity.id}`),
  });

  const counts = new Map<string, number>();
  for (const d of docs) {
    const f = d.folder || d.category;
    counts.set(f, (counts.get(f) ?? 0) + 1);
  }
  const base = entity.document_folders?.length
    ? entity.document_folders
    : ENTITY_DEFAULT_FOLDERS;
  const folders = Array.from(new Set([...base, ...counts.keys()]));
  const shown = q.trim()
    ? folders.filter((f) => f.toLowerCase().includes(q.trim().toLowerCase()))
    : folders;

  const patchFolders = (next: string[]) =>
    api.patch<Entity>(`/api/entities/${entity.id}`, { document_folders: next });
  const createFolder = useMutation({
    mutationFn: (name: string) => patchFolders(Array.from(new Set([...base, name]))),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["entity"] }),
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });
  const deleteFolder = useMutation({
    mutationFn: (name: string) => patchFolders(base.filter((f) => f !== name)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["entity"] }),
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  if (folder) {
    return (
      <Card>
        <CardContent className="p-5 space-y-3">
          <button
            onClick={() => setFolder(null)}
            className="text-sm text-aspora-700 hover:underline"
          >
            ← All folders
          </button>
          <DocumentList
            scope={{ kind: "entity", entityId: entity.id }}
            folder={folder}
            title={folder}
            hint={`New uploads here go to the “${folder}” folder.`}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-5 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="text-sm font-medium">Open a folder to view / upload</div>
          {isAdmin && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                const name = window.prompt("New folder name")?.trim();
                if (name) createFolder.mutate(name);
              }}
            >
              <Plus className="h-4 w-4" />
              New folder
            </Button>
          )}
        </div>
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search folders…"
          className="h-9 max-w-xs"
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {shown.map((f) => {
            const n = counts.get(f) ?? 0;
            return (
              <div
                key={f}
                role="button"
                tabIndex={0}
                onClick={() => setFolder(f)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") setFolder(f);
                }}
                className="rounded-lg border border-border bg-card hover:border-aspora-400 hover:bg-aspora-50/40 px-4 py-3 flex items-center gap-3 cursor-pointer"
              >
                <span className="text-sm font-semibold flex-1 truncate">{f}</span>
                <span className="text-xs tabular-nums text-muted-foreground">{n}</span>
                {isAdmin && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (n > 0) {
                        window.alert(
                          `"${f}" has ${n} document(s). Move or delete them first.`,
                        );
                        return;
                      }
                      if (window.confirm(`Delete the empty folder "${f}"?`))
                        deleteFolder.mutate(f);
                    }}
                    className="shrink-0 p-1 rounded hover:bg-red-50 text-muted-foreground hover:text-red-600"
                    title={n > 0 ? "Folder has documents — empty it first" : "Delete folder"}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function DocumentsTab({ entity }: { entity: Entity }) {
  return (
    <Card>
      <CardContent className="p-5">
        <DocumentList
          scope={{ kind: "entity", entityId: entity.id }}
          title="All documents for this entity"
          hint="Upload formation papers, prior filings, contracts, or expert notes. Max 25 MB per file."
        />
      </CardContent>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Key Persons tab (demo)
// ---------------------------------------------------------------------------
function KeyPersonsTab({ entity, isAdmin }: { entity: Entity; isAdmin: boolean }) {
  const demoPeople: { name: string; role: string; email: string }[] = entity.country_lead
    ? [
        {
          name: entity.country_lead.full_name,
          role: "Authorised signatory",
          email: entity.country_lead.email,
        },
        { name: "—", role: "Director", email: "Add via Settings" },
      ]
    : [];
  return (
    <Card>
      <CardContent className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Directors, officers, signatories</h3>
          <Button size="sm" disabled={!isAdmin} title={isAdmin ? undefined : "Admin only"}>
            {isAdmin ? <Plus className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
            Add person
          </Button>
        </div>
        {demoPeople.length === 0 ? (
          <EmptyState
            icon={<UserCheck className="h-5 w-5" />}
            title="No key persons linked"
            description="Add directors, signatories, and officers so the right people get pinged on each filing."
          />
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {demoPeople.map((p, i) => (
              <li key={i} className="rounded-lg border border-border p-3 flex items-start gap-3">
                <Avatar className="h-10 w-10">
                  <AvatarFallback>{userInitials(p.name)}</AvatarFallback>
                </Avatar>
                <div className="min-w-0">
                  <div className="font-medium truncate">{p.name}</div>
                  <div className="text-xs text-muted-foreground">{p.role}</div>
                  <div className="text-xs text-muted-foreground mt-0.5 truncate">{p.email}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Activity / Audit log tab — wired to /api/activities scoped to this entity.
// ---------------------------------------------------------------------------
function ActivityTab({ entity }: { entity: Entity }) {
  const { data: activities = [], isLoading } = useQuery({
    queryKey: ["activities", "entity", entity.id],
    queryFn: () =>
      api.get<ActivityOut[]>(`/api/activities?entity_id=${entity.id}&limit=100`),
  });

  return (
    <Card>
      <CardContent className="p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Activity log</h3>
          <span className="text-xs text-muted-foreground tabular-nums">
            {activities.length} event{activities.length === 1 ? "" : "s"}
          </span>
        </div>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </div>
        ) : activities.length === 0 ? (
          <EmptyState
            icon={<History className="h-5 w-5" />}
            title="No activity in the selected range"
            description="Update an obligation or upload a document to see the audit trail here."
          />
        ) : (
          <ul className="space-y-2">
            {activities.map((a) => (
              <li
                key={a.id}
                className="flex items-start gap-3 text-sm rounded-lg px-2 py-1.5 hover:bg-secondary/30"
              >
                <Avatar className="h-7 w-7 shrink-0 mt-0.5">
                  <AvatarFallback className="text-[10px]">
                    {userInitials(a.actor?.full_name || "—")}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <div className="leading-snug">
                    <span className="font-medium">
                      {a.actor?.full_name || "System"}
                    </span>{" "}
                    <span className="text-muted-foreground">{a.action.replace(/\./g, " ")}</span>
                    {a.target_label && (
                      <>
                        <span className="text-muted-foreground"> · </span>
                        <span className="font-medium">{a.target_label}</span>
                      </>
                    )}
                  </div>
                </div>
                <span className="text-xs text-muted-foreground whitespace-nowrap mt-1">
                  {fmtRelative(a.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}


