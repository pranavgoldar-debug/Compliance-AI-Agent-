// Shared document list/upload UI. Used inside:
//   - EntityDetailPage Documents tab (scope = entity)
//   - ObligationDetail drawer (scope = obligation)
//   - DocumentsPage right pane (scope = entity / category / all)
//
// Renders the file list (rows or grid), the upload dropzone, and the rename/
// delete/download row actions. The owning page wires up scope + query keys.

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Download,
  FileText,
  Loader2,
  MoreHorizontal,
  Pencil,
  Sparkles,
  Trash2,
  Upload,
  File as FileIcon,
  FileImage,
  FileSpreadsheet,
} from "lucide-react";
import { DocumentExtractDialog } from "@/components/DocumentExtractDialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAiAvailable } from "@/lib/ai";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { EmptyState } from "@/components/EmptyState";
import { api, ApiError } from "@/lib/api";
import { fmtRelative, userInitials } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DocumentCategory, DocumentOut } from "@/types/api";


export type DocumentScope =
  | { kind: "entity"; entityId: number }
  | { kind: "obligation"; obligationId: number; entityId: number }
  | { kind: "all" }
  | { kind: "category"; category: DocumentCategory };


interface Props {
  scope: DocumentScope;
  title?: string;
  hint?: string;
  layout?: "rows" | "grid";
  showEntityColumn?: boolean;
  defaultCategory?: DocumentCategory;
}


/** Cheap icon picker by extension. */
function iconFor(name: string): React.ComponentType<{ className?: string }> {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (["pdf"].includes(ext)) return FileText;
  if (["xlsx", "xls", "csv"].includes(ext)) return FileSpreadsheet;
  if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext)) return FileImage;
  return FileIcon;
}


function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}


function buildQueryKey(scope: DocumentScope) {
  switch (scope.kind) {
    case "entity":
      return ["documents", "entity", scope.entityId];
    case "obligation":
      return ["documents", "obligation", scope.obligationId];
    case "category":
      return ["documents", "category", scope.category];
    default:
      return ["documents", "all"];
  }
}


function buildListPath(scope: DocumentScope): string {
  const params = new URLSearchParams();
  if (scope.kind === "entity") params.set("entity_id", String(scope.entityId));
  if (scope.kind === "obligation") params.set("obligation_id", String(scope.obligationId));
  if (scope.kind === "category") params.set("category", scope.category);
  return `/api/documents${params.toString() ? "?" + params : ""}`;
}


export function DocumentList({
  scope,
  title,
  hint,
  layout = "rows",
  showEntityColumn = false,
  defaultCategory,
}: Props) {
  const queryClient = useQueryClient();
  const queryKey = buildQueryKey(scope);

  const { data: documents = [], isLoading } = useQuery({
    queryKey,
    queryFn: () => api.get<DocumentOut[]>(buildListPath(scope)),
  });

  // ----------------------------------------------------------------
  // Upload
  // ----------------------------------------------------------------
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      if (defaultCategory) form.append("category", defaultCategory);

      if (scope.kind === "obligation") {
        return api.upload<DocumentOut>(
          `/api/obligations/${scope.obligationId}/documents`,
          form,
        );
      }
      if (scope.kind === "entity") {
        return api.upload<DocumentOut>(
          `/api/entities/${scope.entityId}/documents`,
          form,
        );
      }
      throw new Error("This view doesn't support uploads — open an entity or obligation first.");
    },
    onSuccess: () => {
      setUploadError(null);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (e) => setUploadError(e instanceof ApiError ? e.message : String(e)),
  });

  const canUpload = scope.kind === "entity" || scope.kind === "obligation";

  function pickFiles() {
    fileInputRef.current?.click();
  }

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    if (!canUpload) {
      setUploadError("Open an entity or obligation to upload here.");
      return;
    }
    // Upload sequentially so progress feels predictable.
    Array.from(files).forEach((f) => uploadMutation.mutate(f));
  }

  // ----------------------------------------------------------------
  // Render
  // ----------------------------------------------------------------
  return (
    <div className="space-y-3">
      {(title || canUpload) && (
        <div className="flex items-center justify-between gap-3">
          <div>
            {title && <h3 className="text-sm font-semibold">{title}</h3>}
            {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
          </div>
          {canUpload && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => handleFiles(e.target.files)}
              />
              <Button size="sm" onClick={pickFiles} disabled={uploadMutation.isPending}>
                {uploadMutation.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Upload className="h-3.5 w-3.5" />
                )}
                Upload
              </Button>
            </>
          )}
        </div>
      )}

      {/* Dropzone — also serves as the empty state when there are no files */}
      {canUpload && documents.length === 0 && !isLoading ? (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            handleFiles(e.dataTransfer.files);
          }}
          className={cn(
            "rounded-xl border border-dashed border-border bg-secondary/30 p-8 text-center transition-colors",
            dragOver && "bg-aspora-50 border-aspora-300",
          )}
        >
          <EmptyState
            icon={<Upload className="h-5 w-5" />}
            title="No documents yet"
            description="Drag-and-drop PDFs, receipts, or screenshots here. Max 25 MB per file."
            action={
              <Button variant="outline" onClick={pickFiles}>
                <Upload className="h-3.5 w-3.5" />
                Choose files
              </Button>
            }
          />
        </div>
      ) : null}

      {uploadError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {uploadError}
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          <div className="h-10 bg-secondary/50 animate-pulse rounded" />
          <div className="h-10 bg-secondary/50 animate-pulse rounded" />
        </div>
      ) : documents.length > 0 ? (
        layout === "grid" ? (
          <GridList
            documents={documents}
            queryKey={queryKey}
            showEntityColumn={showEntityColumn}
            obligationId={scope.kind === "obligation" ? scope.obligationId : null}
          />
        ) : (
          <RowList
            documents={documents}
            queryKey={queryKey}
            showEntityColumn={showEntityColumn}
            obligationId={scope.kind === "obligation" ? scope.obligationId : null}
          />
        )
      ) : !canUpload ? (
        <EmptyState
          icon={<FileText className="h-5 w-5" />}
          title="No documents match"
          description="Try changing the folder or jurisdiction filter."
        />
      ) : null}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Row list (default)
// ---------------------------------------------------------------------------
function RowList({
  documents,
  queryKey,
  showEntityColumn,
  obligationId,
}: {
  documents: DocumentOut[];
  queryKey: unknown[];
  showEntityColumn: boolean;
  obligationId: number | null;
}) {
  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[720px]">
          <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 text-left font-medium">Name</th>
              {showEntityColumn && (
                <th className="px-3 py-2.5 text-left font-medium">Entity</th>
              )}
              <th className="px-3 py-2.5 text-left font-medium">Linked to</th>
              <th className="px-3 py-2.5 text-left font-medium">Category</th>
              <th className="px-3 py-2.5 text-left font-medium">Uploaded</th>
              <th className="px-3 py-2.5 text-right font-medium">Size</th>
              <th className="px-3 py-2.5 w-20" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {documents.map((d) => (
              <DocumentRow
                key={d.id}
                doc={d}
                queryKey={queryKey}
                showEntityColumn={showEntityColumn}
                obligationId={obligationId}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


function DocumentRow({
  doc,
  queryKey,
  showEntityColumn,
  obligationId,
}: {
  doc: DocumentOut;
  queryKey: unknown[];
  showEntityColumn: boolean;
  obligationId: number | null;
}) {
  const Icon = iconFor(doc.filename);
  return (
    <tr className="hover:bg-secondary/30">
      <td className="px-3 py-2.5">
        <a
          href={`/api/documents/${doc.id}/download`}
          className="inline-flex items-center gap-2 min-w-0 hover:text-aspora-700"
        >
          <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="font-medium truncate">{doc.filename}</span>
        </a>
      </td>
      {showEntityColumn && (
        <td className="px-3 py-2.5 text-muted-foreground truncate">{doc.entity_name || "—"}</td>
      )}
      <td className="px-3 py-2.5 text-muted-foreground">
        {doc.obligation_form_name ? (
          <Badge variant="default">{doc.obligation_form_name}</Badge>
        ) : (
          <span className="text-xs italic">Entity-level</span>
        )}
      </td>
      <td className="px-3 py-2.5">
        <Badge variant="neutral">{doc.category}</Badge>
      </td>
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-1.5 text-xs">
          {doc.uploaded_by && (
            <Avatar className="h-5 w-5">
              <AvatarFallback className="text-[9px]">
                {userInitials(doc.uploaded_by.full_name)}
              </AvatarFallback>
            </Avatar>
          )}
          <span className="text-muted-foreground">{fmtRelative(doc.created_at)}</span>
        </div>
      </td>
      <td className="px-3 py-2.5 text-right text-xs tabular-nums text-muted-foreground">
        {fmtSize(doc.size_bytes)}
      </td>
      <td className="px-3 py-2.5">
        <div className="flex items-center justify-end gap-0.5">
          {obligationId !== null && (
            <AutoFillButton doc={doc} obligationId={obligationId} />
          )}
          <DocumentRowMenu doc={doc} queryKey={queryKey} />
        </div>
      </td>
    </tr>
  );
}


function AutoFillButton({
  doc,
  obligationId,
}: {
  doc: DocumentOut;
  obligationId: number;
}) {
  const { available, tooltip } = useAiAvailable();
  const [open, setOpen] = useState(false);
  // Only useful for PDF/text files; gray out otherwise.
  const ext = (doc.filename.split(".").pop() || "").toLowerCase();
  const extractable = ext === "pdf" || ext === "txt" || ext === "csv" || ext === "json";

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={() => setOpen(true)}
            disabled={!available || !extractable}
            className={cn(
              "h-7 w-7 grid place-items-center rounded-md text-aspora-700",
              available && extractable
                ? "hover:bg-aspora-50"
                : "opacity-40 cursor-not-allowed",
            )}
            aria-label="Auto-fill obligation from this document"
          >
            <Sparkles className="h-3.5 w-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent>
          {!extractable
            ? "Auto-fill only supports PDF / text files."
            : available
              ? "Auto-fill filing fields from this document"
              : tooltip}
        </TooltipContent>
      </Tooltip>
      {open && (
        <DocumentExtractDialog
          doc={doc}
          obligationId={obligationId}
          open={open}
          onOpenChange={setOpen}
        />
      )}
    </>
  );
}


// ---------------------------------------------------------------------------
// Grid (used on the global documents page)
// ---------------------------------------------------------------------------
function GridList({
  documents,
  queryKey,
  showEntityColumn,
  obligationId,
}: {
  documents: DocumentOut[];
  queryKey: unknown[];
  showEntityColumn: boolean;
  obligationId: number | null;
}) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      {documents.map((d) => {
        const Icon = iconFor(d.filename);
        return (
          <div
            key={d.id}
            className="rounded-xl border border-border bg-card overflow-hidden flex flex-col"
          >
            <a
              href={`/api/documents/${d.id}/download`}
              className="aspect-[4/3] bg-secondary/40 grid place-items-center"
              title={d.filename}
            >
              <Icon className="h-10 w-10 text-muted-foreground" />
            </a>
            <div className="p-3 flex-1 flex flex-col gap-1.5">
              <div className="font-medium text-sm truncate" title={d.filename}>
                {d.filename}
              </div>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{fmtSize(d.size_bytes)}</span>
                <span>{fmtRelative(d.created_at)}</span>
              </div>
              <div className="flex items-center gap-1.5 flex-wrap mt-auto pt-1.5 border-t border-border">
                <Badge variant="neutral">{d.category}</Badge>
                {showEntityColumn && d.entity_name && (
                  <span className="text-[11px] text-muted-foreground truncate">{d.entity_name}</span>
                )}
                <div className="ml-auto flex items-center">
                  {obligationId !== null && (
                    <AutoFillButton doc={d} obligationId={obligationId} />
                  )}
                  <DocumentRowMenu doc={d} queryKey={queryKey} />
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Row action menu — Download / Rename / Delete
// ---------------------------------------------------------------------------
function DocumentRowMenu({ doc, queryKey }: { doc: DocumentOut; queryKey: unknown[] }) {
  const queryClient = useQueryClient();
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState(doc.filename);

  useEffect(() => setNewName(doc.filename), [doc.filename]);

  const renameMutation = useMutation({
    mutationFn: (filename: string) =>
      api.patch<DocumentOut>(`/api/documents/${doc.id}`, { filename }),
    onSuccess: () => {
      setRenaming(false);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete<void>(`/api/documents/${doc.id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey });
    },
  });

  if (renaming) {
    return (
      <div className="flex items-center gap-1">
        <input
          autoFocus
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") renameMutation.mutate(newName.trim());
            if (e.key === "Escape") setRenaming(false);
          }}
          className="h-7 rounded-md border border-input bg-background px-2 text-xs w-40"
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => renameMutation.mutate(newName.trim())}
          disabled={!newName.trim() || renameMutation.isPending}
        >
          Save
        </Button>
      </div>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="h-7 w-7 grid place-items-center rounded-md hover:bg-secondary text-muted-foreground">
          <MoreHorizontal className="h-3.5 w-3.5" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem asChild>
          <a href={`/api/documents/${doc.id}/download`} download>
            <Download className="h-3.5 w-3.5 mr-2" />
            Download
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setRenaming(true)}>
          <Pencil className="h-3.5 w-3.5 mr-2" />
          Rename
        </DropdownMenuItem>
        <DropdownMenuItem
          className="text-red-600"
          onClick={() => {
            if (window.confirm(`Delete "${doc.filename}"? This can't be undone.`)) {
              deleteMutation.mutate();
            }
          }}
        >
          <Trash2 className="h-3.5 w-3.5 mr-2" />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
