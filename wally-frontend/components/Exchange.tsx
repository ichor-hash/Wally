"use client";

import { useEffect, useState } from "react";
import { Confidence, QueryMetrics, Source, formatMs } from "@/lib/api";
import { Markdown } from "./Markdown";
import { StageBar, TextButton } from "./ui";

/** One question and its answer. */
export interface Exchange {
  id: string;
  query: string;
  answer: string;
  queryId?: string;
  sources?: Source[];
  confidence?: Confidence;
  metrics?: QueryMetrics;
  reranked?: boolean;
  stage: "queued" | "retrieving" | "retrieved" | "generating" | "done";
  stageTimes?: { embedding_time?: number; search_time?: number; rerank_time?: number };
  error?: string;
  feedback?: "up" | "down";
  startedAt?: number;
}

const GROUNDING: Record<Confidence["level"], { label: string; dot: string; hint: string }> = {
  high: { label: "Well grounded", dot: "bg-ok", hint: "Strong match in your documents" },
  medium: { label: "Partly grounded", dot: "bg-warn", hint: "Related chunks found. Verify key details." },
  low: { label: "Weakly grounded", dot: "bg-bad", hint: "Little supporting evidence. Logged as a knowledge gap." },
  none: { label: "No sources found", dot: "bg-bad", hint: "Nothing relevant found. Logged as a knowledge gap." },
};

function useElapsed(running: boolean, startedAt?: number) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, [running]);
  return startedAt ? Math.max(0, (now - startedAt) / 1000) : 0;
}

function StageLine({ ex }: { ex: Exchange }) {
  const running = ex.stage !== "done" && ex.stage !== "queued";
  const elapsed = useElapsed(running, ex.startedAt);
  if (ex.stage === "queued") {
    return <p className="text-[13.5px] text-warn">Waiting for quota. This question sends automatically when the limit resets.</p>;
  }
  const label =
    ex.stage === "retrieving" ? (ex.reranked ? "Searching and reranking chunks" : "Searching chunks") : ex.stage === "retrieved" ? "Reading sources" : "Writing";
  const t = ex.stageTimes;
  return (
    <div className="flex items-center gap-4 text-[13px] text-muted">
      <span className="hairline-progress h-px w-10 bg-line" />
      <span>{label}</span>
      {t && ex.stage !== "retrieving" && (
        <span className="tabular text-faint">
          retrieved in {formatMs((t.embedding_time ?? 0) + (t.search_time ?? 0) + (t.rerank_time ?? 0))}
        </span>
      )}
      <span className="tabular ml-auto text-faint">{elapsed.toFixed(1)} s</span>
    </div>
  );
}

interface Props {
  ex: Exchange;
  onOpenSource: (source: Source) => void;
  onFeedback: (ex: Exchange, rating: "up" | "down") => void;
  onRetry: (ex: Exchange) => void;
}

export function ExchangeView({ ex, onOpenSource, onFeedback, onRetry }: Props) {
  const [panel, setPanel] = useState<"sources" | "timing" | null>(null);
  const [flashRef, setFlashRef] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);

  const sources = ex.sources ?? [];
  const done = ex.stage === "done";
  const g = ex.confidence ? GROUNDING[ex.confidence.level] : null;
  const m = ex.metrics;

  const cite = (ref: number) => {
    setPanel("sources");
    setFlashRef(null);
    setTimeout(() => {
      setFlashRef(ref);
      document.getElementById(`src-${ex.id}-${ref}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 20);
  };

  return (
    <article className="rise border-b border-line-soft py-12 first:pt-4 last:border-b-0">
      <h2 className="font-display text-[22px] font-medium leading-snug tracking-[-0.015em] text-ink">{ex.query}</h2>

      <div className="mt-6 space-y-6">
        {!done && <StageLine ex={ex} />}

        {ex.error ? (
          <div className="text-[14.5px]">
            <p className="text-bad">{ex.error}</p>
            <TextButton onClick={() => onRetry(ex)} className="mt-2 text-ink underline">
              Try again
            </TextButton>
          </div>
        ) : (
          ex.answer && (
            <div className={`text-[16px] leading-[1.75] text-ink-2 ${ex.stage === "generating" ? "cursor" : ""}`}>
              <Markdown text={ex.answer} onCite={cite} maxRef={sources.length} />
            </div>
          )
        )}

        {done && !ex.error && (
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-line-soft pt-5">
            {g && (
              <span className="flex items-center gap-2 text-[13px] text-ink" title={g.hint}>
                <span className={`h-1.5 w-1.5 rounded-full ${g.dot}`} />
                {g.label}
              </span>
            )}
            {m && (
              <span className="tabular text-[13px] text-faint">
                {formatMs(m.total_time)}
                {m.total_tokens > 0 && ` · ${m.total_tokens.toLocaleString()} tokens`}
              </span>
            )}
            <span className="flex flex-wrap items-center gap-x-5 gap-y-2 sm:ml-auto">
              {sources.length > 0 && (
                <TextButton active={panel === "sources"} onClick={() => setPanel(panel === "sources" ? null : "sources")}>
                  Sources {sources.length}
                </TextButton>
              )}
              {m && (
                <TextButton active={panel === "timing"} onClick={() => setPanel(panel === "timing" ? null : "timing")}>
                  Timing
                </TextButton>
              )}
              <TextButton
                onClick={() => {
                  navigator.clipboard?.writeText(ex.answer);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                }}
              >
                {copied ? "Copied" : "Copy"}
              </TextButton>
              {ex.queryId && (
                <>
                  <TextButton active={ex.feedback === "up"} disabled={!!ex.feedback} onClick={() => onFeedback(ex, "up")}>
                    Helpful
                  </TextButton>
                  <TextButton active={ex.feedback === "down"} disabled={!!ex.feedback} onClick={() => onFeedback(ex, "down")}>
                    Not helpful
                  </TextButton>
                </>
              )}
            </span>
          </div>
        )}

        {panel === "timing" && m && (
          <div className="rise rounded-[14px] bg-subtle p-6 ring-1 ring-line-soft">
            <StageBar metrics={m} />
            <dl className="tabular mt-6 grid grid-cols-2 gap-x-8 gap-y-4 text-[13px] sm:grid-cols-4">
              {(
                [
                  ["First token", formatMs(m.ttft)],
                  ["Prompt tokens", m.prompt_tokens.toLocaleString()],
                  ["Completion tokens", m.completion_tokens.toLocaleString()],
                  ["Chunks scanned", String(m.candidates)],
                ] as const
              ).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-faint">{k}</dt>
                  <dd className="mt-1 text-ink">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        {panel === "sources" && sources.length > 0 && (
          <ol className="rise space-y-1">
            {sources.map((s) => (
              <li
                key={s.id}
                id={`src-${ex.id}-${s.ref}`}
                className={`grid grid-cols-[24px_1fr] gap-x-3 rounded-[10px] px-3 py-3 -mx-3 ${flashRef === s.ref ? "flash" : ""}`}
              >
                <span className="tabular pt-px text-[12.5px] font-semibold text-faint">{s.ref}</span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[13px]">
                    <button onClick={() => onOpenSource(s)} className="truncate font-medium text-ink underline-offset-4 hover:underline">
                      {s.source_file}
                    </button>
                    <span className="text-faint">chunk {s.chunk_index}</span>
                    <span className="tabular ml-auto text-faint">
                      {s.rerank_score != null && `relevance ${(s.rerank_score * 100).toFixed(0)}% · `}
                      match {(s.vector_score * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="mt-1.5 line-clamp-3 text-[13.5px] leading-relaxed text-muted">{s.text}</p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </article>
  );
}
