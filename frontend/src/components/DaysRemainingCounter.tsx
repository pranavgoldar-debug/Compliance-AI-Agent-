import { cn } from "@/lib/utils";
import { leadTimeDays } from "@/lib/format";
import type { EffortBand } from "@/types/api";

interface Props {
  daysRemaining: number;
  effortBand: EffortBand;
  size?: "sm" | "md" | "lg";
  className?: string;
}

/**
 * Big colour-coded counter shown in the obligation header.
 * - overdue: red
 * - inside lead-time alert window: amber
 * - else: gray
 */
export function DaysRemainingCounter({
  daysRemaining,
  effortBand,
  size = "md",
  className,
}: Props) {
  const overdue = daysRemaining < 0;
  const inAlert = !overdue && daysRemaining <= leadTimeDays(effortBand);
  const abs = Math.abs(daysRemaining);

  const tone = overdue
    ? "bg-red-50 border-red-200 text-red-700"
    : inAlert
      ? "bg-amber-50 border-amber-200 text-amber-700"
      : "bg-slate-50 border-slate-200 text-slate-700";

  const sizes = {
    sm: { box: "px-2 py-1 min-w-[60px]", num: "text-base", lbl: "text-[10px]" },
    md: { box: "px-3 py-2 min-w-[80px]", num: "text-2xl", lbl: "text-[10px]" },
    lg: { box: "px-4 py-3 min-w-[110px]", num: "text-4xl", lbl: "text-[11px]" },
  }[size];

  return (
    <div
      className={cn(
        "rounded-lg border flex flex-col items-center justify-center leading-none text-center",
        sizes.box,
        tone,
        className,
      )}
      title={
        overdue
          ? `${abs} days overdue`
          : daysRemaining === 0
            ? "Due today"
            : inAlert
              ? `${abs} days — inside alert window for ${effortBand}`
              : `${abs} days remaining`
      }
    >
      <div className={cn("font-bold tabular-nums", sizes.num)}>{abs}</div>
      <div className={cn("uppercase tracking-wide mt-0.5", sizes.lbl)}>
        {overdue
          ? "Days overdue"
          : daysRemaining === 0
            ? "Due today"
            : daysRemaining === 1
              ? "Day remaining"
              : "Days remaining"}
      </div>
    </div>
  );
}
