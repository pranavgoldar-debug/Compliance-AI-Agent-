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
  if (showDays && typeof daysRemaining === "number") {
    return (
      <Badge variant={isOverdue ? "overdue" : daysRemaining <= 14 ? "alert" : "neutral"}>
        {daysRemainingLabel(daysRemaining)}
      </Badge>
    );
  }
  if (status === "completed" && isAwaitingPayment) {
    return <Badge variant="alert">Filed · awaiting payment</Badge>;
  }
  return <Badge variant={statusVariant(status, isOverdue)}>{statusLabel(status)}</Badge>;
}
