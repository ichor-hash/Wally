"use client";

import { useEffect, useState } from "react";
import { AgentStep, Confidence, Correction, QueryMetrics, Revision, Source, Verdict, Verification, formatMs, formatUsd } from "@/lib/api";
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
  agent?: boolean;
  stage: "queued" | "retrieving" | "retrieved" | "generating" | "verifying" | "revising" | "done";
  stageTimes?: { embedding_time?: number; search_time?: number; rerank_time?: number };
  steps?: AgentStep[];
  verification?: Verification;
  correction?: Correction | null;
  revised?: Revision | null;
  error?: string;
  feedback?: "up" | "down";
  startedAt?: number;
}

type Panel = "sources" | "checks" | "steps" | "timing";

const MATCHED_BY: Record<Source["matched_by"], { label: string; hint: string }> = {
  both: { label: "meaning + keywords", hint: "Found by both vector similarity and BM25 keyword search" },
  dense: { label: "meaning", hint: "Found by vector similarity" },
  keyword: { label: "keywords", hint: "Found by BM25 keyword search; vector similarity alone missed it" },
};

const GROUNDING: Record<Confidence["level"], { label: string; dot: string; hint: string }> = {
  high: { label: "Well grounded", dot: "bg-ok", hint: "Strong match in your documents" },
  medium: { label: "Partly grounded", dot: "bg-warn", hint: "Related chunks found. Verify key details." },
  low: { label: "Weakly grounded", dot: "bg-bad", hint: "Little supporting evidence. Logged as a knowledge gap." },
  none: { label: "No sources found", dot: "bg-bad", hint: "Nothing relevant found. Logged as a knowledge gap." },
};

const VERDICT: Record<Verdict, { label: string; dot: string }> = {
  SUPPORTED: { label: "Supported", dot: "bg-ok" },
  PARTIAL: { label: "Partly supported", dot: "bg-warn" },
  UNSUPPORTED: { label: "Not supported", dot: "bg-bad" },
};

const STAGE_LABEL: Record<string, string> = {
  retrieved: "Reading sources",
  generating: "Writing",
  verifying: "Checking each claim against its sources",
  revising: "Correcting an unsupported claim",
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
    ex.stage === "retrieving"
      ? ex.reranked
        ? "Searching and reranking chunks"
        : "Searching chunks"
      : ex.stage === "generating" && ex.agent && !ex.answer
        ? "Working with tools"
        : STAGE_LABEL[ex.stage];
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

/** "3/3 claims verified", or how many were not. */
function VerificationBadge({ v, onOpen }: { v: Verification; onOpen: () => void }) {
  if (v.status === "no_claims") return null;
  if (v.status === "error") {
    return (
      <button onClick={onOpen} className="flex items-center gap-2 text-[13px] text-muted" title={v.error ?? undefined}>
        <span className="h-1.5 w-1.5 rounded-full bg-faint" />
        Not checked
      </button>
    );
  }
  const clean = v.unsupported === 0 && v.partial === 0;
  return (
    <button onClick={onOpen} className="flex items-center gap-2 text-[13px] text-ink underline-offset-4 hover:underline" title="Each cited claim checked against the chunks it cites">
      <span className={`h-1.5 w-1.5 rounded-full ${v.unsupported ? "bg-bad" : clean ? "bg-ok" : "bg-warn"}`} />
      {clean
        ? `${v.supported}/${v.total} claims verified`
        : v.unsupported
          ? `${v.unsupported} of ${v.total} claims not supported`
          : `${v.supported}/${v.total} claims fully supported`}
    </button>
  );
}

function ChecksPanel({ ex, onCite }: { ex: Exchange; onCite: (ref: number) => void }) {
  const [showOriginal, setShowOriginal] = useState(false);
  const v = ex.verification;
  if (!v) return null;
  return (
    <div className="rise rounded-[14px] bg-subtle p-6 ring-1 ring-line-soft">
      <p className="text-[13px] leading-relaxed text-muted">
        After writing, Ethan checks every cited claim against only the chunks it cites.
        {ex.revised && (
          <>
            {" "}
            The first draft had {ex.revised.problems.length} unsupported {ex.revised.problems.length === 1 ? "claim" : "claims"}, so the answer was
            rewritten and checked again.{" "}
            <button onClick={() => setShowOriginal((s) => !s)} className="text-ink underline underline-offset-4">
              {showOriginal ? "Hide first draft" : "Show first draft"}
            </button>
          </>
        )}
      </p>
      {showOriginal && ex.revised && (
        <div className="mt-4 rounded-[10px] bg-surface p-4 text-[13.5px] leading-relaxed text-muted ring-1 ring-line-soft">
          <p className="mb-2 text-[12px] font-medium text-faint">First draft</p>
          <p className="whitespace-pre-wrap">{ex.revised.original}</p>
          <ul className="mt-3 space-y-1 text-bad">
            {ex.revised.problems.map((p) => (
              <li key={p.id}>
                &ldquo;{p.text}&rdquo;: {p.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {v.status === "error" ? (
        <p className="mt-4 text-[13.5px] text-muted">The check could not run: {v.error}</p>
      ) : (
        <ol className="mt-5 space-y-4">
          {v.claims.map((c) => {
            const verdict = VERDICT[c.verdict ?? "PARTIAL"];
            return (
              <li key={c.id} className="grid grid-cols-[14px_1fr] gap-x-3 text-[13.5px]">
                <span className={`mt-[7px] h-1.5 w-1.5 rounded-full ${verdict.dot}`} />
                <div className="min-w-0">
                  <p className="leading-relaxed text-ink-2">
                    {c.text}{" "}
                    {c.refs.map((r) => (
                      <button key={r} onClick={() => onCite(r)} className="tabular text-[12px] font-semibold text-muted hover:text-ink">
                        [{r}]
                      </button>
                    ))}
                  </p>
                  <p className="mt-0.5 text-[12.5px] text-faint">
                    {verdict.label}
                    {c.reason ? `: ${c.reason}` : ""}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function StepsPanel({ steps, onCite }: { steps: AgentStep[]; onCite: (ref: number) => void }) {
  return (
    <ol className="rise space-y-3 rounded-[14px] bg-subtle p-6 text-[13.5px] ring-1 ring-line-soft">
      {steps.map((s, i) => (
        <li key={i} className="grid grid-cols-[24px_1fr] gap-x-3">
          <span className="tabular pt-px text-[12.5px] font-semibold text-faint">{i + 1}</span>
          <div className="min-w-0">
            <p className="text-ink">
              {s.name === "calculate" ? "Calculated" : s.name === "search_documents" ? "Searched again" : s.name}{" "}
              <code className="rounded-[4px] bg-surface px-1.5 py-0.5 text-[12.5px] ring-1 ring-line-soft">
                {String(s.args.expression ?? s.args.query ?? JSON.stringify(s.args))}
              </code>
            </p>
            <p className={`mt-1 ${s.ok ? "text-muted" : "text-bad"}`}>
              {s.name === "calculate" ? `= ${s.result}` : s.result}
              {s.refs.length > 0 && (
                <>
                  {" "}
                  (
                  {s.refs.map((r, j) => (
                    <button key={r} onClick={() => onCite(r)} className="tabular text-ink underline underline-offset-2">
                      {j > 0 ? ", " : ""}
                      {r}
                    </button>
                  ))}
                  )
                </>
              )}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}

interface Props {
  ex: Exchange;
  onOpenSource: (source: Source) => void;
  onFeedback: (ex: Exchange, rating: "up" | "down") => void;
  onRetry: (ex: Exchange) => void;
}

export function ExchangeView({ ex, onOpenSource, onFeedback, onRetry }: Props) {
  const [panel, setPanel] = useState<Panel | null>(null);
  const [flashRef, setFlashRef] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);

  const sources = ex.sources ?? [];
  const steps = ex.steps ?? [];
  const done = ex.stage === "done";
  const writing = ex.stage === "generating";
  const g = ex.confidence ? GROUNDING[ex.confidence.level] : null;
  const m = ex.metrics;
  const toggle = (p: Panel) => setPanel(panel === p ? null : p);

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

        {ex.correction?.improved && (
          <p className="text-[13px] text-muted">
            The first search found little, so Ethan searched again as <span className="text-ink">&ldquo;{ex.correction.query}&rdquo;</span>.
          </p>
        )}

        {!done && steps.length > 0 && (
          <ul className="space-y-1 text-[13px] text-muted">
            {steps.map((s, i) => (
              <li key={i} className="tabular">
                {s.name === "calculate" ? `Calculated ${String(s.args.expression)} = ${s.result}` : `Searched again: ${String(s.args.query)}`}
              </li>
            ))}
          </ul>
        )}

        {ex.error ? (
          <div className="text-[14.5px]">
            <p className="text-bad">{ex.error}</p>
            <TextButton onClick={() => onRetry(ex)} className="mt-2 text-ink underline">
              Try again
            </TextButton>
          </div>
        ) : (
          ex.answer && (
            <div className={`text-[16px] leading-[1.75] text-ink-2 ${writing ? "cursor" : ""}`}>
              <Markdown text={ex.answer} onCite={cite} maxRef={sources.length} streaming={writing} />
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
            {ex.verification && <VerificationBadge v={ex.verification} onOpen={() => toggle("checks")} />}
            {m && (
              <span className="tabular text-[13px] text-faint">
                {m.cached ? "From cache" : formatMs(m.total_time)}
                {m.total_tokens > 0 && ` · ${m.total_tokens.toLocaleString()} tokens`}
                {m.cost_usd > 0 && ` · ${formatUsd(m.cost_usd)}`}
                {m.cached && m.tokens_saved > 0 && ` · ${m.tokens_saved.toLocaleString()} tokens saved`}
              </span>
            )}
            <span className="flex flex-wrap items-center gap-x-5 gap-y-2 sm:ml-auto">
              {sources.length > 0 && (
                <TextButton active={panel === "sources"} onClick={() => toggle("sources")}>
                  Sources {sources.length}
                </TextButton>
              )}
              {ex.verification && ex.verification.status !== "no_claims" && (
                <TextButton active={panel === "checks"} onClick={() => toggle("checks")}>
                  Checks
                </TextButton>
              )}
              {steps.length > 0 && (
                <TextButton active={panel === "steps"} onClick={() => toggle("steps")}>
                  Steps {steps.length}
                </TextButton>
              )}
              {m && (
                <TextButton active={panel === "timing"} onClick={() => toggle("timing")}>
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

        {panel === "checks" && <ChecksPanel ex={ex} onCite={cite} />}
        {panel === "steps" && steps.length > 0 && <StepsPanel steps={steps} onCite={cite} />}

        {panel === "timing" && m && (
          <div className="rise rounded-[14px] bg-subtle p-6 ring-1 ring-line-soft">
            {m.cached ? (
              <p className="text-[13.5px] leading-relaxed text-muted">
                Served from the answer cache: the same question was asked since the library last changed, so nothing was searched or generated.
              </p>
            ) : (
              <StageBar metrics={m} />
            )}
            <dl className="tabular mt-6 grid grid-cols-2 gap-x-8 gap-y-4 text-[13px] sm:grid-cols-4">
              {(
                [
                  ["First token", formatMs(m.ttft)],
                  ["Prompt tokens", m.prompt_tokens.toLocaleString()],
                  ["Completion tokens", m.completion_tokens.toLocaleString()],
                  ["Model calls", String(m.llm_calls ?? 1)],
                  ["Chunks scanned", String(m.candidates)],
                  ["Search mode", m.mode === "dense" ? "Meaning" : m.mode === "keyword" ? "Keywords" : "Hybrid"],
                  ["Tool calls", String(m.agent_steps ?? 0)],
                  ["Cost", m.cached ? `${formatUsd(m.cost_saved_usd ?? 0)} saved` : formatUsd(m.cost_usd)],
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
                    {s.matched_by && (
                      <span className="text-faint" title={MATCHED_BY[s.matched_by].hint}>
                        via {MATCHED_BY[s.matched_by].label}
                      </span>
                    )}
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
