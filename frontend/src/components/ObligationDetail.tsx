// Shared obligation detail body — used by ObligationDrawer (side panel) and
// ObligationDetailPage (full page). Two layouts diverge only in the right
// sidebar: page shows it inline, drawer stacks it below the main content.

import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity as ActivityIcon,
  Building2,
  CheckCircle2,
  ExternalLink,
  Loader2,
  MessageCircle,
  Send,
  UserCheck,
  UserPlus,
  Calendar as CalendarIcon,
  AlertTriangle,
  Slack,
  Mail,
  Sparkles,
  Tag,
  FileText,
  Trash2,
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
import {
  fmtDate,
  fmtRelative,
  userInitials,
  EFFORT_BANDS,
  effortBandLabel,
  leadTimeDays,
  cleanFilingName,
} from "@/lib/format";
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


interface Props {
  obligationId: number;
  variant: "drawer" | "page";
  onClose?: () => void;
}


export function ObligationDetail({ obligationId, variant, onClose }: Props) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
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

  // Admin-only: permanently delete this filing. Used to clean up
  // obligations whose driving license/rule no longer applies.
  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/api/obligations/${obligationId}`),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ["obligation", obligationId] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["entity-obligations"] });
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      queryClient.invalidateQueries({ queryKey: ["sidebar-task-count"] });
      // Drawer just closes; full page navigates back to the work list.
      if (onClose) onClose();
      else navigate("/tasks");
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
        onDelete={() => deleteMutation.mutate()}
        deleting={deleteMutation.isPending}
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
            {cleanFilingName(obligation.rule_form_name)}
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
// ---------------------------------------------------------------------------
// WorkflowBanner — 4-step visual stepper:
//   1. Compliance prepares the filing
//   2. Admin verifies + hands off
//   3. Finance pays + logs UTR
//   4. Admin final sign-off
//
// State derivation:
//   - "completed"                     → all 4 done
//   - status=pending_review with
//     payment_reference filled        → 4 (admin final sign-off)
//   - status=in_progress / not_started
//     with finance assignee or
//     department=finance              → 3 (finance pays)
//   - status=pending_review (no
//     payment_reference)              → 2 (admin verifies)
//   - status=not_started / in_progress
//     (compliance side)               → 1 (compliance prepares)
//
// We always show all 4 steps so the user sees the whole arc — past steps
// are green, current is amber, upcoming is grey. Same UI for every
// obligation regardless of whether the rule has a payment_rule tagged.
// ---------------------------------------------------------------------------
function WorkflowBanner({ obligation }: { obligation: Obligation }) {
  // The obligation's `department` is the authoritative signal of which
  // leg currently owns the work. It's set to "finance" by the admin's
  // hand-off action and stays that way until admin closes the item.
  // payment_reference filled-or-not is NOT a reliable proxy — finance
  // sometimes submits an item for admin sign-off without a UTR (refund
  // case, internal transfer, etc).
  // "Finance leg" = the PAYMENT leg, which the admin hands off to explicitly
  // (department -> finance). It is NOT inferred from the assignee, so a
  // finance-function filing that finance PREPARES still starts at step 1.
  const isFinanceLeg = obligation.department === "finance";

  // Which team prepares/files this — Finance for VAT/tax filings, Legal for
  // corporate/registry, else Compliance. Same pipeline, just the right name.
  const fn = (obligation.rule_responsible_function || "").toLowerCase();
  const prepareTeam =
    fn === "finance" ? "Finance" : fn === "legal" ? "Legal" : "Compliance";

  // Which step is "active right now"?
  let activeStep: 1 | 2 | 3 | 4 | 5 = 1; // 5 = done
  if (obligation.status === "completed") {
    activeStep = 5;
  } else if (obligation.status === "pending_review") {
    // Pick which admin step we're at based on whose leg just submitted.
    // Finance just submitted → final sign-off (step 4). Compliance just
    // submitted → verify filing (step 2). Without this, the stepper
    // appeared to "go backwards to step 2" right after finance hit
    // Submit, which made the user think their work was lost.
    activeStep = isFinanceLeg ? 4 : 2;
  } else if (isFinanceLeg) {
    activeStep = 3;
  } else {
    activeStep = 1;
  }

  const steps: { n: number; title: string; team: string; action: string }[] = [
    {
      n: 1,
      title: "Prepare filing",
      team: prepareTeam,
      action: "Fill the filing reference + supporting docs, then Submit for review.",
    },
    {
      n: 2,
      title: "Verify filing",
      team: "Admin",
      action: "Review compliance's work. Approve & hand off to finance, or Send back.",
    },
    {
      n: 3,
      title: "Log payment",
      team: "Finance",
      action: "Enter payment amount + UTR / transaction id, then Submit for review.",
    },
    {
      n: 4,
      title: "Final sign-off",
      team: "Admin",
      action: "Verify the payment reference. Click Approve & close.",
    },
  ];

  const active = steps.find((s) => s.n === activeStep);

  return (
    <div className="border-b border-border bg-secondary/20">
      {/* Compact step rail */}
      <div className="flex items-stretch px-5 pt-3 pb-2 gap-1">
        {steps.map((s, i) => {
          const isDone = activeStep > s.n;
          const isActive = activeStep === s.n;
          return (
            <div key={s.n} className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "shrink-0 h-5 w-5 rounded-full grid place-items-center text-[10px] font-semibold",
                    isDone && "bg-emerald-600 text-white",
                    isActive && "bg-amber-500 text-white ring-2 ring-amber-200",
                    !isDone && !isActive && "bg-secondary text-muted-foreground border border-border",
                  )}
                >
                  {isDone ? "✓" : s.n}
                </span>
                <div className="min-w-0 flex-1">
                  <div
                    className={cn(
                      "text-xs truncate",
                      isActive ? "font-medium text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {s.title}
                  </div>
                </div>
              </div>
              {i < steps.length - 1 && (
                <div
                  className={cn(
                    "h-0.5 ml-2 mt-1",
                    isDone ? "bg-emerald-300" : "bg-border",
                  )}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Active step's action */}
      <div className="px-5 py-2 border-t border-border/60 bg-amber-50/40">
        {activeStep === 5 ? (
          <div className="text-sm flex items-center gap-2">
            <span className="inline-flex items-center justify-center h-5 w-5 rounded-full bg-emerald-600 text-white text-[11px]">
              ✓
            </span>
            <span className="font-medium text-emerald-800">Done</span>
            <span className="text-muted-foreground">
              · Filed{obligation.payment_reference?.trim() ? " and paid" : ""}. Sitting in the audit trail.
            </span>
          </div>
        ) : active ? (
          <div className="text-sm">
            <span className="font-medium text-amber-900">
              Now: {active.team} — {active.title}.
            </span>{" "}
            <span className="text-foreground/70">{active.action}</span>
          </div>
        ) : null}
      </div>
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
  onDelete,
  deleting,
}: {
  obligation: Obligation;
  users: UserBrief[];
  onPatch: (p: Partial<Obligation>) => void;
  saving: boolean;
  currentUser: { id: number; role: string } | null;
  onDelete: () => void;
  deleting: boolean;
}) {
  const isAdmin = currentUser?.role === "admin";
  const isAssignee = currentUser?.id === obligation.assignee?.id;
  const isFinanceLeg = obligation.department === "finance";

  // Stage-aware status options. Each role only sees the transitions that
  // apply to THEIR leg of the pipeline:
  //   - Employee (assignee): can toggle within their own leg's working
  //     states. Pushing it to "done" (pending_review) still requires the
  //     primary workflow button below so they don't accidentally submit.
  //   - Admin: sees the employee options PLUS the closing transitions
  //     (Mark N/A is the only one that bypasses the pipeline).
  const statusOptionsForEmployee: { value: ObligationStatus; label: string }[] = [
    { value: "not_started", label: isFinanceLeg ? "Haven't started payment" : "Haven't started filing" },
    { value: "in_progress", label: isFinanceLeg ? "Working on payment" : "Working on filing" },
  ];
  const statusOptionsForAdmin: { value: ObligationStatus; label: string }[] = [
    ...statusOptionsForEmployee,
    { value: "not_applicable", label: "Mark not applicable" },
  ];
  const statusOptions = isAdmin ? statusOptionsForAdmin : statusOptionsForEmployee;
  const canUseDropdown =
    (isAssignee || isAdmin) &&
    obligation.status !== "completed";

  return (
    <div className="border-b border-border bg-background sticky top-0 z-10">
      <div className="flex items-center gap-2 px-5 py-2.5 flex-wrap">
        {/* Update status dropdown — stage-aware. Employees only see
            transitions for their OWN leg (haven't started / working on
            it). The final "done" transition is the primary green button
            below ("Mark filing complete" / "Mark payment complete") so
            an employee can't accidentally submit by picking the wrong
            menu item. Admins additionally get "Mark not applicable" as
            an escape hatch. Nobody — not even admin — can pick
            "Completed" from the menu; that only happens via the
            workflow buttons (Approve & close). */}
        {canUseDropdown && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" disabled={saving}>
              Update status
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuLabel>
              {isFinanceLeg ? "Payment leg" : "Filing leg"} — pick where you are
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {statusOptions.map((o) => (
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
              {obligation.assignee ? (
                <UserCheck className="h-3.5 w-3.5" />
              ) : (
                <UserPlus className="h-3.5 w-3.5" />
              )}
              {obligation.assignee
                ? obligation.assignee.full_name.split(" ")[0]
                : "Assign"}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="max-h-[60vh] overflow-y-auto">
            {(() => {
              // This filing's function (Finance / Compliance / Legal) decides
              // which team should action it — show that team's people first so
              // a VAT filing routes to finance, not compliance.
              const fn = (obligation.rule_responsible_function || "").toLowerCase();
              const targetDept =
                fn === "finance" ? "finance" : fn === "legal" ? "legal" : "compliance";
              const inTeam = users.filter(
                (u) => (u.department ?? "") === targetDept,
              );
              const others = users.filter(
                (u) => (u.department ?? "") !== targetDept,
              );
              const row = (u: UserBrief) => (
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
                  {u.department && (
                    <span className="ml-auto pl-2 text-[10px] text-muted-foreground capitalize">
                      {u.department}
                    </span>
                  )}
                </DropdownMenuItem>
              );
              return (
                <>
                  <DropdownMenuLabel className="capitalize">
                    {targetDept} team — for this {fn || "compliance"} filing
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={() =>
                      onPatch({ assignee: null } as Partial<Obligation>)
                    }
                  >
                    Unassigned
                  </DropdownMenuItem>
                  {inTeam.length > 0 ? (
                    inTeam.map(row)
                  ) : (
                    <div className="px-2 py-1.5 text-[11px] text-muted-foreground italic">
                      No one tagged to the {targetDept} team yet.
                    </div>
                  )}
                  {others.length > 0 && (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuLabel className="text-[10px] text-muted-foreground">
                        Other teams (override)
                      </DropdownMenuLabel>
                      {others.map(row)}
                    </>
                  )}
                </>
              );
            })()}
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

          // Pending admin review — split into:
          //   A) "Final sign-off" (finance just submitted → admin closes → Done)
          //   B) "Filing review" (compliance just finished; admin verifies, then
          //       EITHER hands off to finance (if payment is needed) OR closes
          //       it directly (no payment leg). Both buttons are always shown
          //       so the admin picks per-obligation.
          //
          // We pick A vs B from obligation.department (the leg that just
          // submitted), NOT payment_reference. Finance might submit
          // without a UTR (refund, internal transfer) and still expect
          // final sign-off, not a return to filing-verify.
          if (status === "pending_review") {
            const isFinalReview = obligation.department === "finance";
            return isAdmin ? (
              <>
                {isFinalReview ? (
                  <Button
                    size="sm"
                    onClick={() => onPatch({ status: "completed" })}
                    disabled={saving}
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Approve & close
                  </Button>
                ) : (
                  <>
                    <HandoffToFinanceButton
                      obligationId={obligation.id}
                      users={users}
                      disabled={saving}
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onPatch({ status: "completed" })}
                      disabled={saving}
                      title="No payment needed — close it without sending to finance"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Approve without payment
                    </Button>
                  </>
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

          // Not started / in progress — assignee submits for review when
          // they're done with THEIR leg. Button label changes based on
          // whose leg this currently is: compliance side = "Mark filing
          // complete", finance side = "Mark payment complete". Clicking
          // either pushes status to pending_review and notifies admin;
          // admin then either approves & hands off (compliance → finance)
          // or approves & closes (finance → done). Nobody can jump
          // straight to "completed" — each team only closes their own
          // leg.
          const isFinanceLeg = obligation.department === "finance";
          const submitLabel = isFinanceLeg
            ? "Mark payment complete"
            : "Mark filing complete";
          const submitTitle = isFinanceLeg
            ? "Payment + UTR logged — send to admin for final sign-off"
            : "Filing prepared — send to admin for verification";
          return (
            <>
              {(isAssignee || isAdmin) && (
                <Button
                  size="sm"
                  onClick={() => onPatch({ status: "pending_review" })}
                  disabled={saving}
                  title={submitTitle}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {submitLabel}
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
          {/* Admin-only — removes this scheduled filing from the calendar.
              The underlying rule/filing stays on the license and can be
              re-scheduled anytime; only this scheduled instance + its
              comments go. Kept on the far right, behind a confirm. */}
          {isAdmin && (
            <Button
              variant="ghost"
              size="sm"
              disabled={deleting}
              onClick={() => {
                const form = obligation.rule_form_name || "this filing";
                if (
                  window.confirm(
                    `Remove "${form}" from the calendar?\n\nThis only un-schedules it — the filing stays on the license and you can schedule it again anytime. Uploaded documents are kept; comments on this instance are removed.`,
                  )
                ) {
                  onDelete();
                }
              }}
              className="text-destructive hover:text-destructive hover:bg-destructive/10"
              title="Remove from calendar (filing stays on the license, can be re-scheduled)"
            >
              {deleting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
              Remove from calendar
            </Button>
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
  const isAdmin = currentUser?.role === "admin";
  // Second opinion is now always available — it used to only show on
  // pending_review which meant compliance/finance people couldn't get
  // an AI sanity-check on the work they were drafting. Now anyone can
  // click "Run review" at any stage; the panel just defaults collapsed.
  if (variant === "drawer") {
    return (
      <div className="flex-1 overflow-y-auto p-5 space-y-6 scrollbar-thin">
        <MainContent obligation={obligation} />
        <SecondOpinionPanel obligationId={obligation.id} />
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
        <SecondOpinionPanel obligationId={obligation.id} />
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
// ---------------------------------------------------------------------------
// RegulationChangeBanner — shown when source_changed_at is set on the
// rule. Tells the user how recently the regulator updated the source
// page so they can check whether the template / requirements moved
// before starting work.
// ---------------------------------------------------------------------------
function RegulationChangeBanner({ changedAt }: { changedAt: string }) {
  const rel = fmtRelative(changedAt);
  // Parse as UTC (server is UTC; backend strips tz markers — see fmtRelative)
  const ts = changedAt.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(changedAt)
    ? changedAt
    : changedAt + "Z";
  const daysAgo = Math.max(
    0,
    Math.floor((Date.now() - new Date(ts).getTime()) / (1000 * 60 * 60 * 24)),
  );
  const isFresh = daysAgo <= 30;
  return (
    <div
      className={cn(
        "rounded-lg border px-3 py-2 text-xs flex items-start gap-2",
        isFresh
          ? "border-amber-300 bg-amber-50 text-amber-900"
          : "border-border bg-secondary/40 text-muted-foreground",
      )}
    >
      <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
      <div>
        <strong>Regulation updated {rel}</strong> ({daysAgo} day
        {daysAgo === 1 ? "" : "s"} ago).
        {isFresh
          ? " The regulator changed the source page recently — open it before filing and check the template hasn't moved. Admin: use 'Check for changes' on the rule to see a diff."
          : " No recent changes detected."}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// RegulatorPortalSection — two distinct URLs:
//   - source_url      = info / regulation text / form template page.
//                       Visible to everyone in the team.
//   - submission_url  = e-filing portal where the admin actually submits.
//                       Visible to admin only (gating is UX-only — the
//                       backend doesn't restrict the field, but employees
//                       shouldn't be encouraged to file directly).
// Both default to the same lookup result; admins can split via the
// Compliance Rules edit dialog. The dedicated /submissions page is the
// admin entry point for picking an entity + rule and jumping to its
// submission portal.
// ---------------------------------------------------------------------------
interface PageSummaryResponse {
  available: boolean;
  rule_id: number;
  url: string | null;
  form_name: string | null;
  template_url: string | null;
  key_requirements: string[];
  summary: string | null;
  error: string | null;
}

// Stored URLs sometimes lack a scheme (e.g. "www.difc.ae"); without it the
// browser treats href as a relative path and the link breaks. Force https.
function withScheme(u?: string | null): string | undefined {
  const t = u?.trim();
  if (!t) return undefined;
  return /^https?:\/\//i.test(t) ? t : `https://${t}`;
}

function RegulatorPortalSection({ obligation }: { obligation: Obligation }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const source = obligation.rule_source_url?.trim();
  const submission = obligation.rule_submission_url?.trim();
  const sourceHref = withScheme(source);
  const submissionHref = withScheme(submission);
  // Admins always get a "submit / pay" affordance: the dedicated submission
  // portal if one's set, otherwise fall back to the regulation/source page
  // (for many filings that page IS the e-filing portal).
  const submitHref = submissionHref || sourceHref;
  const [aiSummary, setAiSummary] = useState<PageSummaryResponse | null>(null);
  const aiSummaryMutation = useMutation({
    mutationFn: () =>
      api.post<PageSummaryResponse>(
        `/api/rules/${obligation.rule_id}/read-source`,
      ),
    onSuccess: (result) => setAiSummary(result),
    onError: (e) =>
      setAiSummary({
        available: false,
        rule_id: obligation.rule_id,
        url: source ?? null,
        form_name: null,
        template_url: null,
        key_requirements: [],
        summary: null,
        error: e instanceof Error ? e.message : String(e),
      }),
  });

  if (!source && !submission) {
    return (
      <section>
        <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
          Regulator portal
        </h3>
        <div className="text-sm text-muted-foreground italic">
          No regulator URL captured for this rule yet. Admin can add one
          on the Compliance Rules page (click the source cell on the
          rule's row) so the team can see the regulation + template
          straight from here.
        </div>
      </section>
    );
  }

  return (
    <section>
      <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
        Regulator portal
      </h3>
      <div className="flex flex-wrap gap-2">
        {sourceHref && (
          <a
            href={sourceHref}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-aspora-300 bg-aspora-50 hover:bg-aspora-100 px-3 py-2 text-sm font-medium text-aspora-800"
            title="Read the regulation + download the filing template"
          >
            <ExternalLink className="h-4 w-4" />
            View regulation & template
          </a>
        )}
        {isAdmin && submitHref && (
          <a
            href={submitHref}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 px-3 py-2 text-sm font-medium text-emerald-800"
            title="Admin: submit the filing and make the payment on the regulator's portal"
          >
            <ExternalLink className="h-4 w-4" />
            Submit &amp; pay on regulator's portal →
          </a>
        )}
      </div>
      <div className="text-[11px] text-muted-foreground mt-1.5">
        {isAdmin
          ? submissionHref
            ? "Everyone sees the regulation page. The green button is the e-filing portal where you submit + pay."
            : "Everyone sees the regulation page. The green button opens it as the submission/payment portal (no separate portal URL set — add one on Compliance Rules → edit row)."
          : "Read the regulation and grab the template. Admin handles the actual submission + payment."}
      </div>

      {source && (
        <div className="mt-3 pt-3 border-t border-border space-y-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="text-xs font-medium text-foreground">
              <Sparkles className="inline h-3 w-3 mr-1 text-aspora-600" />
              Ask Claude what this page says
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={aiSummaryMutation.isPending}
              onClick={() => aiSummaryMutation.mutate()}
              title="Fetches the regulator page and asks Claude to extract form name, template link, and key requirements"
            >
              {aiSummaryMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              {aiSummary ? "Re-read" : "Read with Claude"}
            </Button>
          </div>
          {aiSummary && !aiSummary.available && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              {aiSummary.error || "Couldn't extract anything useful."}
            </div>
          )}
          {aiSummary && aiSummary.available && (
            <div className="rounded-lg border border-border bg-secondary/30 px-3 py-2.5 text-xs space-y-2">
              {aiSummary.summary && (
                <p className="text-foreground leading-relaxed">
                  {aiSummary.summary}
                </p>
              )}
              {aiSummary.form_name && (
                <div>
                  <span className="text-muted-foreground">Form:</span>{" "}
                  <span className="font-medium">{aiSummary.form_name}</span>
                </div>
              )}
              {aiSummary.template_url && (
                <div>
                  <a
                    href={aiSummary.template_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-aspora-700 hover:underline inline-flex items-center gap-1 font-medium"
                  >
                    <ExternalLink className="h-3 w-3" />
                    Download the template
                  </a>
                </div>
              )}
              {aiSummary.key_requirements.length > 0 && (
                <div>
                  <div className="text-muted-foreground mb-1">
                    Key requirements:
                  </div>
                  <ul className="list-disc list-inside space-y-0.5">
                    {aiSummary.key_requirements.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}


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

        <RegulatorPortalSection obligation={obligation} />
        {obligation.rule_source_changed_at && (
          <RegulationChangeBanner changedAt={obligation.rule_source_changed_at} />
        )}

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

          <AlertScheduleCard obligation={obligation} />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4 space-y-2">
          <h3 className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <ExternalLink className="h-3.5 w-3.5" />
            ClickUp task
          </h3>
          {obligation.clickup_task_url ? (
            <a
              href={obligation.clickup_task_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-aspora-700 hover:underline"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Open finance task in ClickUp
            </a>
          ) : (
            <p className="text-xs text-muted-foreground">
              No ClickUp task yet — created automatically when this is handed off
              to finance (if ClickUp is connected in Settings).
            </p>
          )}
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
    <FieldRow label="Reminder lead time">
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {EFFORT_BANDS.map((b) => (
            <button
              key={b}
              type="button"
              title={effortBandLabel(b)}
              onClick={() => onChange(b, draftReason.trim() || null)}
              className={cn(
                "h-7 px-2.5 rounded-md text-xs font-medium border",
                b === current
                  ? "bg-aspora-600 border-aspora-600 text-white"
                  : "bg-background border-border hover:bg-secondary",
              )}
            >
              {leadTimeDays(b)}d
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
// Filing fields — split into Compliance-side and Finance-side cards.
// Compliance team sees the filing reference + supporting-doc reminder;
// Finance team sees payment amount/UTR/beneficiary bank details.
// Admin sees both (they manage the whole pipeline). Pick which to show
// based on the user's team membership + the obligation's current
// department (so a finance person who picks up a comp-stage item still
// sees the finance card).
// ---------------------------------------------------------------------------
function FilingFields({
  obligation,
  onPatch,
  currentUser,
}: {
  obligation: Obligation;
  onPatch: (p: Partial<Obligation>) => void;
  currentUser: { id: number; role: string; department?: string | null } | null;
}) {
  const isAdmin = currentUser?.role === "admin";
  const userTeam = (currentUser as { department?: string | null } | null)?.department;
  const obDept = obligation.department;

  // Determine visibility of each card.
  //   - Admin always sees both.
  //   - Otherwise, show Compliance card when user is on the compliance
  //     team OR the obligation is currently compliance-owned.
  //   - Show Finance card when user is finance OR ob is finance-owned OR
  //     the rule has a payment leg (so compliance people get a peek at
  //     payment status without editing).
  const showCompliance = isAdmin || userTeam === "compliance" || obDept === "compliance";
  const showFinance =
    isAdmin ||
    userTeam === "finance" ||
    obDept === "finance" ||
    Boolean(obligation.rule_payment_rule);

  // Edit gating: only the team that "owns" the leg can edit. Compliance
  // edits filing reference; finance edits payment + beneficiary. Admin
  // can edit both. Non-owners see read-only.
  const canEditCompliance = isAdmin || userTeam === "compliance" || obDept === "compliance";
  const canEditFinance = isAdmin || userTeam === "finance" || obDept === "finance";

  return (
    <div className="space-y-4">
      {showCompliance && (
        <Card>
          <CardContent className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs uppercase tracking-wider text-muted-foreground">
                Compliance — Filing record
              </h3>
              <Badge variant="neutral" className="text-[10px]">
                {canEditCompliance ? "Compliance team owns this" : "Read-only"}
              </Badge>
            </div>
            <DebouncedTextField
              label="Filing reference (ACK # / receipt no. / portal reference)"
              placeholder="e.g. ITR-V ACK 567823412, Form 16A ACK # ABCD1234"
              value={obligation.filing_reference}
              onCommit={(v) => onPatch({ filing_reference: v })}
              readOnly={!canEditCompliance}
            />
            <p className="text-[11px] text-muted-foreground">
              📎 Drop the filed PDF / acknowledgement into the{" "}
              <em>Filing documents</em> dropzone above. Required before
              submitting for review.
            </p>
          </CardContent>
        </Card>
      )}

      {showFinance && (
        <Card>
          <CardContent className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs uppercase tracking-wider text-muted-foreground">
                Finance — Payment record
              </h3>
              <Badge variant="neutral" className="text-[10px]">
                {canEditFinance ? "Finance team owns this" : "Read-only"}
              </Badge>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <DebouncedTextField
                label="Amount paid"
                placeholder="₹ 1,25,000 / $ 5,000 / £ 800"
                value={obligation.payment_amount}
                onCommit={(v) => onPatch({ payment_amount: v })}
                readOnly={!canEditFinance}
              />
              <DebouncedTextField
                label="UTR / transaction id"
                placeholder="HDFCN52026052812345678"
                value={obligation.payment_reference}
                onCommit={(v) => onPatch({ payment_reference: v })}
                readOnly={!canEditFinance}
              />
            </div>
            <DebouncedTextField
              label="Beneficiary bank details"
              placeholder={
                "Beneficiary: Income Tax Department\n" +
                "Bank: SBI · Branch: New Delhi\n" +
                "Account: 00000012345678 · IFSC: SBIN0000001"
              }
              value={obligation.beneficiary_details}
              onCommit={(v) => onPatch({ beneficiary_details: v })}
              multiline
              readOnly={!canEditFinance}
            />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-5 space-y-3">
          <h3 className="text-xs uppercase tracking-wider text-muted-foreground">
            Internal notes
          </h3>
          <DebouncedTextField
            label=""
            placeholder="Anything the next reviewer should know…"
            value={obligation.notes}
            onCommit={(v) => onPatch({ notes: v })}
            multiline
          />
        </CardContent>
      </Card>
    </div>
  );
}


function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      {label && (
        <label className="block text-xs font-medium text-muted-foreground mb-1.5">
          {label}
        </label>
      )}
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
  readOnly = false,
}: {
  label: string;
  placeholder?: string;
  value: string | null;
  onCommit: (next: string | null) => void;
  multiline?: boolean;
  readOnly?: boolean;
}) {
  const [local, setLocal] = useState(value ?? "");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => setLocal(value ?? ""), [value]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const scheduleCommit = (next: string) => {
    if (readOnly) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const cleaned = next.trim();
      if (cleaned === (value ?? "")) return;
      onCommit(cleaned || null);
    }, 700);
  };

  const flushCommit = () => {
    if (readOnly) return;
    if (timer.current) clearTimeout(timer.current);
    const cleaned = local.trim();
    if (cleaned === (value ?? "")) return;
    onCommit(cleaned || null);
  };

  const baseClass = cn(
    "w-full rounded-lg border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
    readOnly && "bg-secondary/40 cursor-not-allowed text-muted-foreground",
  );

  return (
    <FieldRow label={label}>
      {multiline ? (
        <textarea
          rows={3}
          value={local}
          placeholder={placeholder}
          readOnly={readOnly}
          onChange={(e) => {
            if (readOnly) return;
            setLocal(e.target.value);
            scheduleCommit(e.target.value);
          }}
          onBlur={flushCommit}
          className={cn(baseClass, "py-2")}
        />
      ) : (
        <input
          type="text"
          value={local}
          placeholder={placeholder}
          readOnly={readOnly}
          onChange={(e) => {
            if (readOnly) return;
            setLocal(e.target.value);
            scheduleCommit(e.target.value);
          }}
          onBlur={flushCommit}
          className={cn(baseClass, "h-9")}
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


// ---------------------------------------------------------------------------
// Compliance → finance hand-off button. Renders inside the Filing record card
// when is_awaiting_payment is true. Compliance person fills in the expected
// payment amount + optional notes; the backend posts an auto-comment and
// fanouts notifications to all finance-dept users + admins.
// ---------------------------------------------------------------------------
function RequestPaymentRow({ obligation }: { obligation: Obligation }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState(obligation.payment_amount ?? "");
  const [notes, setNotes] = useState("");

  const requestMutation = useMutation({
    mutationFn: () =>
      api.post(`/api/obligations/${obligation.id}/request-payment`, {
        amount: amount.trim(),
        notes: notes.trim() || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["obligation", obligation.id] });
      queryClient.invalidateQueries({
        queryKey: ["obligation-comments", obligation.id],
      });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      setOpen(false);
      setNotes("");
    },
  });

  if (!open) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 flex items-start gap-3">
        <div className="text-amber-700 mt-0.5">
          <UserCheck className="h-4 w-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-amber-900">
            Payment owed — hand off to finance
          </div>
          <div className="text-xs text-amber-800/80 mt-0.5">
            Filing's done. Click below to request payment from the finance
            team. They'll get a notification + an auto-comment is posted here.
          </div>
        </div>
        <Button
          size="sm"
          onClick={() => setOpen(true)}
          className="bg-amber-600 hover:bg-amber-700 text-white"
        >
          Request payment
        </Button>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 space-y-3">
      <div className="text-sm font-medium text-amber-900">
        Request payment from finance
      </div>
      <div>
        <label className="text-xs font-medium block mb-1">Amount</label>
        <input
          type="text"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="e.g. ₹ 1,25,000 or USD 4,800"
          className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          autoFocus
        />
      </div>
      <div>
        <label className="text-xs font-medium block mb-1">
          Notes for finance (optional)
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="Wire details, bank account, special instructions…"
          className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
        />
      </div>
      {requestMutation.error && (
        <div className="text-xs text-destructive">
          {(requestMutation.error as Error).message}
        </div>
      )}
      <div className="flex items-center justify-end gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setOpen(false);
            setNotes("");
          }}
          disabled={requestMutation.isPending}
        >
          Cancel
        </Button>
        <Button
          size="sm"
          onClick={() => requestMutation.mutate()}
          disabled={!amount.trim() || requestMutation.isPending}
        >
          {requestMutation.isPending && (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          )}
          Send to finance
        </Button>
      </div>
    </div>
  );
}
