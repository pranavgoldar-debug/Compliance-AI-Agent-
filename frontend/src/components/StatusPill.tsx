import { Badge } from "@/components/ui/badge";
import { daysRemainingLabel, statusLabel, statusVariant } from "@/lib/format";
import type { ObligationStatus } from "@/types/api";

interface Props {
  status: ObligationStatus;
  isOverdue?: boolean;
  daysRemaining?: number;
  showDays?: boolean;
  /** When true, the filing is done but the payment hasn't been logged yet.
      We show "Filed · awaiting payment" instead of plain "Completed" so the
      finance hand-off state is visible at a glance. */
  isAwaitingPayment?: boolean;
}

export function StatusPill({
  status,
  isOverdue = false,
  daysRemaining,
  showDays,
  isAwaitingPayment = false,
}: Props) {
  // Filed items shouldn't render "61 days overdue" just because the due
  // date is in the past — they're done. Show a static completed badge
  // (or "Awaiting payment" when the finance leg is still open).
  if (status === "completed") {
    if (isAwaitingPayment) {
      return <Badge variant="alert">Filed · awaiting payment</Badge>;
    }
    return <Badge variant="completed">Filed</Badge>;
  }
  if (status === "not_applicable") {
    return <Badge variant="neutral">N/A</Badge>;
  }
  if (showDays && typeof daysRemaining === "number") {
    return (
      <Badge variant={isOverdue ? "overdue" : daysRemaining <= 14 ? "alert" : "neutral"}>
        {daysRemainingLabel(daysRemaining)}
      </Badge>
    );
  }
  return <Badge variant={statusVariant(status, isOverdue)}>{statusLabel(status)}</Badge>;
}
