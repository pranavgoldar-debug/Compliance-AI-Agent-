import { jurisdiction } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  code: string;
  showName?: boolean;
  className?: string;
}

// flagcdn.com serves PNG country flags by ISO 3166-1 alpha-2 code at
// fixed widths. Works on every OS/browser — sidesteps the emoji-flag
// rendering bug on Windows / Linux where the Twemoji shape doesn't
// ship with the default system font.
//
// EU isn't a real country but flagcdn does serve `eu`. Anything missing
// from JURISDICTIONS falls back to a textual code chip.
function flagUrl(iso2: string): string {
  return `https://flagcdn.com/24x18/${iso2}.png`;
}

export function JurisdictionBadge({ code, showName = true, className }: Props) {
  const j = jurisdiction(code);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-sm whitespace-nowrap",
        className,
      )}
    >
      {j.iso2 ? (
        <img
          src={flagUrl(j.iso2)}
          srcSet={`https://flagcdn.com/48x36/${j.iso2}.png 2x`}
          width={20}
          height={15}
          alt=""
          aria-hidden
          className="rounded-[2px] border border-black/5 object-cover"
        />
      ) : (
        <span
          aria-hidden
          className="inline-flex items-center justify-center h-[15px] min-w-[20px] px-1 rounded-[2px] border border-border bg-secondary text-[10px] font-semibold text-muted-foreground"
        >
          {code.toUpperCase().slice(0, 2)}
        </span>
      )}
      {showName && <span>{j.name}</span>}
    </span>
  );
}
