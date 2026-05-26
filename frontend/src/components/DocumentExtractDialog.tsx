// "Auto-fill from document" — opens after clicking the AI sparkle button on a
// document row inside an obligation. Calls /api/ai/extract-from-document/{id},
// shows the suggestion as editable fields, and on Apply, PATCHes the parent
// obligation. The user always confirms before anything writes.

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
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
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  DocumentExtractionResult,
  DocumentOut,
  Obligation,
} from "@/types/api";


interface Props {
  doc: DocumentOut;
  obligationId: number;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}


export function DocumentExtractDialog({ doc, obligationId, open, onOpenChange }: Props) {
  const queryClient = useQueryClient();

  // Run the extractor lazily — only fire the call once the dialog is open.
  const extractQuery = useQuery<DocumentExtractionResult, ApiError>({
    queryKey: ["ai-extract", doc.id],
    queryFn: () =>
      api.post<DocumentExtractionResult>(`/api/ai/extract-from-document/${doc.id}`),
    enabled: open,
    staleTime: 60_000,
    retry: false,
  });

  const suggestion = extractQuery.data?.suggestion ?? null;

  // Editable working copy of the suggested values.
  const [filing, setFiling] = useState<string>("");
  const [paymentAmount, setPaymentAmount] = useState<string>("");
  const [paymentRef, setPaymentRef] = useState<string>("");
  const [completedAt, setCompletedAt] = useState<string>("");
  const [notes, setNotes] = useState<string>("");

  useEffect(() => {
    if (suggestion) {
      setFiling(suggestion.filing_reference ?? "");
      setPaymentAmount(suggestion.payment_amount ?? "");
      setPaymentRef(suggestion.payment_reference ?? "");
      setCompletedAt(suggestion.completed_at ?? "");
      setNotes(suggestion.notes_suggestion ?? "");
    } else {
      setFiling("");
      setPaymentAmount("");
      setPaymentRef("");
      setCompletedAt("");
      setNotes("");
    }
  }, [suggestion]);

  const applyMutation = useMutation({
    mutationFn: () => {
      const patch: Partial<Obligation> & { status?: Obligation["status"] } = {};
      if (filing.trim()) patch.filing_reference = filing.trim();
      if (paymentAmount.trim()) patch.payment_amount = paymentAmount.trim();
      if (paymentRef.trim()) patch.payment_reference = paymentRef.trim();
      if (notes.trim()) patch.notes = notes.trim();
      if (completedAt.trim()) {
        patch.status = "completed";
      }
      return api.patch<Obligation>(`/api/obligations/${obligationId}`, patch);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["obligation", obligationId] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["entity-obligations"] });
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      onOpenChange(false);
    },
  });

  const result = extractQuery.data;
  const aiOff = result && !result.available;
  const noText = result?.available && !result.suggestion && result.error;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-aspora-600" />
            Auto-fill from {doc.filename}
          </DialogTitle>
        </DialogHeader>

        <div className="p-6 space-y-3">
          {extractQuery.isLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Reading document and asking Claude…
            </div>
          )}

          {extractQuery.error && (
            <CalloutBox tone="error">{extractQuery.error.message}</CalloutBox>
          )}

          {aiOff && (
            <CalloutBox tone="warn">
              {result?.error ||
                "AI is off in this deployment. Set COMPLIANCE_AGENT_LIVE=1 + ANTHROPIC_API_KEY."}
            </CalloutBox>
          )}

          {noText && (
            <CalloutBox tone="warn">{result?.error}</CalloutBox>
          )}

          {suggestion && (
            <>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">
                  Confidence:{" "}
                  <Badge
                    variant={
                      suggestion.confidence === "high"
                        ? "completed"
                        : suggestion.confidence === "medium"
                          ? "alert"
                          : "neutral"
                    }
                  >
                    {suggestion.confidence}
                  </Badge>
                </span>
                <button
                  onClick={() => extractQuery.refetch()}
                  className="text-aspora-700 hover:underline"
                >
                  Re-extract
                </button>
              </div>

              <Field label="Filing reference">
                <Input
                  value={filing}
                  onChange={(e) => setFiling(e.target.value)}
                  placeholder="ACK # / receipt no."
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Payment amount">
                  <Input
                    value={paymentAmount}
                    onChange={(e) => setPaymentAmount(e.target.value)}
                  />
                </Field>
                <Field label="Payment reference">
                  <Input
                    value={paymentRef}
                    onChange={(e) => setPaymentRef(e.target.value)}
                  />
                </Field>
              </div>
              <Field label="Filed on (sets status to Completed)">
                <Input
                  type="date"
                  value={completedAt}
                  onChange={(e) => setCompletedAt(e.target.value)}
                />
              </Field>
              <Field label="Notes (suggestion)">
                <textarea
                  rows={3}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                />
              </Field>
              <p className="text-[11px] text-muted-foreground">
                Review and edit before applying — Claude can be wrong, especially on
                payment-reference vs filing-reference distinctions.
              </p>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          {suggestion && (
            <Button
              onClick={() => applyMutation.mutate()}
              disabled={applyMutation.isPending}
            >
              {applyMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="h-3.5 w-3.5" />
              )}
              Apply to obligation
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs font-medium text-muted-foreground mb-1 block">{label}</label>
      {children}
    </div>
  );
}


function CalloutBox({
  tone,
  children,
}: {
  tone: "error" | "warn";
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border px-3 py-2 text-sm flex items-start gap-2",
        tone === "error"
          ? "border-destructive/30 bg-destructive/5 text-destructive"
          : "border-amber-200 bg-amber-50 text-amber-900",
      )}
    >
      <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}
