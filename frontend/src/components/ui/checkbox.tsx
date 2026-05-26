import * as React from "react";
import { Check, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

interface CheckboxProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  indeterminate?: boolean;
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, indeterminate, checked, ...props }, ref) => {
    const innerRef = React.useRef<HTMLInputElement | null>(null);
    React.useImperativeHandle(ref, () => innerRef.current!);
    React.useEffect(() => {
      if (innerRef.current) {
        innerRef.current.indeterminate = !!indeterminate && !checked;
      }
    }, [indeterminate, checked]);

    return (
      <span
        className={cn(
          "relative inline-flex h-4 w-4 items-center justify-center rounded border border-input bg-background",
          (checked || indeterminate) && "bg-aspora-600 border-aspora-600 text-white",
          className,
        )}
      >
        <input
          ref={innerRef}
          type="checkbox"
          checked={checked}
          {...props}
          className="absolute inset-0 m-0 cursor-pointer opacity-0"
        />
        {indeterminate && !checked ? (
          <Minus className="h-3 w-3 pointer-events-none" />
        ) : checked ? (
          <Check className="h-3 w-3 pointer-events-none" strokeWidth={3} />
        ) : null}
      </span>
    );
  },
);
Checkbox.displayName = "Checkbox";
