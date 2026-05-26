import { useEffect, useState } from "react";
import {
  Bell,
  Search,
  LogOut,
  Settings as SettingsIcon,
  ChevronRight,
  BellRing,
  AlertCircle,
  AtSign,
  UserCheck,
  CheckCircle2,
  Sparkles,
  Beaker,
} from "lucide-react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/contexts/AuthContext";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { fmtRelative, userInitials } from "@/lib/format";
import { useObligationDrawer } from "@/contexts/ObligationDrawerContext";
import { cn } from "@/lib/utils";
import type { NotificationOut, Obligation, SystemInfo } from "@/types/api";


// ---------------------------------------------------------------------------
// Breadcrumbs
// ---------------------------------------------------------------------------
const ROUTE_LABELS: Record<string, string> = {
  "": "Dashboard",
  calendar: "Compliance Calendar",
  entities: "Entities",
  tasks: "Tasks",
  rules: "Compliance Rules",
  documents: "Documents",
  "audit-log": "Audit Log",
  settings: "Settings",
  obligations: "Obligation",
};

function useBreadcrumbs() {
  const location = useLocation();
  const segments = location.pathname.split("/").filter(Boolean);
  if (segments.length === 0) {
    return [{ label: "Dashboard", to: "/" }];
  }
  const crumbs: { label: string; to: string }[] = [];
  let path = "";
  segments.forEach((seg, idx) => {
    path += `/${seg}`;
    const isLast = idx === segments.length - 1;
    const label = ROUTE_LABELS[seg] ?? (isLast && /^\d+$/.test(seg) ? null : seg);
    if (label) crumbs.push({ label, to: path });
  });
  return crumbs;
}


function Breadcrumbs() {
  const crumbs = useBreadcrumbs();
  return (
    <nav className="hidden md:flex items-center gap-1 text-sm text-muted-foreground min-w-0">
      {crumbs.map((c, i) => {
        const isLast = i === crumbs.length - 1;
        return (
          <span key={c.to} className="inline-flex items-center gap-1 min-w-0">
            {i > 0 && <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-60" />}
            {isLast ? (
              <span className="truncate font-medium text-foreground">{c.label}</span>
            ) : (
              <Link to={c.to} className="truncate hover:text-foreground">
                {c.label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}


// ---------------------------------------------------------------------------
// Mode badge — auto-flips to Live (Claude) when the server has the key set.
// ---------------------------------------------------------------------------
function ModeBadge() {
  const { data } = useQuery({
    queryKey: ["system-info"],
    queryFn: () => api.get<SystemInfo>("/api/system/info"),
    staleTime: 5 * 60_000,
  });
  if (!data) return null;
  const live = data.mode === "live";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "hidden md:inline-flex items-center gap-1 px-2 h-7 rounded-md text-[11px] font-medium border",
            live
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-slate-200 bg-slate-50 text-slate-600",
          )}
        >
          {live ? <Sparkles className="h-3 w-3" /> : <Beaker className="h-3 w-3" />}
          {live ? "Live (Claude)" : "Mock mode"}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {live
          ? "Ask Aspora + Add Rule from text use the real Claude API."
          : "AI features run from curated mocks. Set COMPLIANCE_AGENT_LIVE=1 + ANTHROPIC_API_KEY to switch."}
      </TooltipContent>
    </Tooltip>
  );
}


// ---------------------------------------------------------------------------
// Notifications panel — wired to /api/notifications
// ---------------------------------------------------------------------------
function iconFor(kind: NotificationOut["kind"]) {
  switch (kind) {
    case "overdue":
      return { Icon: AlertCircle, classes: "bg-red-100 text-red-700" };
    case "alert_window":
      return { Icon: BellRing, classes: "bg-amber-100 text-amber-700" };
    case "mention":
      return { Icon: AtSign, classes: "bg-blue-100 text-blue-700" };
    case "assigned":
      return { Icon: UserCheck, classes: "bg-aspora-100 text-aspora-700" };
    case "status_change":
      return { Icon: CheckCircle2, classes: "bg-emerald-100 text-emerald-700" };
  }
}


function NotificationPanel({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<"all" | "mentions" | "alerts">("all");
  const { openObligation } = useObligationDrawer();
  const queryClient = useQueryClient();

  const { data: notifications = [], isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<NotificationOut[]>("/api/notifications"),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const markReadMutation = useMutation({
    mutationFn: (ids: number[]) => api.post("/api/notifications/read", { ids }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const markAllReadMutation = useMutation({
    mutationFn: () => api.post("/api/notifications/read-all"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const visible = notifications.filter((n) => {
    if (tab === "all") return true;
    if (tab === "mentions") return n.kind === "mention";
    return n.kind === "overdue" || n.kind === "alert_window" || n.kind === "status_change";
  });

  const unread = notifications.filter((n) => !n.read);

  return (
    <div className="w-[400px] -m-2">
      <div className="px-4 pt-4 pb-2 flex items-center justify-between">
        <div className="font-semibold text-sm flex items-center gap-1.5">
          Notifications
          {unread.length > 0 && (
            <Badge variant="default" className="text-[10px]">
              {unread.length} new
            </Badge>
          )}
        </div>
        <button
          className="text-xs text-aspora-700 hover:underline disabled:opacity-50"
          disabled={markAllReadMutation.isPending || unread.length === 0}
          onClick={() => markAllReadMutation.mutate()}
        >
          Mark all as read
        </button>
      </div>
      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <TabsList className="mx-4 mb-2">
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="mentions">Mentions</TabsTrigger>
          <TabsTrigger value="alerts">Alerts</TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="max-h-[460px] overflow-y-auto scrollbar-thin border-t border-border">
        {isLoading ? (
          <div className="px-4 py-8 text-center text-sm text-muted-foreground">Loading…</div>
        ) : visible.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-muted-foreground">
            {tab === "mentions"
              ? "No one's mentioned you yet. Quiet."
              : tab === "alerts"
                ? "No alerts. Smooth sailing."
                : "Inbox zero."}
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {visible.map((n) => {
              const { Icon, classes } = iconFor(n.kind);
              return (
                <li key={`${n.kind}-${n.id ?? n.obligation_id}-${n.created_at}`}>
                  <button
                    type="button"
                    className={cn(
                      "w-full text-left px-4 py-3 hover:bg-secondary/50 flex items-start gap-3",
                      !n.read && "bg-aspora-50/30",
                    )}
                    onClick={() => {
                      if (n.id) markReadMutation.mutate([n.id]);
                      if (n.obligation_id) {
                        openObligation(n.obligation_id);
                        onClose();
                      }
                    }}
                  >
                    <span
                      className={cn(
                        "mt-0.5 h-7 w-7 grid place-items-center rounded-full shrink-0",
                        classes,
                      )}
                    >
                      <Icon className="h-4 w-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium truncate">{n.title}</div>
                      {n.body && (
                        <div className="text-xs text-muted-foreground line-clamp-2">{n.body}</div>
                      )}
                      <div className="text-[11px] text-muted-foreground mt-0.5">
                        {fmtRelative(n.created_at)}
                      </div>
                    </div>
                    {!n.read && (
                      <span className="mt-2 h-2 w-2 rounded-full bg-aspora-600 shrink-0" />
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <div className="px-4 py-2 border-t border-border text-center">
        <Link to="/tasks" className="text-xs text-aspora-700 hover:underline" onClick={onClose}>
          View all in Tasks →
        </Link>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Global search (⌘K)
// ---------------------------------------------------------------------------
function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const { openObligation } = useObligationDrawer();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const { data: obligations } = useQuery({
    queryKey: ["search-obligations"],
    queryFn: () => api.get<Obligation[]>("/api/tasks?scope=all"),
    enabled: open,
    staleTime: 60_000,
  });

  const needle = q.trim().toLowerCase();
  const obMatches = needle
    ? (obligations ?? [])
        .filter(
          (o) =>
            o.rule_form_name.toLowerCase().includes(needle) ||
            o.entity_name.toLowerCase().includes(needle) ||
            (o.period_label?.toLowerCase().includes(needle) ?? false),
        )
        .slice(0, 8)
    : [];

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="relative flex-1 max-w-md inline-flex items-center gap-2 rounded-lg border border-input bg-secondary/60 px-3 h-9 text-sm text-muted-foreground hover:bg-secondary transition-colors"
      >
        <Search className="h-4 w-4" />
        <span className="flex-1 text-left">Search obligations, entities…</span>
        <kbd className="hidden md:inline-flex items-center rounded border border-border bg-background px-1.5 py-0.5 text-[10px] font-mono">
          ⌘K
        </kbd>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm grid place-items-start pt-[15vh]"
          onClick={() => setOpen(false)}
        >
          <div
            className="bg-background rounded-2xl shadow-2xl border border-border w-[640px] max-w-[95vw] overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b border-border px-4 h-12">
              <Search className="h-4 w-4 text-muted-foreground" />
              <Input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Type to search obligations, entities…"
                className="border-0 shadow-none focus-visible:ring-0 px-0 h-full"
              />
              <kbd className="text-[10px] text-muted-foreground border border-border rounded px-1.5 py-0.5">
                ESC
              </kbd>
            </div>
            <div className="max-h-[60vh] overflow-y-auto scrollbar-thin py-2">
              {!q.trim() ? (
                <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                  Start typing — searches obligations and entities you have access to.
                </div>
              ) : obMatches.length === 0 ? (
                <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                  No matches for "{q}". Try the audit log for older items.
                </div>
              ) : (
                <ul className="divide-y divide-border">
                  {obMatches.map((o) => (
                    <li key={o.id}>
                      <button
                        type="button"
                        onClick={() => {
                          openObligation(o.id);
                          setOpen(false);
                        }}
                        className="w-full text-left px-4 py-3 hover:bg-secondary/40 flex items-center justify-between gap-3"
                      >
                        <div className="min-w-0">
                          <div className="text-sm font-medium truncate">
                            {o.rule_form_name}
                          </div>
                          <div className="text-xs text-muted-foreground truncate">
                            {o.entity_name} · {o.period_label || o.rule_frequency}
                          </div>
                        </div>
                        <Badge variant={o.is_overdue ? "overdue" : o.is_in_alert_window ? "alert" : "neutral"}>
                          {o.is_overdue
                            ? "Overdue"
                            : o.is_in_alert_window
                              ? "Alert"
                              : o.status.replace(/_/g, " ")}
                        </Badge>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground flex items-center justify-between">
              <span>↑↓ to navigate · enter to open · esc to close</span>
              <button onClick={() => navigate("/calendar")} className="hover:text-foreground">
                Browse calendar →
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}


// ---------------------------------------------------------------------------
// Topbar shell
// ---------------------------------------------------------------------------
export function Topbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [notifOpen, setNotifOpen] = useState(false);

  const { data: notifications = [] } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<NotificationOut[]>("/api/notifications"),
    enabled: !!user,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  if (!user) return null;

  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <header className="h-14 border-b border-border bg-white flex items-center gap-4 px-6 sticky top-0 z-30">
      <div className="flex-1 min-w-0">
        <Breadcrumbs />
      </div>

      <GlobalSearch />

      <div className="flex items-center gap-2">
        <ModeBadge />

        <Popover open={notifOpen} onOpenChange={setNotifOpen}>
          <PopoverTrigger asChild>
            <button
              className="relative p-2 rounded-md hover:bg-secondary text-muted-foreground"
              aria-label="Notifications"
            >
              <Bell className="h-5 w-5" />
              {unreadCount > 0 && (
                <span className="absolute top-1 right-1 inline-flex items-center justify-center h-4 min-w-[16px] px-1 rounded-full bg-red-500 text-white text-[9px] font-bold tabular-nums">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="p-2 w-auto">
            <NotificationPanel onClose={() => setNotifOpen(false)} />
          </PopoverContent>
        </Popover>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-2 pl-1 pr-2 py-1 rounded-md hover:bg-secondary">
              <Avatar>
                <AvatarFallback>{userInitials(user.full_name || user.email)}</AvatarFallback>
              </Avatar>
              <div className="hidden md:flex flex-col items-start leading-tight">
                <span className="text-sm font-medium">{user.full_name || user.email}</span>
                <span className="text-[11px] text-muted-foreground capitalize">{user.role}</span>
              </div>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <div className="flex flex-col">
                <span>{user.full_name || "—"}</span>
                <span className="text-xs text-muted-foreground font-normal">{user.email}</span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate("/settings")}>
              <SettingsIcon className="h-4 w-4 mr-2" />
              Settings
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={async () => {
                await logout();
                navigate("/login", { replace: true });
              }}
            >
              <LogOut className="h-4 w-4 mr-2" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
