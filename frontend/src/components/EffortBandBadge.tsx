import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { effortBandLabel, leadTimeDays } from "@/lib/format";
import type { EffortBand } from "@/types/api";

interface Props {
  band: EffortBand;
  className?: string;
  showLabel?: boolean;
}

const TONE: Record<EffortBand, string> = {
  "1w": "bg-slate-100 text-slate-700 border-slate-200",
  "2w": "bg-blue-50 text-blue-700 border-blue-200",
  "4w": "bg-indigo-50 text-indigo-700 border-indigo-200",
  "8w": "bg-purple-50 text-purple-700 border-purple-200",
  "12w": "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
};

export function EffortBandBadge({ band, className, showLabel }: Props) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-mono text-[10px] tracking-wide border",
        TONE[band],
        className,
      )}
      title={`First reminder fires ${leadTimeDays(band)} days before the due date`}
    >
      {showLabel ? effortBandLabel(band) : band}
    </Badge>
  );
}
