// Structured due-date spec + date math — a faithful mirror of the backend
// `compliance_agent.due_date_spec` so the builder's preview shows exactly the
// dates the calendar will compute. Keep the two in lock-step.

// "event" / "continuous" are unscheduled cadences — no computable due dates.
export type DueFrequency =
  | "annual" | "semiannual" | "quarterly" | "monthly" | "onetime"
  | "event" | "continuous";
export type DueBasis = "fixed" | "after_period";

export interface DueDateSpec {
  frequency: DueFrequency;
  basis?: DueBasis;
  day?: number;
  month?: number; // 1-12
  offset?: number;
  unit?: "months" | "days";
  snap_last?: boolean;
  date?: string; // YYYY-MM-DD (one-time)
}

const INTERVAL: Record<string, number> = { annual: 12, semiannual: 6, quarterly: 3, monthly: 1 };
export const FREQ_LABEL: Record<DueFrequency, string> = {
  annual: "Annual",
  semiannual: "Semi-annual",
  quarterly: "Quarterly",
  monthly: "Monthly",
  onetime: "One-time",
  event: "Event-based",
  continuous: "Continuous",
};
const MONTH_NAME = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// All dates are local, midnight — date-only comparisons.
function clampDay(y: number, m1: number, d: number): Date {
  const last = new Date(y, m1, 0).getDate(); // m1 is 1-based; day 0 → last day of month m1
  return new Date(y, m1 - 1, Math.min(Math.max(d || 1, 1), last));
}
function lastDay(y: number, m1: number): Date {
  return new Date(y, m1, 0);
}
function firstOf(y: number, m1: number): Date {
  return new Date(y, m1 - 1, 1);
}
function addMonths(d: Date, n: number): Date {
  const total = d.getFullYear() * 12 + d.getMonth() + n;
  const y = Math.floor(total / 12);
  const m0 = ((total % 12) + 12) % 12;
  return clampDay(y, m0 + 1, d.getDate());
}
function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}
function parseIso(s?: string): Date | null {
  if (!s) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

export function nextDueDates(
  spec: DueDateSpec | null | undefined,
  base: Date,
  fyEnd: [number, number] | null,
  count = 3,
): Date[] {
  if (!spec || !spec.frequency) return [];
  const b = new Date(base.getFullYear(), base.getMonth(), base.getDate());
  if (spec.frequency === "onetime") {
    const d = parseIso(spec.date);
    return d ? [d] : [];
  }
  if (spec.frequency === "event" || spec.frequency === "continuous") return [];
  const interval = INTERVAL[spec.frequency];
  if (!interval) return [];
  const steps = Math.floor(48 / interval) + count + 4;
  const out: Date[] = [];

  if (spec.basis === "fixed") {
    const day = spec.day || 1;
    const anchorMonth = spec.frequency === "monthly" ? 1 : spec.month || 1;
    const origin = firstOf(b.getFullYear() - 2, anchorMonth);
    for (let i = 0; i < steps; i++) {
      const t = addMonths(origin, i * interval);
      const occ = clampDay(t.getFullYear(), t.getMonth() + 1, day);
      if (occ >= b) {
        out.push(occ);
        if (out.length >= count) break;
      }
    }
    return out;
  }

  if (spec.basis === "after_period") {
    const offset = spec.offset || 0;
    const unit = spec.unit || "months";
    const snap = !!spec.snap_last;
    const fyMonth = fyEnd ? fyEnd[0] : 12;
    const originPe = lastDay(b.getFullYear() - 2, fyMonth);
    for (let i = 0; i < steps; i++) {
      const t = addMonths(firstOf(originPe.getFullYear(), originPe.getMonth() + 1), i * interval);
      const pe = lastDay(t.getFullYear(), t.getMonth() + 1);
      let due: Date;
      if (unit === "days") {
        due = addDays(pe, offset);
      } else {
        due = addMonths(pe, offset);
        if (snap) due = lastDay(due.getFullYear(), due.getMonth() + 1);
      }
      if (due >= b) {
        out.push(due);
        if (out.length >= count) break;
      }
    }
    return out;
  }
  return [];
}

export function periodEndFor(
  spec: DueDateSpec | null | undefined,
  due: Date,
): Date | null {
  if (!spec || spec.basis !== "after_period") return null;
  const offset = spec.offset || 0;
  const unit = spec.unit || "months";
  if (unit === "days") return addDays(due, -offset);
  const t = addMonths(firstOf(due.getFullYear(), due.getMonth() + 1), -offset);
  return lastDay(t.getFullYear(), t.getMonth() + 1);
}

export function summarizeSpec(spec: DueDateSpec | null | undefined): string {
  if (!spec || !spec.frequency) return "";
  if (spec.frequency === "onetime") {
    const d = parseIso(spec.date);
    return d ? `Due once on ${fmtDue(d)}` : "Pick a date";
  }
  if (spec.frequency === "event") return "Event-based — due when the triggering event occurs";
  if (spec.frequency === "continuous") return "Continuous — maintained at all times; no fixed due date";
  if (!spec.basis) return "";
  const cadence: Record<string, string> = {
    annual: "every year",
    semiannual: "every 6 months",
    quarterly: "every quarter",
    monthly: "every month",
  };
  if (spec.basis === "fixed") {
    const day = spec.day || 1;
    if (spec.frequency === "monthly") return `Due on the ${ordinal(day)} of every month`;
    const month = MONTH_NAME[((spec.month || 1) - 1) % 12];
    if (spec.frequency === "annual") return `Due every year on ${day} ${month}`;
    return `Due ${cadence[spec.frequency]}, anchored on ${day} ${month}`;
  }
  const offset = spec.offset || 0;
  const unit = spec.unit || "months";
  const anchor = spec.frequency === "annual" ? "financial year end" : "each period end";
  const tail = unit === "months" && spec.snap_last ? ", on the last day of that month" : "";
  return `Due ${offset} ${unit} after ${anchor}${tail}`;
}

export function fmtDue(d: Date): string {
  const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getMonth()];
  return `${d.getDate()} ${mon} ${d.getFullYear()}`;
}
function ordinal(n: number): string {
  const s = n % 100 >= 11 && n % 100 <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
  return `${n}${s}`;
}
