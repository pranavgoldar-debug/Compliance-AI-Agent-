import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  CalendarDays,
  Building2,
  ListChecks,
  Library,
  Settings,
  PanelLeftClose,
  PanelLeft,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/calendar", label: "Compliance Calendar", icon: CalendarDays },
  { to: "/entities", label: "Entities", icon: Building2 },
  { to: "/tasks", label: "Tasks", icon: ListChecks },
  { to: "/rules", label: "Compliance Rules", icon: Library, adminOnly: true },
  { to: "/settings", label: "Settings", icon: Settings, adminOnly: true },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

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
          {/* Aspora purple "a" lockup. Falls back to wordmark when expanded. */}
          {collapsed ? (
            <div className="h-9 w-9 rounded-md bg-aspora-500 grid place-items-center text-white font-extrabold text-lg">
              a
            </div>
          ) : (
            <img
              src="/static/brand/aspora-wordmark.png"
              alt="Aspora"
              className="h-7"
            />
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
        {NAV.filter((n) => !n.adminOnly || isAdmin).map((item) => {
          const Icon = item.icon;
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
              {!collapsed && <span className="truncate">{item.label}</span>}
            </NavLink>
          );
        })}
      </nav>

      {/* Collapse-expand handle when collapsed */}
      {collapsed && (
        <button
          onClick={onToggle}
          className="m-2 p-2 rounded-md hover:bg-secondary text-muted-foreground self-center"
          aria-label="Expand sidebar"
        >
          <PanelLeft className="h-4 w-4" />
        </button>
      )}
    </aside>
  );
}
