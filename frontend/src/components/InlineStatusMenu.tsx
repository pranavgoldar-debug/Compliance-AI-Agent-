// Inline status dropdown for any obligation row. Clicking opens a menu of
// statuses; selecting one PATCHes the obligation and invalidates the right
// query keys so the row re-renders in place. Drop into any table.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Loader2 } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { StatusPill } from "@/components/StatusPill";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Obligation, ObligationStatus } from "@/types/api";


const STATUSES: { value: ObligationStatus; label: string }[] = [
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "pending_review", label: "Pending review" },
  { value: "completed", label: "Completed" },
  { value: "not_applicable", label: "Not applicable" },
];


interface Props {
  obligationId: number;
  status: ObligationStatus;
  isOverdue: boolean;
  /** Render as a small icon-only trigger next to a pill, vs replacing the pill. */
  compact?: boolean;
}


export function InlineStatusMenu({
  obligationId,
  status,
  isOverdue,
  compact,
}: Props) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (newStatus: ObligationStatus) =>
      api.patch<Obligation>(`/api/obligations/${obligationId}`, { status: newStatus }),
    onSuccess: () => {
      // Same invalidation set as the drawer uses, so every row that shows
      // this obligation refreshes in place.
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["entity-obligations"] });
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      queryClient.invalidateQueries({ queryKey: ["sidebar-task-count"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      queryClient.invalidateQueries({ queryKey: ["obligation", obligationId] });
    },
  });

  function stop(e: React.MouseEvent) {
    e.stopPropagation();
    e.preventDefault();
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild onClick={stop}>
        {compact ? (
          <button
            type="button"
            className="h-7 w-7 grid place-items-center rounded-md hover:bg-secondary text-muted-foreground"
            aria-label="Change status"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
          </button>
        ) : (
          <button
            type="button"
            className="inline-flex items-center gap-1 group"
            disabled={mutation.isPending}
          >
            <StatusPill status={status} isOverdue={isOverdue} />
            {mutation.isPending ? (
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            ) : (
              <ChevronDown className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
            )}
          </button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" onClick={stop}>
        <DropdownMenuLabel>Change status to…</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {STATUSES.map((s) => {
          const current = s.value === status;
          return (
            <DropdownMenuItem
              key={s.value}
              onClick={(e) => {
                stop(e);
                if (!current) mutation.mutate(s.value);
              }}
              className={cn(current && "bg-aspora-50 text-aspora-800")}
            >
              {current && <Check className="h-3.5 w-3.5 mr-2" />}
              {!current && <span className="w-3.5 mr-2" />}
              {s.label}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
