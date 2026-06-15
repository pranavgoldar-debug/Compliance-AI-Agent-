import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  CalendarDays,
  CheckCircle2,
  FolderOpen,
  BookOpen,
  Building2,
  Library,
  ScrollText,
  Settings,
  Users,
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
  exact?: boolean;
}

interface NavGroup {
  heading: string;
  items: NavItem[];
  adminOnly?: boolean;
}

// Flat IA — top-level entries for the daily-use screens. Admin stuff
// stays in its own collapsible group out of the way.
//
// Compliance & Finance is a SINGLE entry (matches the user's reference
// design): one Tasks page where compliance + finance teams both work,
// with the Awaiting payment chip distinguishing the two phases.
const NAV_GROUPS: NavGroup[] = [
  {
    heading: "Finance Compliance OS",
    items: [
      { to: "/", label: "Home", icon: LayoutDashboard, exact: true },
      { to: "/calendar", label: "Calendar", icon: CalendarDays },
      {
        to: "/tasks",
        label: "Filings",
        icon: CheckCircle2,
        badge: "tasks",
      },
      // Employees should see what admin uploaded — the page itself
      // gates the upload affordance on isAdmin, but reading is open.
      { to: "/documents", label: "Documents", icon: FolderOpen },
    ],
  },
  {
    heading: "Admin",
    adminOnly: true,
    items: [
      { to: "/entities", label: "Entities", icon: Building2, adminOnly: true },
      { to: "/rules", label: "Review & Assign", icon: Library, adminOnly: true },
      // /regulations (Regulation Library) intentionally hidden — overlaps
      // with "Add rule from text" on the Compliance Rules page and was
      // confusing users with a slow/blank state. Re-add the line above to
      // restore.
      { to: "/admin/users", label: "Users", icon: Users, adminOnly: true },
      { to: "/audit-log", label: "Audit Log", icon: ScrollText, adminOnly: true },
    ],
  },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  // Live count of obligations assigned to me — drives the badge on
  // Compliance & Finance.
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
        "flex flex-col bg-card border-r border-border transition-all duration-200",
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
            <img
              src="/static/brand/aspora-mark.svg"
              alt="Aspora"
              className="h-9 w-9"
            />
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

      {/* Nav */}
      <nav className="flex-1 px-2 py-2 space-y-3">
        {NAV_GROUPS.map((group, gi) => {
          if (group.adminOnly && !isAdmin) return null;
          return (
            <div key={group.heading} className="space-y-1">
              {!collapsed && (
                <div
                  className={cn(
                    "px-3 text-[11px] uppercase tracking-wider text-muted-foreground",
                    gi === 0 ? "pt-2 pb-2" : "pt-3 pb-2",
                  )}
                >
                  {group.heading}
                </div>
              )}
              {collapsed && gi > 0 && (
                <div className="mx-2 my-2 border-t border-border" />
              )}
              {group.items.map((item) => {
                const Icon = item.icon;
                const isGated = item.adminOnly && !isAdmin;
                if (isGated && collapsed) return null;
                const badgeCount =
                  item.badge === "tasks" ? openCount : undefined;
                const showBadge =
                  typeof badgeCount === "number" && badgeCount > 0;
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
                    // Top-level items match exact — they're leaf pages now,
                    // no child routes to keep them highlighted for.
                    end={item.exact ?? true}
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
                            {badgeCount}
                          </span>
                        )}
                      </>
                    )}
                  </NavLink>
                );
              })}
            </div>
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
