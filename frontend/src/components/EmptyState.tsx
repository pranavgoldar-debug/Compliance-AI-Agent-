import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface Props {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/**
 * Standardised empty state — friendly heading, one-line explanation, optional
 * primary CTA. Use everywhere "nothing here yet" instead of bespoke divs.
 */
export function EmptyState({ icon, title, description, action, className }: Props) {
  return (
    <div
      className={cn(
        "rounded-xl border border-dashed border-border bg-card/50 px-6 py-10",
        "flex flex-col items-center text-center gap-3",
        className,
      )}
    >
      {icon && (
        <div className="h-12 w-12 rounded-full bg-secondary/60 grid place-items-center text-muted-foreground">
          {icon}
        </div>
      )}
      <div className="space-y-1">
        <div className="text-sm font-semibold">{title}</div>
        {description && (
          <div className="text-sm text-muted-foreground max-w-md">{description}</div>
        )}
      </div>
      {action && <div className="pt-1">{action}</div>}
    </div>
  );
}
