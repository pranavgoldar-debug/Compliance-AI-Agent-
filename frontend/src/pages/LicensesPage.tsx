// Licenses page — admin uploads a license, sees its details, and gets a
// list of compliance rules that apply (matched on jurisdiction + tokens
// from the license's authority/type/name).
import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  Download,
  ExternalLink,
  FileBadge,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
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
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { fmtDate, JURISDICTIONS } from "@/lib/format";
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

  const [q, setQ] = useState("");
  const [jurisdiction, setJurisdiction] = useState<string>("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [activeLicense, setActiveLicense] = useState<License | null>(null);
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
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
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
                  onClick={() => setActiveLicense(lic)}
                >
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
      <LicenseDetailDialog
        license={activeLicense}
        onClose={() => setActiveLicense(null)}
        isAdmin={isAdmin}
        onChanged={() => {
          invalidate();
          setActiveLicense(null);
        }}
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

  // Grok reads the uploaded PDF and pre-fills the form fields below.
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
      setAiNote("Grok pre-filled these from the PDF — review and edit before saving.");
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
    file !== null &&
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

          <Field label="License file (PDF) *">
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
                  ? "Grok is reading the PDF…"
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
  category: string;
  area: string;
  form_name: string;
  authority: string;
  frequency: string;
  due_date_rule: string;
  payment_rule: string | null;
  applicability: string;
  applicability_note: string | null;
}

interface AIExtractResponse {
  available: boolean;
  license_id: number;
  jurisdiction_hint: string | null;
  extracted_chars: number;
  candidates: CandidateRule[];
  notes: string | null;
}

function AIExtractDialog({
  license,
  open,
  onOpenChange,
  onCreated,
}: {
  license: License;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: () => void;
}) {
  const [response, setResponse] = useState<AIExtractResponse | null>(null);
  const [kept, setKept] = useState<Set<number>>(new Set());

  const extractMutation = useMutation({
    mutationFn: () =>
      api.post<AIExtractResponse>(`/api/licenses/${license.id}/ai-extract`),
    onSuccess: (data) => {
      setResponse(data);
      // Default to all candidates ticked.
      setKept(new Set(data.candidates.map((_, i) => i)));
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

  function reset() {
    setResponse(null);
    setKept(new Set());
    extractMutation.reset();
    createMutation.reset();
  }

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
            <Sparkles className="h-5 w-5 text-aspora-600" />
            Extract obligations from this license
          </DialogTitle>
          <DialogDescription>
            Grok reads the uploaded license file and pulls out every ongoing
            compliance obligation the licensee owes. You review, tick the ones
            to keep, and they're created as Staging rules attached to{" "}
            <strong>{license.entity_name}</strong>.
          </DialogDescription>
        </DialogHeader>

        <div className="p-6 space-y-4">
          {!response ? (
            <div className="text-sm text-muted-foreground space-y-3">
              <p>
                Hit Extract — we'll read{" "}
                <strong>{license.filename || "your license file"}</strong> and
                ask Grok what filings it triggers. Takes ~20–30 seconds.
              </p>
              {extractMutation.error && (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-destructive">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>{(extractMutation.error as Error).message}</div>
                </div>
              )}
            </div>
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
                  "Grok didn't find any recurring filings in this document. Either the file doesn't list ongoing obligations or the text didn't extract cleanly."}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="text-sm">
                Found <strong>{response.candidates.length}</strong> candidate{" "}
                obligation{response.candidates.length === 1 ? "" : "s"}. Tick
                the ones to create — they'll land in{" "}
                <strong>Compliance Rules → Staging</strong> for an admin to
                approve.
              </div>
              {response.notes && (
                <div className="rounded-lg border border-border bg-secondary/30 px-3 py-2 text-xs text-muted-foreground">
                  {response.notes}
                </div>
              )}
              <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1 scrollbar-thin">
                {response.candidates.map((r, i) => {
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
                        <div className="font-medium">{r.form_name}</div>
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {r.authority} · {r.category} · {r.frequency}
                        </div>
                        <div className="text-xs text-muted-foreground mt-1 italic">
                          {r.due_date_rule}
                        </div>
                        {r.payment_rule && (
                          <div className="text-xs text-muted-foreground mt-0.5">
                            <strong>Payment:</strong> {r.payment_rule}
                          </div>
                        )}
                        {r.applicability_note && (
                          <div className="text-[11px] text-muted-foreground mt-0.5">
                            {r.applicability_note}
                          </div>
                        )}
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

        <DialogFooter>
          {!response ? (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button
                onClick={() => extractMutation.mutate()}
                disabled={extractMutation.isPending}
              >
                {extractMutation.isPending && (
                  <Loader2 className="h-4 w-4 animate-spin" />
                )}
                <Sparkles className="h-4 w-4" />
                Extract
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={reset}>
                Re-extract
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
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function LicenseDetailDialog({
  license,
  onClose,
  isAdmin,
  onChanged,
}: {
  license: License | null;
  onClose: () => void;
  isAdmin: boolean;
  onChanged: () => void;
}) {
  const open = license !== null;
  const [aiOpen, setAiOpen] = useState(false);

  const rulesQuery = useQuery({
    queryKey: ["license-rules", license?.id],
    queryFn: () =>
      api.get<ApplicableRulesResponse>(
        `/api/licenses/${license!.id}/applicable-rules`,
      ),
    enabled: open,
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/api/licenses/${license!.id}`),
    onSuccess: () => onChanged(),
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="xl">
        {license && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FileBadge className="h-5 w-5 text-aspora-600" />
                {license.name}
              </DialogTitle>
              <DialogDescription>
                {license.license_type || "License"} · {license.authority}
              </DialogDescription>
            </DialogHeader>

            <div className="p-6 space-y-5">
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
                    {rulesQuery.data && (
                      <div className="text-xs text-muted-foreground">
                        {rulesQuery.data.direct.length} applicable to this license
                      </div>
                    )}
                    {isAdmin && license.has_file ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setAiOpen(true)}
                        title="Read the uploaded license with Grok and surface obligations"
                      >
                        <Sparkles className="h-3.5 w-3.5" />
                        Extract with AI
                      </Button>
                    ) : isAdmin ? (
                      <span
                        className="text-[11px] text-muted-foreground italic"
                        title="Re-open this license, upload the PDF, and Extract with AI will appear here."
                      >
                        Upload a file to enable AI extract
                      </span>
                    ) : null}
                  </div>
                </div>

                {rulesQuery.isLoading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <Skeleton key={i} className="h-14 w-full" />
                    ))}
                  </div>
                ) : !rulesQuery.data ? null : rulesQuery.data.direct.length === 0 ? (
                  <div className="rounded-lg border border-border bg-secondary/30 px-3 py-3 text-sm text-muted-foreground">
                    No rules matched this license in the catalogue yet. Try
                    sharpening the authority or license type fields, or add a
                    rule with a matching authority.
                  </div>
                ) : (
                  <div className="space-y-4 max-h-[480px] overflow-y-auto pr-1 scrollbar-thin">
                    <TrackingCounts counts={rulesQuery.data.counts} />
                    {(() => {
                      const direct = rulesQuery.data.direct;
                      const mandatory = direct.filter(
                        (r) => r.applicability === "Mandatory",
                      );
                      const optional = direct.filter(
                        (r) => r.applicability !== "Mandatory",
                      );
                      return (
                        <>
                          {mandatory.length > 0 && (
                            <RuleGroup
                              title={`Mandatory · ${mandatory.length}`}
                              subtitle="You MUST file these — non-compliance is a regulatory breach."
                              items={mandatory}
                              tone="mandatory"
                              licenseId={license.id}
                              isAdmin={isAdmin}
                              onScheduled={() => rulesQuery.refetch()}
                            />
                          )}
                          {optional.length > 0 && (
                            <RuleGroup
                              title={`Conditional / Sector-specific · ${optional.length}`}
                              subtitle="File these only if your business triggers the conditions (turnover thresholds, sector activity, etc.)."
                              items={optional}
                              tone="conditional"
                              licenseId={license.id}
                              isAdmin={isAdmin}
                              onScheduled={() => rulesQuery.refetch()}
                            />
                          )}
                        </>
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
              onCreated={() => {
                onChanged();
              }}
            />

            <DialogFooter>
              {isAdmin && (
                <Button
                  variant="outline"
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
              )}
              <Button onClick={onClose}>Close</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ScheduleRuleButton({
  licenseId,
  ruleId,
  onScheduled,
}: {
  licenseId: number;
  ruleId: number;
  onScheduled: () => void;
}) {
  const mutation = useMutation({
    mutationFn: () =>
      api.post<{ obligation_id: number; due_date: string }>(
        `/api/licenses/${licenseId}/schedule-rule`,
        { rule_id: ruleId },
      ),
    onSuccess: (result) => {
      onScheduled();
      // Drop the user straight into the new obligation — they wanted to
      // schedule it because they're about to assign / work on it.
      window.location.href = `/obligations/${result.obligation_id}`;
    },
    onError: (e) => {
      // Without this, a 404 (server not restarted with the new endpoint) or
      // 409 (duplicate) silently fails and the button just stops spinning.
      const msg = e instanceof Error ? e.message : String(e);
      window.alert(
        `Couldn't schedule this rule:\n\n${msg}\n\n` +
          `If you see "Not Found", restart the backend so the new endpoint is loaded.`,
      );
    },
  });
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        e.preventDefault();
        mutation.mutate();
      }}
      disabled={mutation.isPending}
      className="inline-flex items-center gap-1 rounded-md border border-aspora-300 bg-aspora-50 px-2 py-1 text-[11px] font-medium text-aspora-800 hover:bg-aspora-100 disabled:opacity-50"
      title="Create a single obligation for this rule + entity. Default due date is based on the rule's frequency; you can change it after."
    >
      {mutation.isPending ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : (
        <Plus className="h-3 w-3" />
      )}
      Schedule
    </button>
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
                    ) : (
                      <span className="text-xs text-muted-foreground italic">
                        {r.due_date_rule}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 align-top text-right">
                    {r.next_obligation_id ? (
                      <ExternalLink className="h-3 w-3 text-muted-foreground inline" />
                    ) : isAdmin ? (
                      <ScheduleRuleButton
                        licenseId={licenseId}
                        ruleId={r.id}
                        onScheduled={onScheduled}
                      />
                    ) : null}
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
