// Shared obligation detail body — used by ObligationDrawer (side panel) and
// ObligationDetailPage (full page). Two layouts diverge only in the right
// sidebar: page shows it inline, drawer stacks it below the main content.

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity as ActivityIcon,
  Building2,
  CheckCircle2,
  ExternalLink,
  Loader2,
  MessageCircle,
  Pencil,
  Send,
  UserCheck,
  Calendar as CalendarIcon,
  AlertTriangle,
  Slack,
  Mail,
  Tag,
  FileText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { StatusPill } from "@/components/StatusPill";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { EffortBandBadge } from "@/components/EffortBandBadge";
import { DaysRemainingCounter } from "@/components/DaysRemainingCounter";
import { AssigneeChip } from "@/components/AssigneeChip";
import { DocumentList } from "@/components/DocumentList";
import { MentionTextarea, renderCommentBody } from "@/components/MentionTextarea";
import { SecondOpinionPanel } from "@/components/SecondOpinionPanel";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { fmtDate, fmtRelative, userInitials, EFFORT_BANDS } from "@/lib/format";
import { cn } from "@/lib/utils";
import type {
  ActivityOut,
  Comment as ApiComment,
  EffortBand,
  Obligation,
  ObligationStatus,
  UserBrief,
} from "@/types/api";


// ---------------------------------------------------------------------------
// HandoffToFinanceButton — admin approves filing + reassigns to a finance
// team member in one move. Replaces "Approve & file" when the rule has a
// payment leg, because the obligation isn't actually done until finance pays.
// ---------------------------------------------------------------------------
function HandoffToFinanceButton({
  obligationId,
  users,
  disabled,
}: {
  obligationId: number;
  users: UserBrief[];
  disabled: boolean;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [pickedId, setPickedId] = useState<number | "">("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const financeUsers = users.filter(
    (u) => (u.department ?? "") === "finance",
  );

  const mutation = useMutation({
    mutationFn: () =>
      api.post(`/api/obligations/${obligationId}/handoff-to-finance`, {
        finance_user_id: pickedId,
        notes: note.trim() || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["obligation", obligationId] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["sidebar-task-count"] });
      setOpen(false);
      setPickedId("");
      setNote("");
      setError(null);
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  });

  return (
    <>
      <Button
        size="sm"
        onClick={() => setOpen(true)}
        disabled={disabled}
        title="Approve the filing + assign payment to a finance team member"
      >
        <CheckCircle2 className="h-3.5 w-3.5" />
        Approve & hand off to finance
      </Button>
      {open && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm grid place-items-center"
          onClick={() => !mutation.isPending && setOpen(false)}
        >
          <div
            className="bg-background rounded-2xl shadow-2xl border border-border w-[480px] max-w-[95vw] p-5 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h3 className="font-semibold text-lg">
                Approve & hand off to finance
              </h3>
              <p className="text-sm text-muted-foreground mt-1">
                Filing is verified. Pick a finance team member to log the
                payment and UTR. They'll get a notification + Slack ping
                immediately.
              </p>
            </div>

            {financeUsers.length === 0 ? (
              <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5 text-sm text-amber-900">
                No users tagged with the <strong>finance</strong> team yet.
                Set someone's team in Settings → Users & Roles → Edit user →
                Team.
              </div>
            ) : (
              <div className="space-y-1">
                <label className="text-xs font-medium">
                  Finance team member
                </label>
                <select
                  value={pickedId}
                  onChange={(e) =>
                    setPickedId(e.target.value ? Number(e.target.value) : "")
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-2 text-sm"
                >
                  <option value="">Pick someone…</option>
                  {financeUsers.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.full_name || u.email}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="space-y-1">
              <label className="text-xs font-medium">
                Note for finance (optional)
              </label>
              <textarea
                rows={3}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Anything finance needs to know — payment amount, beneficiary, deadline…"
                className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm"
              />
            </div>

            {error && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setOpen(false)}
                disabled={mutation.isPending}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => mutation.mutate()}
                disabled={
                  mutation.isPending ||
                  !pickedId ||
                  financeUsers.length === 0
                }
              >
                {mutation.isPending && (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                )}
                Hand off
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}


const STATUS_OPTIONS: { value: ObligationStatus; label: string }[] = [
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "pending_review", label: "Pending review" },
  { value: "completed", label: "Completed" },
  { value: "not_applicable", label: "Not applicable" },
];


interface Props {
  obligationId: number;
  variant: "drawer" | "page";
  onClose?: () => void;
}


export function ObligationDetail({ obligationId, variant, onClose }: Props) {
  const queryClient = useQueryClient();
  const { user: currentUser } = useAuth();

  const { data: obligation, isLoading } = useQuery({
    queryKey: ["obligation", obligationId],
    queryFn: () => api.get<Obligation>(`/api/obligations/${obligationId}`),
    // Poll while open so other users' changes (status flips, assignee
    // moves, payment fields) propagate without manual refresh. 10s feels
    // close to real-time without hammering the server.
    refetchInterval: 10_000,
    refetchOnWindowFocus: true,
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
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["entity-obligations"] });
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      queryClient.invalidateQueries({ queryKey: ["sidebar-task-count"] });
    },
  });

  if (isLoading || !obligation) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-10 w-3/4" />
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-32" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <div className={cn(variant === "drawer" ? "flex flex-col h-full" : "")}>
      <Header obligation={obligation} variant={variant} onClose={onClose} />
      <WorkflowBanner obligation={obligation} />
      <ActionBar
        obligation={obligation}
        users={users}
        onPatch={(p) => patchMutation.mutate(p)}
        saving={patchMutation.isPending}
        currentUser={currentUser}
      />
      <Body
        obligation={obligation}
        users={users}
        onPatch={(p) => patchMutation.mutate(p)}
        variant={variant}
        currentUser={currentUser}
      />
    </div>
  );
}


// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------
function Header({
  obligation,
  variant,
  onClose,
}: {
  obligation: Obligation;
  variant: "drawer" | "page";
  onClose?: () => void;
}) {
  return (
    <div
      className={cn(
        "border-b border-border bg-gradient-to-br from-aspora-50 to-background",
        variant === "drawer" ? "px-5 pt-5 pb-4" : "px-6 pt-6 pb-5 rounded-t-xl",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="text-xs uppercase tracking-wider text-muted-foreground">
            {obligation.rule_category} · {obligation.rule_authority}
          </div>
          <h1
            className={cn(
              "font-semibold leading-tight mt-1",
              variant === "drawer" ? "text-lg" : "text-2xl",
            )}
          >
            {obligation.rule_form_name}
          </h1>
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

          <div className="mt-4 flex items-center gap-2 flex-wrap">
            <StatusPill
              status={obligation.status}
              isOverdue={obligation.is_overdue}
              isAwaitingPayment={obligation.is_awaiting_payment}
            />
            <Badge variant="neutral">Due {fmtDate(obligation.due_date)}</Badge>
            {obligation.period_label && <Badge variant="neutral">{obligation.period_label}</Badge>}
            <EffortBandBadge band={obligation.effort_band} showLabel />
          </div>
        </div>

        <div className="flex items-start gap-3">
          <DaysRemainingCounter
            daysRemaining={obligation.days_remaining}
            effortBand={obligation.effort_band}
            size={variant === "page" ? "lg" : "md"}
          />
          {variant === "drawer" && onClose && (
            <Button variant="ghost" size="sm" onClick={onClose}>
              Close
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Workflow banner — shows where this item is in the verification → payment
// → done pipeline. Helps employees + finance know what's expected of them
// without reading the status enum.
// ---------------------------------------------------------------------------
function WorkflowBanner({ obligation }: { obligation: Obligation }) {
  const hasPaymentLeg = Boolean(obligation.rule_payment_rule);
  const hasPaymentLogged = Boolean(obligation.payment_reference?.trim());
  const isFinanceAssignee =
    (obligation.assignee?.department ?? "") === "finance";

  let tone: "info" | "amber" | "emerald" = "info";
  let title = "";
  let body = "";

  if (obligation.status === "not_started") {
    tone = "info";
    title = "Step 1 — Compliance prepares the filing";
    body = "Assignee works on the filing. When ready, hit Submit for review and an admin will verify it.";
  } else if (obligation.status === "in_progress") {
    if (isFinanceAssignee || (hasPaymentLeg && !hasPaymentLogged && obligation.department === "finance")) {
      // Admin handed off to finance — Step 3
      tone = "amber";
      title = "Step 3 — Finance logs the payment";
      body = "Filing was verified by the admin. Enter the payment amount + UTR below, then hit Submit for review for the final sign-off.";
    } else {
      tone = "info";
      title = "Step 1 — Compliance prepares the filing";
      body = "Assignee works on the filing. When ready, hit Submit for review and an admin will verify it.";
    }
  } else if (obligation.status === "pending_review") {
    if (hasPaymentLogged) {
      // Finance submitted payment — admin's final review
      tone = "amber";
      title = "Step 4 — Admin final sign-off";
      body = "Finance has logged the payment. Admin: review the UTR + amount and click Approve & close to finish.";
    } else {
      tone = "amber";
      title = "Step 2 — Admin verifies the filing";
      body = hasPaymentLeg
        ? "Compliance submitted. Admin will verify, then hand off to finance for payment."
        : "Compliance submitted. Admin will verify and approve.";
    }
  } else if (obligation.status === "completed" && obligation.is_awaiting_payment) {
    // Legacy state — pre-handoff completion. Shouldn't reach here in the new flow.
    tone = "amber";
    title = "Step 3 — Finance pays";
    body = "Filing approved. Log the payment amount + UTR below to close it out.";
  } else if (obligation.status === "completed") {
    tone = "emerald";
    title = "Done";
    body = hasPaymentLogged
      ? "Filed and paid. Sitting in the audit trail."
      : hasPaymentLeg
        ? "Marked completed without a payment record. Verify in Filing Record below."
        : "Filed. No payment leg on this rule.";
  } else {
    return null;
  }

  const toneClasses = {
    info: "border-aspora-200 bg-aspora-50 text-aspora-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-900",
  }[tone];

  return (
    <div className={cn("border-b px-5 py-2.5 text-sm", toneClasses)}>
      <span className="font-medium">{title}</span>
      <span className="text-foreground/70"> — {body}</span>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Sticky action bar — Update status / Assign / Mark filed / Request ext. / kebab
// ---------------------------------------------------------------------------
function ActionBar({
  obligation,
  users,
  onPatch,
  saving,
  currentUser,
}: {
  obligation: Obligation;
  users: UserBrief[];
  onPatch: (p: Partial<Obligation>) => void;
  saving: boolean;
  currentUser: { id: number; role: string } | null;
}) {
  const isAdmin = currentUser?.role === "admin";
  const isAssignee = currentUser?.id === obligation.assignee?.id;
  return (
    <div className="border-b border-border bg-background sticky top-0 z-10">
      <div className="flex items-center gap-2 px-5 py-2.5 flex-wrap">
        {/* Anyone can pop the status menu, but for employees it's only
            useful on items assigned to them. Admins can manipulate any item. */}
        {(isAdmin || isAssignee) && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" disabled={saving}>
              <Pencil className="h-3.5 w-3.5" />
              Update status
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuLabel>Change status to…</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {STATUS_OPTIONS.map((o) => (
              <DropdownMenuItem
                key={o.value}
                onClick={() => onPatch({ status: o.value })}
                disabled={o.value === obligation.status}
              >
                {o.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        )}

        {isAdmin && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" disabled={saving}>
              <UserCheck className="h-3.5 w-3.5" />
              Assign
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuLabel>Assign to…</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => onPatch({ assignee: null } as Partial<Obligation>)}
            >
              Unassigned
            </DropdownMenuItem>
            {users.map((u) => (
              <DropdownMenuItem
                key={u.id}
                onClick={() => onPatch({ assignee_id: u.id } as never)}
              >
                <Avatar className="h-5 w-5 mr-2">
                  <AvatarFallback className="text-[9px]">
                    {userInitials(u.full_name)}
                  </AvatarFallback>
                </Avatar>
                {u.full_name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        )}

        {/* Verification workflow buttons — shown based on status + role.
            Employees submit for review; admins approve or send back. */}
        {(() => {
          const status = obligation.status;

          // Done — show a quiet "reopen" affordance for admins only
          if (status === "completed") {
            return isAdmin ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onPatch({ status: "in_progress" })}
                disabled={saving}
                title="Move back to in-progress"
              >
                Reopen
              </Button>
            ) : null;
          }

          // Pending admin review — admin gets Approve / Send back.
          // Two flavours: filing review (compliance just finished prepping)
          // vs payment review (finance just logged the UTR). We pick which
          // by checking payment_reference: empty = filing phase, filled =
          // payment phase. Filing phase + payment_rule → Hand off button.
          if (status === "pending_review") {
            const hasPaymentLeg = Boolean(obligation.rule_payment_rule);
            const isPaymentReview =
              hasPaymentLeg && Boolean(obligation.payment_reference?.trim());
            return isAdmin ? (
              <>
                {hasPaymentLeg && !isPaymentReview ? (
                  // Filing-review phase + payment leg exists → admin hands
                  // off to finance instead of completing directly.
                  <HandoffToFinanceButton
                    obligationId={obligation.id}
                    users={users}
                    disabled={saving}
                  />
                ) : (
                  <Button
                    size="sm"
                    onClick={() => onPatch({ status: "completed" })}
                    disabled={saving}
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    {isPaymentReview ? "Approve & close" : "Approve & file"}
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onPatch({ status: "in_progress" })}
                  disabled={saving}
                  title="Send back to the assignee"
                >
                  Send back
                </Button>
              </>
            ) : (
              <span className="text-xs text-muted-foreground italic">
                Awaiting admin review.
              </span>
            );
          }

          // Not started / in progress
          // - Assignee submits for review when they're done
          // - Admins can ALSO directly approve & file in one click
          return (
            <>
              {(isAssignee || isAdmin) && (
                <Button
                  size="sm"
                  onClick={() => onPatch({ status: "pending_review" })}
                  disabled={saving}
                  title="Mark done — admin will review + approve"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Submit for review
                </Button>
              )}
              {isAdmin && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onPatch({ status: "completed" })}
                  disabled={saving}
                  title="Skip review and mark as filed directly"
                >
                  Mark as filed
                </Button>
              )}
            </>
          );
        })()}

        <div className="ml-auto flex items-center gap-2">
          {saving && (
            <span className="text-xs text-muted-foreground inline-flex items-center gap-1.5">
              <Loader2 className="h-3 w-3 animate-spin" />
              Saving…
            </span>
          )}
        </div>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Body — two layouts. Page = 2-column; Drawer = stacked.
// ---------------------------------------------------------------------------
function Body({
  obligation,
  users,
  onPatch,
  variant,
  currentUser,
}: {
  obligation: Obligation;
  users: UserBrief[];
  onPatch: (p: Partial<Obligation>) => void;
  variant: "drawer" | "page";
  currentUser: { id: number; role: string } | null;
}) {
  const showSecondOpinion = obligation.status === "pending_review";
  const isAdmin = currentUser?.role === "admin";
  if (variant === "drawer") {
    return (
      <div className="flex-1 overflow-y-auto p-5 space-y-6 scrollbar-thin">
        <MainContent obligation={obligation} />
        {showSecondOpinion && <SecondOpinionPanel obligationId={obligation.id} />}
        <FilingFields obligation={obligation} onPatch={onPatch} />
        {/* Comments live HIGH in the drawer scroll so they're discoverable.
            Sidebar (assignee + effort + alert) is below since those are
            already in the action bar at the top. */}
        <CommentsSection obligationId={obligation.id} />
        <Sidebar obligation={obligation} users={users} onPatch={onPatch} isAdmin={isAdmin} />
        <ActivityFeed obligationId={obligation.id} />
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 p-6">
      <div className="space-y-6 min-w-0">
        <MainContent obligation={obligation} />
        {showSecondOpinion && <SecondOpinionPanel obligationId={obligation.id} />}
        <FilingFields obligation={obligation} onPatch={onPatch} />
        <CommentsSection obligationId={obligation.id} />
        <ActivityFeed obligationId={obligation.id} />
      </div>
      <div className="space-y-4">
        <Sidebar obligation={obligation} users={users} onPatch={onPatch} isAdmin={isAdmin} />
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Main content (left/top): description, source, form template, prior filings,
// expert notes.
// ---------------------------------------------------------------------------
function MainContent({ obligation }: { obligation: Obligation }) {
  return (
    <Card>
      <CardContent className="p-5 space-y-5">
        <section>
          <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
            Description
          </h3>
          <p className="text-sm leading-relaxed">
            {obligation.rule_due_date_rule || (
              <span className="italic text-muted-foreground">
                No description captured for this rule yet.
              </span>
            )}
          </p>
        </section>

        <section>
          <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
            Source
          </h3>
          {obligation.rule_source_url ? (
            <a
              href={obligation.rule_source_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-aspora-700 hover:underline"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Regulator page
            </a>
          ) : (
            <div className="text-sm text-muted-foreground italic">
              No source URL captured yet — add one in the rule template.
            </div>
          )}
        </section>

        <section>
          <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            Filing documents
          </h3>
          <DocumentList
            scope={{
              kind: "obligation",
              obligationId: obligation.id,
              entityId: obligation.entity_id,
            }}
            hint="Attach proof-of-filing, receipts, or supporting docs. Max 25 MB per file."
            layout="rows"
          />
        </section>

        <section>
          <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
            Notes from country expert
          </h3>
          <div className="rounded-lg border border-border bg-secondary/20 px-4 py-3 text-sm text-muted-foreground italic">
            {obligation.notes || "No expert notes attached. Use the Notes field below to add internal context."}
          </div>
        </section>
      </CardContent>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Right sidebar (page) — assignee, effort band, alert schedule, ClickUp, tags
// ---------------------------------------------------------------------------
function Sidebar({
  obligation,
  users,
  onPatch,
  isAdmin,
}: {
  obligation: Obligation;
  users: UserBrief[];
  onPatch: (p: Partial<Obligation>) => void;
  isAdmin: boolean;
}) {
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 space-y-4">
          <AssigneeRow
            obligation={obligation}
            users={users}
            onSave={(newId) =>
              onPatch({
                assignee_id: newId,
              } as Partial<Obligation>)
            }
            isAdmin={isAdmin}
          />

          <EffortBandRow
            current={obligation.effort_band}
            reason={obligation.effort_band_reason}
            onChange={(band, reason) => onPatch({ effort_band: band, effort_band_reason: reason || null })}
          />

          <AlertScheduleCard obligation={obligation} />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4 space-y-3">
          <h3 className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <Tag className="h-3.5 w-3.5" />
            Tags
          </h3>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="neutral">{obligation.rule_category}</Badge>
            <Badge variant="neutral">{obligation.rule_frequency}</Badge>
            {obligation.period_label && (
              <Badge variant="neutral">{obligation.period_label}</Badge>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}


function AssigneeRow({
  obligation,
  users,
  onSave,
  isAdmin,
}: {
  obligation: Obligation;
  users: UserBrief[];
  onSave: (newId: number | null) => void;
  isAdmin: boolean;
}) {
  const [editing, setEditing] = useState(false);
  // Staged value while editing — only commits on Save. Cancel discards.
  const [draftId, setDraftId] = useState<number | "">(
    obligation.assignee?.id ?? "",
  );
  useEffect(() => {
    setDraftId(obligation.assignee?.id ?? "");
  }, [obligation.assignee?.id]);

  if (!isAdmin) {
    return (
      <FieldRow label="Assignee">
        <div className="flex items-center gap-2">
          <AssigneeChip user={obligation.assignee} size="sm" />
          <span className="text-xs text-muted-foreground italic">
            Admins manage assignment.
          </span>
        </div>
      </FieldRow>
    );
  }

  if (!editing) {
    return (
      <FieldRow label="Assignee">
        <div className="flex items-center gap-2">
          <AssigneeChip user={obligation.assignee} size="sm" />
          <span className="text-sm truncate flex-1">
            {obligation.assignee?.full_name || (
              <span className="italic text-muted-foreground">Unassigned</span>
            )}
          </span>
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="text-xs text-aspora-700 hover:underline"
          >
            Edit
          </button>
        </div>
      </FieldRow>
    );
  }

  const changed = (draftId || null) !== (obligation.assignee?.id ?? null);
  return (
    <FieldRow label="Assignee">
      <div className="space-y-2">
        <select
          autoFocus
          value={draftId}
          onChange={(e) =>
            setDraftId(e.target.value ? Number(e.target.value) : "")
          }
          className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
        >
          <option value="">Unassigned</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name || u.email}
              {u.department ? ` — ${u.department}` : ""}
            </option>
          ))}
        </select>
        <div className="flex justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setDraftId(obligation.assignee?.id ?? "");
              setEditing(false);
            }}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!changed}
            onClick={() => {
              onSave(draftId ? Number(draftId) : null);
              setEditing(false);
            }}
          >
            Save
          </Button>
        </div>
      </div>
    </FieldRow>
  );
}


function EffortBandRow({
  current,
  reason,
  onChange,
}: {
  current: EffortBand;
  reason: string | null;
  onChange: (band: EffortBand, reason: string | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draftReason, setDraftReason] = useState(reason ?? "");
  useEffect(() => setDraftReason(reason ?? ""), [reason]);

  if (!editing) {
    return (
      <FieldRow label="Effort band">
        <div className="flex items-center gap-2">
          <EffortBandBadge band={current} showLabel />
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="text-xs text-aspora-700 hover:underline"
          >
            Change
          </button>
        </div>
        {reason && <div className="text-xs text-muted-foreground mt-1.5 italic">Reason: {reason}</div>}
      </FieldRow>
    );
  }
  return (
    <FieldRow label="Effort band">
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {EFFORT_BANDS.map((b) => (
            <button
              key={b}
              type="button"
              onClick={() => onChange(b, draftReason.trim() || null)}
              className={cn(
                "h-7 px-2.5 rounded-md text-xs font-medium border",
                b === current
                  ? "bg-aspora-600 border-aspora-600 text-white"
                  : "bg-background border-border hover:bg-secondary",
              )}
            >
              {b}
            </button>
          ))}
        </div>
        <input
          type="text"
          value={draftReason}
          onChange={(e) => setDraftReason(e.target.value)}
          placeholder="Why are you changing it?"
          className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
        />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
            Done
          </Button>
        </div>
      </div>
    </FieldRow>
  );
}


function AlertScheduleCard({ obligation }: { obligation: Obligation }) {
  return (
    <FieldRow label="Alert schedule">
      <div className="rounded-lg border border-border bg-secondary/30 p-3 space-y-2">
        <div className="flex items-center gap-2 text-sm">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
          {obligation.is_overdue ? (
            <span className="text-red-700">Already past due — escalating</span>
          ) : obligation.is_in_alert_window ? (
            <span>Currently inside alert window</span>
          ) : (
            <span>
              Next alert{" "}
              <span className="font-medium">
                {obligation.next_alert_at ? fmtDate(obligation.next_alert_at) : "—"}
              </span>
            </span>
          )}
        </div>
        <div className="text-[11px] text-muted-foreground">
          Reminders fire on these channels when the assignee has them enabled:
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
          <span className="inline-flex items-center gap-1" title="Workspace channel — admin pastes a webhook URL in Settings → Integrations">
            <Slack className="h-3 w-3" />
            Slack
          </span>
          <span className="inline-flex items-center gap-1" title="In-app inbox always works. Email pings need SMTP creds on the server">
            <Mail className="h-3 w-3" />
            Email
          </span>
          <span
            className="inline-flex items-center gap-1 opacity-60"
            title="Google Calendar sync — not yet wired"
          >
            <CalendarIcon className="h-3 w-3" />
            Calendar (soon)
          </span>
        </div>
      </div>
    </FieldRow>
  );
}


// ---------------------------------------------------------------------------
// Filing fields — filing reference / payment / notes (debounced text inputs)
// ---------------------------------------------------------------------------
function FilingFields({
  obligation,
  onPatch,
}: {
  obligation: Obligation;
  onPatch: (p: Partial<Obligation>) => void;
}) {
  return (
    <Card>
      <CardContent className="p-5 space-y-4">
        <h3 className="text-xs uppercase tracking-wider text-muted-foreground">
          Filing record
        </h3>
        <DebouncedTextField
          label="Filing reference"
          placeholder="ACK # / receipt no. / portal reference"
          value={obligation.filing_reference}
          onCommit={(v) => onPatch({ filing_reference: v })}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
        </div>
        <DebouncedTextField
          label="Internal notes"
          placeholder="Anything the next reviewer should know…"
          value={obligation.notes}
          onCommit={(v) => onPatch({ notes: v })}
          multiline
        />
      </CardContent>
    </Card>
  );
}


function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-muted-foreground mb-1.5">{label}</label>
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
  const [local, setLocal] = useState(value ?? "");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => setLocal(value ?? ""), [value]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

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
    // Refetch every 20s while the drawer/page is open so a comment posted
    // in another browser tab shows up without manual refresh — matches the
    // obligation detail's own polling cadence.
    refetchInterval: 20_000,
    refetchOnWindowFocus: true,
  });

  const postMutation = useMutation({
    mutationFn: (body: string) =>
      api.post<ApiComment>(`/api/obligations/${obligationId}/comments`, { body }),
    onSuccess: () => {
      setDraft("");
      queryClient.invalidateQueries({ queryKey: ["obligation-comments", obligationId] });
      queryClient.invalidateQueries({ queryKey: ["activities", "obligation", obligationId] });
    },
  });

  function submit() {
    const cleaned = draft.trim();
    if (!cleaned || postMutation.isPending) return;
    postMutation.mutate(cleaned);
  }

  // Cmd/Ctrl + Enter submits — common in chat UIs. Plain Enter inserts a
  // newline (still useful for multi-line comments).
  function handleTextareaKeyDown(
    e: React.KeyboardEvent<HTMLTextAreaElement>,
  ) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      submit();
    }
  }

  return (
    <Card>
      <CardContent className="p-5 space-y-4">
        <h3 className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
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
                <div className="mt-2 text-sm whitespace-pre-wrap">
                  {renderCommentBody(c.body)}
                </div>
              </li>
            ))}
          </ul>
        )}

        {postMutation.error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            Couldn't post: {(postMutation.error as Error).message}
          </div>
        )}

        {/* Note: NO overflow-hidden here — the MentionTextarea's autocomplete
            dropdown renders absolutely positioned above the textarea and got
            clipped when the parent hid overflow. */}
        <div className="rounded-lg border border-border bg-background">
          <MentionTextarea
            rows={3}
            value={draft}
            onChange={setDraft}
            placeholder="Add a comment… type @ to mention a teammate"
            className="border-0"
            onKeyDown={handleTextareaKeyDown}
          />
          <div className="flex justify-between items-center px-2 py-2 border-t border-border bg-secondary/30">
            <span className="text-[11px] text-muted-foreground pl-2">
              <kbd className="px-1 bg-background border border-border rounded">@</kbd>{" "}
              to mention ·{" "}
              <kbd className="px-1 bg-background border border-border rounded">⌘ Enter</kbd>{" "}
              to post
            </span>
            <Button
              size="sm"
              // mousedown fires before the textarea loses focus, so the
              // click is registered even if the user clicked from inside
              // the textarea (where focus-loss could otherwise cancel it).
              onMouseDown={(e) => {
                e.preventDefault();
                submit();
              }}
              disabled={!draft.trim() || postMutation.isPending}
            >
              {postMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Send className="h-3.5 w-3.5" />
              )}
              Post
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Activity feed — chronological events for this obligation.
// ---------------------------------------------------------------------------
function ActivityFeed({ obligationId }: { obligationId: number }) {
  const { data: activities = [], isLoading } = useQuery({
    queryKey: ["activities", "obligation", obligationId],
    queryFn: () =>
      api.get<ActivityOut[]>(
        `/api/activities?obligation_id=${obligationId}&limit=50`,
      ),
  });

  return (
    <Card>
      <CardContent className="p-5 space-y-3">
        <h3 className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
          <ActivityIcon className="h-3.5 w-3.5" />
          Activity
          <Badge variant="neutral">{activities.length}</Badge>
        </h3>

        {isLoading ? (
          <div className="space-y-1.5">
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
          </div>
        ) : activities.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-secondary/30 px-4 py-6 text-center text-sm text-muted-foreground">
            No activity recorded yet for this obligation.
          </div>
        ) : (
          <ul className="space-y-2">
            {activities.map((a) => (
              <li
                key={a.id}
                className="flex items-start gap-2.5 text-sm rounded-lg px-2 py-1.5 hover:bg-secondary/30"
              >
                <Avatar className="h-6 w-6 shrink-0 mt-0.5">
                  <AvatarFallback className="text-[10px]">
                    {userInitials(a.actor?.full_name || "—")}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <div className="leading-snug">
                    <span className="font-medium">
                      {a.actor?.full_name?.split(" ")[0] || "System"}
                    </span>{" "}
                    <span className="text-muted-foreground">
                      {humaniseAction(a.action)}
                    </span>{" "}
                    {a.payload && Object.keys(a.payload).length > 0 && (
                      <PayloadPills payload={a.payload} />
                    )}
                  </div>
                </div>
                <span className="text-[11px] text-muted-foreground whitespace-nowrap mt-1">
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


function humaniseAction(action: string): string {
  switch (action) {
    case "obligation.updated":
      return "updated this obligation";
    case "comment.added":
      return "added a comment";
    case "document.uploaded":
      return "attached a document";
    case "document.updated":
      return "renamed a document";
    case "document.deleted":
      return "deleted a document";
    default:
      return action;
  }
}


function PayloadPills({ payload }: { payload: Record<string, unknown> }) {
  // Show changed_fields when present (from obligation.updated), else short summary.
  const fields = (payload.changed_fields ?? payload.fields) as string[] | undefined;
  if (Array.isArray(fields) && fields.length > 0) {
    return (
      <>
        {fields.slice(0, 4).map((f) => (
          <Badge key={f} variant="neutral" className="ml-0.5">
            {f}
          </Badge>
        ))}
      </>
    );
  }
  if (typeof payload.filename === "string") {
    return <Badge variant="neutral">{payload.filename}</Badge>;
  }
  return null;
}
