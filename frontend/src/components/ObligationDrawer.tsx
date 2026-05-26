import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, ExternalLink, MessageCircle, Send, Loader2 } from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/StatusPill";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { fmtDate, fmtRelative, userInitials } from "@/lib/format";
import { cn } from "@/lib/utils";
import type {
  Comment as ApiComment,
  Obligation,
  ObligationStatus,
  UserBrief,
} from "@/types/api";


const STATUS_OPTIONS: { value: ObligationStatus; label: string }[] = [
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "pending_review", label: "Pending review" },
  { value: "completed", label: "Completed" },
  { value: "not_applicable", label: "Not applicable" },
];


export function ObligationDrawer() {
  const { obligationId, closeObligation } = useObligationDrawer();
  return (
    <Dialog open={obligationId !== null} onOpenChange={(open) => !open && closeObligation()}>
      <DialogContent side="right" hideCloseButton className="p-0">
        {obligationId !== null && <Body obligationId={obligationId} />}
      </DialogContent>
    </Dialog>
  );
}


function Body({ obligationId }: { obligationId: number }) {
  const queryClient = useQueryClient();
  const { closeObligation } = useObligationDrawer();

  const { data: obligation, isLoading } = useQuery({
    queryKey: ["obligation", obligationId],
    queryFn: () => api.get<Obligation>(`/api/obligations/${obligationId}`),
  });

  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserBrief[]>("/api/users"),
  });

  const patchMutation = useMutation({
    mutationFn: (patch: Partial<Obligation>) =>
      api.patch<Obligation>(`/api/obligations/${obligationId}`, patch),
    onSuccess: (fresh) => {
      queryClient.setQueryData(["obligation", obligationId], fresh);
      // Invalidate the lists that show this obligation so counts/rows refresh.
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["entity-obligations"] });
      queryClient.invalidateQueries({ queryKey: ["entities"] });
    },
  });

  if (isLoading || !obligation) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-24" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <Header obligation={obligation} onClose={closeObligation} />
      <div className="flex-1 overflow-y-auto p-5 space-y-6 scrollbar-thin">
        <Fields
          obligation={obligation}
          users={users}
          onPatch={(p) => patchMutation.mutate(p)}
          isPatching={patchMutation.isPending}
        />
        <CommentsSection obligationId={obligationId} />
      </div>
    </div>
  );
}


function Header({ obligation, onClose }: { obligation: Obligation; onClose: () => void }) {
  return (
    <div className="px-5 pt-5 pb-4 border-b border-border bg-gradient-to-br from-aspora-50 to-background">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wider text-muted-foreground">
            {obligation.rule_category} · {obligation.rule_authority}
          </div>
          <h2 className="text-lg font-semibold leading-tight mt-1">
            {obligation.rule_form_name}
          </h2>
          <Link
            to={`/entities/${obligation.entity_id}`}
            onClick={onClose}
            className="mt-2 inline-flex items-center gap-1.5 text-sm text-aspora-700 hover:text-aspora-800 hover:underline"
          >
            <Building2 className="h-3.5 w-3.5" />
            <JurisdictionBadge code={obligation.entity_jurisdiction_code} showName={false} />
            <span className="font-medium">{obligation.entity_name}</span>
            <ExternalLink className="h-3 w-3 opacity-60" />
          </Link>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>

      <div className="mt-4 flex items-center gap-2 flex-wrap">
        <StatusPill status={obligation.status} isOverdue={obligation.is_overdue} />
        <StatusPill
          status={obligation.status}
          isOverdue={obligation.is_overdue}
          daysRemaining={obligation.days_remaining}
          showDays
        />
        <Badge variant="neutral">Due {fmtDate(obligation.due_date)}</Badge>
        {obligation.period_label && <Badge variant="neutral">{obligation.period_label}</Badge>}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Editable fields
// ---------------------------------------------------------------------------
function Fields({
  obligation,
  users,
  onPatch,
  isPatching,
}: {
  obligation: Obligation;
  users: UserBrief[];
  onPatch: (p: Partial<Obligation>) => void;
  isPatching: boolean;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs uppercase tracking-wider text-muted-foreground">Details</h3>
        {isPatching && (
          <span className="text-xs text-muted-foreground inline-flex items-center gap-1.5">
            <Loader2 className="h-3 w-3 animate-spin" />
            Saving…
          </span>
        )}
      </div>

      <FieldRow label="Status">
        <select
          value={obligation.status}
          onChange={(e) => onPatch({ status: e.target.value as ObligationStatus })}
          className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </FieldRow>

      <FieldRow label="Assignee">
        <div className="flex items-center gap-2">
          {obligation.assignee && (
            <Avatar className="h-7 w-7">
              <AvatarFallback className="text-[10px]">
                {userInitials(obligation.assignee.full_name)}
              </AvatarFallback>
            </Avatar>
          )}
          <select
            value={obligation.assignee?.id ?? ""}
            onChange={(e) =>
              onPatch({
                assignee_id: e.target.value ? Number(e.target.value) : null,
              } as Partial<Obligation>)
            }
            className="h-9 flex-1 rounded-lg border border-input bg-background px-3 text-sm"
          >
            <option value="">Unassigned</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name} ({u.role})
              </option>
            ))}
          </select>
        </div>
      </FieldRow>

      <DebouncedTextField
        label="Filing reference"
        placeholder="ACK # / receipt no. / portal reference"
        value={obligation.filing_reference}
        onCommit={(v) => onPatch({ filing_reference: v })}
      />
      <DebouncedTextField
        label="Payment amount"
        placeholder="₹, $, £…"
        value={obligation.payment_amount}
        onCommit={(v) => onPatch({ payment_amount: v })}
      />
      <DebouncedTextField
        label="Payment reference"
        placeholder="UTR / transaction id"
        value={obligation.payment_reference}
        onCommit={(v) => onPatch({ payment_reference: v })}
      />
      <DebouncedTextField
        label="Notes"
        placeholder="Anything the next reviewer should know…"
        value={obligation.notes}
        onCommit={(v) => onPatch({ notes: v })}
        multiline
      />

      <FieldRow label="Due-date rule">
        <div className="rounded-lg border border-border bg-secondary/40 px-3 py-2 text-sm text-muted-foreground">
          {fmtDate(obligation.due_date)} ·{" "}
          <span className="italic">{obligation.rule_frequency}</span>
        </div>
      </FieldRow>
    </div>
  );
}


function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-muted-foreground mb-1.5">
        {label}
      </label>
      {children}
    </div>
  );
}


function DebouncedTextField({
  label,
  placeholder,
  value,
  onCommit,
  multiline = false,
}: {
  label: string;
  placeholder?: string;
  value: string | null;
  onCommit: (next: string | null) => void;
  multiline?: boolean;
}) {
  // Local state so the user can type without each keystroke hitting the API.
  // Commit on blur OR after 700ms of inactivity.
  const [local, setLocal] = useState(value ?? "");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync local when the prop changes (e.g. drawer opened on a different obligation).
  useEffect(() => {
    setLocal(value ?? "");
  }, [value]);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const scheduleCommit = (next: string) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const cleaned = next.trim();
      if (cleaned === (value ?? "")) return;
      onCommit(cleaned || null);
    }, 700);
  };

  const flushCommit = () => {
    if (timer.current) clearTimeout(timer.current);
    const cleaned = local.trim();
    if (cleaned === (value ?? "")) return;
    onCommit(cleaned || null);
  };

  return (
    <FieldRow label={label}>
      {multiline ? (
        <textarea
          rows={3}
          value={local}
          placeholder={placeholder}
          onChange={(e) => {
            setLocal(e.target.value);
            scheduleCommit(e.target.value);
          }}
          onBlur={flushCommit}
          className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      ) : (
        <input
          type="text"
          value={local}
          placeholder={placeholder}
          onChange={(e) => {
            setLocal(e.target.value);
            scheduleCommit(e.target.value);
          }}
          onBlur={flushCommit}
          className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      )}
    </FieldRow>
  );
}


// ---------------------------------------------------------------------------
// Comments
// ---------------------------------------------------------------------------
function CommentsSection({ obligationId }: { obligationId: number }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");

  const { data: comments = [], isLoading } = useQuery({
    queryKey: ["obligation-comments", obligationId],
    queryFn: () => api.get<ApiComment[]>(`/api/obligations/${obligationId}/comments`),
  });

  const postMutation = useMutation({
    mutationFn: (body: string) =>
      api.post<ApiComment>(`/api/obligations/${obligationId}/comments`, { body }),
    onSuccess: () => {
      setDraft("");
      queryClient.invalidateQueries({ queryKey: ["obligation-comments", obligationId] });
    },
  });

  function submit() {
    const cleaned = draft.trim();
    if (!cleaned || postMutation.isPending) return;
    postMutation.mutate(cleaned);
  }

  return (
    <div>
      <h3 className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5 mb-3">
        <MessageCircle className="h-3.5 w-3.5" />
        Comments
        <Badge variant="neutral">{comments.length}</Badge>
      </h3>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : comments.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-secondary/30 px-3 py-4 text-sm text-muted-foreground text-center">
          No comments yet. Drop a note for the next reviewer.
        </div>
      ) : (
        <ul className="space-y-3">
          {comments.map((c) => (
            <li
              key={c.id}
              className={cn(
                "rounded-lg border border-border px-3 py-2.5",
                c.author.id === user?.id ? "bg-aspora-50/40" : "bg-background",
              )}
            >
              <div className="flex items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2">
                  <Avatar className="h-5 w-5">
                    <AvatarFallback className="text-[9px]">
                      {userInitials(c.author.full_name)}
                    </AvatarFallback>
                  </Avatar>
                  <span className="font-medium">{c.author.full_name}</span>
                </div>
                <span className="text-muted-foreground">{fmtRelative(c.created_at)}</span>
              </div>
              <div className="mt-2 text-sm whitespace-pre-wrap">{c.body}</div>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 rounded-lg border border-border bg-background overflow-hidden">
        <textarea
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a comment…"
          className="block w-full px-3 py-2 text-sm focus:outline-none resize-none border-0"
        />
        <div className="flex justify-end px-2 py-2 border-t border-border bg-secondary/30">
          <Button size="sm" onClick={submit} disabled={!draft.trim() || postMutation.isPending}>
            {postMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
            Post
          </Button>
        </div>
      </div>
    </div>
  );
}
