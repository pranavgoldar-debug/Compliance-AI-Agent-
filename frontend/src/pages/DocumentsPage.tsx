// Global Documents page — 2-pane Drive-like view.
// Left: folder tree by Entity → Category.
// Right: file list (or grid) for the current selection.

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/contexts/AuthContext";
import {
  ChevronDown,
  ChevronRight,
  FolderClosed,
  FolderOpen,
  FolderPlus,
  LayoutGrid,
  List,
  Search,
  Building2,
  FileStack,
  Loader2,
  Trash2,
} from "lucide-react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { PageHeader } from "@/components/PageHeader";
import { DocumentList } from "@/components/DocumentList";
import { DOCUMENT_CATEGORIES } from "@/types/api";
import { cn } from "@/lib/utils";
import type {
  DocumentCategory,
  DocumentOut,
  Entity,
} from "@/types/api";


type Selection =
  | { kind: "all" }
  | { kind: "entity"; entityId: number }
  | { kind: "entity-folder"; entityId: number; folder: string };


// Default folders every entity starts with (mirrors the backend).
const DEFAULT_FOLDERS = ["Filings", "Templates", "Incorporation Documents"];

// The folders to show for an entity: its saved folders (or defaults) plus any
// folder that already has documents.
function foldersFor(entity: Entity | undefined, counts: Map<string, number>): string[] {
  const base = entity?.document_folders?.length ? entity.document_folders : DEFAULT_FOLDERS;
  const set = new Set<string>([...base, ...counts.keys()]);
  return Array.from(set);
}

export function DocumentsPage() {
  const [selection, setSelection] = useState<Selection>({ kind: "all" });
  const [layout, setLayout] = useState<"rows" | "grid">("rows");
  const [q, setQ] = useState("");

  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const queryClient = useQueryClient();

  // Eager-loaded entity list — fuels the left tree.
  const { data: entities = [] } = useQuery({
    queryKey: ["entities"],
    queryFn: () => api.get<Entity[]>("/api/entities"),
  });

  // Counts per (entity, category) — one cheap query that the tree slices.
  const { data: allDocs = [] } = useQuery({
    queryKey: ["documents", "all"],
    queryFn: () => api.get<DocumentOut[]>("/api/documents"),
  });

  const countsByEntity = useMemo(() => {
    const m = new Map<number, Map<string, number>>();
    for (const d of allDocs) {
      if (!m.has(d.entity_id)) m.set(d.entity_id, new Map());
      const cm = m.get(d.entity_id)!;
      const f = d.folder || d.category;
      cm.set(f, (cm.get(f) ?? 0) + 1);
    }
    return m;
  }, [allDocs]);

  // Create a new folder on an entity (admin).
  const createFolder = useMutation({
    mutationFn: ({ entity, name }: { entity: Entity; name: string }) =>
      api.patch<Entity>(`/api/entities/${entity.id}`, {
        document_folders: Array.from(
          new Set([...(entity.document_folders?.length ? entity.document_folders : DEFAULT_FOLDERS), name]),
        ),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["entities"] }),
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });
  const promptNewFolder = (entity: Entity) => {
    const name = window.prompt("New folder name")?.trim();
    if (name) createFolder.mutate({ entity, name });
  };

  // Delete a folder (admin). Only removes the folder label from the entity;
  // refuses when the folder still holds documents so nothing is orphaned.
  const deleteFolder = useMutation({
    mutationFn: ({ entity, name }: { entity: Entity; name: string }) => {
      const current = entity.document_folders?.length
        ? entity.document_folders
        : DEFAULT_FOLDERS;
      return api.patch<Entity>(`/api/entities/${entity.id}`, {
        document_folders: current.filter((f) => f !== name),
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["entities"] }),
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });
  const confirmDeleteFolder = (entity: Entity, name: string, count: number) => {
    if (count > 0) {
      window.alert(
        `"${name}" still has ${count} document(s). Move or delete them first, then remove the folder.`,
      );
      return;
    }
    if (window.confirm(`Delete the empty folder "${name}"?`)) {
      deleteFolder.mutate({ entity, name });
    }
  };

  // Apply optional name filter to whatever the right pane is showing.
  // The pane uses its own React Query under the hood; we just pass the q
  // through to the same endpoint. For "all" we filter client-side because
  // we already have the list cached.
  const filteredAll = useMemo(() => {
    if (selection.kind !== "all") return allDocs;
    let arr = allDocs;
    if (q.trim()) {
      const n = q.trim().toLowerCase();
      arr = arr.filter((d) => d.filename.toLowerCase().includes(n));
    }
    return arr;
  }, [allDocs, q, selection]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Documents"
        description="Filings, certificates, and audit artifacts. Pick an entity in the sidebar to upload — files always live under one entity."
        actions={
          <div className="flex items-center gap-2">
          <div className="inline-flex rounded-lg border border-input overflow-hidden">
            <button
              onClick={() => setLayout("rows")}
              className={cn(
                "h-9 px-3 text-sm inline-flex items-center gap-1.5",
                layout === "rows" ? "bg-aspora-600 text-white" : "bg-background hover:bg-secondary",
              )}
            >
              <List className="h-3.5 w-3.5" />
              List
            </button>
            <button
              onClick={() => setLayout("grid")}
              className={cn(
                "h-9 px-3 text-sm inline-flex items-center gap-1.5 border-l border-input",
                layout === "grid" ? "bg-aspora-600 text-white" : "bg-background hover:bg-secondary",
              )}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              Grid
            </button>
          </div>
          </div>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-4 items-start">
        {/* ---------------- Left: folder tree ---------------- */}
        <Card className="overflow-hidden">
          <div className="p-2">
            <button
              onClick={() => setSelection({ kind: "all" })}
              className={cn(
                "w-full text-left px-3 py-2 rounded-md text-sm font-medium flex items-center gap-2",
                selection.kind === "all" ? "bg-aspora-50 text-aspora-800" : "hover:bg-secondary",
              )}
            >
              <FileStack className="h-4 w-4" />
              All documents
              <span className="ml-auto text-xs text-muted-foreground tabular-nums">
                {allDocs.length}
              </span>
            </button>
          </div>
          <div className="border-t border-border max-h-[60vh] overflow-y-auto scrollbar-thin">
            {entities.length === 0 ? (
              <div className="px-3 py-4 text-xs text-muted-foreground italic">
                No entities yet.
              </div>
            ) : (
              entities.map((e) => (
                <EntityNode
                  key={e.id}
                  entity={e}
                  counts={countsByEntity.get(e.id) ?? new Map()}
                  selection={selection}
                  onSelect={setSelection}
                />
              ))
            )}
          </div>
        </Card>

        {/* ---------------- Right: file list ---------------- */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="text-sm flex items-center gap-1.5 min-w-0">
              <SelectionCrumbs selection={selection} entities={entities} />
            </div>
            <div className="ml-auto relative w-[220px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Search in folder…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="pl-7 h-9"
              />
            </div>
          </div>

          {selection.kind === "all" ? (
            <AllDocsView
              documents={filteredAll}
              layout={layout}
              entities={entities}
              isAdmin={isAdmin}
              onPickEntity={(id) =>
                setSelection({ kind: "entity", entityId: id })
              }
            />
          ) : selection.kind === "entity" ? (
            <FolderCards
              entity={entities.find((e) => e.id === selection.entityId)}
              counts={countsByEntity.get(selection.entityId) ?? new Map()}
              isAdmin={isAdmin}
              query={q}
              onPick={(folder) =>
                setSelection({
                  kind: "entity-folder",
                  entityId: selection.entityId,
                  folder,
                })
              }
              onNewFolder={() => {
                const e = entities.find((x) => x.id === selection.entityId);
                if (e) promptNewFolder(e);
              }}
              onDeleteFolder={(folder, count) => {
                const e = entities.find((x) => x.id === selection.entityId);
                if (e) confirmDeleteFolder(e, folder, count);
              }}
            />
          ) : (
            <>
              <div className="flex items-center justify-between gap-2 text-sm">
                <button
                  type="button"
                  onClick={() =>
                    setSelection({ kind: "entity", entityId: selection.entityId })
                  }
                  className="text-aspora-700 hover:underline"
                >
                  ← All folders for this entity
                </button>
              </div>
              <DocumentList
                key={`ef-${selection.entityId}-${selection.folder}`}
                scope={{ kind: "entity", entityId: selection.entityId }}
                layout={layout}
                showEntityColumn={false}
                folder={selection.folder}
                query={q}
                title={selection.folder}
                hint={`New uploads here go to the “${selection.folder}” folder.`}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Folder-tree node — an entity, expandable to category leaves
// ---------------------------------------------------------------------------
function EntityNode({
  entity,
  counts,
  selection,
  onSelect,
}: {
  entity: Entity;
  counts: Map<string, number>;
  selection: Selection;
  onSelect: (s: Selection) => void;
}) {
  const total = Array.from(counts.values()).reduce((a, b) => a + b, 0);
  const selectedHere =
    (selection.kind === "entity" && selection.entityId === entity.id) ||
    (selection.kind === "entity-folder" && selection.entityId === entity.id);
  const [open, setOpen] = useState(selectedHere);
  const folders = foldersFor(entity, counts);

  return (
    <div>
      <div
        className={cn(
          "px-3 py-1.5 flex items-center gap-1.5 text-sm hover:bg-secondary/40",
          selection.kind === "entity" && selection.entityId === entity.id && "bg-aspora-50 text-aspora-800",
        )}
      >
        <button
          onClick={() => setOpen((o) => !o)}
          className="p-0.5 -ml-0.5 text-muted-foreground"
          aria-label={open ? "Collapse" : "Expand"}
        >
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>
        <button
          onClick={() => onSelect({ kind: "entity", entityId: entity.id })}
          className="flex-1 text-left flex items-center gap-1.5 min-w-0"
        >
          {open ? (
            <FolderOpen className="h-3.5 w-3.5 text-aspora-600" />
          ) : (
            <FolderClosed className="h-3.5 w-3.5 text-muted-foreground" />
          )}
          <JurisdictionBadge code={entity.jurisdiction_code} showName={false} />
          <span className="truncate font-medium">{entity.name.replace(/^Aspora\s+/, "")}</span>
          {total > 0 && (
            <span className="ml-auto text-[11px] text-muted-foreground tabular-nums">{total}</span>
          )}
        </button>
      </div>
      {open && (
        <div className="pl-7 pr-2 pb-1 space-y-0.5">
          {folders.map((folder) => {
            const n = counts.get(folder) ?? 0;
            const isSelected =
              selection.kind === "entity-folder" &&
              selection.entityId === entity.id &&
              selection.folder === folder;
            return (
              <button
                key={folder}
                onClick={() =>
                  onSelect({ kind: "entity-folder", entityId: entity.id, folder })
                }
                className={cn(
                  "w-full text-left px-2 py-1 rounded-md text-[12px] flex items-center gap-1.5",
                  isSelected
                    ? "bg-aspora-50 text-aspora-800"
                    : "text-muted-foreground hover:bg-secondary",
                )}
              >
                <FolderClosed className="h-3 w-3" />
                <span className="truncate">{folder}</span>
                {n > 0 && (
                  <span className="ml-auto text-[10px] tabular-nums">{n}</span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}


function SelectionCrumbs({
  selection,
  entities,
}: {
  selection: Selection;
  entities: Entity[];
}) {
  if (selection.kind === "all") {
    return (
      <>
        <FileStack className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="font-medium">All documents</span>
      </>
    );
  }
  const entity = entities.find((e) => e.id === selection.entityId);
  return (
    <>
      <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="font-medium truncate">{entity?.name || "Entity"}</span>
      {selection.kind === "entity-folder" && (
        <>
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
          <FolderClosed className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="truncate">{selection.folder}</span>
        </>
      )}
    </>
  );
}


// ---------------------------------------------------------------------------
// All-documents view (no upload here — pick an entity first)
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Category cards — shown when an entity is selected. Each card jumps to that
// entity's documents filtered to a category. Lets the user upload as a
// specific category in one click instead of uploading and renaming after.
// ---------------------------------------------------------------------------
function FolderCards({
  entity,
  counts,
  isAdmin,
  query,
  onPick,
  onNewFolder,
  onDeleteFolder,
}: {
  entity: Entity | undefined;
  counts: Map<string, number>;
  isAdmin: boolean;
  query?: string;
  onPick: (folder: string) => void;
  onNewFolder: () => void;
  onDeleteFolder: (folder: string, count: number) => void;
}) {
  const all = foldersFor(entity, counts);
  const q = (query ?? "").trim().toLowerCase();
  const folders = q ? all.filter((f) => f.toLowerCase().includes(q)) : all;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">
          {entity?.name ?? "Entity"} — open a folder to view / upload
        </div>
        {isAdmin && (
          <Button size="sm" variant="outline" onClick={onNewFolder}>
            <FolderPlus className="h-4 w-4" />
            New folder
          </Button>
        )}
      </div>
      {folders.length === 0 ? (
        <p className="text-sm text-muted-foreground px-1 py-6">
          {q ? `No folders match “${query}”.` : "No folders yet."}
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {folders.map((folder) => {
            const n = counts.get(folder) ?? 0;
            return (
              <div
                key={folder}
                role="button"
                tabIndex={0}
                onClick={() => onPick(folder)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onPick(folder);
                }}
                className="group rounded-lg border border-border bg-card hover:border-aspora-400 hover:bg-aspora-50/40 px-4 py-3 text-left transition-colors flex items-center gap-3 cursor-pointer"
              >
                <FolderClosed className="h-5 w-5 text-aspora-600 shrink-0" />
                <span className="text-sm font-semibold flex-1 truncate">{folder}</span>
                <span className="text-xs tabular-nums text-muted-foreground">{n}</span>
                {isAdmin && (
                  <button
                    type="button"
                    aria-label={`Delete folder ${folder}`}
                    title={
                      n > 0
                        ? "Folder has documents — move or delete them first"
                        : "Delete folder"
                    }
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteFolder(folder, n);
                    }}
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-red-50 text-muted-foreground hover:text-red-600"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


function AllDocsView({
  documents,
  layout,
  entities,
  isAdmin,
  onPickEntity,
}: {
  documents: DocumentOut[];
  layout: "rows" | "grid";
  entities: Entity[];
  isAdmin: boolean;
  onPickEntity: (entityId: number) => void;
}) {
  const qc = useQueryClient();
  const [sel, setSel] = useState<Set<number>>(new Set());
  const toggle = (id: number) =>
    setSel((p) => {
      const n = new Set(p);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  const deleteSel = useMutation({
    mutationFn: (ids: number[]) =>
      Promise.all(ids.map((id) => api.delete(`/api/documents/${id}`))),
    onSuccess: (_r, ids) => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      setSel(new Set());
      window.alert(`Deleted ${ids.length} document(s).`);
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : String(e)),
  });
  const allSel = documents.length > 0 && documents.every((d) => sel.has(d.id));
  if (documents.length === 0) {
    return (
      <Card>
        <div className="p-10 text-center text-sm space-y-3">
          <div className="text-muted-foreground">
            No documents uploaded yet across the whole workspace.
          </div>
          <div className="text-xs text-muted-foreground">
            Documents always belong to one entity. Pick the entity below and
            you'll get a drag-and-drop zone to upload PDFs, receipts, and
            anything else (max 25 MB per file).
          </div>
          {entities.length > 0 && (
            <div className="flex items-center justify-center gap-2 pt-1">
              <select
                defaultValue=""
                onChange={(e) => {
                  if (e.target.value) onPickEntity(Number(e.target.value));
                }}
                className="h-9 rounded-md border border-input bg-background px-3 text-sm max-w-xs"
              >
                <option value="">Pick an entity…</option>
                {entities.map((ent) => (
                  <option key={ent.id} value={ent.id}>
                    {ent.name} ({ent.jurisdiction_code})
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </Card>
    );
  }
  // We render via DocumentList's RowList/GridList styling indirectly by faking
  // a scope-less list. Simplest: render inline here so we don't double-load.
  return layout === "rows" ? (
    <Card className="overflow-hidden">
      {isAdmin && sel.size > 0 && (
        <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border bg-secondary/30">
          <span className="text-sm">{sel.size} selected</span>
          <Button
            size="sm"
            variant="outline"
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
            disabled={deleteSel.isPending}
            onClick={() => {
              if (
                window.confirm(
                  `Permanently delete ${sel.size} selected document(s) and their files?`,
                )
              ) {
                deleteSel.mutate(Array.from(sel));
              }
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete selected
          </Button>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              {isAdmin && (
                <th className="px-3 py-2.5 w-8">
                  <input
                    type="checkbox"
                    checked={allSel}
                    onChange={(e) =>
                      setSel(e.target.checked ? new Set(documents.map((d) => d.id)) : new Set())
                    }
                    className="accent-aspora-600"
                  />
                </th>
              )}
              <th className="px-3 py-2.5 text-left font-medium">Name</th>
              <th className="px-3 py-2.5 text-left font-medium">Entity</th>
              <th className="px-3 py-2.5 text-left font-medium">Linked to</th>
              <th className="px-3 py-2.5 text-left font-medium">Folder</th>
              <th className="px-3 py-2.5 text-left font-medium">Uploaded</th>
              <th className="px-3 py-2.5 text-right font-medium">Size</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {documents.map((d) => (
              <tr key={d.id} className="hover:bg-secondary/30">
                {isAdmin && (
                  <td className="px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={sel.has(d.id)}
                      onChange={() => toggle(d.id)}
                      className="accent-aspora-600"
                    />
                  </td>
                )}
                <td className="px-3 py-2.5">
                  <a
                    href={`/api/documents/${d.id}/download`}
                    className="font-medium hover:text-aspora-700"
                  >
                    {d.filename}
                  </a>
                </td>
                <td className="px-3 py-2.5 text-muted-foreground truncate">
                  {d.entity_name || "—"}
                </td>
                <td className="px-3 py-2.5 text-muted-foreground text-xs">
                  {d.obligation_form_name || "Entity-level"}
                </td>
                <td className="px-3 py-2.5 text-xs">{d.folder || d.category}</td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground">
                  {new Date(d.created_at).toLocaleDateString()}
                </td>
                <td className="px-3 py-2.5 text-right text-xs tabular-nums text-muted-foreground">
                  {(d.size_bytes / 1024).toFixed(0)} KB
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  ) : (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      {documents.map((d) => (
        <a
          key={d.id}
          href={`/api/documents/${d.id}/download`}
          className="rounded-xl border border-border bg-card p-3 hover:shadow-md transition-shadow"
        >
          <div className="aspect-[4/3] bg-secondary/40 rounded-md grid place-items-center mb-2 text-muted-foreground text-xs uppercase tracking-wider">
            {d.filename.split(".").pop()?.toUpperCase() || "FILE"}
          </div>
          <div className="font-medium text-sm truncate">{d.filename}</div>
          <div className="text-[11px] text-muted-foreground truncate mt-0.5">
            {d.entity_name} · {d.folder || d.category}
          </div>
        </a>
      ))}
    </div>
  );
}


