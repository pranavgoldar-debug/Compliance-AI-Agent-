// Bulk CSV / Excel rule import. Three steps in one dialog:
//   1. Pick file (or download a template).
//   2. Preview parsed rows with per-row validation errors.
//   3. Tick rows to keep, optionally attach to entities, commit as Staging.
//
// No Claude calls — this is the plain bulk import path for an existing
// compliance tracker sheet.
import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Loader2,
  Upload,
  XCircle,
} from "lucide-react";
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
import { api, ApiError } from "@/lib/api";
import type { Entity } from "@/types/api";

interface ParsedRow {
  row_number: number;
  name: string;
  jurisdiction_code: string;
  category: string;
  area: string;
  form_name: string;
  authority: string;
  frequency: string;
  due_date_rule: string;
  payment_rule: string | null;
  applicability: string;
  applicability_note: string | null;
  source_url: string | null;
  errors: string[];
}

interface PreviewResponse {
  detected_columns: string[];
  unknown_columns: string[];
  missing_required: string[];
  rows: ParsedRow[];
  valid_count: number;
  error_count: number;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ImportRulesDialog({ open, onOpenChange }: Props) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [kept, setKept] = useState<Set<number>>(new Set());
  const [entityIds, setEntityIds] = useState<Set<number>>(new Set());

  const { data: entities = [] } = useQuery({
    queryKey: ["entities", "for-import"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
    enabled: open,
  });

  const previewMutation = useMutation({
    mutationFn: async (f: File) => {
      const form = new FormData();
      form.append("file", f);
      return api.upload<PreviewResponse>("/api/rules/import/preview", form);
    },
    onSuccess: (data) => {
      setPreview(data);
      // Tick every row that parsed without errors by default.
      const valid = new Set<number>();
      data.rows.forEach((r, i) => {
        if (r.errors.length === 0) valid.add(i);
      });
      setKept(valid);
    },
  });

  const commitMutation = useMutation({
    mutationFn: () => {
      if (!preview) throw new Error("Preview the file first.");
      const rows = preview.rows
        .filter((_, i) => kept.has(i))
        .map((r) => ({
          name: r.name,
          jurisdiction_code: r.jurisdiction_code,
          category: r.category,
          area: r.area,
          form_name: r.form_name,
          authority: r.authority,
          frequency: r.frequency,
          due_date_rule: r.due_date_rule,
          payment_rule: r.payment_rule,
          applicability: r.applicability,
          applicability_note: r.applicability_note,
          source_url: r.source_url,
        }));
      return api.post<{ created: unknown[] }>("/api/rules/import/commit", {
        rows,
        entity_ids: Array.from(entityIds),
        status: "staging",
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
      queryClient.invalidateQueries({ queryKey: ["rules-staging-count"] });
      reset();
      onOpenChange(false);
    },
  });

  function reset() {
    setFile(null);
    setPreview(null);
    setKept(new Set());
    setEntityIds(new Set());
    previewMutation.reset();
    commitMutation.reset();
    templateMutation.reset();
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function handleFile(f: File | null) {
    if (!f) return;
    setFile(f);
    setPreview(null);
    setKept(new Set());
    previewMutation.mutate(f);
  }

  // Download via fetch so we can surface auth / network failures inline
  // rather than letting the browser silently navigate to a JSON error body
  // or an HTML SPA-fallback document with a misleading .csv filename.
  const templateMutation = useMutation({
    mutationFn: async (format: "csv" | "xlsx") => {
      const res = await fetch(`/api/rules/import/template?format=${format}`, {
        credentials: "include",
      });
      if (!res.ok) {
        let msg = `Download failed (HTTP ${res.status})`;
        try {
          const j = await res.json();
          if (j?.detail) msg = String(j.detail);
        } catch {
          /* not JSON */
        }
        throw new Error(msg);
      }
      const ct = res.headers.get("content-type") || "";
      if (ct.includes("text/html")) {
        throw new Error(
          "Server returned HTML instead of the template — the import endpoint isn't deployed yet. Pull the latest build and restart.",
        );
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `aspora-rules-import-template.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      return true;
    },
  });

  const isPreviewing = previewMutation.isPending;
  const isCommitting = commitMutation.isPending;
  const previewError = previewMutation.error as Error | ApiError | null;
  const commitError = commitMutation.error as Error | ApiError | null;

  // Group selected entities by jurisdiction so we can give honest feedback —
  // attachments only land on entities whose jurisdiction matches the rule.
  const jurisdictionsInSelection = useMemo(() => {
    if (!preview) return new Set<string>();
    const out = new Set<string>();
    preview.rows.forEach((r, i) => {
      if (kept.has(i) && r.jurisdiction_code) out.add(r.jurisdiction_code);
    });
    return out;
  }, [preview, kept]);

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent size="xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5 text-aspora-600" />
            Import rule template
          </DialogTitle>
          <DialogDescription>
            Upload a CSV or Excel file with one rule per row. We'll parse it,
            flag any problems, and let you pick which rows to bring in as
            Staging rules.
          </DialogDescription>
        </DialogHeader>

        <div className="p-6 space-y-4">
          {!preview ? (
            <>
              <div className="rounded-lg border border-border bg-secondary/30 px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm">
                    <div className="font-medium">No template yet?</div>
                    <div className="text-muted-foreground">
                      Download the starter file — it has every column the
                      importer recognises plus three example rules.
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => templateMutation.mutate("csv")}
                      disabled={templateMutation.isPending}
                    >
                      {templateMutation.isPending &&
                      templateMutation.variables === "csv" ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                      CSV
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => templateMutation.mutate("xlsx")}
                      disabled={templateMutation.isPending}
                    >
                      {templateMutation.isPending &&
                      templateMutation.variables === "xlsx" ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                      Excel
                    </Button>
                  </div>
                </div>
              </div>

              <label
                className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-border rounded-lg px-6 py-10 text-center cursor-pointer hover:border-aspora-400 hover:bg-aspora-50/40 transition-colors"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const f = e.dataTransfer.files?.[0] || null;
                  handleFile(f);
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  className="hidden"
                  onChange={(e) => handleFile(e.target.files?.[0] || null)}
                />
                <Upload className="h-8 w-8 text-muted-foreground" />
                <div className="text-sm font-medium">
                  {file ? file.name : "Drop a CSV or Excel file here"}
                </div>
                <div className="text-xs text-muted-foreground">
                  or click to browse · max ~5 MB
                </div>
                {isPreviewing && (
                  <div className="flex items-center gap-2 text-xs text-aspora-700 mt-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Parsing…
                  </div>
                )}
              </label>

              <div className="text-xs text-muted-foreground space-y-1">
                <div>
                  <strong>Required columns:</strong> name, jurisdiction_code,
                  category, form_name, authority, frequency, due_date_rule
                </div>
                <div>
                  <strong>Optional:</strong> area, payment_rule, applicability,
                  applicability_note, source_url
                </div>
                <div>
                  Header names are forgiving — &quot;Country&quot;, &quot;Form&quot;, &quot;Regulator&quot;,
                  &quot;Due date&quot; etc. are all recognised.
                </div>
              </div>

              {previewError && (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>{previewError.message}</div>
                </div>
              )}
              {templateMutation.error && (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>{(templateMutation.error as Error).message}</div>
                </div>
              )}
            </>
          ) : (
            <div className="space-y-4">
              {/* Header summary */}
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-muted-foreground">{file?.name}</span>
                <Badge variant="default">
                  {preview.rows.length} row{preview.rows.length === 1 ? "" : "s"}
                </Badge>
                {preview.valid_count > 0 && (
                  <Badge variant="completed">{preview.valid_count} valid</Badge>
                )}
                {preview.error_count > 0 && (
                  <Badge variant="alert">{preview.error_count} with errors</Badge>
                )}
                <button
                  type="button"
                  className="ml-auto text-xs text-aspora-600 hover:underline"
                  onClick={reset}
                >
                  Choose a different file
                </button>
              </div>

              {preview.missing_required.length > 0 && (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>
                    <div className="font-medium">Missing required columns</div>
                    <div className="text-xs">
                      Your file doesn't have:{" "}
                      <strong>{preview.missing_required.join(", ")}</strong>.
                      Download the template above for the expected layout.
                    </div>
                  </div>
                </div>
              )}

              {preview.unknown_columns.length > 0 && (
                <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                  <strong>Ignored columns:</strong>{" "}
                  {preview.unknown_columns.join(", ")} — these don't match any
                  rule field, so we skipped them. Edit your header row if any
                  were supposed to map across.
                </div>
              )}

              {/* Bulk select toolbar */}
              <div className="flex items-center gap-3 text-xs">
                <button
                  type="button"
                  className="text-aspora-600 hover:underline"
                  onClick={() =>
                    setKept(new Set(preview.rows.map((_, i) => i)))
                  }
                >
                  Select all
                </button>
                <button
                  type="button"
                  className="text-aspora-600 hover:underline"
                  onClick={() => {
                    const valid = new Set<number>();
                    preview.rows.forEach((r, i) => {
                      if (r.errors.length === 0) valid.add(i);
                    });
                    setKept(valid);
                  }}
                >
                  Select valid only
                </button>
                <button
                  type="button"
                  className="text-aspora-600 hover:underline"
                  onClick={() => setKept(new Set())}
                >
                  Clear
                </button>
                <span className="ml-auto text-muted-foreground">
                  {kept.size} selected
                </span>
              </div>

              {/* Row list */}
              <div className="max-h-[360px] overflow-y-auto pr-1 scrollbar-thin space-y-1.5">
                {preview.rows.length === 0 && (
                  <div className="rounded-lg border border-border bg-secondary/40 px-4 py-3 text-sm text-muted-foreground">
                    No data rows found.
                  </div>
                )}
                {preview.rows.map((r, i) => {
                  const isKept = kept.has(i);
                  const hasErr = r.errors.length > 0;
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
                        <div className="flex items-center gap-2">
                          {hasErr ? (
                            <XCircle className="h-4 w-4 text-destructive shrink-0" />
                          ) : (
                            <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                          )}
                          <span className="font-medium truncate">
                            {r.form_name || r.name || `Row ${r.row_number}`}
                          </span>
                          {r.jurisdiction_code && (
                            <Badge variant="default" className="shrink-0">
                              {r.jurisdiction_code}
                            </Badge>
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground mt-0.5 truncate">
                          {[r.authority, r.category, r.frequency]
                            .filter(Boolean)
                            .join(" · ")}
                        </div>
                        {r.due_date_rule && (
                          <div className="text-xs text-muted-foreground mt-0.5 italic truncate">
                            {r.due_date_rule}
                          </div>
                        )}
                        {hasErr && (
                          <div className="text-xs text-destructive mt-1">
                            {r.errors.join(" · ")}
                          </div>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground shrink-0 tabular-nums">
                        row {r.row_number}
                      </div>
                    </label>
                  );
                })}
              </div>

              {/* Entity targeting */}
              {entities.length > 0 && jurisdictionsInSelection.size > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
                    Apply to entities (optional)
                  </div>
                  <div className="text-xs text-muted-foreground mb-2">
                    Only entities matching a rule's jurisdiction will be
                    attached. Selected jurisdictions:{" "}
                    {Array.from(jurisdictionsInSelection).join(", ") || "none"}.
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {entities
                      .filter((e) =>
                        jurisdictionsInSelection.has(e.jurisdiction_code),
                      )
                      .map((e) => {
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
                            {e.name}{" "}
                            <span className="opacity-60">
                              ({e.jurisdiction_code})
                            </span>
                          </button>
                        );
                      })}
                  </div>
                </div>
              )}

              {commitError && (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>{commitError.message}</div>
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          {!preview ? (
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
          ) : (
            <>
              <Button variant="outline" onClick={reset}>
                Start over
              </Button>
              <Button
                onClick={() => commitMutation.mutate()}
                disabled={kept.size === 0 || isCommitting}
              >
                {isCommitting && <Loader2 className="h-4 w-4 animate-spin" />}
                Import {kept.size} rule{kept.size === 1 ? "" : "s"} as Staging
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
