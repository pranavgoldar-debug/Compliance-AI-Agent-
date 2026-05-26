// Textarea with @mention autocomplete. Pops a list of workspace users when
// the user types `@` at the start of a word; arrow keys to navigate, Enter
// or Tab to insert "<name>" (we insert the email local-part so the backend
// can match deterministically).

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { userInitials } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { UserBrief } from "@/types/api";


interface Props {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  rows?: number;
  className?: string;
  onKeyDown?: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
}


/** Find an active "@word" at the caret. Returns the token + its start index. */
function findActiveMention(text: string, caret: number): { token: string; start: number } | null {
  // Walk back from caret looking for a `@` not preceded by an alphanumeric.
  let i = caret - 1;
  while (i >= 0) {
    const ch = text[i];
    if (ch === "@") {
      const prev = i > 0 ? text[i - 1] : "";
      if (prev === "" || /[\s.,;:!?(\[{]/.test(prev)) {
        const token = text.slice(i + 1, caret);
        // Stop at first whitespace if any sneaks in.
        if (/\s/.test(token)) return null;
        return { token, start: i };
      }
      return null;
    }
    if (/\s/.test(ch)) return null;
    i--;
  }
  return null;
}


export function MentionTextarea({
  value,
  onChange,
  placeholder,
  rows = 2,
  className,
  onKeyDown,
}: Props) {
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const [active, setActive] = useState<{ token: string; start: number } | null>(null);
  const [highlight, setHighlight] = useState(0);

  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserBrief[]>("/api/users"),
  });

  // Filter users by the active token (matches first name OR email local part).
  const matches = active
    ? users
        .filter((u) => {
          const t = active.token.toLowerCase();
          if (!t) return true;
          const first = (u.full_name || "").split(" ")[0]?.toLowerCase() || "";
          const local = u.email.toLowerCase().split("@")[0];
          const full = (u.full_name || "").toLowerCase();
          return (
            first.startsWith(t) || local.includes(t) || full.includes(t)
          );
        })
        .slice(0, 6)
    : [];

  // Clamp highlight when matches shrink.
  useEffect(() => {
    if (highlight >= matches.length) setHighlight(0);
  }, [matches.length, highlight]);

  function insertMention(user: UserBrief) {
    const ta = taRef.current;
    if (!ta || !active) return;
    const local = user.email.split("@")[0];
    const before = value.slice(0, active.start);
    const after = value.slice(active.start + 1 + active.token.length); // +1 for '@'
    const inserted = `@${local} `;
    const next = before + inserted + after;
    onChange(next);
    setActive(null);
    // Re-focus and move caret to just after the insertion.
    requestAnimationFrame(() => {
      const pos = (before + inserted).length;
      ta.focus();
      ta.setSelectionRange(pos, pos);
    });
  }

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const next = e.target.value;
    onChange(next);
    const caret = e.target.selectionStart ?? next.length;
    setActive(findActiveMention(next, caret));
  }

  function handleSelect(e: React.SyntheticEvent<HTMLTextAreaElement>) {
    const ta = e.currentTarget;
    setActive(findActiveMention(ta.value, ta.selectionStart ?? 0));
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Mention popup handling takes priority.
    if (active && matches.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlight((h) => (h + 1) % matches.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlight((h) => (h - 1 + matches.length) % matches.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertMention(matches[highlight]);
        return;
      }
      if (e.key === "Escape") {
        setActive(null);
        return;
      }
    }
    onKeyDown?.(e);
  }

  return (
    <div className="relative">
      <textarea
        ref={taRef}
        rows={rows}
        value={value}
        onChange={handleChange}
        onSelect={handleSelect}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className={cn(
          "block w-full px-3 py-2 text-sm focus:outline-none resize-none",
          className,
        )}
      />
      {active && matches.length > 0 && (
        <div className="absolute left-2 bottom-full mb-1 z-30 w-64 rounded-lg border border-border bg-background shadow-lg overflow-hidden">
          <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground bg-secondary/40">
            Mention a teammate
          </div>
          <ul className="max-h-64 overflow-y-auto">
            {matches.map((u, idx) => (
              <li key={u.id}>
                <button
                  type="button"
                  onMouseDown={(e) => {
                    // mousedown so the textarea doesn't lose focus before insert
                    e.preventDefault();
                    insertMention(u);
                  }}
                  onMouseEnter={() => setHighlight(idx)}
                  className={cn(
                    "w-full px-3 py-1.5 text-left flex items-center gap-2 text-sm",
                    idx === highlight && "bg-aspora-50 text-aspora-800",
                  )}
                >
                  <Avatar className="h-6 w-6">
                    <AvatarFallback className="text-[10px]">
                      {userInitials(u.full_name)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="min-w-0">
                    <div className="font-medium truncate">{u.full_name || u.email}</div>
                    <div className="text-[11px] text-muted-foreground truncate">
                      @{u.email.split("@")[0]}
                    </div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}


/**
 * Render a comment body with @mentions highlighted (purple chip). Used in
 * the comment list. Detects the same token shape the backend resolves.
 */
export function renderCommentBody(body: string) {
  const parts: React.ReactNode[] = [];
  const re = /(?<![A-Za-z0-9_])@([A-Za-z0-9._+\-]+)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = re.exec(body)) !== null) {
    if (match.index > last) {
      parts.push(body.slice(last, match.index));
    }
    parts.push(
      <span
        key={key++}
        className="rounded px-1 py-0.5 bg-aspora-50 text-aspora-800 font-medium"
      >
        @{match[1]}
      </span>,
    );
    last = match.index + match[0].length;
  }
  if (last < body.length) parts.push(body.slice(last));
  return parts;
}
