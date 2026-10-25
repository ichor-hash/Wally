"use client";

import { Insights, KnowledgeGap, timeAgo } from "@/lib/api";
import { Figure, TextButton, ViewHeader } from "../ui";

const REASON: Record<KnowledgeGap["reason"], string> = {
  no_results: "No chunks found",
  low_relevance: "Weak match",
  negative_feedback: "Marked not helpful",
};

interface Props {
  insights: Insights | null;
  onResolve: (gap: KnowledgeGap) => void;
  onAsk: (query: string) => void;
}

export function GapsView({ insights, onResolve, onAsk }: Props) {
  const gaps = insights?.gaps ?? [];
  const fb = insights?.feedback ?? { up: 0, down: 0 };
  const rated = fb.up + fb.down;
  const threshold = Math.round((insights?.gap_threshold ?? 0.25) * 100);

  return (
    <div className="mx-auto w-full max-w-[960px] px-6 py-12 sm:px-12 sm:py-16">
      <ViewHeader
        title="Knowledge gaps"
        description={`Questions the library could not answer well: matches below ${threshold}% similarity, and answers people marked not helpful. Add a document that covers them, then resolve.`}
      />

      <div className="grid grid-cols-2 gap-x-10 gap-y-10 border-y border-line-soft py-10 md:grid-cols-4">
        <Figure label="Open gaps" value={String(gaps.length)} />
        <Figure label="Times asked" value={String(gaps.reduce((n, g) => n + g.count, 0))} />
        <Figure label="Rated helpful" value={rated ? `${Math.round((fb.up / rated) * 100)}%` : "–"} note={rated ? `${fb.up} of ${rated} ratings` : "no ratings yet"} />
        <Figure label="Not helpful" value={String(fb.down)} />
      </div>

      {gaps.length === 0 ? (
        <p className="py-16 text-[14px] text-muted">No gaps. Every question so far found solid sources.</p>
      ) : (
        <ul className="mt-6">
          {gaps.map((g) => (
            <li key={g.normalized} className="group flex flex-col gap-3 border-b border-line-soft py-6 sm:flex-row sm:items-baseline sm:justify-between sm:gap-10">
              <div className="min-w-0">
                <p className="font-display text-[17px] font-medium leading-snug text-ink">{g.query}</p>
                <p className="tabular mt-2 text-[13px] text-faint">
                  {REASON[g.reason]}
                  {g.reason !== "negative_feedback" && ` · best match ${(g.top_score * 100).toFixed(0)}%`}
                  {` · asked ${g.count}× · ${timeAgo(g.last_seen)}`}
                </p>
              </div>
              <div className="flex shrink-0 gap-5">
                <TextButton onClick={() => onAsk(g.query)}>Ask again</TextButton>
                <TextButton onClick={() => onResolve(g)} className="text-ink">
                  Resolve
                </TextButton>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
