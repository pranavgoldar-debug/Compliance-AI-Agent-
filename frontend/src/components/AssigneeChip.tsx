import { UserPlus } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { userInitials } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { UserBrief } from "@/types/api";

interface Props {
  user: UserBrief | null | undefined;
  showName?: boolean;
  size?: "xs" | "sm" | "md";
  className?: string;
}

const SIZES = {
  xs: { av: "h-5 w-5", txt: "text-[10px]", label: "text-xs" },
  sm: { av: "h-6 w-6", txt: "text-[10px]", label: "text-xs" },
  md: { av: "h-7 w-7", txt: "text-[11px]", label: "text-sm" },
};

export function AssigneeChip({ user, showName = false, size = "sm", className }: Props) {
  const s = SIZES[size];
  if (!user) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 text-muted-foreground italic",
          s.label,
          className,
        )}
        title="Unassigned"
      >
        <UserPlus className="h-3.5 w-3.5" />
        {showName && "Unassigned"}
      </span>
    );
  }
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 min-w-0", s.label, className)}
      title={user.full_name || user.email}
    >
      <Avatar className={s.av}>
        <AvatarFallback className={s.txt}>{userInitials(user.full_name || user.email)}</AvatarFallback>
      </Avatar>
      {showName && <span className="truncate">{user.full_name?.split(" ")[0] || user.email}</span>}
    </span>
  );
}
