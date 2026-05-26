// "Check for changes" — admin-only. POSTs to /api/ai/check-rule-changes/{id}
// and renders the diff against the previous snapshot.

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  ExternalLink,
  History,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, ApiError } from "@/lib/api";
import { fmtDate, fmtRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Rule, RuleSnapshot, RuleSourceCheckResult } from "@/types/api";


interface Props {
  rule: Rule;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}


export function RuleChangeCheckDialog({ rule, open, onOpenChange }: Props) {
  const [result, setResult] = useState<RuleSourceCheckResult | null>(null);

  const { data: snapshots = [] } = useQuery({
    queryKey: ["rule-snapshots", rule.id],
    queryFn: () => api.get<RuleSnapshot[]>(`/api/rules/${rule.id}/snapshots`),
    enabled: open,
  });

  const checkMutation = useMutation({
    mutationFn: () =>
      api.post<RuleSourceCheckResult>(`/api/ai/check-rule-changes/${rule.id}`),
    onSuccess: (r) => setResult(r),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RefreshCw className="h-4 w-4 text-aspora-600" />
            Check for changes — {rule.form_name}
          </DialogTitle>
        </DialogHeader>

        <div className="p-6 space-y-4">
          {/* Source URL */}
          <div className="rounded-lg border border-border bg-secondary/30 px-3 py-2 flex items-center gap-2 text-sm">
            <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
            {rule.source_url ? (
              <a
                href={rule.source_url}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-xs text-aspora-700 hover:underline truncate"
              >
                {rule.source_url}
              </a>
            ) : (
              <span className="text-muted-foreground italic">
                No source URL on this rule yet. Edit the rule to add one.
              </span>
            )}
          </div>

          {/* Action */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Fetches the regulator page, strips to plain text, compares against the last
              snapshot.
            </p>
            <Button
              onClick={() => checkMutation.mutate()}
              disabled={checkMutation.isPending || !rule.source_url}
            >
              {checkMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              {snapshots.length === 0 ? "Take first snapshot" : "Check now"}
            </Button>
          </div>

          {checkMutation.error && (
            <Callout tone="error">
              {(checkMutation.error as ApiError).message}
            </Callout>
          )}

          {/* Result */}
          {result && <ResultView result={result} />}

          {/* History */}
          {snapshots.length > 0 && (
            <div className="pt-3 border-t border-border">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-2 flex items-center gap-1.5">
                <History className="h-3 w-3" />
                Snapshot history
              </div>
              <ul className="space-y-1 max-h-48 overflow-y-auto scrollbar-thin">
                {snapshots.map((s) => (
                  <li
                    key={s.id}
                    className="flex items-center gap-2 text-xs text-muted-foreground border-b border-border last:border-0 py-1.5"
                  >
                    <Clock className="h-3 w-3 shrink-0" />
                    <span>{fmtDate(s.fetched_at, "d MMM yyyy HH:mm")}</span>
                    <Badge
                      variant={
                        s.http_status && s.http_status >= 200 && s.http_status < 300
                          ? "completed"
                          : "overdue"
                      }
                      className="text-[10px]"
                    >
                      {s.http_status ?? "—"}
                    </Badge>
                    <span className="font-mono text-[10px] opacity-70 truncate">
                      {s.content_hash.slice(0, 12)}…
                    </span>
                    {s.change_summary && (
                      <span className="ml-auto truncate max-w-[40%]" title={s.change_summary}>
                        {s.change_summary}
                      </span>
                    )}
                    {s.fetched_by && (
                      <span className="ml-auto text-[10px]">
                        by {s.fetched_by.full_name?.split(" ")[0]}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function ResultView({ result }: { result: RuleSourceCheckResult }) {
  if (result.error) {
    return <Callout tone="error">{result.error}</Callout>;
  }
  if (result.is_first_snapshot) {
    return (
      <Callout tone="info">
        First snapshot captured ({result.content_length.toLocaleString()} chars). Future
        checks will diff against this baseline.
      </Callout>
    );
  }
  if (!result.changed) {
    return (
      <Callout tone="ok">
        No changes since the last check ({fmtRelative(result.fetched_at)}).
      </Callout>
    );
  }
  return (
    <div className="space-y-3">
      <Callout tone="warn">
        Source page changed. {result.content_length.toLocaleString()} chars total.
      </Callout>

      {result.change_summary && (
        <div className="rounded-lg border border-aspora-200 bg-aspora-50 px-3 py-2 flex items-start gap-2 text-sm">
          <Sparkles className="h-4 w-4 text-aspora-700 mt-0.5 shrink-0" />
          <div>
            <div className="text-[10px] uppercase tracking-wider text-aspora-700 font-semibold">
              AI summary
            </div>
            <div>{result.change_summary}</div>
          </div>
        </div>
      )}

      {result.diff_excerpt && (
        <div>
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5">
            Unified diff (truncated)
          </div>
          <pre className="rounded-lg border border-border bg-secondary/40 p-3 text-xs font-mono overflow-auto max-h-64 scrollbar-thin whitespace-pre-wrap">
            {result.diff_excerpt.split("\n").map((line, i) => (
              <div
                key={i}
                className={cn(
                  line.startsWith("+") && !line.startsWith("+++") && "text-emerald-700",
                  line.startsWith("-") && !line.startsWith("---") && "text-red-700",
                  (line.startsWith("@@") || line.startsWith("+++") || line.startsWith("---")) &&
                    "text-muted-foreground",
                )}
              >
                {line}
              </div>
            ))}
          </pre>
        </div>
      )}
    </div>
  );
}


function Callout({
  tone,
  children,
}: {
  tone: "ok" | "warn" | "error" | "info";
  children: React.ReactNode;
}) {
  const toneCfg = {
    ok: { cls: "border-emerald-200 bg-emerald-50 text-emerald-800", Icon: CheckCircle2 },
    warn: { cls: "border-amber-200 bg-amber-50 text-amber-900", Icon: AlertCircle },
    error: { cls: "border-destructive/30 bg-destructive/5 text-destructive", Icon: AlertCircle },
    info: { cls: "border-aspora-200 bg-aspora-50 text-aspora-800", Icon: Sparkles },
  }[tone];
  const Icon = toneCfg.Icon;
  return (
    <div className={cn("rounded-lg border px-3 py-2 text-sm flex items-start gap-2", toneCfg.cls)}>
      <Icon className="h-4 w-4 mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}
