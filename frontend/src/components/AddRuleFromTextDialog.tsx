import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles, AlertCircle, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { JURISDICTIONS } from "@/lib/format";
import type { Entity } from "@/types/api";

interface CandidateRule {
  name: string;
  category: string;
  area: string;
  form_name: string;
  authority: string;
  frequency: string;
  due_date_rule: string;
  payment_rule: string | null;
  applicability: "Mandatory" | "Conditional" | "Sector-specific";
  applicability_note: string | null;
}

interface ExtractResponse {
  available: boolean;
  jurisdiction_hint: string | null;
  rules: CandidateRule[];
  notes: string | null;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddRuleFromTextDialog({ open, onOpenChange }: Props) {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [jurisdiction, setJurisdiction] = useState<string>("");
  const [extraction, setExtraction] = useState<ExtractResponse | null>(null);
  const [kept, setKept] = useState<Set<number>>(new Set());
  const [entityIds, setEntityIds] = useState<Set<number>>(new Set());

  const { data: entities = [] } = useQuery({
    queryKey: ["entities", "for-bulk-create"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
    enabled: open,
  });

  // Filter entities to the selected jurisdiction once we know it.
  const targetJurisdiction = extraction?.jurisdiction_hint || jurisdiction || "";
  const availableEntities = useMemo(
    () =>
      targetJurisdiction
        ? entities.filter((e) => e.jurisdiction_code === targetJurisdiction)
        : entities,
    [entities, targetJurisdiction],
  );

  const extractMutation = useMutation({
    mutationFn: () =>
      api.post<ExtractResponse>("/api/rules/extract", {
        text,
        jurisdiction_hint: jurisdiction || undefined,
      }),
    onSuccess: (data) => {
      setExtraction(data);
      setKept(new Set(data.rules.map((_, i) => i)));
    },
  });

  const createMutation = useMutation({
    mutationFn: () => {
      if (!extraction) throw new Error("Nothing to create.");
      const finalJurisdiction = extraction.jurisdiction_hint || jurisdiction;
      if (!finalJurisdiction) throw new Error("Pick a jurisdiction first.");
      return api.post("/api/rules/bulk-create", {
        jurisdiction_code: finalJurisdiction,
        rules: extraction.rules.filter((_, i) => kept.has(i)),
        entity_ids: Array.from(entityIds),
        status: "staging",
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      reset();
      onOpenChange(false);
    },
  });

  function reset() {
    setText("");
    setJurisdiction("");
    setExtraction(null);
    setKept(new Set());
    setEntityIds(new Set());
    extractMutation.reset();
    createMutation.reset();
  }

  const isExtracting = extractMutation.isPending;
  const isCreating = createMutation.isPending;
  const extractError = extractMutation.error;
  const createError = createMutation.error;

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-aspora-600" />
            Add Compliance Rules from regulation text
          </DialogTitle>
          <DialogDescription>
            Paste the text of a law, circular, or notice. Claude will pull out the filing
            obligations as candidate rules. You review, tick the ones to keep, pick which
            entities they apply to, and create them as Staging rules.
          </DialogDescription>
        </DialogHeader>

        <div className="p-6 space-y-4">
          {!extraction ? (
            <>
              <div className="flex gap-2">
                <select
                  value={jurisdiction}
                  onChange={(e) => setJurisdiction(e.target.value)}
                  className="h-10 rounded-lg border border-input bg-background px-3 text-sm"
                >
                  <option value="">Jurisdiction (optional hint)</option>
                  {Object.entries(JURISDICTIONS).map(([code, j]) => (
                    <option key={code} value={code}>
                      {j.flag} {j.name}
                    </option>
                  ))}
                </select>
              </div>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste regulatory text here (article numbers and section text help most)…"
                rows={14}
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm font-mono leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
              {extractError && (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>{(extractError as Error).message}</div>
                </div>
              )}
            </>
          ) : !extraction.available ? (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <div className="font-medium mb-1">AI is off in this deployment.</div>
              <div className="text-amber-800/80">
                {extraction.notes ||
                  "Set COMPLIANCE_AGENT_LIVE=1 and ANTHROPIC_API_KEY on the server, then retry."}
              </div>
            </div>
          ) : extraction.rules.length === 0 ? (
            <div className="rounded-lg border border-border bg-secondary/40 px-4 py-3 text-sm">
              <div className="font-medium mb-1">No filing obligations detected.</div>
              <div className="text-muted-foreground">
                {extraction.notes ||
                  "Claude didn't find any recurring or event-based filings in the text. Try a different excerpt that describes returns, reports, or notification timings."}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-sm">
                <div>
                  Found <strong>{extraction.rules.length}</strong> candidate rule
                  {extraction.rules.length === 1 ? "" : "s"}
                  {extraction.jurisdiction_hint && (
                    <>
                      {" "}
                      · jurisdiction inferred as{" "}
                      <Badge variant="default">{extraction.jurisdiction_hint}</Badge>
                    </>
                  )}
                </div>
                <button
                  className="text-xs text-aspora-600 hover:underline"
                  onClick={() => setExtraction(null)}
                >
                  Re-extract
                </button>
              </div>

              {extraction.notes && (
                <div className="rounded-lg border border-border bg-secondary/30 px-3 py-2 text-xs text-muted-foreground">
                  {extraction.notes}
                </div>
              )}

              {/* Candidate list */}
              <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1 scrollbar-thin">
                {extraction.rules.map((r, i) => {
                  const isKept = kept.has(i);
                  return (
                    <label
                      key={i}
                      className={`flex gap-3 items-start rounded-lg border px-3 py-2.5 text-sm cursor-pointer transition-colors ${
                        isKept
                          ? "border-aspora-300 bg-aspora-50/50"
                          : "border-border hover:bg-secondary/40"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isKept}
                        onChange={(e) => {
                          const copy = new Set(kept);
                          if (e.target.checked) copy.add(i);
                          else copy.delete(i);
                          setKept(copy);
                        }}
                        className="mt-1 accent-aspora-600"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="font-medium">{r.form_name}</div>
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {r.authority} · {r.category} · {r.frequency}
                        </div>
                        <div className="text-xs text-muted-foreground mt-1 italic">
                          {r.due_date_rule}
                        </div>
                        {r.payment_rule && (
                          <div className="text-xs text-muted-foreground mt-0.5">
                            <strong>Payment:</strong> {r.payment_rule}
                          </div>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>

              {/* Entity targeting */}
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
                  Apply to entities ({targetJurisdiction || "any jurisdiction"})
                </div>
                <div className="flex flex-wrap gap-2">
                  {availableEntities.length === 0 ? (
                    <div className="text-xs text-muted-foreground italic">
                      No entities match the jurisdiction. The rules will be created without
                      entity attachment — you can attach them from the rules table later.
                    </div>
                  ) : (
                    availableEntities.map((e) => {
                      const checked = entityIds.has(e.id);
                      return (
                        <button
                          key={e.id}
                          type="button"
                          onClick={() => {
                            const copy = new Set(entityIds);
                            if (copy.has(e.id)) copy.delete(e.id);
                            else copy.add(e.id);
                            setEntityIds(copy);
                          }}
                          className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                            checked
                              ? "border-aspora-500 bg-aspora-50 text-aspora-700"
                              : "border-border text-muted-foreground hover:bg-secondary"
                          }`}
                        >
                          {e.name}
                        </button>
                      );
                    })
                  )}
                </div>
              </div>

              {createError && (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>{(createError as Error).message}</div>
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          {!extraction ? (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button
                onClick={() => extractMutation.mutate()}
                disabled={text.trim().length < 80 || isExtracting}
              >
                {isExtracting && <Loader2 className="h-4 w-4 animate-spin" />}
                <Sparkles className="h-4 w-4" />
                Extract candidates
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={reset}>
                Start over
              </Button>
              {extraction.available && extraction.rules.length > 0 && (
                <Button
                  onClick={() => createMutation.mutate()}
                  disabled={kept.size === 0 || isCreating}
                >
                  {isCreating && <Loader2 className="h-4 w-4 animate-spin" />}
                  Create {kept.size} rule{kept.size === 1 ? "" : "s"} as Staging
                </Button>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
