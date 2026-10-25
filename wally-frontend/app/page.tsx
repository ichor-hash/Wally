"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE,
  ApiError,
  ChatTurn,
  DocumentInfo,
  Health,
  Insights,
  KnowledgeGap,
  MetricsSummary,
  RateLimit,
  Source,
  getJson,
  search,
  streamSearch,
} from "@/lib/api";
import { DocumentDrawer } from "@/components/DocumentDrawer";
import { Exchange } from "@/components/Exchange";
import { Wally } from "@/components/mascot/Wally";
import { Connection, Sidebar, View } from "@/components/Sidebar";
import { useToast } from "@/components/Toaster";
import { AskView } from "@/components/views/AskView";
import { GapsView } from "@/components/views/GapsView";
import { LibraryView } from "@/components/views/LibraryView";
import { PerformanceView } from "@/components/views/PerformanceView";
import { Settings, SettingsView } from "@/components/views/SettingsView";

const SETTINGS_KEY = "wally.settings";
const DEFAULT_SETTINGS: Settings = { streaming: true, rerank: false, topK: 5 };

const uid = () => Math.random().toString(36).slice(2, 10);

export default function Home() {
  const { toast } = useToast();

  const [view, setView] = useState<View>("ask");
  const [health, setHealth] = useState<Health | null>(null);
  const [connection, setConnection] = useState<Connection>("checking");
  const [pingMs, setPingMs] = useState<number | null>(null);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [rateLimit, setRateLimit] = useState<RateLimit | null>(null);
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [rerankerWarming, setRerankerWarming] = useState(false);

  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [queue, setQueue] = useState<{ id: string; query: string }[]>([]);
  const [drawer, setDrawer] = useState<{ doc: string; chunkId?: string } | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const prevConnection = useRef<Connection>("checking");
  const exchangesRef = useRef<Exchange[]>([]);

  useEffect(() => {
    exchangesRef.current = exchanges;
  }, [exchanges]);

  // ---------------- data ----------------
  const checkHealth = useCallback(async () => {
    const t0 = performance.now();
    try {
      const h = await getJson<Health>("/health", { signal: AbortSignal.timeout(5000) });
      setPingMs(Math.round(performance.now() - t0));
      setHealth(h);
      setConnection(h.status === "healthy" ? "online" : "degraded");
    } catch {
      setPingMs(null);
      setConnection("offline");
    }
  }, []);

  const refreshDocuments = useCallback(async () => {
    try {
      setDocuments((await getJson<{ documents: DocumentInfo[] }>("/documents")).documents);
    } catch {}
  }, []);

  const refreshRateLimit = useCallback(async () => {
    try {
      setRateLimit(await getJson<RateLimit>("/rate-limit"));
    } catch {}
  }, []);

  const refreshStats = useCallback(async () => {
    try {
      const [m, i] = await Promise.all([getJson<MetricsSummary>("/metrics"), getJson<Insights>("/insights")]);
      setMetrics(m);
      setInsights(i);
    } catch {}
  }, []);

  const refreshAll = useCallback(() => {
    checkHealth();
    refreshDocuments();
    refreshRateLimit();
    refreshStats();
  }, [checkHealth, refreshDocuments, refreshRateLimit, refreshStats]);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(SETTINGS_KEY);
      if (saved) setSettings({ ...DEFAULT_SETTINGS, ...JSON.parse(saved) });
    } catch {}
    refreshAll();
  }, [refreshAll]);

  // Health check every 10s, every 3s while disconnected
  useEffect(() => {
    const t = setInterval(checkHealth, connection === "online" ? 10000 : 3000);
    return () => clearInterval(t);
  }, [checkHealth, connection]);

  useEffect(() => {
    const t = setInterval(() => {
      if (connection !== "offline") {
        refreshRateLimit();
        refreshStats();
      }
    }, 5000);
    return () => clearInterval(t);
  }, [connection, refreshRateLimit, refreshStats]);

  // Toast on connection changes
  useEffect(() => {
    const prev = prevConnection.current;
    prevConnection.current = connection;
    if (prev === "checking") {
      if (connection === "offline") toast("error", "Cannot reach the API", `Is the backend running at ${API_BASE}?`);
      return;
    }
    if (prev === connection) return;
    if (connection === "online") {
      toast("success", "Back online");
      refreshDocuments();
    } else if (connection === "offline") toast("error", "Connection lost", "Retrying every few seconds.");
    else toast("warning", "Vector database unavailable", "Questions will fail until Qdrant is back.");
  }, [connection, toast, refreshDocuments]);

  const updateSettings = (next: Settings) => {
    const turningOnRerank = next.rerank && !settings.rerank;
    setSettings(next);
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
    } catch {}
    if (turningOnRerank && health && !health.reranker_loaded) {
      setRerankerWarming(true);
      toast("info", "Loading the reranker", "This happens once and can take a few seconds.");
      getJson<{ load_time: number }>("/reranker/warmup", { method: "POST" })
        .then((r) => {
          toast("success", "Reranker ready", `Loaded in ${r.load_time.toFixed(1)}s`);
          checkHealth();
        })
        .catch((e) => toast("error", "Reranker failed to load", e.message))
        .finally(() => setRerankerWarming(false));
    }
  };

  // ---------------- questions ----------------
  const patch = (id: string, update: Partial<Exchange> | ((e: Exchange) => Partial<Exchange>)) =>
    setExchanges((prev) => prev.map((e) => (e.id === id ? { ...e, ...(typeof update === "function" ? update(e) : update) } : e)));

  /** Last few completed exchanges, so follow-up questions have context. */
  const historyBefore = (id: string): ChatTurn[] => {
    const all = exchangesRef.current;
    const idx = all.findIndex((e) => e.id === id);
    return all
      .slice(0, Math.max(0, idx))
      .filter((e) => e.stage === "done" && e.answer && !e.error)
      .slice(-3)
      .flatMap((e) => [
        { role: "user" as const, content: e.query },
        { role: "assistant" as const, content: e.answer },
      ]);
  };

  const runQuery = useCallback(
    async (id: string, query: string) => {
      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;
      const body = { query, top_k: settings.topK, rerank: settings.rerank, history: historyBefore(id) };
      patch(id, { stage: "retrieving", error: undefined, answer: "", reranked: settings.rerank, startedAt: Date.now() });

      try {
        if (settings.streaming) {
          await streamSearch(
            body,
            {
              onStage: (stage, data) =>
                patch(id, {
                  stage: stage as Exchange["stage"],
                  ...(stage === "retrieved"
                    ? { stageTimes: { embedding_time: Number(data.embedding_time), search_time: Number(data.search_time), rerank_time: Number(data.rerank_time) } }
                    : {}),
                }),
              onSources: (sources, confidence) => patch(id, { sources, confidence }),
              onToken: (token) => patch(id, (e) => ({ answer: e.answer + token, stage: "generating" })),
              onComplete: (queryId, metrics, rl) => {
                patch(id, { queryId, metrics, stage: "done" });
                if (rl) setRateLimit((prev) => ({ ...rl, upstream: prev?.upstream }));
              },
            },
            controller.signal,
          );
        } else {
          const res = await search(body);
          patch(id, { answer: res.answer, sources: res.sources, confidence: res.confidence, metrics: res.metrics, queryId: res.query_id, stage: "done" });
        }
        refreshStats();
        refreshDocuments();
        refreshRateLimit();
      } catch (err) {
        if (controller.signal.aborted) {
          patch(id, (e) => ({ stage: "done", answer: e.answer ? `${e.answer}\n\n*Stopped.*` : "*Stopped.*" }));
        } else if (err instanceof ApiError && err.status === 429) {
          // Back to the front of the queue; it drains when the window resets
          patch(id, { stage: "queued" });
          setQueue((q) => [{ id, query }, ...q]);
          setRateLimit((prev) => (prev ? { ...prev, remaining: 0, reset_in_seconds: err.retryAfter ?? prev.reset_in_seconds } : prev));
          toast("warning", "Rate limit reached", `Your question will send in about ${err.retryAfter ?? 60}s.`);
        } else {
          const message = err instanceof ApiError && err.status !== 0 ? err.message : "Could not reach the API. Check the status in the sidebar and try again.";
          patch(id, { error: message, stage: "done" });
          toast("error", "No answer", message);
          if (!(err instanceof ApiError)) checkHealth();
        }
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [settings, toast],
  );

  const ask = (raw: string) => {
    const query = raw.trim();
    if (!query) return;
    const id = uid();
    stickToBottom.current = true;
    setView("ask");
    setExchanges((prev) => [...prev, { id, query, answer: "", stage: "queued" }]);
    setQueue((q) => [...q, { id, query }]);
  };

  // Queue: send the next question when idle and quota allows
  useEffect(() => {
    if (busy || queue.length === 0 || connection === "offline") return;
    if (rateLimit && rateLimit.remaining <= 0) {
      const t = setTimeout(refreshRateLimit, Math.max(1, rateLimit.reset_in_seconds) * 1000 + 250);
      return () => clearTimeout(t);
    }
    const [next, ...rest] = queue;
    setQueue(rest);
    runQuery(next.id, next.query);
  }, [busy, queue, rateLimit, connection, runQuery, refreshRateLimit]);

  // Follow the answer while it streams, unless the reader scrolled up
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [exchanges]);

  const onFeedback = async (ex: Exchange, rating: "up" | "down") => {
    if (!ex.queryId) return;
    patch(ex.id, { feedback: rating });
    try {
      await getJson("/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query_id: ex.queryId, query: ex.query, rating }),
      });
      toast("success", "Thanks for the feedback", rating === "down" ? "Added to knowledge gaps for review." : undefined);
      refreshStats();
    } catch (e) {
      patch(ex.id, { feedback: undefined });
      toast("error", "Feedback not sent", e instanceof Error ? e.message : undefined);
    }
  };

  const onResolveGap = async (gap: KnowledgeGap) => {
    try {
      await getJson(`/insights/gaps?normalized=${encodeURIComponent(gap.normalized)}`, { method: "DELETE" });
      toast("success", "Gap resolved");
      refreshStats();
    } catch (e) {
      toast("error", "Could not resolve", e instanceof Error ? e.message : undefined);
    }
  };

  // Chunks cited by the last 10 answers, highlighted in document previews
  const recentChunkUse = useMemo(() => {
    const map = new Map<string, number>();
    exchanges.slice(-10).forEach((e) => e.sources?.forEach((s) => map.set(s.id, (map.get(s.id) ?? 0) + 1)));
    return map;
  }, [exchanges]);

  const recentlyCitedDocs = useMemo(() => {
    const set = new Set<string>();
    exchanges.slice(-3).forEach((e) => e.sources?.forEach((s) => set.add(s.source_file)));
    return set;
  }, [exchanges]);

  return (
    <div className="flex min-h-screen flex-col lg:h-screen lg:flex-row">
      <Sidebar
        view={view}
        onNavigate={setView}
        counts={{ library: documents.length, gaps: insights?.gaps.length }}
        health={health}
        connection={connection}
        pingMs={pingMs}
        rateLimit={rateLimit}
        queued={queue.length}
        onRetryConnection={refreshAll}
      />

      <main className="flex min-h-[calc(100vh-72px)] min-w-0 flex-1 flex-col p-2 pt-0 lg:min-h-0 lg:p-3 lg:pl-0">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[18px] bg-surface shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_1px_3px_rgba(0,0,0,0.04)]">
          {view === "ask" && (
            <AskView
              exchanges={exchanges}
              documents={documents}
              companyName={health && health.company_name !== "your company" ? health.company_name : undefined}
              input={input}
              onInput={setInput}
              onAsk={ask}
              onStop={() => abortRef.current?.abort()}
              onClear={() => {
                abortRef.current?.abort();
                setQueue([]);
                setExchanges([]);
              }}
              busy={busy}
              queued={queue.length}
              settings={settings}
              rateLimit={rateLimit}
              connection={connection}
              scrollRef={scrollRef}
              onScroll={() => {
                const el = scrollRef.current;
                if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
              }}
              onOpenSource={(s: Source) => setDrawer({ doc: s.source_file, chunkId: s.id })}
              onFeedback={onFeedback}
              onRetry={(ex) => {
                patch(ex.id, { error: undefined, stage: "queued" });
                setQueue((q) => [...q, { id: ex.id, query: ex.query }]);
              }}
              onOpenSettings={() => setView("settings")}
              onOpenLibrary={() => setView("library")}
            />
          )}
          {view !== "ask" && (
            <div className="min-h-0 flex-1 overflow-y-auto">
              {view === "library" && (
                <LibraryView
                  documents={documents}
                  recentlyCited={recentlyCitedDocs}
                  onChanged={() => {
                    refreshDocuments();
                    checkHealth();
                  }}
                  onOpenDocument={(doc) => setDrawer({ doc })}
                />
              )}
              {view === "performance" && <PerformanceView metrics={metrics} />}
              {view === "gaps" && <GapsView insights={insights} onResolve={onResolveGap} onAsk={ask} />}
              {view === "settings" && <SettingsView settings={settings} onChange={updateSettings} health={health} rerankerWarming={rerankerWarming} />}
            </div>
          )}
        </div>
      </main>

      <Wally view={view} />

      {drawer && <DocumentDrawer key={drawer.doc} docName={drawer.doc} focusChunkId={drawer.chunkId} recentChunkUse={recentChunkUse} onClose={() => setDrawer(null)} />}
    </div>
  );
}
