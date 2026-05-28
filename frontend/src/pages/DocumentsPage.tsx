// Global Documents page — 2-pane Drive-like view.
// Left: folder tree by Entity → Category.
// Right: file list (or grid) for the current selection.

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  FolderClosed,
  FolderOpen,
  LayoutGrid,
  List,
  Search,
  Building2,
  FileStack,
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
  | { kind: "entity-category"; entityId: number; category: DocumentCategory };


// Buckets shown as top-of-page chips. Maps to the DocumentCategory enum
// for the filter; "all" is the unfiltered passthrough.
const CATEGORY_CHIPS: { key: "all" | DocumentCategory; label: string }[] = [
  { key: "all", label: "All" },
  { key: "Filings", label: "Filed documents" },
  { key: "Formation", label: "Formation" },
  { key: "Contracts", label: "Templates" },
  { key: "Expert notes", label: "Reference" },
  { key: "Other", label: "Other" },
];

export function DocumentsPage() {
  const [selection, setSelection] = useState<Selection>({ kind: "all" });
  const [layout, setLayout] = useState<"rows" | "grid">("rows");
  const [q, setQ] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<"all" | DocumentCategory>("all");

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
    const m = new Map<number, Map<DocumentCategory, number>>();
    for (const d of allDocs) {
      if (!m.has(d.entity_id)) m.set(d.entity_id, new Map());
      const cm = m.get(d.entity_id)!;
      cm.set(d.category, (cm.get(d.category) ?? 0) + 1);
    }
    return m;
  }, [allDocs]);

  // Apply optional name filter to whatever the right pane is showing.
  // The pane uses its own React Query under the hood; we just pass the q
  // through to the same endpoint. For "all" we filter client-side because
  // we already have the list cached.
  const filteredAll = useMemo(() => {
    if (selection.kind !== "all") return allDocs;
    let arr = allDocs;
    if (categoryFilter !== "all") {
      arr = arr.filter((d) => d.category === categoryFilter);
    }
    if (q.trim()) {
      const n = q.trim().toLowerCase();
      arr = arr.filter((d) => d.filename.toLowerCase().includes(n));
    }
    return arr;
  }, [allDocs, q, selection, categoryFilter]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Documents"
        description="Filings, certificates, and audit artifacts. Pick an entity in the sidebar to upload — files always live under one entity."
        actions={
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
            // Custom rendering for "all" — uses cached docs + client-side q filter
            // so it doesn't refetch on every keystroke.
            <>
              <div className="flex flex-wrap gap-1.5 mb-3">
                {CATEGORY_CHIPS.map((c) => (
                  <button
                    key={c.key}
                    type="button"
                    onClick={() => setCategoryFilter(c.key)}
                    className={
                      categoryFilter === c.key
                        ? "rounded-full border border-aspora-500 bg-aspora-50 px-3 py-1 text-xs text-aspora-700 font-medium"
                        : "rounded-full border border-border bg-background px-3 py-1 text-xs text-muted-foreground hover:bg-secondary"
                    }
                  >
                    {c.label}
                  </button>
                ))}
              </div>
              <AllDocsView
                documents={filteredAll}
                layout={layout}
                entities={entities}
                onPickEntity={(id) =>
                  setSelection({ kind: "entity", entityId: id })
                }
              />
            </>
          ) : selection.kind === "entity" ? (
            <>
              <CategoryCards
                entityName={
                  entities.find((e) => e.id === selection.entityId)?.name ?? "Entity"
                }
                counts={countsByEntity.get(selection.entityId) ?? new Map()}
                onPick={(cat) =>
                  setSelection({
                    kind: "entity-category",
                    entityId: selection.entityId,
                    category: cat,
                  })
                }
              />
              <DocumentList
                key={`e-${selection.entityId}`}
                scope={{ kind: "entity", entityId: selection.entityId }}
                layout={layout}
                showEntityColumn={false}
                title={undefined}
                hint="Drag files here to upload. Set the category after upload, or pick a category card above for a category-targeted upload."
              />
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 text-sm">
                <button
                  type="button"
                  onClick={() =>
                    setSelection({ kind: "entity", entityId: selection.entityId })
                  }
                  className="text-aspora-700 hover:underline"
                >
                  ← All categories for this entity
                </button>
              </div>
              <DocumentList
                key={`ec-${selection.entityId}-${selection.category}`}
                scope={{ kind: "entity", entityId: selection.entityId }}
                layout={layout}
                showEntityColumn={false}
                defaultCategory={selection.category}
                title={selection.category}
                hint={`New uploads here will be tagged as ${selection.category}.`}
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
  counts: Map<DocumentCategory, number>;
  selection: Selection;
  onSelect: (s: Selection) => void;
}) {
  const total = Array.from(counts.values()).reduce((a, b) => a + b, 0);
  const selectedHere =
    (selection.kind === "entity" && selection.entityId === entity.id) ||
    (selection.kind === "entity-category" && selection.entityId === entity.id);
  const [open, setOpen] = useState(selectedHere);

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
          {DOCUMENT_CATEGORIES.map((cat) => {
            const n = counts.get(cat) ?? 0;
            const isSelected =
              selection.kind === "entity-category" &&
              selection.entityId === entity.id &&
              selection.category === cat;
            return (
              <button
                key={cat}
                onClick={() =>
                  onSelect({ kind: "entity-category", entityId: entity.id, category: cat })
                }
                className={cn(
                  "w-full text-left px-2 py-1 rounded-md text-[12px] flex items-center gap-1.5",
                  isSelected
                    ? "bg-aspora-50 text-aspora-800"
                    : "text-muted-foreground hover:bg-secondary",
                )}
              >
                <FolderClosed className="h-3 w-3" />
                <span className="truncate">{cat}</span>
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
      {selection.kind === "entity-category" && (
        <>
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
          <FolderClosed className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="truncate">{selection.category}</span>
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
function CategoryCards({
  entityName,
  counts,
  onPick,
}: {
  entityName: string;
  counts: Map<DocumentCategory, number>;
  onPick: (cat: DocumentCategory) => void;
}) {
  const CATEGORY_HINTS: Record<DocumentCategory, string> = {
    "Formation": "Incorporation docs, MoA / AoA, certificates of registration.",
    "Filings": "Filed returns, ACK receipts, regulator portal printouts.",
    "Contracts": "Agreements, NDAs, vendor / customer contracts.",
    "Expert notes": "Country expert advice, opinions, internal SOPs.",
    "Other": "Templates, blank forms, anything that doesn't fit the rest.",
  };
  return (
    <div className="space-y-2">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">
        Upload to {entityName} — pick a category
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
        {DOCUMENT_CATEGORIES.map((cat) => {
          const n = counts.get(cat) ?? 0;
          return (
            <button
              key={cat}
              type="button"
              onClick={() => onPick(cat)}
              className="rounded-lg border border-border bg-card hover:border-aspora-400 hover:bg-aspora-50/40 px-3 py-2.5 text-left transition-colors"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">{cat}</span>
                <span className="text-xs tabular-nums text-muted-foreground">
                  {n}
                </span>
              </div>
              <div className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">
                {CATEGORY_HINTS[cat]}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}


function AllDocsView({
  documents,
  layout,
  entities,
  onPickEntity,
}: {
  documents: DocumentOut[];
  layout: "rows" | "grid";
  entities: Entity[];
  onPickEntity: (entityId: number) => void;
}) {
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
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 text-left font-medium">Name</th>
              <th className="px-3 py-2.5 text-left font-medium">Entity</th>
              <th className="px-3 py-2.5 text-left font-medium">Linked to</th>
              <th className="px-3 py-2.5 text-left font-medium">Category</th>
              <th className="px-3 py-2.5 text-left font-medium">Uploaded</th>
              <th className="px-3 py-2.5 text-right font-medium">Size</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {documents.map((d) => (
              <tr key={d.id} className="hover:bg-secondary/30">
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
                <td className="px-3 py-2.5 text-xs">{d.category}</td>
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
            {d.entity_name} · {d.category}
          </div>
        </a>
      ))}
    </div>
  );
}


