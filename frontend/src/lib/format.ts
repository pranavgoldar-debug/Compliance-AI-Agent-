// Display helpers shared across pages.

import { format, formatDistanceToNow, parseISO } from "date-fns";
import type { ObligationStatus } from "@/types/api";

// Country code → flag emoji + display name. Used by JurisdictionBadge.
export const JURISDICTIONS: Record<string, { name: string; flag: string }> = {
  india: { name: "India", flag: "🇮🇳" },
  uk: { name: "United Kingdom", flag: "🇬🇧" },
  us: { name: "United States", flag: "🇺🇸" },
  eu: { name: "European Union", flag: "🇪🇺" },
  uae: { name: "United Arab Emirates", flag: "🇦🇪" },
  singapore: { name: "Singapore", flag: "🇸🇬" },
  canada: { name: "Canada", flag: "🇨🇦" },
  lithuania: { name: "Lithuania", flag: "🇱🇹" },
};

export function jurisdiction(code: string): { name: string; flag: string } {
  return JURISDICTIONS[code] ?? { name: code.toUpperCase(), flag: "🏳️" };
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
    return formatDistanceToNow(parseISO(iso), { addSuffix: true });
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
