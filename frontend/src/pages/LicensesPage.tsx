// Licenses page — admin uploads a license, sees its details, and gets a
// list of compliance rules that apply (matched on jurisdiction + tokens
// from the license's authority/type/name).
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  Download,
  ExternalLink,
  FileBadge,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/PageHeader";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { EmptyState } from "@/components/EmptyState";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { fmtDate, JURISDICTIONS, cleanFilingName, deriveFunction } from "@/lib/format";
import {
  gatesForJurisdiction,
  followupsForJurisdiction,
} from "@/lib/financeGates";
import type { GateOption } from "@/lib/financeGates";
import type {
  ApplicableRulesResponse,
  Entity,
  License,
  LicenseExpiryStatus,
  LicenseRuleHit,
} from "@/types/api";

function expiryBadgeVariant(
  s: LicenseExpiryStatus,
): "completed" | "alert" | "overdue" | "neutral" {
  if (s === "valid") return "completed";
  if (s === "expiring") return "alert";
  if (s === "expired") return "overdue";
  return "neutral";
}

function expiryLabel(lic: License): string {
  if (lic.expiry_status === "expired") {
    return `Expired ${Math.abs(lic.days_to_expiry ?? 0)}d ago`;
  }
  if (lic.expiry_status === "expiring") {
    return `Expires in ${lic.days_to_expiry}d`;
  }
  if (lic.expiry_status === "valid") {
    return `Valid · ${lic.days_to_expiry}d left`;
  }
  return "No expiry date";
}

export function LicensesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [q, setQ] = useState("");
  const [jurisdiction, setJurisdiction] = useState<string>("");
  const [uploadOpen, setUploadOpen] = useState(false);
  // Brief check-mark flash after a successful manual refresh so the user
  // gets visual confirmation even when no new data arrived.
  const [justRefreshed, setJustRefreshed] = useState(false);

  const licensesQuery = useQuery({
    queryKey: ["licenses", jurisdiction],
    queryFn: () => {
      const params = new URLSearchParams();
      if (jurisdiction) params.set("jurisdiction_code", jurisdiction);
      return api.get<License[]>(`/api/licenses?${params.toString()}`);
    },
    // Poll every 20s + on window focus + on every mount so a license an admin
    // uploaded in one tab shows up in an employee's tab quickly. staleTime: 0
    // forces a fresh fetch when the page is revisited.
    refetchInterval: 20_000,
    refetchOnWindowFocus: true,
    refetchOnMount: "always",
    staleTime: 0,
  });

  const filtered = useMemo(() => {
    const list = licensesQuery.data ?? [];
    if (!q.trim()) return list;
    const needle = q.trim().toLowerCase();
    return list.filter(
      (l) =>
        l.name.toLowerCase().includes(needle) ||
        l.authority.toLowerCase().includes(needle) ||
        l.license_type.toLowerCase().includes(needle) ||
        (l.license_number ?? "").toLowerCase().includes(needle) ||
        l.entity_name.toLowerCase().includes(needle),
    );
  }, [licensesQuery.data, q]);

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["licenses"] });
  }

  const [selectedLics, setSelectedLics] = useState<Set<number>>(new Set());
  const toggleLic = (id: number) =>
    setSelectedLics((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const deleteLicenses = useMutation({
    mutationFn: (ids: number[]) =>
      Promise.all(ids.map((id) => api.delete(`/api/licenses/${id}`))),
    onSuccess: (_r, ids) => {
      queryClient.invalidateQueries({ queryKey: ["licenses"] });
      queryClient.invalidateQueries({ queryKey: ["entities"] });
      setSelectedLics(new Set());
      window.alert(`Deleted ${ids.length} license(s).`);
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title="Licenses"
        description="Authorisations each entity holds from regulators. Upload one to see which filings apply to it."
        actions={
          isAdmin && (
            <Button onClick={() => setUploadOpen(true)}>
              <Plus className="h-4 w-4" />
              Upload license
            </Button>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[260px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name, authority, license number, entity…"
            className="pl-9"
          />
        </div>
        <select
          value={jurisdiction}
          onChange={(e) => setJurisdiction(e.target.value)}
          className="h-9 rounded-lg border border-input bg-background px-3 text-sm"
        >
          <option value="">All jurisdictions</option>
          {Object.entries(JURISDICTIONS).map(([code, j]) => (
            <option key={code} value={code}>
              {j.flag} {j.name}
            </option>
          ))}
        </select>
        <Button
          variant="outline"
          size="sm"
          onClick={async () => {
            await licensesQuery.refetch();
            setJustRefreshed(true);
            setTimeout(() => setJustRefreshed(false), 1500);
          }}
          disabled={licensesQuery.isFetching}
          title="Fetch the latest licenses from the server"
        >
          {licensesQuery.isFetching ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : justRefreshed ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          {justRefreshed ? "Up to date" : "Refresh"}
        </Button>
      </div>

      {licensesQuery.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<FileBadge className="h-6 w-6" />}
          title="No licenses yet"
          description={
            isAdmin
              ? "Upload a license to see which compliance rules apply to it."
              : "Ask an admin to upload licenses to see them here."
          }
          action={
            isAdmin && (
              <Button onClick={() => setUploadOpen(true)} size="sm">
                <Plus className="h-4 w-4" />
                Upload license
              </Button>
            )
          }
        />
      ) : (
        <div className="rounded-lg border border-border overflow-hidden bg-card">
          {isAdmin && selectedLics.size > 0 && (
            <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border bg-secondary/30">
              <span className="text-sm">{selectedLics.size} selected</span>
              <Button
                size="sm"
                variant="outline"
                className="text-destructive hover:text-destructive hover:bg-destructive/10"
                disabled={deleteLicenses.isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      `Permanently delete ${selectedLics.size} selected license(s) and their files? This can't be undone.`,
                    )
                  ) {
                    deleteLicenses.mutate(Array.from(selectedLics));
                  }
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete selected
              </Button>
            </div>
          )}
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                {isAdmin && (
                  <th className="px-3 py-2 w-8">
                    <input
                      type="checkbox"
                      checked={filtered.length > 0 && filtered.every((l) => selectedLics.has(l.id))}
                      onChange={(e) =>
                        setSelectedLics(
                          e.target.checked
                            ? new Set(filtered.map((l) => l.id))
                            : new Set(),
                        )
                      }
                      className="accent-aspora-600"
                    />
                  </th>
                )}
                <th className="text-left px-3 py-2 font-medium">License</th>
                <th className="text-left px-3 py-2 font-medium">Entity</th>
                <th className="text-left px-3 py-2 font-medium">Authority</th>
                <th className="text-left px-3 py-2 font-medium">License No.</th>
                <th className="text-left px-3 py-2 font-medium">Expiry</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((lic) => (
                <tr
                  key={lic.id}
                  className="border-t border-border hover:bg-secondary/20 cursor-pointer"
                  onClick={() => navigate(`/licenses/${lic.id}`)}
                >
                  {isAdmin && (
                    <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedLics.has(lic.id)}
                        onChange={() => toggleLic(lic.id)}
                        className="accent-aspora-600"
                      />
                    </td>
                  )}
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <JurisdictionBadge code={lic.jurisdiction_code} showName={false} />
                      <div className="min-w-0">
                        <div className="font-medium truncate">{lic.name}</div>
                        {lic.license_type && (
                          <div className="text-xs text-muted-foreground truncate">
                            {lic.license_type}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-sm">{lic.entity_name}</td>
                  <td className="px-3 py-2 text-sm">{lic.authority}</td>
                  <td className="px-3 py-2 text-xs font-mono text-muted-foreground">
                    {lic.license_number ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    <Badge variant={expiryBadgeVariant(lic.expiry_status)}>
                      {expiryLabel(lic)}
                    </Badge>
                    {lic.expiry_date && (
                      <div className="text-[11px] text-muted-foreground mt-0.5">
                        {fmtDate(lic.expiry_date)}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {lic.has_file && (
                      <a
                        href={`/api/licenses/${lic.id}/download`}
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 text-xs text-aspora-600 hover:underline"
                        title="Download file"
                      >
                        <Download className="h-3 w-3" />
                        File
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={invalidate}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Upload dialog
// ---------------------------------------------------------------------------
interface LicenseAnalyze {
  available: boolean;
  notes: string | null;
  suggested_entity_id: number | null;
  entity_name: string | null;
  name: string | null;
  license_type: string | null;
  authority: string | null;
  jurisdiction_code: string | null;
  license_number: string | null;
  issue_date: string | null;
  expiry_date: string | null;
}

function UploadDialog({
  open,
  onOpenChange,
  onUploaded,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onUploaded: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [aiNote, setAiNote] = useState<string | null>(null);

  const { data: entities = [] } = useQuery({
    queryKey: ["entities", "for-license-upload"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
    enabled: open,
  });

  const [entityId, setEntityId] = useState<number | "">("");
  const [name, setName] = useState("");
  const [licenseType, setLicenseType] = useState("");
  const [authority, setAuthority] = useState("");
  const [jurisdictionCode, setJurisdictionCode] = useState("");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [issueDate, setIssueDate] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);

  // When the user picks an entity, default the jurisdiction to match.
  const selectedEntity = entities.find((e) => e.id === entityId);
  function pickEntity(id: number) {
    setEntityId(id);
    const ent = entities.find((e) => e.id === id);
    if (ent && !jurisdictionCode) setJurisdictionCode(ent.jurisdiction_code);
  }

  function reset() {
    setEntityId("");
    setName("");
    setLicenseType("");
    setAuthority("");
    setJurisdictionCode("");
    setLicenseNumber("");
    setIssueDate("");
    setExpiryDate("");
    setNotes("");
    setFile(null);
    setAiNote(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    uploadMutation.reset();
    analyzeMutation.reset();
  }

  // Claude reads the uploaded PDF and pre-fills the form fields below.
  const analyzeMutation = useMutation({
    mutationFn: async (f: File) => {
      const form = new FormData();
      form.append("file", f);
      return api.upload<LicenseAnalyze>("/api/licenses/analyze", form);
    },
    onSuccess: (r) => {
      if (!r.available) {
        setAiNote(r.notes || "Couldn't auto-read the file — fill the fields manually.");
        return;
      }
      setAiNote("Claude pre-filled these from the PDF — review and edit before saving.");
      if (r.suggested_entity_id) pickEntity(r.suggested_entity_id);
      if (r.name) setName(r.name);
      if (r.license_type) setLicenseType(r.license_type);
      if (r.authority) setAuthority(r.authority);
      if (r.jurisdiction_code) setJurisdictionCode(r.jurisdiction_code);
      if (r.license_number) setLicenseNumber(r.license_number);
      if (r.issue_date) setIssueDate(r.issue_date);
      if (r.expiry_date) setExpiryDate(r.expiry_date);
    },
    onError: (e) => setAiNote((e as Error).message),
  });

  function handleFile(f: File | null) {
    setFile(f);
    setAiNote(null);
    if (f && f.name.toLowerCase().endsWith(".pdf")) {
      analyzeMutation.mutate(f);
    }
  }

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (entityId === "") throw new Error("Pick an entity.");
      const form = new FormData();
      form.append("entity_id", String(entityId));
      form.append("name", name);
      form.append("license_type", licenseType);
      form.append("authority", authority);
      form.append("jurisdiction_code", jurisdictionCode);
      if (licenseNumber) form.append("license_number", licenseNumber);
      if (issueDate) form.append("issue_date", issueDate);
      if (expiryDate) form.append("expiry_date", expiryDate);
      if (notes) form.append("notes", notes);
      if (file) form.append("file", file);
      return api.upload<License>("/api/licenses", form);
    },
    onSuccess: () => {
      onUploaded();
      reset();
      onOpenChange(false);
    },
  });

  const canSubmit =
    entityId !== "" &&
    name.trim() &&
    authority.trim() &&
    jurisdictionCode &&
    !uploadMutation.isPending &&
    !analyzeMutation.isPending;

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileBadge className="h-5 w-5 text-aspora-600" />
            Upload license
          </DialogTitle>
          <DialogDescription>
            Pin a regulator + jurisdiction to one of your entities. Once saved,
            open the license to see which compliance rules apply.
          </DialogDescription>
        </DialogHeader>

        <div className="p-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Entity *">
              <select
                value={entityId}
                onChange={(e) =>
                  e.target.value ? pickEntity(Number(e.target.value)) : setEntityId("")
                }
                className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm"
              >
                <option value="">Pick an entity…</option>
                {entities.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name} ({e.jurisdiction_code})
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Jurisdiction *">
              <select
                value={jurisdictionCode}
                onChange={(e) => setJurisdictionCode(e.target.value)}
                className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm"
              >
                <option value="">Pick a jurisdiction…</option>
                {Object.entries(JURISDICTIONS).map(([code, j]) => (
                  <option key={code} value={code}>
                    {j.flag} {j.name}
                  </option>
                ))}
              </select>
              {selectedEntity &&
                jurisdictionCode &&
                jurisdictionCode !== selectedEntity.jurisdiction_code && (
                  <div className="text-[11px] text-amber-700 mt-1">
                    Note: this jurisdiction doesn't match the entity's home
                    jurisdiction ({selectedEntity.jurisdiction_code}).
                  </div>
                )}
            </Field>
          </div>

          <Field label="License name *">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. CBUAE SVF Licence, DMCC Trade License"
            />
          </Field>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="License type">
              <Input
                value={licenseType}
                onChange={(e) => setLicenseType(e.target.value)}
                placeholder="Stored Value Facility, Trade License, EMI, FCA Authorisation…"
              />
            </Field>
            <Field label="Issuing authority *">
              <Input
                value={authority}
                onChange={(e) => setAuthority(e.target.value)}
                placeholder="CBUAE, DMCC, FCA, MAS…"
              />
            </Field>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="License number">
              <Input
                value={licenseNumber}
                onChange={(e) => setLicenseNumber(e.target.value)}
                placeholder="Optional"
              />
            </Field>
            <Field label="Issue date">
              <Input
                type="date"
                value={issueDate}
                onChange={(e) => setIssueDate(e.target.value)}
              />
            </Field>
            <Field label="Expiry date">
              <Input
                type="date"
                value={expiryDate}
                onChange={(e) => setExpiryDate(e.target.value)}
              />
            </Field>
          </div>

          <Field label="Notes">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Optional context — scope, conditions, renewal cadence…"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
            />
          </Field>

          <Field label="License file (PDF — optional, but Claude auto-fills from it)">
            <label
              className="flex items-center gap-2 border border-dashed border-border rounded-lg px-3 py-2 cursor-pointer hover:border-aspora-400 hover:bg-aspora-50/40"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                handleFile(e.dataTransfer.files?.[0] ?? null);
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
              />
              {analyzeMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin text-aspora-600" />
              ) : (
                <Upload className="h-4 w-4 text-muted-foreground" />
              )}
              <span className="text-sm">
                {analyzeMutation.isPending
                  ? "Claude is reading the PDF…"
                  : file
                    ? file.name
                    : "Drop the license PDF or click to browse"}
              </span>
              {file && !analyzeMutation.isPending && (
                <button
                  type="button"
                  className="ml-auto text-xs text-muted-foreground hover:text-foreground"
                  onClick={(e) => {
                    e.preventDefault();
                    setFile(null);
                    setAiNote(null);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </label>
            {aiNote && (
              <div className="mt-1.5 flex items-start gap-1.5 text-[11px] text-muted-foreground">
                <Sparkles className="h-3 w-3 mt-0.5 shrink-0 text-aspora-600" />
                <span>{aiNote}</span>
              </div>
            )}
          </Field>

          {uploadMutation.error && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <div>{(uploadMutation.error as Error).message}</div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => uploadMutation.mutate()}
            disabled={!canSubmit}
          >
            {uploadMutation.isPending && (
              <Loader2 className="h-4 w-4 animate-spin" />
            )}
            Save license
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
        {label}
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail dialog — license summary + applicable rules
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// AI extract dialog — reads the uploaded license file, surfaces obligations,
// admin ticks which ones to create as Staging rules.
// ---------------------------------------------------------------------------
interface CandidateRule {
  name: string;
  plain_description?: string | null;
  category: string;
  area: string;
  form_name: string;
  authority: string;
  frequency: string;
  due_date_rule: string;
  payment_rule: string | null;
  applicability: string;
  applicability_note: string | null;
  // Reconciliation against the curated catalogue (the website's source of truth).
  matched_standard?: boolean;
  catalogue_due_date_rule?: string | null;
  catalogue_frequency?: string | null;
  catalogue_applicability?: string | null;
  due_date_differs?: boolean;
  frequency_differs?: boolean;
  applicability_differs?: boolean;
}

interface AIExtractResponse {
  available: boolean;
  license_id: number;
  jurisdiction_hint: string | null;
  extracted_chars: number;
  from_document?: boolean;
  candidates: CandidateRule[];
  notes: string | null;
}

// Loose match so "GST Return GSTR-3B" lines up with a tracked "GSTR-3B".
function normForm(s: string): string {
  return (s || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
}
// Generic words that don't help tell two filings apart — dropped before the
// token-overlap check so e.g. "Annual MLRO report" matches "MLRO report".
const _MATCH_STOP = new Set([
  "the", "and", "for", "of", "to", "in", "on", "a", "an", "with",
  "annual", "monthly", "quarterly", "report", "reports", "return", "returns",
  "form", "filing", "filings", "submission", "review", "notification",
  "fca", "hmrc", "ofsi", "uk", "update", "fees", "fee", "register",
]);
function matchTokens(s: string): Set<string> {
  return new Set(
    (s || "").toLowerCase().match(/[a-z0-9]+/g)?.filter(
      (t) => t.length > 2 && !_MATCH_STOP.has(t),
    ) ?? [],
  );
}
function isTracked(candidateForm: string, existing: string[]): boolean {
  const c = normForm(candidateForm);
  if (!c) return false;
  // 1) Fast path — one name is a substring of the other ("GSTR-3B" in "GST Return GSTR-3B").
  if (
    existing.some((e) => {
      const n = normForm(e);
      return n.length > 2 && (n.includes(c) || c.includes(n));
    })
  )
    return true;
  // 2) Token-overlap — catches reworded names ("Complaints Return" vs
  //    "DISP complaints + Ombudsman cooperation") so genuinely-same filings
  //    aren't flagged "Missing" just because the AI phrased them differently.
  const ct = matchTokens(candidateForm);
  if (ct.size === 0) return false;
  return existing.some((e) => {
    const et = matchTokens(e);
    if (et.size === 0) return false;
    let shared = 0;
    ct.forEach((t) => {
      if (et.has(t)) shared += 1;
    });
    // 2+ shared keywords, or 1 keyword that fully covers the shorter name.
    return shared >= 2 || (shared >= 1 && shared === Math.min(ct.size, et.size));
  });
}

export function AIExtractDialog({
  license,
  open,
  onOpenChange,
  onCreated,
  existingForms = [],
}: {
  license: License;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: () => void;
  existingForms?: string[];
}) {
  const [response, setResponse] = useState<AIExtractResponse | null>(null);
  const [kept, setKept] = useState<Set<number>>(new Set());
  const [candSearch, setCandSearch] = useState("");
  const [candFn, setCandFn] = useState("");
  const [candReg, setCandReg] = useState("");
  const [candCat, setCandCat] = useState("");
  const [candFreq, setCandFreq] = useState("");
  const [candAppl, setCandAppl] = useState("");

  // Qualifying-questions step. `phase` is "questionnaire" until we have the
  // entity's answers, then "extract" (the running / results view).
  const [phase, setPhase] = useState<"questionnaire" | "extract">("questionnaire");
  const [answers, setAnswers] = useState<Record<string, string>>({});

  // Fetch the entity to read its saved finance_profile (and jurisdiction).
  const entityClient = useQueryClient();
  const entityQuery = useQuery({
    queryKey: ["entity", license.entity_id],
    queryFn: () => api.get<Entity>(`/api/entities/${license.entity_id}`),
    enabled: open,
  });
  const juris = entityQuery.data?.jurisdiction_code ?? license.jurisdiction_code;
  const gates = gatesForJurisdiction(juris);

  const extractMutation = useMutation({
    mutationFn: () =>
      api.post<AIExtractResponse>(`/api/licenses/${license.id}/ai-extract`),
    onSuccess: (data) => {
      setResponse(data);
      // Default-tick ONLY the genuinely new filings (not already in your
      // tracked list). So "Search again" with nothing new ticks nothing —
      // it won't create duplicates of what you already track.
      setKept(
        new Set(
          data.candidates
            .map((c, i) => ({ c, i }))
            .filter(({ c }) => !isTracked(c.name || c.form_name, existingForms))
            .map(({ i }) => i),
        ),
      );
    },
  });

  const createMutation = useMutation({
    mutationFn: () => {
      if (!response) throw new Error("Extract first.");
      const picked = response.candidates.filter((_, i) => kept.has(i));
      return api.post("/api/rules/bulk-create", {
        jurisdiction_code:
          response.jurisdiction_hint ?? license.jurisdiction_code,
        rules: picked,
        entity_ids: [license.entity_id],
        status: "staging",
      });
    },
    onSuccess: () => {
      onCreated();
      onOpenChange(false);
      setResponse(null);
      setKept(new Set());
    },
  });

  // Save the questionnaire answers onto the entity, then run the extraction.
  const saveProfileMutation = useMutation({
    mutationFn: () =>
      api.patch<Entity>(`/api/entities/${license.entity_id}`, {
        finance_profile: answers,
      }),
    onSuccess: () => {
      entityClient.invalidateQueries({ queryKey: ["entity", license.entity_id] });
      // Entering the extract phase triggers the run effect below.
      setPhase("extract");
    },
  });

  function reset() {
    setResponse(null);
    setKept(new Set());
    extractMutation.reset();
    createMutation.reset();
  }

  // Decide the opening phase ONCE per open, after the entity loads: if it
  // already has saved answers, skip straight to the extract (they answered
  // before → don't nag); otherwise show the questionnaire. The once-guard keeps
  // a background refetch (or "Edit answers") from snapping the phase back.
  const phaseDecidedRef = useRef(false);
  useEffect(() => {
    if (!open) {
      phaseDecidedRef.current = false;
      return;
    }
    if (phaseDecidedRef.current || !entityQuery.data) return;
    phaseDecidedRef.current = true;
    const saved = entityQuery.data.finance_profile;
    if (saved && Object.keys(saved).length > 0) {
      setAnswers(saved);
      setPhase("extract");
    } else {
      setPhase("questionnaire");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, entityQuery.data]);

  // Once in the extract phase, kick off the run so the user lands on the
  // running state rather than a "click to start" screen.
  useEffect(() => {
    if (
      open &&
      phase === "extract" &&
      !response &&
      !extractMutation.isPending &&
      !extractMutation.isError
    ) {
      extractMutation.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, phase]);

  function answer(key: string, value: string) {
    setAnswers((a) => ({ ...a, [key]: value }));
  }

  const renderOptions = (key: string, options: GateOption[]) => (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => answer(key, o.value)}
          className={cn(
            "rounded-md border px-2.5 py-1 text-xs transition-colors",
            answers[key] === o.value
              ? "border-aspora-500 bg-aspora-50 text-aspora-700 font-medium"
              : "border-border text-muted-foreground hover:bg-secondary",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );

  if (!open) return null;
  return (
    <Card className="border-aspora-300 bg-aspora-50/20">
      <CardContent className="p-5 space-y-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="font-semibold flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-aspora-600" />
              Find Regulations
            </h3>
          </div>
          <div className="flex items-center gap-1">
            {phase === "extract" && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  reset();
                  setPhase("questionnaire");
                }}
              >
                Edit answers
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                reset();
                onOpenChange(false);
              }}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="space-y-4">
          {phase === "questionnaire" ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                A few quick questions about{" "}
                <strong>{entityQuery.data?.name ?? license.entity_name}</strong>{" "}
                so we can mark each filing mandatory or conditional. Answer what
                you know — skip the rest.
              </p>
              {entityQuery.isLoading ? (
                <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin text-aspora-600" />
                  Loading…
                </div>
              ) : (
                <div className="space-y-3 max-h-[440px] overflow-y-auto pr-1 scrollbar-thin">
                  {gates.map((g) => {
                    const fups = followupsForJurisdiction(g, juris);
                    return (
                      <div
                        key={g.id}
                        className="rounded-lg border border-border bg-background/60 px-3 py-2.5"
                      >
                        <div className="text-sm font-medium">{g.question}</div>
                        <div className="text-xs text-muted-foreground mb-2">
                          Drives: {g.drives}
                        </div>
                        {renderOptions(g.key, g.options)}
                        {answers[g.key] === "yes" && fups.length > 0 && (
                          <div className="mt-3 space-y-2.5 border-l-2 border-aspora-200 pl-3">
                            {fups.map((f) => (
                              <div key={f.key}>
                                <div className="text-sm">{f.question}</div>
                                <div className="mt-1.5">
                                  {renderOptions(f.key, f.options)}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : !response ? (
            extractMutation.isError ? (
              <div className="text-sm space-y-3">
                <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-destructive">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>{(extractMutation.error as Error).message}</div>
                </div>
                <Button size="sm" onClick={() => extractMutation.mutate()}>
                  <Sparkles className="h-4 w-4" />
                  Try again
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-3 py-6 text-sm text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin text-aspora-600 shrink-0" />
                Finding finance regulations for this license… (~20–30s)
              </div>
            )
          ) : !response.available ? (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <div className="font-medium mb-1">Couldn't extract.</div>
              <div className="text-amber-800/80">{response.notes}</div>
            </div>
          ) : response.candidates.length === 0 ? (
            <div className="rounded-lg border border-border bg-secondary/40 px-4 py-3 text-sm">
              <div className="font-medium mb-1">No obligations detected.</div>
              <div className="text-muted-foreground">
                {response.notes ||
                  "Claude didn't find any recurring filings in this document. Either the file doesn't list ongoing obligations or the text didn't extract cleanly."}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {(() => {
                // "new vs already tracked" only makes sense once you HAVE a
                // tracked list. On a fresh/empty catalogue everything is just a
                // filing to add — don't flag it all as "NEW".
                const hasTrackedList = existingForms.length > 0;
                const newOnes = response.candidates.filter(
                  (r) => !isTracked(r.name || r.form_name, existingForms),
                );
                const trackedCount = response.candidates.length - newOnes.length;
                if (!hasTrackedList) {
                  return (
                    <div className="text-sm">
                      Claude found <strong>{response.candidates.length}</strong>{" "}
                      filing{response.candidates.length === 1 ? "" : "s"} — all
                      ticked. Untick any you don't want, then create them as
                      Staging.
                    </div>
                  );
                }
                return (
                  <>
                    <div className="text-sm">
                      Claude found <strong>{response.candidates.length}</strong>{" "}
                      filing{response.candidates.length === 1 ? "" : "s"}:{" "}
                      <strong>{newOnes.length} new</strong> (ticked below),{" "}
                      {trackedCount} already tracked.
                    </div>
                    <div
                      className={`rounded-lg border px-3 py-2 text-xs ${
                        newOnes.length === 0
                          ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                          : "border-amber-200 bg-amber-50 text-amber-900"
                      }`}
                    >
                      {newOnes.length === 0 ? (
                        <>
                          <strong>Nothing new.</strong> Everything Claude found is
                          already in your catalogue — nothing is ticked, so
                          nothing will be added. Re-run "Search again" anytime;
                          only genuinely new regulations get ticked.
                        </>
                      ) : (
                        <>
                          <strong>{newOnes.length} new</strong> filing
                          {newOnes.length === 1 ? "" : "s"} (marked{" "}
                          <strong>NEW</strong> below) are ticked to add as
                          Staging. {trackedCount} already-tracked filing
                          {trackedCount === 1 ? "" : "s"} are left unticked.
                        </>
                      )}
                    </div>
                  </>
                );
              })()}
              {(() => {
                const diffs = response.candidates.filter(
                  (r) =>
                    r.due_date_differs ||
                    r.frequency_differs ||
                    r.applicability_differs,
                );
                if (diffs.length === 0) return null;
                return (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900">
                    <strong>Differences vs your tracked rules:</strong>{" "}
                    {diffs.length} of {response.candidates.length} matched filing
                    {diffs.length === 1 ? "" : "s"} have a different due date,
                    frequency, or mandatory/conditional status than what you
                    currently track (marked ⚠ below). Review each and decide
                    which is right — neither side is assumed correct.
                  </div>
                );
              })()}
              {response.notes && (
                <div className="rounded-lg border border-border bg-secondary/30 px-3 py-2 text-xs text-muted-foreground">
                  {response.notes}
                </div>
              )}
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  value={candSearch}
                  onChange={(e) => setCandSearch(e.target.value)}
                  placeholder="Search filings by name, authority, category…"
                  className="pl-8 h-9 text-sm"
                />
              </div>
              {(() => {
                const uniq = (vals: string[]) =>
                  Array.from(new Set(vals.filter(Boolean))).sort((a, b) =>
                    a.localeCompare(b),
                  );
                const sel = (
                  value: string,
                  set: (v: string) => void,
                  opts: string[],
                  label: string,
                ) => (
                  <select
                    value={value}
                    onChange={(e) => set(e.target.value)}
                    className="h-8 rounded border border-input bg-background px-2 text-xs"
                  >
                    <option value="">All {label}</option>
                    {opts.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </select>
                );
                return (
                  <div className="flex flex-wrap gap-2">
                    {sel(candReg, setCandReg, uniq(response.candidates.map((r) => r.authority)), "regulators")}
                    {sel(candCat, setCandCat, uniq(response.candidates.map((r) => r.category)), "categories")}
                    {sel(candFreq, setCandFreq, uniq(response.candidates.map((r) => r.frequency)), "frequencies")}
                    {sel(candAppl, setCandAppl, ["Mandatory", "Conditional", "Sector-specific"], "status")}
                  </div>
                );
              })()}
              <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1 scrollbar-thin">
                {response.candidates
                  .map((r, i) => ({ r, i }))
                  .filter(({ r }) => {
                    const q = candSearch.trim().toLowerCase();
                    if (q &&
                      !`${r.form_name} ${r.plain_description ?? ""} ${r.authority} ${r.category} ${r.frequency}`
                        .toLowerCase()
                        .includes(q))
                      return false;
                    if (candFn && deriveFunction(r.category, r.area) !== candFn)
                      return false;
                    if (candReg && r.authority !== candReg) return false;
                    if (candCat && r.category !== candCat) return false;
                    if (candFreq && r.frequency !== candFreq) return false;
                    if (candAppl && r.applicability !== candAppl) return false;
                    return true;
                  })
                  .map(({ r, i }) => {
                  const isKept = kept.has(i);
                  return (
                    <label
                      key={i}
                      className={`flex gap-3 items-start rounded-lg border px-3 py-2.5 text-sm cursor-pointer transition-colors ${
                        isKept
                          ? "border-aspora-300 bg-aspora-50/50"
                          : "border-border hover:bg-secondary/40"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isKept}
                        onChange={(e) => {
                          const copy = new Set(kept);
                          if (e.target.checked) copy.add(i);
                          else copy.delete(i);
                          setKept(copy);
                        }}
                        className="mt-1 accent-aspora-600"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium">{cleanFilingName(r.name || r.form_name)}</span>
                          <Badge variant="neutral">{deriveFunction(r.category, r.area)}</Badge>
                          {existingForms.length > 0 &&
                            (isTracked(r.name || r.form_name, existingForms) ? (
                              <Badge variant="neutral">Already tracked</Badge>
                            ) : (
                              <Badge variant="alert">NEW</Badge>
                            ))}
                          {r.due_date_differs && (
                            <Badge
                              variant="overdue"
                              title={`Your tracked rule says: ${r.catalogue_due_date_rule ?? "—"}`}
                            >
                              ⚠ Due date differs
                            </Badge>
                          )}
                          {r.frequency_differs && (
                            <Badge
                              variant="overdue"
                              title={`Your tracked rule says: ${r.catalogue_frequency ?? "—"}`}
                            >
                              ⚠ Frequency differs
                            </Badge>
                          )}
                          {r.applicability_differs && (
                            <Badge
                              variant="overdue"
                              title={`Your tracked rule says: ${r.catalogue_applicability ?? "—"}`}
                            >
                              ⚠ Mandatory/Conditional differs
                            </Badge>
                          )}
                        </div>
                        {(r.due_date_differs || r.frequency_differs || r.applicability_differs) && (
                          <div className="text-[11px] text-amber-700 mt-1">
                            Your tracked rule:{" "}
                            {[
                              r.due_date_differs && `due — ${r.catalogue_due_date_rule}`,
                              r.frequency_differs && `frequency — ${r.catalogue_frequency}`,
                              r.applicability_differs &&
                                `applicability — ${r.catalogue_applicability}`,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </div>
                        )}
                        {r.plain_description && (
                          <div className="text-xs text-foreground/80 mt-0.5">
                            {r.plain_description}
                          </div>
                        )}
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {r.authority} · {r.category} · {r.frequency}
                        </div>
                      </div>
                      <Badge
                        variant={
                          r.applicability === "Mandatory" ? "alert" : "neutral"
                        }
                      >
                        {r.applicability}
                      </Badge>
                    </label>
                  );
                })}
              </div>
              {createMutation.error && (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>{(createMutation.error as Error).message}</div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-1">
          {phase === "questionnaire" ? (
            <>
              <Button
                variant="outline"
                onClick={() => {
                  reset();
                  onOpenChange(false);
                }}
              >
                Cancel
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  // Skip — run without saving any answers (the run effect
                  // fires on the phase change).
                  setPhase("extract");
                }}
              >
                Skip
              </Button>
              <Button
                onClick={() => saveProfileMutation.mutate()}
                disabled={saveProfileMutation.isPending}
              >
                {saveProfileMutation.isPending && (
                  <Loader2 className="h-4 w-4 animate-spin" />
                )}
                <Sparkles className="h-4 w-4" />
                Find Regulations
              </Button>
            </>
          ) : !response ? (
            <Button
              variant="outline"
              onClick={() => {
                reset();
                onOpenChange(false);
              }}
            >
              Cancel
            </Button>
          ) : (
            <>
              <Button
                variant="outline"
                onClick={() => {
                  setResponse(null);
                  setKept(new Set());
                  createMutation.reset();
                  extractMutation.mutate();
                }}
              >
                Search again
              </Button>
              {response.available && response.candidates.length > 0 && (
                <Button
                  onClick={() => createMutation.mutate()}
                  disabled={kept.size === 0 || createMutation.isPending}
                >
                  {createMutation.isPending && (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  )}
                  Create {kept.size} rule{kept.size === 1 ? "" : "s"} as Staging
                </Button>
              )}
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}


// Full-page license detail body (revamp Phase 5 — moved out of the pop-up).
// Renders the summary, the hierarchical applicable-regulations table, AI
// extract + schedule-all actions, and delete. Used by LicenseDetailPage.
export function LicenseDetailBody({
  license,
  isAdmin,
  onChanged,
}: {
  license: License;
  isAdmin: boolean;
  onChanged: () => void;
}) {
  const [aiOpen, setAiOpen] = useState(false);
  const [ruleSearch, setRuleSearch] = useState("");
  const detailQueryClient = useQueryClient();

  const rulesQuery = useQuery({
    queryKey: ["license-rules", license.id],
    queryFn: () =>
      api.get<ApplicableRulesResponse>(
        `/api/licenses/${license.id}/applicable-rules`,
      ),
  });

  // Auto-schedule: every Production filing in this jurisdiction lands on the
  // calendar automatically when the license is opened. Idempotent on the
  // server (skips anything already scheduled), so it's safe to fire on mount.
  const autoSchedule = useMutation({
    mutationFn: () =>
      api.post<{ scheduled: number }>(`/api/licenses/${license.id}/schedule-all`),
    onSuccess: (r) => {
      if (r.scheduled > 0) {
        rulesQuery.refetch();
        detailQueryClient.invalidateQueries({ queryKey: ["calendar"] });
        detailQueryClient.invalidateQueries({ queryKey: ["obligations"] });
        detailQueryClient.invalidateQueries({ queryKey: ["dashboard"] });
      }
    },
  });
  useEffect(() => {
    if (isAdmin) autoSchedule.mutate();
    // Fire once per license open; autoSchedule identity is stable enough.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [license.id, isAdmin]);

  const detailNavigate = useNavigate();
  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/api/licenses/${license.id}`),
    onSuccess: () => {
      onChanged();
      // Jump back to the Licenses list — the detail we were on is gone.
      detailNavigate("/licenses");
    },
  });


  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    name: "",
    license_type: "",
    authority: "",
    jurisdiction_code: "",
    license_number: "",
    issue_date: "",
    expiry_date: "",
    notes: "",
  });
  const openEdit = () => {
    setForm({
      name: license.name ?? "",
      license_type: license.license_type ?? "",
      authority: license.authority ?? "",
      jurisdiction_code: license.jurisdiction_code ?? "",
      license_number: license.license_number ?? "",
      issue_date: license.issue_date ?? "",
      expiry_date: license.expiry_date ?? "",
      notes: license.notes ?? "",
    });
    setEditing(true);
  };
  const editMutation = useMutation({
    mutationFn: () =>
      api.patch(`/api/licenses/${license.id}`, {
        name: form.name.trim(),
        license_type: form.license_type.trim(),
        authority: form.authority.trim(),
        jurisdiction_code: form.jurisdiction_code.trim().toLowerCase(),
        license_number: form.license_number.trim() || null,
        issue_date: form.issue_date || null,
        expiry_date: form.expiry_date || null,
        notes: form.notes.trim() || null,
      }),
    onSuccess: () => {
      onChanged();
      detailQueryClient.invalidateQueries({ queryKey: ["licenses"] });
      setEditing(false);
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });
  const fld = (k: keyof typeof form) => ({
    value: form[k],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [k]: e.target.value })),
  });

  return (
    <Card>
      <CardContent className="p-6">
        <div className="space-y-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <FileBadge className="h-5 w-5 text-aspora-600" />
                {license.name}
              </h2>
              <div className="text-sm text-muted-foreground">
                {license.license_type || "License"} · {license.authority}
              </div>
            </div>
            {isAdmin && (
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={openEdit}>
                  <Pencil className="h-4 w-4" />
                  Edit
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:text-destructive hover:bg-destructive/10"
                  onClick={() => {
                    if (
                      confirm(
                        `Delete license "${license.name}"? This also removes its uploaded file.`,
                      )
                    ) {
                      deleteMutation.mutate();
                    }
                  }}
                  disabled={deleteMutation.isPending}
                >
                  {deleteMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                  Delete
                </Button>
              </div>
            )}
          </div>

          {editing && (
            <div className="rounded-lg border border-aspora-300 bg-aspora-50/30 p-4 space-y-3">
              <div className="text-sm font-semibold">Edit license</div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label="Name"><Input {...fld("name")} /></Field>
                <Field label="License type"><Input {...fld("license_type")} /></Field>
                <Field label="Authority"><Input {...fld("authority")} /></Field>
                <Field label="Jurisdiction code"><Input {...fld("jurisdiction_code")} placeholder="uae / uk / us…" /></Field>
                <Field label="License number"><Input {...fld("license_number")} /></Field>
                <Field label="Issue date"><Input type="date" {...fld("issue_date")} /></Field>
                <Field label="Expiry date"><Input type="date" {...fld("expiry_date")} /></Field>
                <Field label="Notes"><Input {...fld("notes")} /></Field>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={() => editMutation.mutate()}
                  disabled={editMutation.isPending}
                >
                  {editMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Save
                </Button>
              </div>
            </div>
          )}

          <div>
              {/* Summary grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <Stat label="Entity" value={license.entity_name} />
                <Stat
                  label="Jurisdiction"
                  value={
                    <div className="flex items-center gap-1">
                      <JurisdictionBadge code={license.jurisdiction_code} />
                    </div>
                  }
                />
                <Stat
                  label="License No."
                  value={
                    <span className="font-mono">
                      {license.license_number ?? "—"}
                    </span>
                  }
                />
                <Stat
                  label="Expiry"
                  value={
                    <div>
                      <Badge variant={expiryBadgeVariant(license.expiry_status)}>
                        {expiryLabel(license)}
                      </Badge>
                      {license.expiry_date && (
                        <div className="text-[11px] text-muted-foreground mt-0.5 inline-flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          {fmtDate(license.expiry_date)}
                        </div>
                      )}
                    </div>
                  }
                />
                {license.issue_date && (
                  <Stat label="Issued" value={fmtDate(license.issue_date)} />
                )}
                {license.has_file && (
                  <Stat
                    label="File"
                    value={
                      <a
                        href={`/api/licenses/${license.id}/download`}
                        className="text-aspora-600 hover:underline inline-flex items-center gap-1 text-xs"
                      >
                        <Download className="h-3 w-3" />
                        {license.filename ?? "Download"}
                      </a>
                    }
                  />
                )}
              </div>

              {license.notes && (
                <div className="rounded-lg border border-border bg-secondary/30 px-3 py-2 text-sm">
                  {license.notes}
                </div>
              )}

              {/* Applicable rules */}
              <div>
                <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
                  <div className="text-sm font-semibold">
                    Applicable regulations
                  </div>
                  <div className="flex items-center gap-2">
                    {isAdmin && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setAiOpen(true)}
                        title={
                          license.has_file
                            ? "Read the uploaded license with Claude and find the filings it triggers"
                            : "No PDF needed — Claude finds the finance filings this license type owes, ready to review and add"
                        }
                      >
                        <Sparkles className="h-3.5 w-3.5" />
                        Find Regulations
                      </Button>
                    )}
                  </div>
                </div>

                {rulesQuery.isLoading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <Skeleton key={i} className="h-14 w-full" />
                    ))}
                  </div>
                ) : !rulesQuery.data ? null : rulesQuery.data.direct.length === 0 ? null : (
                  <div className="space-y-4 max-h-[480px] overflow-y-auto pr-1 scrollbar-thin">
                    <TrackingCounts counts={rulesQuery.data.counts} />
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                      <Input
                        value={ruleSearch}
                        onChange={(e) => setRuleSearch(e.target.value)}
                        placeholder="Search filings by name, authority, category…"
                        className="pl-8 h-9 text-sm"
                      />
                    </div>
                    {(() => {
                      const q = ruleSearch.trim().toLowerCase();
                      const direct = q
                        ? rulesQuery.data.direct.filter((r) =>
                            `${r.form_name} ${r.name} ${r.plain_description ?? ""} ${r.authority} ${r.category} ${r.area} ${r.frequency} ${r.responsible_function ?? ""}`
                              .toLowerCase()
                              .includes(q),
                          )
                        : rulesQuery.data.direct;
                      return (
                        <RegulationsTable
                          items={direct}
                          licenseId={license.id}
                          isAdmin={isAdmin}
                          onScheduled={() => rulesQuery.refetch()}
                        />
                      );
                    })()}
                  </div>
                )}
              </div>

              {deleteMutation.error && (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>{(deleteMutation.error as Error).message}</div>
                </div>
              )}
            </div>

            <AIExtractDialog
              license={license}
              open={aiOpen}
              onOpenChange={setAiOpen}
              existingForms={[
                ...(rulesQuery.data?.direct ?? []),
                ...(rulesQuery.data?.entity_other ?? []),
              ].flatMap((r) => [r.form_name, r.name].filter(Boolean) as string[])}
              onCreated={() => {
                onChanged();
              }}
            />

        </div>
      </CardContent>
    </Card>
  );
}


function Stat({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5">{value}</div>
    </div>
  );
}

function TrackingCounts({ counts }: { counts: Record<string, number> }) {
  const items: { key: string; label: string; tone: string }[] = [
    { key: "total", label: "Applicable rules", tone: "bg-secondary/60 text-foreground" },
    { key: "not_scheduled", label: "No deadline scheduled", tone: "bg-slate-100 text-slate-700" },
    { key: "unassigned", label: "Unassigned", tone: "bg-amber-100 text-amber-800" },
    { key: "not_started", label: "Not started", tone: "bg-slate-100 text-slate-700" },
    { key: "in_progress", label: "In progress", tone: "bg-blue-100 text-blue-700" },
    { key: "pending_review", label: "Pending review", tone: "bg-purple-100 text-purple-700" },
  ];
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      {items.map((it) => {
        const n = counts[it.key] ?? 0;
        if (it.key !== "total" && n === 0) return null;
        return (
          <span
            key={it.key}
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 ${it.tone}`}
          >
            <span className="font-semibold tabular-nums">{n}</span>
            <span>{it.label}</span>
          </span>
        );
      })}
    </div>
  );
}

function statusBadgeVariant(
  status: string | null,
): "completed" | "progress" | "review" | "neutral" | "overdue" {
  if (!status) return "neutral";
  if (status === "completed") return "completed";
  if (status === "in_progress") return "progress";
  if (status === "pending_review") return "review";
  return "neutral";
}

function statusLabel(status: string | null): string {
  if (!status) return "Not scheduled";
  return status.replace(/_/g, " ");
}

// Hierarchical, per-column filterable regulations table (revamp Phase 2/3).
// Columns: Function · Regulator · Category · Obligation (plain English) ·
// Frequency · Due · Mandatory/Conditional. Every column except the obligation
// text gets a dropdown filter.
function RegulationsTable({
  items,
  licenseId,
  isAdmin,
  onScheduled,
}: {
  items: LicenseRuleHit[];
  licenseId: number;
  isAdmin: boolean;
  onScheduled: () => void;
}) {
  const [fn, setFn] = useState("");
  const [reg, setReg] = useState("");
  const [cat, setCat] = useState("");
  const [freq, setFreq] = useState("");
  const [appl, setAppl] = useState("");

  const uniq = (vals: (string | null | undefined)[]) =>
    Array.from(new Set(vals.filter((v): v is string => !!v))).sort((a, b) =>
      a.localeCompare(b),
    );
  const fnOpts = uniq(items.map((r) => r.responsible_function));
  const regOpts = uniq(items.map((r) => r.authority));
  const catOpts = uniq(items.map((r) => r.category));
  const freqOpts = uniq(items.map((r) => r.frequency));

  const rows = items.filter(
    (r) =>
      (!fn || r.responsible_function === fn) &&
      (!reg || r.authority === reg) &&
      (!cat || r.category === cat) &&
      (!freq || r.frequency === freq) &&
      (!appl ||
        (appl === "Mandatory"
          ? r.applicability === "Mandatory"
          : r.applicability !== "Mandatory")),
  );


  const Sel = ({
    value,
    onChange,
    opts,
    label,
  }: {
    value: string;
    onChange: (v: string) => void;
    opts: string[];
    label: string;
  }) => (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full bg-transparent text-[11px] font-normal normal-case text-foreground border border-border rounded px-1 py-0.5 mt-1"
    >
      <option value="">All {label}</option>
      {opts.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );

  return (
    <div className="space-y-2">
      {isAdmin && (
        <div className="text-xs text-muted-foreground">
          Showing Finance filings only. These are auto-scheduled onto the
          calendar — every Production filing in this jurisdiction appears
          automatically when you open the license.
        </div>
      )}
      <div className="rounded-lg border border-border overflow-x-auto">
      <table className="w-full text-sm min-w-[920px]">
        <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground align-top">
          <tr>
            <th className="px-3 py-2 text-left font-medium w-[110px]">
              Function
              <div className="mt-1 text-xs font-normal normal-case text-foreground">
                Finance
              </div>
            </th>
            <th className="px-3 py-2 text-left font-medium w-[150px]">
              Regulator
              <Sel value={reg} onChange={setReg} opts={regOpts} label="" />
            </th>
            <th className="px-3 py-2 text-left font-medium w-[140px]">
              Category
              <Sel value={cat} onChange={setCat} opts={catOpts} label="" />
            </th>
            <th className="px-3 py-2 text-left font-medium">Obligation</th>
            <th className="px-3 py-2 text-left font-medium w-[120px]">
              Frequency
              <Sel value={freq} onChange={setFreq} opts={freqOpts} label="" />
            </th>
            <th className="px-3 py-2 text-left font-medium w-[130px]">Due</th>
            <th className="px-3 py-2 text-left font-medium w-[120px]">
              Status
              <Sel
                value={appl}
                onChange={setAppl}
                opts={["Mandatory", "Conditional"]}
                label=""
              />
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={7} className="px-3 py-6 text-center text-sm text-muted-foreground">
                No filings match these filters.
              </td>
            </tr>
          ) : (
            rows.map((r) => (
              <tr
                key={r.id}
                className={cn(
                  "hover:bg-secondary/20",
                  r.next_obligation_id && "cursor-pointer",
                )}
                onClick={() => {
                  if (r.next_obligation_id)
                    window.location.href = `/obligations/${r.next_obligation_id}`;
                }}
              >
                <td className="px-3 py-2 align-top">
                  <Badge variant="neutral">{r.responsible_function || "—"}</Badge>
                </td>
                <td className="px-3 py-2 align-top text-xs text-muted-foreground">
                  {r.authority}
                </td>
                <td className="px-3 py-2 align-top text-xs">
                  <div>{r.category}</div>
                  {r.tax_type && r.tax_type !== "Not a Tax" && (
                    <div className="text-[10px] text-muted-foreground">{r.tax_type}</div>
                  )}
                </td>
                <td className="px-3 py-2 align-top">
                  <div className="font-medium">{cleanFilingName(r.name || r.form_name)}</div>
                  {r.plain_description && (
                    <div className="text-[11px] text-muted-foreground">
                      {r.plain_description}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 align-top text-xs">{r.frequency}</td>
                <td className="px-3 py-2 align-top text-xs">
                  {r.next_due_date ? (
                    <div>
                      {r.next_due_date}
                      <div className="text-[10px] text-muted-foreground">
                        {r.next_status ? statusLabel(r.next_status) : ""}
                      </div>
                    </div>
                  ) : r.projected_due_date ? (
                    <div>
                      {r.projected_due_date}
                      <div className="text-[10px] text-muted-foreground">
                        projected
                      </div>
                    </div>
                  ) : (
                    <span className="text-muted-foreground">Not scheduled</span>
                  )}
                </td>
                <td className="px-3 py-2 align-top">
                  <Badge variant={r.applicability === "Mandatory" ? "overdue" : "alert"}>
                    {r.applicability === "Mandatory" ? "Mandatory" : "Conditional"}
                  </Badge>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
      </div>
    </div>
  );
}

function RuleGroup({
  title,
  subtitle,
  items,
  tone,
  licenseId,
  isAdmin,
  onScheduled,
}: {
  title: string;
  subtitle: string;
  items: LicenseRuleHit[];
  tone?: "mandatory" | "conditional";
  licenseId: number;
  isAdmin: boolean;
  onScheduled: () => void;
}) {
  const headingClass =
    tone === "mandatory"
      ? "text-red-700"
      : tone === "conditional"
        ? "text-amber-700"
        : "text-muted-foreground";
  return (
    <div>
      <div className={`text-xs uppercase tracking-wider font-semibold ${headingClass}`}>
        {title}
      </div>
      <div className="text-[11px] text-muted-foreground mb-2">{subtitle}</div>
      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Filing</th>
              <th className="px-3 py-2 text-left font-medium">Status</th>
              <th className="px-3 py-2 text-left font-medium">Assignee</th>
              <th className="px-3 py-2 text-left font-medium">Next due</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map((r) => {
              const assignee = r.next_assignee;
              const daysOut = r.days_to_next;
              return (
                <tr
                  key={r.id}
                  className="hover:bg-secondary/20 cursor-pointer"
                  onClick={(e) => {
                    if (r.next_obligation_id) {
                      e.stopPropagation();
                      window.location.href = `/obligations/${r.next_obligation_id}`;
                    }
                  }}
                >
                  <td className="px-3 py-2 align-top">
                    <div className="font-medium text-sm">{r.form_name}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {r.authority} · {r.category}
                      {r.area ? ` · ${r.area}` : ""}
                    </div>
                    <div className="flex flex-wrap gap-1 mt-1 items-center">
                      <Badge variant="neutral">{r.frequency}</Badge>
                      <Badge
                        variant={
                          r.applicability === "Mandatory" ? "overdue" : "alert"
                        }
                        title={
                          r.applicability === "Mandatory"
                            ? "You MUST file this. Non-compliance = regulatory breach."
                            : "File only if your business triggers the conditions (turnover thresholds, sector activity, etc.)."
                        }
                      >
                        {r.applicability === "Mandatory" ? "Mandatory" : "Optional"}
                      </Badge>
                      {r.match_reason && (
                        <span
                          className="text-[11px] text-muted-foreground italic"
                          title="How we matched this rule to the license — either license keywords (authority / type) or because the rule is registered against this entity."
                        >
                          {r.match_reason}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 align-top">
                    <Badge variant={statusBadgeVariant(r.next_status)}>
                      {statusLabel(r.next_status)}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 align-top text-sm">
                    {assignee ? (
                      <div>
                        <div className="text-sm">
                          {assignee.full_name || assignee.email}
                        </div>
                        {assignee.full_name && (
                          <div className="text-[11px] text-muted-foreground">
                            {assignee.email}
                          </div>
                        )}
                      </div>
                    ) : r.next_obligation_id ? (
                      <span className="text-xs text-amber-700">Unassigned</span>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 align-top text-sm">
                    {r.next_due_date ? (
                      <div>
                        <div>{r.next_due_date}</div>
                        <div className="text-[11px] text-muted-foreground">
                          {daysOut !== null && daysOut !== undefined
                            ? `in ${daysOut} day${daysOut === 1 ? "" : "s"}`
                            : ""}
                        </div>
                      </div>
                    ) : r.projected_due_date ? (
                      <div>
                        <div>{r.projected_due_date}</div>
                        <div className="text-[11px] text-muted-foreground">
                          projected
                        </div>
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 align-top text-right">
                    {r.next_obligation_id ? (
                      <ExternalLink className="h-3 w-3 text-muted-foreground inline" />
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
