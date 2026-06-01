// AI second-opinion card — shown on pending_review obligations. The user
// clicks "Get AI second opinion" and we POST to /api/ai/second-opinion/{id};
// the result renders inline with verdict pill + reasoning + risk flags.

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  HelpCircle,
  Loader2,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api, ApiError } from "@/lib/api";
import { useAiAvailable } from "@/lib/ai";
import { cn } from "@/lib/utils";
import type { SecondOpinion, SecondOpinionResult } from "@/types/api";


interface Props {
  obligationId: number;
}


export function SecondOpinionPanel({ obligationId }: Props) {
  const { available, tooltip } = useAiAvailable();
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.post<SecondOpinionResult>(`/api/ai/second-opinion/${obligationId}`),
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
    onSuccess: (r) => {
      setError(r.error ?? null);
    },
  });

  const result = mutation.data;

  return (
    <Card>
      <CardContent className="p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5" />
            Second opinion
          </h3>
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button
                  size="sm"
                  onClick={() => mutation.mutate()}
                  disabled={!available || mutation.isPending}
                >
                  {mutation.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="h-3.5 w-3.5" />
                  )}
                  Get AI second opinion
                </Button>
              </span>
            </TooltipTrigger>
            {!available && <TooltipContent>{tooltip}</TooltipContent>}
          </Tooltip>
        </div>

        {!result && !mutation.isPending && (
          <p className="text-sm text-muted-foreground">
            Grok reviews the rule, the filled fields, comments, and attached document
            list, and returns a verdict (approve / needs_more_info / reject) plus risk
            flags. Useful as a second pair of eyes before you sign off a pending review.
          </p>
        )}

        {mutation.isPending && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Reviewing the obligation…
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive flex items-start gap-2">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
            <div>{error}</div>
          </div>
        )}

        {result?.opinion && <OpinionView opinion={result.opinion} />}
      </CardContent>
    </Card>
  );
}


function OpinionView({ opinion }: { opinion: SecondOpinion }) {
  const verdictConfig = {
    approve: {
      label: "Approve",
      tone: "bg-emerald-50 border-emerald-200 text-emerald-800",
      Icon: CheckCircle2,
    },
    needs_more_info: {
      label: "Needs more info",
      tone: "bg-amber-50 border-amber-200 text-amber-800",
      Icon: HelpCircle,
    },
    reject: {
      label: "Reject",
      tone: "bg-red-50 border-red-200 text-red-800",
      Icon: XCircle,
    },
  }[opinion.verdict];

  const Icon = verdictConfig.Icon;

  return (
    <div className="space-y-3">
      <div
        className={cn(
          "rounded-lg border px-4 py-3 flex items-start gap-3",
          verdictConfig.tone,
        )}
      >
        <Icon className="h-5 w-5 mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="font-semibold">{verdictConfig.label}</div>
            <Badge variant="neutral" className="text-[10px]">
              {opinion.confidence} confidence
            </Badge>
          </div>
          <p className="text-sm mt-1 leading-relaxed">{opinion.reasoning}</p>
        </div>
      </div>

      {opinion.risk_flags.length > 0 && (
        <div>
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5">
            Risk flags
          </div>
          <ul className="space-y-1">
            {opinion.risk_flags.map((f, i) => (
              <li key={i} className="text-sm flex items-start gap-2">
                <AlertCircle className="h-3.5 w-3.5 mt-0.5 text-red-600 shrink-0" />
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {opinion.suggested_next_steps.length > 0 && (
        <div>
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5">
            Suggested next steps
          </div>
          <ol className="list-decimal list-inside text-sm space-y-1 text-muted-foreground">
            {opinion.suggested_next_steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </div>
      )}

      <p className="text-[11px] text-muted-foreground italic">
        Grok's review is advisory — confirm with the rule itself and the attached
        documents before approving.
      </p>
    </div>
  );
}
