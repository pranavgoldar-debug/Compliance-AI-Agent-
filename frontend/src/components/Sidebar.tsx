import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  CalendarDays,
  Building2,
  ListChecks,
  Library,
  FolderOpen,
  ScrollText,
  Settings,
  PanelLeftClose,
  PanelLeft,
  Lock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type { Obligation } from "@/types/api";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
  badge?: "tasks";
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/calendar", label: "Compliance Calendar", icon: CalendarDays },
  { to: "/entities", label: "Entities", icon: Building2 },
  { to: "/tasks", label: "Tasks", icon: ListChecks, badge: "tasks" },
  { to: "/rules", label: "Compliance Rules", icon: Library, adminOnly: true },
  { to: "/documents", label: "Documents", icon: FolderOpen },
  { to: "/audit-log", label: "Audit Log", icon: ScrollText, adminOnly: true },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  // Live count of obligations assigned to me, surfaced as a badge on Tasks.
  const { data: openCount } = useQuery({
    queryKey: ["sidebar-task-count"],
    queryFn: async () => {
      const tasks = await api.get<Obligation[]>("/api/tasks?scope=assigned");
      return tasks.filter((t) => t.status !== "completed" && t.status !== "not_applicable").length;
    },
    enabled: !!user,
    staleTime: 60_000,
  });

  return (
    <aside
      className={cn(
        "flex flex-col bg-white border-r border-border transition-all duration-200",
        collapsed ? "w-[64px]" : "w-[240px]",
      )}
    >
      {/* Brand */}
      <div
        className={cn(
          "h-16 flex items-center border-b border-border",
          collapsed ? "justify-center" : "justify-between px-5",
        )}
      >
        <a href="/" className="flex items-center gap-2">
          {collapsed ? (
            <div className="h-9 w-9 rounded-md bg-aspora-500 grid place-items-center text-white font-extrabold text-lg">
              a
            </div>
          ) : (
            <img src="/static/brand/aspora-wordmark.png" alt="Aspora" className="h-7" />
          )}
        </a>
        {!collapsed && (
          <button
            onClick={onToggle}
            className="p-1 rounded-md hover:bg-secondary text-muted-foreground"
            aria-label="Collapse sidebar"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        )}
      </div>

      {!collapsed && (
        <div className="px-5 pt-4 pb-2 text-[11px] uppercase tracking-wider text-muted-foreground">
          Compliance OS
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 px-2 py-2 space-y-1">
        {NAV.map((item) => {
          const Icon = item.icon;
          const isGated = item.adminOnly && !isAdmin;
          if (isGated && collapsed) return null;
          const showBadge = item.badge === "tasks" && typeof openCount === "number" && openCount > 0;
          if (isGated) {
            return (
              <div
                key={item.to}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground/60",
                  collapsed && "justify-center px-2",
                )}
                title={`${item.label} (admin only)`}
              >
                <Icon className="h-[18px] w-[18px] shrink-0" />
                {!collapsed && (
                  <>
                    <span className="truncate flex-1">{item.label}</span>
                    <Lock className="h-3 w-3 shrink-0 opacity-70" />
                  </>
                )}
              </div>
            );
          }
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-aspora-50 text-aspora-700"
                    : "text-foreground/70 hover:bg-secondary hover:text-foreground",
                  collapsed && "justify-center px-2",
                )
              }
              title={collapsed ? item.label : undefined}
            >
              <Icon className="h-[18px] w-[18px] shrink-0" />
              {!collapsed && (
                <>
                  <span className="truncate flex-1">{item.label}</span>
                  {showBadge && (
                    <span className="ml-auto inline-flex items-center justify-center min-w-[20px] h-[18px] px-1.5 rounded-full bg-aspora-600 text-white text-[10px] font-semibold tabular-nums">
                      {openCount}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Settings + collapse handle */}
      <div className="border-t border-border p-2 space-y-1">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-aspora-50 text-aspora-700"
                : "text-foreground/70 hover:bg-secondary hover:text-foreground",
              collapsed && "justify-center px-2",
            )
          }
          title={collapsed ? "Settings" : undefined}
        >
          <Settings className="h-[18px] w-[18px] shrink-0" />
          {!collapsed && <span className="truncate">Settings</span>}
        </NavLink>
        {collapsed && (
          <button
            onClick={onToggle}
            className="w-full p-2 rounded-md hover:bg-secondary text-muted-foreground grid place-items-center"
            aria-label="Expand sidebar"
          >
            <PanelLeft className="h-4 w-4" />
          </button>
        )}
      </div>
    </aside>
  );
}
