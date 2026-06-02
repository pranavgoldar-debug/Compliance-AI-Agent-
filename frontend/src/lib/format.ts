// Display helpers shared across pages.

import { format, formatDistanceToNow, parseISO } from "date-fns";
import type { EffortBand, ObligationStatus } from "@/types/api";

// Country code → display name + ISO 3166-1 alpha-2 for the flag CDN.
// `flag` (emoji) is kept for backwards compatibility with anything still
// rendering text-flags, but the JurisdictionBadge component now uses
// `iso2` to pull a PNG flag from flagcdn.com — Windows / Linux can't
// render the emoji flags reliably, the PNG approach works everywhere.
export const JURISDICTIONS: Record<
  string,
  { name: string; flag: string; iso2: string }
> = {
  india: { name: "India", flag: "🇮🇳", iso2: "in" },
  uk: { name: "United Kingdom", flag: "🇬🇧", iso2: "gb" },
  us: { name: "United States", flag: "🇺🇸", iso2: "us" },
  eu: { name: "European Union", flag: "🇪🇺", iso2: "eu" },
  uae: { name: "United Arab Emirates", flag: "🇦🇪", iso2: "ae" },
  singapore: { name: "Singapore", flag: "🇸🇬", iso2: "sg" },
  canada: { name: "Canada", flag: "🇨🇦", iso2: "ca" },
  lithuania: { name: "Lithuania", flag: "🇱🇹", iso2: "lt" },
  australia: { name: "Australia", flag: "🇦🇺", iso2: "au" },
};

// Strip jurisdiction codes/suffixes that AI extraction sometimes appends to
// filing names ("VAT_CA", "VAT (CA)", "VAT — DIFC") so the UI shows the plain
// name ("VAT"). Conservative: only removes a trailing country/zone token.
const _JUR_SUFFIX =
  /[\s_\-—]*(?:[\(\[]\s*)?(?:CA|UK|US|USA|UAE|SG|SGP|LT|LTU|EU|IN|IND|DIFC|ADGM|GIFT|IFSC)(?:\s*[\)\]])?\s*$/i;

export function cleanFilingName(name: string | null | undefined): string {
  let s = (name ?? "").trim();
  // Keep only the real obligation name — drop secondary clauses appended with
  // " + " or an em/en-dash, e.g.
  //   "Annual MLRO report + business-wide risk assessment refresh" -> "Annual MLRO report"
  //   "HMRC AML supervised business — annual fees + register update"  -> "HMRC AML supervised business"
  s = s.split(/\s+[—–-]\s+/)[0].trim();
  s = s.split(/\s+\+\s+/)[0].trim();
  // Drop trailing parenthetical explanations: "AGM (not a filing, …)" -> "AGM",
  // "Corporation Tax return (CT600)" -> "Corporation Tax return".
  for (let i = 0; i < 3; i++) {
    const next = s.replace(/\s*[\(\[][^()\[\]]*[\)\]]\s*$/, "").trim();
    if (next === s || next.length < 2) break;
    s = next;
  }
  // Strip up to two trailing jurisdiction tokens (e.g. "VAT_CA", "X — DIFC").
  for (let i = 0; i < 2; i++) {
    const next = s.replace(_JUR_SUFFIX, "").trim();
    if (next === s || next.length < 2) break;
    s = next;
  }
  return s || (name ?? "");
}

// Mirror of the backend classification.derive_function — maps a rule's
// category/area to the responsible team (Finance / Compliance / Legal). Used
// client-side (e.g. AI-extract candidates that don't carry a function yet).
export function deriveFunction(category = "", area = ""): string {
  const t = `${category} ${area}`.toLowerCase();
  const has = (kws: string[]) => kws.some((k) => t.includes(k));
  if (
    has([
      "aml", "cft", "ctf", "financial regulation", "consumer protection",
      "data protection", "risk", "fraud", "regulatory reporting", "regdata",
      "economic substance", "statistics", "complaints", "sanction",
      "fitness", "conduct", "prudential", "reporting",
    ])
  )
    return "Compliance";
  if (
    has([
      "tax", "vat", "gst", "hst", "pst", "qst", "excise", "payroll",
      "pension", "social security", "accounting", "information return",
      "unclaimed property", "duty", "customs", "withholding", "remittance",
      "intrastat",
    ])
  )
    return "Finance";
  if (
    has([
      "corporate law", "corporate record", "corporate & statutory",
      "statutory filing", "statutory account", "company registration",
      "registry", "registrar", "beneficial owner", "ubo", "psc",
      "licens", "incorporation", "governance", "confirmation statement",
      "annual return", "change notification", "premises",
    ])
  )
    return "Legal";
  return "Compliance";
}

export function jurisdiction(code: string): {
  name: string;
  flag: string;
  iso2: string;
} {
  return (
    JURISDICTIONS[code] ?? {
      name: code.toUpperCase(),
      flag: "🏳️",
      iso2: "",
    }
  );
}

export function fmtDate(iso: string | null | undefined, pattern = "d MMM yyyy"): string {
  if (!iso) return "—";
  try {
    return format(parseISO(iso), pattern);
  } catch {
    return iso;
  }
}

export function fmtShortDate(iso: string | null | undefined): string {
  return fmtDate(iso, "d MMM");
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    // Backend serialises datetimes from SQLAlchemy with no timezone
    // marker (e.g. "2026-05-28T12:34:56"). parseISO treats those as
    // LOCAL time, which makes a 2-min-old event look 5h old in IST.
    // Force the parser to read them as UTC by appending Z when no
    // explicit offset is present.
    const looksAware = /Z$|[+-]\d{2}:?\d{2}$/.test(iso);
    const normalised = looksAware ? iso : iso + "Z";
    return formatDistanceToNow(parseISO(normalised), { addSuffix: true });
  } catch {
    return iso;
  }
}

export function statusLabel(status: ObligationStatus): string {
  switch (status) {
    case "not_started":
      return "Not started";
    case "in_progress":
      return "In progress";
    case "pending_review":
      return "Pending review";
    case "completed":
      return "Completed";
    case "not_applicable":
      return "N/A";
  }
}

export function statusVariant(
  status: ObligationStatus,
  isOverdue: boolean,
): "overdue" | "alert" | "progress" | "completed" | "review" | "neutral" {
  if (isOverdue) return "overdue";
  switch (status) {
    case "completed":
      return "completed";
    case "in_progress":
      return "progress";
    case "pending_review":
      return "review";
    case "not_applicable":
      return "neutral";
    default:
      return "neutral";
  }
}

export function daysRemainingLabel(days: number): string {
  if (days < 0) {
    return `${Math.abs(days)} day${Math.abs(days) === 1 ? "" : "s"} overdue`;
  }
  if (days === 0) return "Due today";
  if (days === 1) return "1 day";
  return `${days} days`;
}

export function userInitials(name: string | null | undefined, fallback = "?"): string {
  if (!name) return fallback;
  return (
    name
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase() ?? "")
      .join("") || fallback
  );
}

// Effort band → display + lead-time math. Mirrors compliance_agent/db/models.py.
export const EFFORT_BAND_DAYS: Record<EffortBand, number> = {
  "1w": 7,
  "2w": 14,
  "4w": 28,
  "8w": 56,
  "12w": 84,
};

export const EFFORT_BANDS: EffortBand[] = ["1w", "2w", "4w", "8w", "12w"];

// How early the FIRST reminder fires, per band. Single source of truth —
// matches the backend reminder policy (monthly → 1 week, quarterly → 1 month,
// annual → 45 days before the due date).
const _LEAD_DAYS: Record<EffortBand, number> = {
  "1w": 7,
  "2w": 30,
  "4w": 30,
  "8w": 45,
  "12w": 60,
};

const _LEAD_LABEL: Record<EffortBand, string> = {
  "1w": "1 week before",
  "2w": "1 month before",
  "4w": "30 days before",
  "8w": "45 days before",
  "12w": "60 days before",
};

export function effortBandLabel(b: EffortBand): string {
  // Human-readable reminder lead time instead of the raw band code.
  return _LEAD_LABEL[b] ?? `${b} effort`;
}

export function leadTimeDays(b: EffortBand): number {
  return _LEAD_DAYS[b] ?? 30;
}

export function statusLabelShort(status: ObligationStatus, isOverdue: boolean): string {
  if (isOverdue) return "Overdue";
  return statusLabel(status);
}
