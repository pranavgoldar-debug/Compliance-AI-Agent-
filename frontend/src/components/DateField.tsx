// DateField — a device-agnostic date input. The native <input type="date">
// is unreliable across browsers (Safari desktop in particular makes it hard
// to type the year and swallows clicks), so this uses three plain controls:
// a numeric Day, a Month dropdown, and a typeable 4-digit Year. Works
// identically on every desktop and mobile browser. Value is an ISO
// "YYYY-MM-DD" string (or "" when incomplete) so callers are unchanged.
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const fieldCls =
  "h-10 rounded-lg border border-input bg-background px-2 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50";

function splitIso(iso: string): { d: string; m: string; y: string } {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!match) return { d: "", m: "", y: "" };
  return { y: match[1], m: String(Number(match[2])), d: String(Number(match[3])) };
}

const pad = (n: number) => String(n).padStart(2, "0");

export function DateField({
  value,
  onChange,
  disabled,
  className,
}: {
  value: string;
  onChange: (iso: string) => void;
  disabled?: boolean;
  className?: string;
}) {
  const initial = splitIso(value);
  const [d, setD] = useState(initial.d);
  const [m, setM] = useState(initial.m);
  const [y, setY] = useState(initial.y);
  // Track what we last emitted so an external value change (e.g. AI autofill,
  // form reset) re-seeds the three boxes without clobbering live typing.
  const lastEmitted = useRef(value);

  useEffect(() => {
    if (value !== lastEmitted.current) {
      const s = splitIso(value);
      setD(s.d);
      setM(s.m);
      setY(s.y);
      lastEmitted.current = value;
    }
  }, [value]);

  const emit = (nd: string, nm: string, ny: string) => {
    const di = parseInt(nd, 10);
    const mi = parseInt(nm, 10);
    const yi = parseInt(ny, 10);
    let iso = "";
    if (
      di >= 1 && di <= 31 &&
      mi >= 1 && mi <= 12 &&
      ny.length === 4 && yi >= 1900 && yi <= 2200
    ) {
      const lastDay = new Date(yi, mi, 0).getDate(); // clamp e.g. 31 Feb → 28/29
      iso = `${yi}-${pad(mi)}-${pad(Math.min(di, lastDay))}`;
    }
    lastEmitted.current = iso;
    onChange(iso);
  };

  const onDay = (v: string) => {
    const clean = v.replace(/\D/g, "").slice(0, 2);
    setD(clean);
    emit(clean, m, y);
  };
  const onYear = (v: string) => {
    const clean = v.replace(/\D/g, "").slice(0, 4);
    setY(clean);
    emit(d, m, clean);
  };
  const onMonth = (v: string) => {
    setM(v);
    emit(d, v, y);
  };

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <input
        type="text"
        inputMode="numeric"
        aria-label="Day"
        placeholder="DD"
        disabled={disabled}
        value={d}
        onChange={(e) => onDay(e.target.value)}
        className={cn(fieldCls, "w-14 text-center")}
      />
      <select
        aria-label="Month"
        disabled={disabled}
        value={m}
        onChange={(e) => onMonth(e.target.value)}
        className={cn(fieldCls, "flex-1 min-w-[6rem] pr-7")}
      >
        <option value="">Month</option>
        {MONTHS.map((name, i) => (
          <option key={name} value={i + 1}>{name}</option>
        ))}
      </select>
      <input
        type="text"
        inputMode="numeric"
        aria-label="Year"
        placeholder="YYYY"
        disabled={disabled}
        value={y}
        onChange={(e) => onYear(e.target.value)}
        className={cn(fieldCls, "w-20 text-center")}
      />
    </div>
  );
}
