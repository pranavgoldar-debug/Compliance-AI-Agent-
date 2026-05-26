import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sparkles, FileText, CheckCircle2, AlertCircle, AlertTriangle, BookOpen } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/PageHeader";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { cn } from "@/lib/utils";
import type {
  ComplianceRequirement,
  CountrySummary,
  RegulationView,
  Severity,
  VerificationFinding,
} from "@/types/api";


const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  informational: "Info",
};

const SEVERITY_RANK: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  informational: 4,
};

function severityVariant(s: Severity): "overdue" | "alert" | "review" | "completed" | "neutral" {
  switch (s) {
    case "critical":
      return "overdue";
    case "high":
      return "alert";
    case "medium":
      return "review";
    case "low":
      return "completed";
    case "informational":
      return "neutral";
  }
}


export function RegulationLibraryPage() {
  const [countryCode, setCountryCode] = useState<string>("");
  const [regulationId, setRegulationId] = useState<string>("");

  const { data: countries = [], isLoading: loadingCountries } = useQuery({
    queryKey: ["regulation-countries"],
    queryFn: () => api.get<CountrySummary[]>("/api/countries"),
  });

  const country = useMemo(
    () => countries.find((c) => c.code === countryCode),
    [countries, countryCode],
  );

  const { data: view, isLoading: loadingExtraction } = useQuery({
    queryKey: ["regulation-view", regulationId],
    queryFn: () => api.get<RegulationView>(`/api/regulations/${regulationId}`),
    enabled: !!regulationId,
  });

  // Group requirements by category, sorted by severity within each category.
  const groupedRequirements = useMemo(() => {
    if (!view) return [];
    const map = new Map<string, ComplianceRequirement[]>();
    for (const req of view.extraction.requirements) {
      const list = map.get(req.category) ?? [];
      list.push(req);
      map.set(req.category, list);
    }
    return Array.from(map.entries())
      .map(([cat, reqs]) => ({
        category: cat,
        requirements: reqs.sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]),
      }))
      .sort((a, b) => a.category.localeCompare(b.category));
  }, [view]);

  const findingsById = useMemo(() => {
    const map: Record<string, VerificationFinding> = {};
    if (view?.verification) {
      for (const f of view.verification.findings) map[f.requirement_id] = f;
    }
    return map;
  }, [view]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Regulation Library"
        description="Pick a country and a regulation to see every obligation it imposes, extracted from the source text — with severity, evidence artifacts, and verification."
      />

      {/* Picker */}
      <Card>
        <CardContent className="p-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1.5">
                Country / Region
              </label>
              <select
                value={countryCode}
                onChange={(e) => {
                  setCountryCode(e.target.value);
                  setRegulationId("");
                }}
                disabled={loadingCountries}
                className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm"
              >
                <option value="">— select a country —</option>
                {countries.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.flag} {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1.5">
                Regulation
              </label>
              <select
                value={regulationId}
                onChange={(e) => setRegulationId(e.target.value)}
                disabled={!country}
                className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm disabled:opacity-50"
              >
                <option value="">
                  {country ? "— select a regulation —" : "Pick a country first"}
                </option>
                {country?.regulations.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.short_name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Loading / empty / result */}
      {!regulationId ? (
        <Card>
          <CardContent className="p-10 text-center space-y-3">
            <BookOpen className="h-10 w-10 text-muted-foreground mx-auto" />
            <p className="text-sm text-muted-foreground max-w-md mx-auto">
              The Regulation Library breaks a law down into individual obligations a
              compliance team can act on: title, severity, the verbatim source quote, who
              it applies to, and what auditors will ask to see.
            </p>
            <p className="text-xs text-muted-foreground">
              Bundled: <strong>India</strong> (DPDP 2023, CERT-In 2022) ·{" "}
              <strong>EU</strong> (GDPR, NIS2) · <strong>US</strong> (HIPAA, CCPA, PCI
              DSS) · <strong>UK</strong> (UK GDPR + DPA 2018) · <strong>UAE</strong>{" "}
              (PDPL 2021) · <strong>Singapore</strong> (PDPA)
            </p>
          </CardContent>
        </Card>
      ) : loadingExtraction || !view ? (
        <div className="space-y-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-12" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      ) : (
        <Results view={view} groupedRequirements={groupedRequirements} findingsById={findingsById} />
      )}
    </div>
  );
}


function Results({
  view,
  groupedRequirements,
  findingsById,
}: {
  view: RegulationView;
  groupedRequirements: { category: string; requirements: ComplianceRequirement[] }[];
  findingsById: Record<string, VerificationFinding>;
}) {
  // Severity tally
  const sevCounts: Record<Severity, number> = {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    informational: 0,
  };
  for (const r of view.extraction.requirements) sevCounts[r.severity]++;

  // Verification tally
  const verifTally = { pass: 0, warning: 0, fail: 0 };
  if (view.verification) {
    for (const f of view.verification.findings) {
      verifTally[f.status]++;
    }
  }

  return (
    <>
      {/* Header card */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-start gap-4">
            <div className="h-12 w-12 rounded-xl bg-aspora-100 text-aspora-700 grid place-items-center shrink-0">
              <FileText className="h-6 w-6" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 mb-1">
                <JurisdictionBadge code={view.country_code} />
                {view.regulation.framework && (
                  <Badge variant="default">{view.regulation.framework}</Badge>
                )}
              </div>
              <h2 className="text-xl font-semibold leading-tight">{view.regulation.name}</h2>
              <p className="text-sm text-muted-foreground mt-1.5 max-w-3xl">
                {view.regulation.scope}
              </p>
            </div>
          </div>

          {/* Severity pills */}
          <div className="mt-5 flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground uppercase tracking-wider mr-1">
              {view.extraction.requirements.length} requirement
              {view.extraction.requirements.length === 1 ? "" : "s"}:
            </span>
            {(Object.keys(sevCounts) as Severity[]).map((s) =>
              sevCounts[s] > 0 ? (
                <Badge key={s} variant={severityVariant(s)}>
                  {sevCounts[s]} {SEVERITY_LABEL[s]}
                </Badge>
              ) : null,
            )}
          </div>

          {/* Extraction notes (mostly: "MOCK MODE — curated…") */}
          {view.extraction.extraction_notes && (
            <p className="mt-3 text-xs text-muted-foreground italic">
              {view.extraction.extraction_notes}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Verification card */}
      {view.verification && (
        <Card>
          <CardContent className="p-5 flex flex-wrap items-center gap-3">
            <Sparkles className="h-5 w-5 text-aspora-600 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium">Verification</div>
              <div className="text-xs text-muted-foreground">
                {view.verification.overall_summary}
              </div>
            </div>
            <div className="flex gap-2">
              <Badge variant="completed">
                <CheckCircle2 className="h-3 w-3 mr-1" />
                pass {verifTally.pass}
              </Badge>
              <Badge variant="alert">
                <AlertTriangle className="h-3 w-3 mr-1" />
                warning {verifTally.warning}
              </Badge>
              <Badge variant="overdue">
                <AlertCircle className="h-3 w-3 mr-1" />
                fail {verifTally.fail}
              </Badge>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Missed requirements (live mode only) */}
      {view.verification && view.verification.missed_requirements.length > 0 && (
        <Card>
          <CardContent className="p-5">
            <h3 className="text-sm font-semibold mb-2">
              Possibly missed by the extractor
            </h3>
            <ul className="space-y-1 text-sm">
              {view.verification.missed_requirements.map((m, i) => (
                <li key={i} className="text-muted-foreground">
                  • {m}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Grouped requirements */}
      {groupedRequirements.map(({ category, requirements }) => (
        <div key={category} className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground px-1">
            {category.replace(/_/g, " ")}
          </h3>
          {requirements.map((req) => (
            <RequirementCard
              key={req.requirement_id}
              req={req}
              finding={findingsById[req.requirement_id]}
            />
          ))}
        </div>
      ))}
    </>
  );
}


function RequirementCard({
  req,
  finding,
}: {
  req: ComplianceRequirement;
  finding?: VerificationFinding;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h4 className="text-base font-semibold leading-tight">{req.title}</h4>
            <div className="text-xs text-muted-foreground mt-0.5 font-mono">
              {req.requirement_id}
              {req.section_reference && (
                <span className="font-sans"> · {req.section_reference}</span>
              )}
            </div>
          </div>
          <Badge variant={severityVariant(req.severity)}>{SEVERITY_LABEL[req.severity]}</Badge>
        </div>

        <p className="text-sm mt-3">{req.summary}</p>

        {/* Applies-to + evidence */}
        <dl className="mt-3 grid grid-cols-[100px_1fr] gap-x-3 gap-y-2 text-xs">
          <dt className="text-muted-foreground">Applies to</dt>
          <dd>{req.applies_to.length === 0 ? <em className="text-muted-foreground">—</em> : <Tags items={req.applies_to} />}</dd>
          <dt className="text-muted-foreground">Evidence</dt>
          <dd>{req.evidence_artifacts.length === 0 ? <em className="text-muted-foreground">—</em> : <Tags items={req.evidence_artifacts} />}</dd>
        </dl>

        {req.source_quote && (
          <blockquote className="mt-3 rounded-lg border-l-2 border-aspora-400 bg-aspora-50/40 px-3 py-2 text-xs text-muted-foreground whitespace-pre-wrap">
            {req.source_quote}
          </blockquote>
        )}

        {finding && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <Badge
              variant={
                finding.status === "pass"
                  ? "completed"
                  : finding.status === "warning"
                    ? "alert"
                    : "overdue"
              }
            >
              {finding.status}
            </Badge>
            <span
              className={cn(
                "text-muted-foreground",
                finding.quote_verbatim ? "text-emerald-700" : "text-amber-700",
              )}
            >
              {finding.quote_verbatim ? "✓ verbatim quote" : "✗ quote not verbatim"}
            </span>
            {finding.issues.length > 0 && (
              <ul className="basis-full mt-1 ml-1 text-muted-foreground space-y-0.5">
                {finding.issues.map((issue, i) => (
                  <li key={i}>• {issue}</li>
                ))}
              </ul>
            )}
            {finding.suggested_fix && (
              <p className="basis-full italic text-muted-foreground">
                Suggested fix: {finding.suggested_fix}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}


function Tags({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((t, i) => (
        <span
          key={i}
          className="inline-block rounded-md bg-secondary text-foreground px-1.5 py-0.5 text-[11px]"
        >
          {t}
        </span>
      ))}
    </div>
  );
}
