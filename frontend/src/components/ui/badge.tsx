import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-aspora-100 text-aspora-700",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "text-foreground",
        overdue: "border-transparent bg-red-100 text-red-700",
        alert: "border-transparent bg-amber-100 text-amber-800",
        progress: "border-transparent bg-blue-100 text-blue-700",
        completed: "border-transparent bg-emerald-100 text-emerald-700",
        review: "border-transparent bg-purple-100 text-purple-700",
        neutral: "border-transparent bg-slate-100 text-slate-700",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
