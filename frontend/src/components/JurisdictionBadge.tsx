import { jurisdiction } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  code: string;
  showName?: boolean;
  className?: string;
}

export function JurisdictionBadge({ code, showName = true, className }: Props) {
  const j = jurisdiction(code);
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm", className)}>
      <span aria-hidden className="text-base leading-none">
        {j.flag}
      </span>
      {showName && <span>{j.name}</span>}
    </span>
  );
}
