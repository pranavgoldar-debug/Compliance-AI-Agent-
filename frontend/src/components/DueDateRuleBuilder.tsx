// Structured Due-Date Builder — pick a frequency + basis and the calendar
// computes real dates from the resulting spec. The "Next due dates" preview is
// computed by the same math the backend uses (lib/dueDateSpec), so what you see
// here is exactly what lands on the calendar once the filing is approved.

import { cn } from "@/lib/utils";
import {
  type DueDateSpec,
  type DueFrequency,
  type DueBasis,
  nextDueDates,
  periodEndFor,
  summarizeSpec,
  fmtDue,
} from "@/lib/dueDateSpec";
import { useState } from "react";

const FREQUENCIES: { value: DueFrequency; label: string }[] = [
  { value: "annual", label: "Annual" },
  { value: "semiannual", label: "Semi-annual" },
  { value: "quarterly", label: "Quarterly" },
  { value: "monthly", label: "Monthly" },
  { value: "onetime", label: "One-time" },
];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = Array.from({ length: 31 }, (_, i) => i + 1);

function Seg<T extends string>({
  options,
  value,
  onChange,
  disabled,
}: {
  options: { value: T; label: string }[];
  value: T | undefined;
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-lg border px-3 py-1.5 text-sm transition-colors disabled:opacity-60",
            value === o.value
              ? "border-aspora-500 bg-aspora-50 text-aspora-700 font-medium"
              : "border-input bg-background hover:bg-secondary text-muted-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const FieldLabel = ({ children }: { children: React.ReactNode }) => (
  <div className="text-xs font-medium text-muted-foreground mb-1">{children}</div>
);
const selectCls =
  "rounded-md border border-input bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-aspora-200";

export function DueDateRuleBuilder({
  value,
  onChange,
  disabled,
}: {
  value: DueDateSpec | null | undefined;
  onChange: (spec: DueDateSpec) => void;
  disabled?: boolean;
}) {
  const spec: DueDateSpec = value ?? { frequency: "annual", basis: "fixed", day: 1, month: 1 };
  // Preview-only fiscal year-end (the real calendar uses each entity's FY end).
  const [fyDay, setFyDay] = useState(31);
  const [fyMonth, setFyMonth] = useState(3);

  const patch = (p: Partial<DueDateSpec>) => onChange({ ...spec, ...p });

  const setFrequency = (frequency: DueFrequency) => {
    if (frequency === "onetime") {
      onChange({ frequency, date: spec.date });
      return;
    }
    // Default a sensible basis + fields when switching frequency.
    const basis: DueBasis = spec.basis === "after_period" ? "after_period" : "fixed";
    onChange({
      frequency,
      basis,
      day: spec.day ?? 1,
      month: spec.month ?? 1,
      offset: spec.offset ?? 6,
      unit: spec.unit ?? "months",
      snap_last: spec.snap_last ?? false,
    });
  };

  const isAnnual = spec.frequency === "annual";
  const basisOptions: { value: DueBasis; label: string }[] = [
    { value: "fixed", label: isAnnual ? "Fixed date each year" : "Fixed day each period" },
    { value: "after_period", label: isAnnual ? "After financial year end" : "After period end" },
  ];

  const dates = nextDueDates(spec, new Date(), [fyMonth, fyDay], 3);
  const summary = summarizeSpec(spec);

  return (
    <div className="space-y-4">
      <div>
        <FieldLabel>Filing frequency</FieldLabel>
        <Seg options={FREQUENCIES} value={spec.frequency} onChange={setFrequency} disabled={disabled} />
      </div>

      {spec.frequency === "onetime" ? (
        <div>
          <FieldLabel>Due date</FieldLabel>
          <input
            type="date"
            disabled={disabled}
            value={spec.date ?? ""}
            onChange={(e) => patch({ date: e.target.value })}
            className={selectCls}
          />
        </div>
      ) : (
        <>
          <div>
            <FieldLabel>Due date basis</FieldLabel>
            <Seg
              options={basisOptions}
              value={spec.basis}
              onChange={(b) => patch({ basis: b })}
              disabled={disabled}
            />
          </div>

          {spec.basis === "fixed" ? (
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <FieldLabel>Day</FieldLabel>
                <select
                  className={selectCls}
                  disabled={disabled}
                  value={spec.day ?? 1}
                  onChange={(e) => patch({ day: Number(e.target.value) })}
                >
                  {DAYS.map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
              </div>
              {spec.frequency !== "monthly" && (
                <div>
                  <FieldLabel>Month</FieldLabel>
                  <select
                    className={selectCls}
                    disabled={disabled}
                    value={spec.month ?? 1}
                    onChange={(e) => patch({ month: Number(e.target.value) })}
                  >
                    {MONTHS.map((m, i) => (
                      <option key={m} value={i + 1}>{m}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex flex-wrap items-end gap-3">
                <div>
                  <FieldLabel>Offset</FieldLabel>
                  <input
                    type="number"
                    min={0}
                    disabled={disabled}
                    value={spec.offset ?? 0}
                    onChange={(e) => patch({ offset: Number(e.target.value) })}
                    className={cn(selectCls, "w-20")}
                  />
                </div>
                <div>
                  <FieldLabel>Unit</FieldLabel>
                  <select
                    className={selectCls}
                    disabled={disabled}
                    value={spec.unit ?? "months"}
                    onChange={(e) => patch({ unit: e.target.value as "months" | "days" })}
                  >
                    <option value="months">months</option>
                    <option value="days">days</option>
                  </select>
                </div>
                <div className="pb-1.5 text-sm text-muted-foreground">
                  After {isAnnual ? "financial year end" : "each period end"}
                </div>
              </div>
              {spec.unit !== "days" && (
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="accent-aspora-600"
                    disabled={disabled}
                    checked={!!spec.snap_last}
                    onChange={(e) => patch({ snap_last: e.target.checked })}
                  />
                  Snap to last day of the resulting month
                </label>
              )}
            </div>
          )}
        </>
      )}

      {/* Human summary banner */}
      <div className="rounded-lg bg-aspora-50/60 border border-aspora-100 px-3 py-2.5 text-sm font-medium text-aspora-700">
        {summary || "Set the rule above to see the schedule"}
      </div>

      {/* Computed preview */}
      <div className="rounded-lg border border-border bg-secondary/30 p-3">
        <div className="flex items-center justify-between gap-2 flex-wrap mb-2">
          <div className="text-sm font-medium">Next due dates (preview)</div>
          {spec.frequency !== "onetime" && spec.basis === "after_period" && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              FY ends
              <select className={cn(selectCls, "py-1")} value={fyDay} onChange={(e) => setFyDay(Number(e.target.value))}>
                {DAYS.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
              <select className={cn(selectCls, "py-1")} value={fyMonth} onChange={(e) => setFyMonth(Number(e.target.value))}>
                {MONTHS_SHORT.map((m, i) => (
                  <option key={m} value={i + 1}>{m}</option>
                ))}
              </select>
            </div>
          )}
        </div>
        {dates.length === 0 ? (
          <p className="text-sm text-muted-foreground">Set the rule above to see computed due dates.</p>
        ) : (
          <ul className="divide-y divide-border text-sm">
            {dates.map((d, i) => {
              const pe = periodEndFor(spec, d);
              const label =
                spec.frequency === "onetime"
                  ? "Due"
                  : pe
                    ? `Period ending ${fmtDue(pe)}`
                    : i === 0
                      ? "Next"
                      : "Then";
              return (
                <li key={d.toISOString()} className="flex items-center justify-between gap-3 py-2">
                  <span className="text-muted-foreground">{label}</span>
                  <span className={cn("font-medium", i === 0 && "text-emerald-700")}>{fmtDue(d)}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
