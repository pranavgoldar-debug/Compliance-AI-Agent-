import { Bell, Search, LogOut, Settings as SettingsIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";
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
import { Input } from "@/components/ui/input";

function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("") || "?";
}

export function Topbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  if (!user) return null;

  return (
    <header className="h-16 border-b border-border bg-white flex items-center gap-4 px-8">
      <div className="relative flex-1 max-w-xl">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search obligations, entities, documents…"
          className="pl-9 bg-secondary/60 border-transparent focus-visible:bg-background"
        />
      </div>

      <div className="flex items-center gap-2">
        <button
          className="relative p-2 rounded-md hover:bg-secondary text-muted-foreground"
          aria-label="Notifications"
        >
          <Bell className="h-5 w-5" />
          <span className="absolute top-1.5 right-1.5 h-2 w-2 bg-status-overdue rounded-full" />
        </button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-2 pl-1 pr-2 py-1 rounded-md hover:bg-secondary">
              <Avatar>
                <AvatarFallback>{initials(user.full_name || user.email)}</AvatarFallback>
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
                <span className="text-xs text-muted-foreground font-normal">
                  {user.email}
                </span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {user.role === "admin" && (
              <DropdownMenuItem onClick={() => navigate("/settings")}>
                <SettingsIcon className="h-4 w-4 mr-2" />
                Settings
              </DropdownMenuItem>
            )}
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
