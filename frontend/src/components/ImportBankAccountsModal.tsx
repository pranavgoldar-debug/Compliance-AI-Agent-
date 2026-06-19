// Admin tool — bulk-import bank accounts from a spreadsheet onto existing
// entities. The file is parsed IN THE BROWSER and the rows are written to each
// matched entity's bank_details via the normal entity PATCH, so the (very
// confidential) bank data goes file -> your DB and is NEVER committed to git.
//
// Rows are matched to entities by name (and short code) — anything that doesn't
// match an existing entity is skipped and reported. Accounts are APPENDED to
// whatever an entity already has. Numbers are imported exactly as they appear in
// the sheet (fix any Excel-truncated values by hand afterwards).
import { useMemo, useRef, useState } from "react";
import * as XLSX from "xlsx";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Upload } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { BankDetails, Entity } from "@/types/api";

type Field =
  | "account_name"
  | "account_type"
  | "bank_name"
  | "currency"
  | "account_number"
  | "sort_code"
  | "iban"
  | "swift";

const FIELDS: { key: Field; label: string }[] = [
  { key: "account_name", label: "Account name / holder" },
  { key: "account_type", label: "Account type / purpose" },
  { key: "bank_name", label: "Bank" },
  { key: "currency", label: "Currency" },
  { key: "account_number", label: "Account number" },
  { key: "sort_code", label: "Sort code / routing" },
  { key: "iban", label: "IBAN" },
  { key: "swift", label: "SWIFT / BIC" },
];

// Header keyword → field, used to pre-fill the column mapping. `entity` is the
// column that names which entity each row belongs to.
const GUESS: Record<string, RegExp> = {
  entity: /entit|company|^name$/i,
  account_name: /holder|account\s*name/i,
  account_type: /type|purpose|product/i,
  bank_name: /bank/i,
  currency: /currency|ccy/i,
  account_number: /account\s*(number|no)|acc.*no/i,
  sort_code: /sort|routing/i,
  iban: /iban/i,
  swift: /swift|bic/i,
};

function normName(s: unknown): string {
  return String(s ?? "")
    .trim()
    .toLowerCase()
    .replace(/\s*\([a-z]{2,3}\)\s*$/i, "") // drop trailing "(IE)", "(GE)"…
    .replace(/[.,]/g, "")
    .replace(/\s+/g, " ");
}

function existingAccounts(bd: BankDetails | null | undefined): BankDetails[] {
  if (!bd) return [];
  if (Array.isArray(bd.accounts) && bd.accounts.length) return bd.accounts;
  const { accounts: _drop, ...flat } = bd;
  return Object.values(flat).some((v) => v) ? [flat] : [];
}

export function ImportBankAccountsModal({
  open,
  onOpenChange,
  entities,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  entities: Entity[];
}) {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [rows, setRows] = useState<string[][]>([]);
  const [entityCol, setEntityCol] = useState<number>(-1);
  const [map, setMap] = useState<Record<Field, number>>(
    () => Object.fromEntries(FIELDS.map((f) => [f.key, -1])) as Record<Field, number>,
  );
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const reset = () => {
    setHeaders([]); setRows([]); setEntityCol(-1);
    setMap(Object.fromEntries(FIELDS.map((f) => [f.key, -1])) as Record<Field, number>);
    setError(null); setResult(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const onFile = async (file: File) => {
    setError(null); setResult(null);
    try {
      const wb = XLSX.read(await file.arrayBuffer());
      const ws = wb.Sheets[wb.SheetNames[0]];
      const aoa = XLSX.utils.sheet_to_json<string[]>(ws, { header: 1, defval: "", raw: false });
      const hdr = (aoa[0] ?? []).map((h) => String(h ?? "").trim());
      const body = aoa.slice(1).filter((r) => r.some((c) => String(c ?? "").trim()));
      if (!hdr.length || !body.length) {
        setError("That sheet looks empty. First row should be column headers.");
        return;
      }
      // Pre-fill mapping from header keywords.
      const find = (re: RegExp) => hdr.findIndex((h) => re.test(h));
      setEntityCol(find(GUESS.entity));
      setMap(
        Object.fromEntries(
          FIELDS.map((f) => [f.key, find(GUESS[f.key])]),
        ) as Record<Field, number>,
      );
      setHeaders(hdr);
      setRows(body.map((r) => r.map((c) => String(c ?? "").trim())));
    } catch {
      setError("Couldn't read that file. Use .xlsx, .xls or .csv.");
    }
  };

  // Resolve entity-name → entity once (by normalised name and by short code).
  const lookup = useMemo(() => {
    const m = new Map<string, Entity>();
    for (const e of entities) {
      m.set(normName(e.name), e);
      if (e.short_code) m.set(normName(e.short_code), e);
    }
    return m;
  }, [entities]);

  const matchEntity = (name: string): Entity | undefined =>
    lookup.get(normName(name));

  // Live preview: how many rows map to a known entity vs get skipped.
  const preview = useMemo(() => {
    if (!rows.length || entityCol < 0) return null;
    let matched = 0;
    const skipped = new Set<string>();
    for (const r of rows) {
      const name = r[entityCol] ?? "";
      if (!name.trim()) continue;
      if (matchEntity(name)) matched++;
      else skipped.add(name.trim());
    }
    return { matched, skipped: [...skipped] };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, entityCol, lookup]);

  const doImport = useMutation({
    mutationFn: async () => {
      // Group new accounts by entity id.
      const byEntity = new Map<number, BankDetails[]>();
      let skipped = 0;
      for (const r of rows) {
        const ent = matchEntity(r[entityCol] ?? "");
        if (!ent) {
          if ((r[entityCol] ?? "").trim()) skipped++;
          continue;
        }
        const acc: BankDetails = {};
        for (const f of FIELDS) {
          const col = map[f.key];
          const val = col >= 0 ? (r[col] ?? "").trim() : "";
          if (val) (acc as Record<string, string>)[f.key] = val;
        }
        if (!Object.keys(acc).length) continue;
        if (!byEntity.has(ent.id)) byEntity.set(ent.id, []);
        byEntity.get(ent.id)!.push(acc);
      }
      let imported = 0;
      await Promise.all(
        [...byEntity.entries()].map(([id, accts]) => {
          const ent = entities.find((e) => e.id === id)!;
          const merged = [...existingAccounts(ent.bank_details), ...accts];
          imported += accts.length;
          return api.patch(`/api/entities/${id}`, { bank_details: { accounts: merged } });
        }),
      );
      return { imported, entities: byEntity.size, skipped };
    },
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      queryClient.invalidateQueries({ queryKey: ["entity"] });
      setResult(
        `Imported ${r.imported} account(s) across ${r.entities} entity(ies).` +
          (r.skipped ? ` Skipped ${r.skipped} row(s) whose entity isn't in the app.` : ""),
      );
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  });

  const colSelect = (value: number, onChange: (n: number) => void) => (
    <select
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
    >
      <option value={-1}>— none —</option>
      {headers.map((h, i) => (
        <option key={i} value={i}>{h || `Column ${i + 1}`}</option>
      ))}
    </select>
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => { if (!v) reset(); onOpenChange(v); }}
    >
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>Import bank accounts</DialogTitle>
        </DialogHeader>
        <div className="p-6 space-y-4">
          <p className="text-xs text-muted-foreground">
            Upload a spreadsheet (.xlsx/.xls/.csv, first row = headers). Rows are
            matched to entities by name/short code and appended to each entity's
            bank accounts. The file is read in your browser — the data goes
            straight to your database and is never stored in the codebase.
          </p>

          <div>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }}
              className="block w-full text-sm file:mr-3 file:rounded-md file:border file:border-input file:bg-secondary file:px-3 file:py-1.5 file:text-sm"
            />
          </div>

          {error && <p className="text-xs text-red-600">{error}</p>}

          {headers.length > 0 && (
            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-xs font-medium">Entity column (which entity each row belongs to)</label>
                {colSelect(entityCol, setEntityCol)}
              </div>
              <div className="grid grid-cols-2 gap-2">
                {FIELDS.map((f) => (
                  <div key={f.key} className="space-y-1">
                    <label className="text-[11px] text-muted-foreground">{f.label}</label>
                    {colSelect(map[f.key], (n) => setMap((m) => ({ ...m, [f.key]: n })))}
                  </div>
                ))}
              </div>
              {preview && (
                <p className="text-xs text-muted-foreground">
                  {preview.matched} row(s) match an entity
                  {preview.skipped.length > 0 && (
                    <> · {preview.skipped.length} unmatched: <span className="text-foreground">{preview.skipped.slice(0, 6).join(", ")}{preview.skipped.length > 6 ? "…" : ""}</span></>
                  )}
                </p>
              )}
            </div>
          )}

          {result && <p className="text-xs text-emerald-700 font-medium">{result}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => { reset(); onOpenChange(false); }}>
            {result ? "Close" : "Cancel"}
          </Button>
          <Button
            onClick={() => doImport.mutate()}
            disabled={
              doImport.isPending || entityCol < 0 || !rows.length ||
              !preview || preview.matched === 0
            }
          >
            {doImport.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            Import {preview ? `(${preview.matched})` : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
