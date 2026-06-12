// Searchable single-country picker for the entity Jurisdiction field. Type to
// filter; the alphabetical list (all ISO countries + legacy slugs, merged via
// jurisdictionOptions) shows flags. The chosen value is the entity's
// jurisdiction code, which flows everywhere else automatically.
import { useMemo, useRef, useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { jurisdictionOptions } from "@/lib/countries";
import { jurisdiction } from "@/lib/format";
import { cn } from "@/lib/utils";

function Flag({ iso2 }: { iso2: string }) {
  if (!iso2) {
    return <span className="inline-block w-5 h-[14px] rounded-[2px] border border-border bg-secondary shrink-0" />;
  }
  return (
    <img
      src={`https://flagcdn.com/24x18/${iso2}.png`}
      srcSet={`https://flagcdn.com/48x36/${iso2}.png 2x`}
      alt=""
      aria-hidden
      className="block w-5 h-[14px] shrink-0 rounded-[2px] border border-black/5 object-cover"
    />
  );
}

export function CountrySelect({
  value,
  onChange,
  placeholder = "— Select —",
}: {
  value: string;
  onChange: (code: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const options = jurisdictionOptions();

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return options;
    return options.filter(
      (o) => o.name.toLowerCase().includes(needle) || o.value.includes(needle) || o.iso2.includes(needle),
    );
  }, [q, options]);

  const current = value ? jurisdiction(value) : null;

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) {
          setQ("");
          setTimeout(() => inputRef.current?.focus(), 30);
        }
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm flex items-center gap-2 text-left"
        >
          {current ? (
            <>
              <Flag iso2={current.iso2} />
              <span className="truncate">{current.name}</span>
            </>
          ) : (
            <span className="text-muted-foreground">{placeholder}</span>
          )}
          <span className="ml-auto text-muted-foreground">▾</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
        <div className="p-2 border-b border-border">
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search country…"
            className="h-9 w-full rounded-md border border-input bg-background px-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <div className="max-h-72 overflow-auto scrollbar-thin py-1">
          {filtered.length === 0 ? (
            <div className="px-3 py-3 text-sm text-muted-foreground">No match.</div>
          ) : (
            filtered.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => {
                  onChange(o.value);
                  setOpen(false);
                }}
                className={cn(
                  "w-full text-left px-3 py-1.5 flex items-center gap-2 text-sm hover:bg-secondary",
                  o.value === value && "bg-aspora-50 text-aspora-800",
                )}
              >
                <Flag iso2={o.iso2} />
                <span className="truncate">{o.name}</span>
              </button>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
