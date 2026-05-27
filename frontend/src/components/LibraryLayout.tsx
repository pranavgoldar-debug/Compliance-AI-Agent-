// Regulatory Library — single home for everything regulation-related.
// Tabs: Catalog (per-jurisdiction filings list) and Regulations (the
// uploaded source documents + AI-extracted obligations).
//
// Like WorkspaceLayout, sub-routes are wired in App.tsx so deep links
// keep working.
import { NavLink, Outlet } from "react-router-dom";
import { BookOpen, Table2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Tab {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const TABS: Tab[] = [
  { to: "/library/catalog", label: "Filings Catalog", icon: Table2 },
  { to: "/library/regulations", label: "Regulations", icon: BookOpen },
];

export function LibraryLayout() {
  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Regulatory Library
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            The canonical catalog of filings + the source regulations they're derived from.
          </p>
        </div>
      </div>

      <div className="border-b border-border">
        <nav className="-mb-px flex gap-1 overflow-x-auto scrollbar-thin">
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <NavLink
                key={t.to}
                to={t.to}
                className={({ isActive }) =>
                  cn(
                    "inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap",
                    isActive
                      ? "border-aspora-600 text-aspora-700"
                      : "border-transparent text-muted-foreground hover:text-foreground hover:border-border",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {t.label}
              </NavLink>
            );
          })}
        </nav>
      </div>

      <div>
        <Outlet />
      </div>
    </div>
  );
}
