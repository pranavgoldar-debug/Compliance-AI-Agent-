import { Badge } from "@/components/ui/badge";
import { daysRemainingLabel, statusLabel, statusVariant } from "@/lib/format";
import type { ObligationStatus } from "@/types/api";

interface Props {
  status: ObligationStatus;
  isOverdue?: boolean;
  daysRemaining?: number;
  showDays?: boolean;
}

export function StatusPill({ status, isOverdue = false, daysRemaining, showDays }: Props) {
  if (showDays && typeof daysRemaining === "number") {
    return (
      <Badge variant={isOverdue ? "overdue" : daysRemaining <= 14 ? "alert" : "neutral"}>
        {daysRemainingLabel(daysRemaining)}
      </Badge>
    );
  }
  return <Badge variant={statusVariant(status, isOverdue)}>{statusLabel(status)}</Badge>;
}
