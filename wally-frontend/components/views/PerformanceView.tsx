"use client";

import { useState } from "react";
import { MetricsSummary, RecentQuery, formatMs } from "@/lib/api";
import { Figure, SectionTitle, STAGES, StageBar, TextButton, ViewHeader } from "../ui";

function niceMax(v: number) {
  if (v <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(v));
  const n = v / pow;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow;
}

function LatencyColumns({ queries }: { queries: RecentQuery[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = niceMax(Math.max(...queries.map((q) => q.total_time)));
  const h = hover != null ? queries[hover] : null;

  return (
    <div className="relative">
      <div className="flex">
        <div className="tabular flex h-56 w-12 shrink-0 flex-col justify-between pr-3 text-right text-[11px] text-faint">
          <span>{formatMs(max)}</span>
          <span>{formatMs(max / 2)}</span>
          <span>0</span>
        </div>
        <div className="relative h-56 flex-1 border-b border-line" onMouseLeave={() => setHover(null)}>
          <div className="pointer-events-none absolute inset-x-0 top-0 border-t border-dashed border-line-soft" />
          <div className="pointer-events-none absolute inset-x-0 top-1/2 border-t border-dashed border-line-soft" />
          <div className="absolute inset-0 flex items-end gap-[3px]">
            {queries.map((q, i) => {
              const segs = STAGES.map((s) => ({ ...s, v: q[s.key] ?? 0 })).filter((s) => s.v > 0);
              return (
                <div
                  key={q.id}
                  onMouseEnter={() => setHover(i)}
                  className={`flex h-full max-w-8 flex-1 flex-col-reverse transition-opacity ${hover != null && hover !== i ? "opacity-30" : ""}`}
                >
                  <div className="flex flex-col-reverse gap-[2px]" style={{ height: `${(q.total_time / max) * 100}%` }}>
                    {segs.map((s, si) => (
                      <div key={s.key} className={`${s.color} ${si === segs.length - 1 ? "rounded-t-[4px]" : ""}`} style={{ flexGrow: s.v, flexBasis: 0, minHeight: 2 }} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {h && (
        <div className="pointer-events-none absolute top-0 right-0 z-10 w-64 rounded-[12px] bg-surface p-4 text-[12.5px] shadow-[0_12px_32px_-12px_rgba(0,0,0,0.25)] ring-1 ring-line">
          <p className="line-clamp-2 font-medium text-ink">{h.query}</p>
          <div className="tabular mt-3 space-y-1.5">
            {STAGES.map((s) => (
              <p key={s.key} className="flex items-center justify-between gap-4">
                <span className="flex items-center gap-2 text-muted">
                  <span className={`h-2 w-2 rounded-[2px] ${s.color}`} />
                  {s.label}
                </span>
                <span className="text-ink">{formatMs(h[s.key])}</span>
              </p>
            ))}
            <p className="flex justify-between border-t border-line-soft pt-1.5 text-ink">
              <span>Total, {h.total_tokens.toLocaleString()} tokens</span>
              <span>{formatMs(h.total_time)}</span>
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function LatencyTable({ queries }: { queries: RecentQuery[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="tabular w-full min-w-[640px] text-[13px]">
        <thead>
          <tr className="text-left text-[12px] text-faint">
            <th className="py-2 pr-4 font-normal">Question</th>
            {STAGES.map((s) => (
              <th key={s.key} className="py-2 pr-4 text-right font-normal">
                {s.label}
              </th>
            ))}
            <th className="py-2 pr-4 text-right font-normal">First token</th>
            <th className="py-2 pr-4 text-right font-normal">Tokens</th>
            <th className="py-2 text-right font-normal">Total</th>
          </tr>
        </thead>
        <tbody>
          {[...queries].reverse().map((q) => (
            <tr key={q.id} className="border-t border-line-soft">
              <td className="max-w-[16rem] truncate py-2.5 pr-4 text-ink" title={q.query}>
                {q.query}
              </td>
              {STAGES.map((s) => (
                <td key={s.key} className="py-2.5 pr-4 text-right text-muted">
                  {q[s.key] ? formatMs(q[s.key]) : "–"}
                </td>
              ))}
              <td className="py-2.5 pr-4 text-right text-muted">{formatMs(q.ttft)}</td>
              <td className="py-2.5 pr-4 text-right text-muted">{q.total_tokens.toLocaleString()}</td>
              <td className="py-2.5 text-right text-ink">{formatMs(q.total_time)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PerformanceView({ metrics }: { metrics: MetricsSummary | null }) {
  const [asTable, setAsTable] = useState(false);
  const m = metrics;
  const has = !!m && m.count > 0;

  return (
    <div className="mx-auto w-full max-w-[960px] px-6 py-12 sm:px-12 sm:py-16">
      <ViewHeader title="Performance" description="Live timings for every question since the server started. Token counts come from the model provider." />

      <div className="grid grid-cols-2 gap-x-10 gap-y-10 border-y border-line-soft py-10 md:grid-cols-4">
        <Figure label="Median response" value={formatMs(has ? m.p50_total_time : null)} note={has ? `95th percentile ${formatMs(m.p95_total_time)}` : undefined} />
        <Figure label="First token" value={formatMs(has && m.avg_ttft ? m.avg_ttft : null)} note="average, streamed" />
        <Figure label="Tokens per answer" value={has ? m.avg_tokens.toLocaleString() : "–"} note={has ? `${m.total_tokens.toLocaleString()} in total` : undefined} />
        <Figure label="Questions" value={has ? m.count.toLocaleString() : "0"} note="since server start" />
      </div>

      {!has ? (
        <p className="py-16 text-[14px] text-muted">Ask a question and its timings appear here.</p>
      ) : (
        <>
          <section className="mt-14">
            <SectionTitle>Where the time goes</SectionTitle>
            <StageBar
              height={10}
              metrics={{ embedding_time: m.avg_embedding_time, search_time: m.avg_search_time, rerank_time: m.avg_rerank_time, llm_time: m.avg_llm_time }}
            />
            <p className="mt-4 max-w-xl text-[13px] leading-relaxed text-faint">
              Averages across recent questions. Embedding and vector search run locally; generation is the round trip to the language model.
            </p>
          </section>

          <section className="mt-16">
            <SectionTitle aside={<TextButton onClick={() => setAsTable((v) => !v)}>{asTable ? "Show chart" : "Show table"}</TextButton>}>
              Recent questions
            </SectionTitle>
            {asTable ? <LatencyTable queries={m.recent} /> : <LatencyColumns queries={m.recent} />}
            {!asTable && (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-[12px] text-faint">
                <span className="flex flex-wrap gap-x-5 gap-y-2">
                  {STAGES.map((s) => (
                    <span key={s.key} className="flex items-center gap-2 text-muted">
                      <span className={`h-2 w-2 rounded-[2px] ${s.color}`} />
                      {s.label}
                    </span>
                  ))}
                </span>
                <span>oldest to newest, last {m.recent.length}</span>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
