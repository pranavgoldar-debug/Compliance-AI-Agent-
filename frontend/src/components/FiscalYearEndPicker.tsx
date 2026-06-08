import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

// Day-number + month-dropdown picker for an entity's fiscal year end. Holds day
// and month in LOCAL state so partial entry (e.g. typing the day before picking
// a month) isn't wiped, and emits a short canonical "DD-Mon" string (e.g.
// "31-Dec") to the parent once both are set. The backend also normalises input.
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
  const [day, setDay] = useState(() => parseValue(value).day);
  const [mon, setMon] = useState(() => parseValue(value).mon);

  // Re-sync only when the external value genuinely differs from what we hold
  // (e.g. a different entity is loaded) — never while the user is mid-entry.
  useEffect(() => {
    const combined = day && mon ? `${day}-${mon}` : "";
    if ((value || "") !== combined) {
      const p = parseValue(value);
      setDay(p.day);
      setMon(p.mon);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const update = (d: string, mo: string) => {
    setDay(d);
    setMon(mo);
    onChange(d && mo ? `${d}-${mo}` : "");
  };

  const field =
    "flex h-10 rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1";
  return (
    <div className="flex gap-2">
      <input
        type="number"
        min={1}
        max={31}
        placeholder="DD"
        value={day}
        onChange={(e) => update(e.target.value, mon)}
        className={cn(field, "w-20")}
      />
      <select
        value={mon}
        onChange={(e) => update(day, e.target.value)}
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
