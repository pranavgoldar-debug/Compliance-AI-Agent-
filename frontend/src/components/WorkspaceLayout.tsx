// Compliance Workspace — single-screen hub for daily compliance work.
// Tabs: Queue (Tasks), Calendar, Licenses, Documents. Each tab is a child
// route that renders the existing page, so deep links still work and the
// browser back/forward buttons mirror tab switches.
//
// Sub-routes are wired in App.tsx; this file is the shell + tab bar.
import { NavLink, Outlet } from "react-router-dom";
import {
  CalendarDays,
  FileBadge,
  FolderOpen,
  ListChecks,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface Tab {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const TABS: Tab[] = [
  { to: "/workspace/queue", label: "Queue", icon: ListChecks },
  { to: "/workspace/calendar", label: "Calendar", icon: CalendarDays },
  { to: "/workspace/licenses", label: "Licenses", icon: FileBadge },
  { to: "/workspace/documents", label: "Documents", icon: FolderOpen },
];

export function WorkspaceLayout() {
  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Compliance Workspace
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Your queue, calendar, licenses, and evidence in one place.
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
