// Regulation news inbox. Two views:
//   - Inbox: unread / all items pulled from regulator RSS / Atom feeds.
//   - Feeds: list of configured feeds with last poll status; admins can
//     add/disable/poll-now.
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Check,
  CheckCheck,
  ExternalLink,
  Loader2,
  Newspaper,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { JurisdictionBadge } from "@/components/JurisdictionBadge";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { fmtRelative, JURISDICTIONS } from "@/lib/format";

interface FeedItem {
  id: number;
  feed_id: number;
  feed_name: string;
  jurisdiction_code: string;
  title: string;
  link: string | null;
  summary: string | null;
  published_at: string | null;
  fetched_at: string;
  read_at: string | null;
  dismissed_at: string | null;
  promoted_rule_id: number | null;
}

interface Feed {
  id: number;
  name: string;
  jurisdiction_code: string;
  url: string;
  feed_type: string;
  enabled: boolean;
  last_polled_at: string | null;
  last_status: string | null;
  last_error: string | null;
  unread_count: number;
  total_count: number;
}

interface PollSummary {
  total_new: number;
  results: {
    feed_id: number;
    feed_name: string;
    new_items: number;
    total_items: number;
    http_status: number | null;
    error: string | null;
  }[];
}

export function RegulationNewsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"inbox" | "feeds">("inbox");
  const [unreadOnly, setUnreadOnly] = useState(true);
  const [jurisdiction, setJurisdiction] = useState<string>("");
  const [pollSummary, setPollSummary] = useState<PollSummary | null>(null);

  const itemsQuery = useQuery({
    queryKey: ["regulation-news", unreadOnly, jurisdiction],
    queryFn: () => {
      const params = new URLSearchParams();
      if (unreadOnly) params.set("unread_only", "true");
      if (jurisdiction) params.set("jurisdiction_code", jurisdiction);
      params.set("limit", "200");
      return api.get<FeedItem[]>(`/api/regulation-news?${params.toString()}`);
    },
  });

  const feedsQuery = useQuery({
    queryKey: ["regulation-feeds"],
    queryFn: () => api.get<Feed[]>("/api/regulation-feeds"),
  });

  function invalidateAll() {
    queryClient.invalidateQueries({ queryKey: ["regulation-news"] });
    queryClient.invalidateQueries({ queryKey: ["regulation-feeds"] });
    queryClient.invalidateQueries({ queryKey: ["sidebar-news-count"] });
  }

  const pollAllMutation = useMutation({
    mutationFn: () => api.post<PollSummary>("/api/regulation-feeds/poll"),
    onSuccess: (data) => {
      setPollSummary(data);
      invalidateAll();
    },
  });

  const pollOneMutation = useMutation({
    mutationFn: (feedId: number) =>
      api.post<PollSummary>(`/api/regulation-feeds/poll?feed_id=${feedId}`),
    onSuccess: (data) => {
      setPollSummary(data);
      invalidateAll();
    },
  });

  const markReadMutation = useMutation({
    mutationFn: (itemId: number) =>
      api.post(`/api/regulation-news/${itemId}/read`),
    onSuccess: () => invalidateAll(),
  });

  const dismissMutation = useMutation({
    mutationFn: (itemId: number) =>
      api.post(`/api/regulation-news/${itemId}/dismiss`),
    onSuccess: () => invalidateAll(),
  });

  const readAllMutation = useMutation({
    mutationFn: () => {
      const params = new URLSearchParams();
      if (jurisdiction) params.set("jurisdiction_code", jurisdiction);
      return api.post(`/api/regulation-news/read-all?${params.toString()}`);
    },
    onSuccess: () => invalidateAll(),
  });

  // Group inbox items by jurisdiction for the inbox view.
  const groupedItems = useMemo(() => {
    const items = itemsQuery.data ?? [];
    const groups = new Map<string, FeedItem[]>();
    for (const item of items) {
      const arr = groups.get(item.jurisdiction_code) ?? [];
      arr.push(item);
      groups.set(item.jurisdiction_code, arr);
    }
    return Array.from(groups.entries()).sort(([a], [b]) =>
      a.localeCompare(b),
    );
  }, [itemsQuery.data]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Regulation News"
        description="New filings, guidance, and circulars pulled from regulator feeds. Use these to spot rules you haven't loaded yet."
        actions={
          isAdmin && (
            <Button
              variant="outline"
              onClick={() => pollAllMutation.mutate()}
              disabled={pollAllMutation.isPending}
            >
              {pollAllMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Poll all feeds
            </Button>
          )
        }
      />

      {pollSummary && (
        <div className="rounded-lg border border-aspora-200 bg-aspora-50 px-4 py-3 text-sm flex items-start gap-2">
          <Sparkles className="h-4 w-4 text-aspora-600 mt-0.5 shrink-0" />
          <div className="flex-1">
            <div className="font-medium text-aspora-700">
              {pollSummary.total_new} new item
              {pollSummary.total_new === 1 ? "" : "s"} across{" "}
              {pollSummary.results.length} feed
              {pollSummary.results.length === 1 ? "" : "s"}.
            </div>
            {pollSummary.results.some((r) => r.error) && (
              <div className="text-xs text-aspora-700/80 mt-1">
                {pollSummary.results.filter((r) => r.error).length} feed(s)
                returned errors — see Feeds tab for details.
              </div>
            )}
          </div>
          <button
            type="button"
            className="text-aspora-700/70 hover:text-aspora-900"
            onClick={() => setPollSummary(null)}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <TabsList>
          <TabsTrigger value="inbox">
            Inbox
            {itemsQuery.data && itemsQuery.data.length > 0 && (
              <Badge variant="neutral" className="ml-1">
                {itemsQuery.data.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="feeds">
            Feeds
            {feedsQuery.data && (
              <Badge variant="neutral" className="ml-1">
                {feedsQuery.data.length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {tab === "inbox" ? (
        <InboxView
          itemsQuery={itemsQuery}
          groupedItems={groupedItems}
          unreadOnly={unreadOnly}
          setUnreadOnly={setUnreadOnly}
          jurisdiction={jurisdiction}
          setJurisdiction={setJurisdiction}
          markRead={(id) => markReadMutation.mutate(id)}
          dismiss={(id) => dismissMutation.mutate(id)}
          readAll={() => readAllMutation.mutate()}
          readAllPending={readAllMutation.isPending}
        />
      ) : (
        <FeedsView
          feedsQuery={feedsQuery}
          isAdmin={isAdmin}
          pollOne={(id) => pollOneMutation.mutate(id)}
          pollingId={
            pollOneMutation.isPending
              ? (pollOneMutation.variables as number | undefined)
              : undefined
          }
          onChanged={invalidateAll}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inbox
// ---------------------------------------------------------------------------
function InboxView({
  itemsQuery,
  groupedItems,
  unreadOnly,
  setUnreadOnly,
  jurisdiction,
  setJurisdiction,
  markRead,
  dismiss,
  readAll,
  readAllPending,
}: {
  itemsQuery: ReturnType<typeof useQuery<FeedItem[]>>;
  groupedItems: [string, FeedItem[]][];
  unreadOnly: boolean;
  setUnreadOnly: (v: boolean) => void;
  jurisdiction: string;
  setJurisdiction: (v: string) => void;
  markRead: (id: number) => void;
  dismiss: (id: number) => void;
  readAll: () => void;
  readAllPending: boolean;
}) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={unreadOnly}
            onChange={(e) => setUnreadOnly(e.target.checked)}
            className="accent-aspora-600"
          />
          Unread only
        </label>
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
        <div className="ml-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={readAll}
            disabled={readAllPending || (itemsQuery.data?.length ?? 0) === 0}
          >
            <CheckCheck className="h-4 w-4" />
            Mark all read
          </Button>
        </div>
      </div>

      {itemsQuery.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : groupedItems.length === 0 ? (
        <EmptyState
          icon={<Newspaper className="h-6 w-6" />}
          title="Nothing new"
          description={
            unreadOnly
              ? "No unread items. Try poll all feeds, or untick Unread only to see history."
              : "No items yet — add a feed or poll all feeds to fetch the latest."
          }
        />
      ) : (
        <div className="space-y-6">
          {groupedItems.map(([code, items]) => (
            <div key={code} className="space-y-2">
              <div className="flex items-center gap-2 sticky top-0 bg-background py-1 z-10">
                <JurisdictionBadge code={code} />
                <span className="text-sm text-muted-foreground">
                  {items.length} item{items.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="space-y-1.5">
                {items.map((item) => (
                  <NewsCard
                    key={item.id}
                    item={item}
                    onMarkRead={() => markRead(item.id)}
                    onDismiss={() => dismiss(item.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function NewsCard({
  item,
  onMarkRead,
  onDismiss,
}: {
  item: FeedItem;
  onMarkRead: () => void;
  onDismiss: () => void;
}) {
  const isUnread = item.read_at === null && item.dismissed_at === null;
  return (
    <div
      className={
        "rounded-lg border px-4 py-3 transition-colors " +
        (isUnread
          ? "border-aspora-200 bg-aspora-50/40"
          : "border-border bg-background")
      }
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="truncate">{item.feed_name}</span>
            <span>·</span>
            <span>
              {item.published_at
                ? fmtRelative(item.published_at)
                : `fetched ${fmtRelative(item.fetched_at)}`}
            </span>
          </div>
          <div className="mt-1 text-sm font-medium leading-snug">
            {item.link ? (
              <a
                href={item.link}
                target="_blank"
                rel="noreferrer"
                className="hover:underline inline-flex items-baseline gap-1"
              >
                {item.title}
                <ExternalLink className="h-3 w-3 text-muted-foreground" />
              </a>
            ) : (
              item.title
            )}
          </div>
          {item.summary && (
            <div className="mt-1 text-xs text-muted-foreground line-clamp-2">
              {item.summary}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {isUnread && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onMarkRead}
              title="Mark read"
            >
              <Check className="h-4 w-4" />
            </Button>
          )}
          {item.dismissed_at === null && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onDismiss}
              title="Dismiss"
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Feeds tab
// ---------------------------------------------------------------------------
function FeedsView({
  feedsQuery,
  isAdmin,
  pollOne,
  pollingId,
  onChanged,
}: {
  feedsQuery: ReturnType<typeof useQuery<Feed[]>>;
  isAdmin: boolean;
  pollOne: (id: number) => void;
  pollingId: number | undefined;
  onChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState("us");
  const [url, setUrl] = useState("");

  const addMutation = useMutation({
    mutationFn: () =>
      api.post<Feed>("/api/regulation-feeds", {
        name,
        jurisdiction_code: code,
        url,
      }),
    onSuccess: () => {
      setShowAdd(false);
      setName("");
      setUrl("");
      onChanged();
    },
  });

  const seedDefaults = useMutation({
    mutationFn: () =>
      api.post<{ added: number }>("/api/regulation-feeds/seed-defaults"),
    onSuccess: () => onChanged(),
  });

  const toggleEnabled = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      api.patch<Feed>(`/api/regulation-feeds/${id}`, { enabled }),
    onSuccess: () => onChanged(),
  });

  const deleteFeed = useMutation({
    mutationFn: (id: number) => api.delete(`/api/regulation-feeds/${id}`),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["regulation-feeds"] }),
  });

  return (
    <div className="space-y-3">
      {isAdmin && (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={() => setShowAdd((v) => !v)}>
            <Plus className="h-4 w-4" />
            Add feed
          </Button>
          <Button
            variant="outline"
            onClick={() => seedDefaults.mutate()}
            disabled={seedDefaults.isPending}
          >
            {seedDefaults.isPending && (
              <Loader2 className="h-4 w-4 animate-spin" />
            )}
            Seed default feeds
          </Button>
          {seedDefaults.data && (
            <span className="text-xs text-muted-foreground">
              Added {seedDefaults.data.added} new feed(s).
            </span>
          )}
        </div>
      )}

      {showAdd && (
        <div className="rounded-lg border border-border bg-secondary/30 px-4 py-3 space-y-2">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <Input
              placeholder="Display name (e.g. HMRC News)"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <select
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="h-10 rounded-lg border border-input bg-background px-3 text-sm"
            >
              {Object.entries(JURISDICTIONS).map(([c, j]) => (
                <option key={c} value={c}>
                  {j.flag} {j.name}
                </option>
              ))}
            </select>
            <Input
              placeholder="Feed URL (RSS or Atom)"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={() => setShowAdd(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => addMutation.mutate()}
              disabled={
                addMutation.isPending || !name.trim() || !url.trim() || !code
              }
            >
              {addMutation.isPending && (
                <Loader2 className="h-4 w-4 animate-spin" />
              )}
              Add
            </Button>
          </div>
          {addMutation.error && (
            <div className="flex items-start gap-2 text-xs text-destructive">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              {(addMutation.error as Error).message}
            </div>
          )}
        </div>
      )}

      {feedsQuery.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : (feedsQuery.data?.length ?? 0) === 0 ? (
        <EmptyState
          icon={<Newspaper className="h-6 w-6" />}
          title="No feeds yet"
          description={
            isAdmin
              ? "Add a feed manually or click Seed default feeds to load the built-in regulator list."
              : "An admin needs to add feeds before news will appear."
          }
        />
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Feed</th>
                <th className="text-left px-3 py-2 font-medium">Last poll</th>
                <th className="text-left px-3 py-2 font-medium">Status</th>
                <th className="text-right px-3 py-2 font-medium">Items</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {feedsQuery.data!.map((f) => (
                <tr
                  key={f.id}
                  className="border-t border-border hover:bg-secondary/20"
                >
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <JurisdictionBadge code={f.jurisdiction_code} />
                      <div className="min-w-0">
                        <div className="font-medium truncate">{f.name}</div>
                        <a
                          href={f.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-muted-foreground hover:underline truncate inline-flex items-baseline gap-1"
                        >
                          {f.url}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {f.last_polled_at ? fmtRelative(f.last_polled_at) : "never"}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {f.last_error ? (
                      <span
                        className="inline-flex items-center gap-1 text-destructive"
                        title={f.last_error}
                      >
                        <AlertCircle className="h-3 w-3" />
                        {f.last_status || "error"}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">
                        {f.last_status || "—"}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right text-xs tabular-nums">
                    <span className="text-aspora-700 font-semibold">
                      {f.unread_count}
                    </span>
                    <span className="text-muted-foreground"> / {f.total_count}</span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="inline-flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => pollOne(f.id)}
                        disabled={pollingId === f.id}
                        title="Poll this feed now"
                      >
                        {pollingId === f.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <RefreshCw className="h-4 w-4" />
                        )}
                      </Button>
                      {isAdmin && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              toggleEnabled.mutate({
                                id: f.id,
                                enabled: !f.enabled,
                              })
                            }
                            title={f.enabled ? "Disable" : "Enable"}
                          >
                            {f.enabled ? "On" : "Off"}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              if (
                                confirm(`Delete feed "${f.name}"? This also removes its news items.`)
                              ) {
                                deleteFeed.mutate(f.id);
                              }
                            }}
                            title="Delete"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
