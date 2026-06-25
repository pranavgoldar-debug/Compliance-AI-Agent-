// Display helpers shared across pages.

import { format, formatDistanceToNow, parseISO } from "date-fns";
import type { EffortBand, ObligationStatus } from "@/types/api";
import { countryFor } from "@/lib/countries";

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

// Jurisdiction options for dropdowns: alphabetical by name, and excluding the
// EU bloc (entities file in specific member states, not "European Union").
// Single source so every jurisdiction picker stays consistent.
export const JURISDICTION_OPTIONS: { code: string; name: string; flag: string }[] =
  Object.entries(JURISDICTIONS)
    .filter(([code]) => code !== "eu")
    .map(([code, j]) => ({ code, name: j.name, flag: j.flag }))
    .sort((a, b) => a.name.localeCompare(b.name));

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

// Pull the official form code(s) out of a filing/form name so we can show a
// separate "Form" column. Conservative on purpose: a code must contain BOTH a
// letter and a digit (CT600, FSA056, GSTR-3B, AOC-4, REP017, FSA029), so plain
// descriptive words ("Senior Accounting Officer") are never mistaken for codes.
// Returns "" when there is no recognisable form code.
export function extractFormCode(formName: string | null | undefined): string {
  const s = (formName ?? "").trim();
  if (!s) return "";
  const codes =
    s.match(/\b[A-Z0-9][A-Z0-9]*(?:[-\/][A-Z0-9]+)*\b/g)?.filter(
      (t) => /\d/.test(t) && /[A-Z]/.test(t) && t.length >= 3 && t.length <= 14,
    ) ?? [];
  // De-dupe while keeping order.
  return Array.from(new Set(codes)).join(" / ");
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
  if (JURISDICTIONS[code]) return JURISDICTIONS[code];
  // Any ISO country code (new jurisdictions stored by alpha-2) resolves to its
  // name + flag; otherwise fall back to the raw code chip.
  const c = countryFor(code);
  if (c) return { name: c.name, flag: "", iso2: c.iso2 };
  return {
    name: code.toUpperCase(),
    flag: "🏳️",
    iso2: "",
  };
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

// Parse a backend timestamp into a Date. SQLAlchemy serialises naive UTC
// (no offset, e.g. "2026-05-28T12:34:56"), which `new Date` / parseISO would
// otherwise read as LOCAL time — making an IST viewer see the raw UTC
// wall-clock. Append Z when there's no explicit timezone so it's read as UTC.
// Use this for ANY API datetime before formatting it for display.
export function parseBackendDate(iso: string): Date {
  const looksAware = /Z$|[+-]\d{2}:?\d{2}$/.test(iso);
  return new Date(looksAware ? iso : iso + "Z");
}

// Localised wall-clock time (e.g. "12:42 PM") in the viewer's own timezone.
export function fmtTime(
  iso: string | null | undefined,
  opts: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" },
): string {
  if (!iso) return "—";
  try {
    return parseBackendDate(iso).toLocaleTimeString([], opts);
  } catch {
    return iso;
  }
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNow(parseBackendDate(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

export function statusLabel(status: ObligationStatus): string {
  switch (status) {
    case "not_started":
      return "Not Started";
    case "in_progress":
      return "Started";
    case "pending_review":
      return "Under Progress";
    case "completed":
      return "Filed";
    case "not_applicable":
      return "Not Applicable";
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
  if (days === 1) return "1 day remaining";
  return `${days} days remaining`;
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

// Friendly labels for entity (and other) field names that show up in the audit
// log / activity feed. Mirrors the Business Information labels on the entity
// overview so "fiscal_year_end" reads "Fiscal year end / ARD". Falls back to a
// title-cased version of the raw field name for anything not mapped.
const FIELD_LABELS: Record<string, string> = {
  name: "Legal name",
  legal_type: "Legal type",
  jurisdiction_code: "Jurisdiction",
  short_code: "Short code",
  registration_number: "Registration number",
  tax_id: "GST / Tax No",
  address: "Address",
  incorporation_date: "Incorporation date",
  fiscal_year_end: "Fiscal year end / ARD",
  annual_return_date: "Annual return date",
  nature_of_operation: "Nature of operation",
  qualification: "Qualification",
  bank_details: "Bank details",
  ownership: "Ownership",
  finance_profile: "Primary activity",
  document_folders: "Document folders",
  status: "Status",
};

// Entity onboarding/operational status → display label + badge variant.
// not_started → slate · in_progress → blue · live → green.
export function entityStatusLabel(status: string | null | undefined): string {
  switch (status) {
    case "in_progress":
      return "In Progress";
    case "live":
      return "Live";
    default:
      return "Not Started";
  }
}

export function entityStatusVariant(
  status: string | null | undefined,
): "neutral" | "progress" | "completed" {
  switch (status) {
    case "in_progress":
      return "progress";
    case "live":
      return "completed";
    default:
      return "neutral";
  }
}

export function fieldLabel(field: string): string {
  return (
    FIELD_LABELS[field] ??
    field.replace(/[._]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
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
