import { cn } from "@/lib/utils";

// Day-number + month-dropdown picker for an entity's fiscal year end. Emits a
// short canonical "DD-Mon" string (e.g. "31-Dec") — case/format-insensitive and
// safe for the column. The backend also normalises whatever it receives.
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function parseValue(v: string): { day: string; mon: string } {
  const m = (v || "").trim().match(/^(\d{1,2})\s*[-/ ]\s*(.+)$/);
  if (!m) return { day: "", mon: "" };
  const day = m[1];
  const rest = m[2].toLowerCase();
  let idx = MONTHS.findIndex((x) => rest.startsWith(x.toLowerCase()));
  if (idx < 0) {
    const num = parseInt(rest, 10);
    if (num >= 1 && num <= 12) idx = num - 1;
  }
  return { day, mon: idx >= 0 ? MONTHS[idx] : "" };
}

export function FiscalYearEndPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const { day, mon } = parseValue(value);
  const field =
    "flex h-10 rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1";
  const emit = (d: string, mo: string) => onChange(d && mo ? `${d}-${mo}` : "");
  return (
    <div className="flex gap-2">
      <input
        type="number"
        min={1}
        max={31}
        placeholder="DD"
        value={day}
        onChange={(e) => emit(e.target.value, mon)}
        className={cn(field, "w-20")}
      />
      <select
        value={mon}
        onChange={(e) => emit(day, e.target.value)}
        className={cn(field, "flex-1")}
      >
        <option value="">Month</option>
        {MONTHS.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </div>
  );
}
