"use client";

import { Health, RateLimit } from "@/lib/api";

export type View = "ask" | "library" | "performance" | "gaps" | "settings";
export type Connection = "online" | "degraded" | "offline" | "checking";

const CONNECTION: Record<Connection, { label: string; dot: string }> = {
  online: { label: "Online", dot: "bg-ok" },
  degraded: { label: "Database offline", dot: "bg-warn" },
  offline: { label: "API offline", dot: "bg-bad" },
  checking: { label: "Connecting", dot: "bg-faint" },
};

interface Props {
  view: View;
  onNavigate: (v: View) => void;
  counts: Partial<Record<View, number>>;
  health: Health | null;
  connection: Connection;
  pingMs: number | null;
  rateLimit: RateLimit | null;
  queued: number;
  onRetryConnection: () => void;
}

const NAV: { id: View; label: string }[] = [
  { id: "ask", label: "Ask" },
  { id: "library", label: "Library" },
  { id: "performance", label: "Performance" },
  { id: "gaps", label: "Knowledge gaps" },
  { id: "settings", label: "Settings" },
];

function compact(n: number) {
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n);
}

export function Sidebar({ view, onNavigate, counts, health, connection, pingMs, rateLimit, queued, onRetryConnection }: Props) {
  const c = CONNECTION[connection];
  const remaining = rateLimit?.remaining ?? 0;
  const limit = rateLimit?.limit ?? 0;
  const pct = limit ? (remaining / limit) * 100 : 0;
  const low = rateLimit && remaining <= Math.ceil(limit * 0.2);
  const up = rateLimit?.upstream;

  return (
    <aside className="flex shrink-0 flex-col gap-6 px-4 pt-5 pb-2 lg:h-screen lg:w-[248px] lg:gap-0 lg:px-6 lg:pt-10 lg:pb-8">
      <nav className="-mx-1 flex gap-1 overflow-x-auto [scrollbar-width:none] lg:mx-0 lg:flex-col lg:gap-0.5 lg:overflow-visible" aria-label="Sections">
        {NAV.map((item) => {
          const active = view === item.id;
          const count = counts[item.id];
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              aria-current={active ? "page" : undefined}
              className={`flex shrink-0 items-center justify-between gap-3 rounded-[9px] px-3 py-2 text-left text-[14px] transition-colors lg:py-[9px] ${
                active ? "bg-surface font-medium text-ink shadow-[0_1px_2px_rgba(0,0,0,0.04)]" : "text-muted hover:text-ink"
              }`}
            >
              {item.label}
              {count ? <span className="tabular text-[12px] text-faint">{count}</span> : null}
            </button>
          );
        })}
      </nav>

      <div className="hidden lg:mt-auto lg:block">
        <div className="space-y-5 border-t border-line pt-6 text-[12.5px]">
          <div>
            <div className="flex items-baseline justify-between">
              <span className="text-muted">Queries this minute</span>
              <span className="tabular text-ink">
                {rateLimit ? `${remaining} / ${limit}` : "–"}
              </span>
            </div>
            <div className="mt-2 h-[3px] overflow-hidden rounded-full bg-[#e6e6e6]">
              <div className={`h-full rounded-full transition-all duration-500 ${remaining === 0 ? "bg-bad" : low ? "bg-warn" : "bg-ink"}`} style={{ width: `${pct}%` }} />
            </div>
            {queued > 0 && (
              <p className="mt-2 text-warn">
                {queued} queued · resumes in {Math.ceil(rateLimit?.reset_in_seconds ?? 0)}s
              </p>
            )}
          </div>

          {up?.remaining_tokens != null && up.limit_tokens != null && (
            <div className="flex items-baseline justify-between">
              <span className="text-muted">Model tokens / min</span>
              <span className="tabular text-ink">
                {compact(up.remaining_tokens)} / {compact(up.limit_tokens)}
              </span>
            </div>
          )}

          <button onClick={onRetryConnection} className="flex w-full items-center justify-between text-left" title={health ? `${health.llm_provider} · ${health.llm_model}` : "Retry"}>
            <span className="flex items-center gap-2 text-muted">
              <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
              {c.label}
            </span>
            {pingMs != null && connection !== "offline" && <span className="tabular text-faint">{pingMs} ms</span>}
          </button>
        </div>
      </div>
    </aside>
  );
}
