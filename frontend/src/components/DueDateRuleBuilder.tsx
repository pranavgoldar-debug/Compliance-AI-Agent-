// Structured Due-Date Builder — pick a frequency + basis and the calendar
// computes real dates from the resulting spec (same math as the backend,
// lib/dueDateSpec), shown as a one-line human summary.

import { cn } from "@/lib/utils";
import { DateField } from "@/components/DateField";
import {
  type DueDateSpec,
  type DueFrequency,
  type DueBasis,
  summarizeSpec,
} from "@/lib/dueDateSpec";

const FREQUENCIES: { value: DueFrequency; label: string }[] = [
  { value: "annual", label: "Annual" },
  { value: "semiannual", label: "Semi-annual" },
  { value: "quarterly", label: "Quarterly" },
  { value: "monthly", label: "Monthly" },
  { value: "onetime", label: "One-time" },
  { value: "event", label: "Event-based" },
  { value: "continuous", label: "Continuous" },
];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
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

  const patch = (p: Partial<DueDateSpec>) => onChange({ ...spec, ...p });

  const setFrequency = (frequency: DueFrequency) => {
    if (frequency === "onetime") {
      onChange({ frequency, date: spec.date });
      return;
    }
    // No schedule to configure — the summary banner explains the cadence.
    if (frequency === "event" || frequency === "continuous") {
      onChange({ frequency });
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

  const summary = summarizeSpec(spec);

  return (
    <div className="space-y-4">
      <div>
        <FieldLabel>Filing frequency</FieldLabel>
        <Seg options={FREQUENCIES} value={spec.frequency} onChange={setFrequency} disabled={disabled} />
      </div>

      {spec.frequency === "event" || spec.frequency === "continuous" ? null : spec.frequency === "onetime" ? (
        <div>
          <FieldLabel>Due date</FieldLabel>
          <DateField
            disabled={disabled}
            value={spec.date ?? ""}
            onChange={(v) => patch({ date: v })}
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
                  After {isAnnual ? (spec.anchor === "ard" ? "the Annual Return Date (ARD)" : "financial year end") : "each period end"}
                </div>
              </div>
              {isAnnual && (
                <div>
                  <FieldLabel>Anchor on</FieldLabel>
                  <select
                    className={selectCls}
                    disabled={disabled}
                    value={spec.anchor ?? "fye"}
                    onChange={(e) => patch({ anchor: e.target.value as "fye" | "ard" })}
                  >
                    <option value="fye">Fiscal year end</option>
                    <option value="ard">Annual Return Date (ARD)</option>
                  </select>
                  <p className="text-[11px] text-muted-foreground mt-1">
                    ARD uses each entity's Annual Return Date (falls back to its
                    fiscal year end when they're the same).
                  </p>
                </div>
              )}
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
    </div>
  );
}
