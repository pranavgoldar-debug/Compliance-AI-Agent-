// Tiny Export button with CSV / Excel options. Builds the right URL for
// the unified /api/exports/{kind} endpoint and triggers a browser download.

import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";


interface Props {
  kind: "obligations" | "entities" | "rules" | "documents";
  /** Optional query params (entity_id, status, etc.) to forward. */
  params?: Record<string, string | number | undefined | null>;
  label?: string;
  size?: "default" | "sm";
}


function buildUrl(kind: string, format: "csv" | "xlsx", params?: Props["params"]): string {
  const usp = new URLSearchParams({ format });
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === "") continue;
      usp.set(k, String(v));
    }
  }
  return `/api/exports/${kind}?${usp.toString()}`;
}


export function ExportMenu({ kind, params, label = "Export", size = "sm" }: Props) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size={size}>
          <Download className="h-4 w-4" />
          {label}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Export current view</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <a href={buildUrl(kind, "csv", params)} download>
            <FileText className="h-3.5 w-3.5 mr-2" />
            CSV
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <a href={buildUrl(kind, "xlsx", params)} download>
            <FileSpreadsheet className="h-3.5 w-3.5 mr-2" />
            Excel (.xlsx)
          </a>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
