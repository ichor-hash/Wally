"use client";

import { ReactNode, useState } from "react";
import { QueryMetrics, formatMs } from "@/lib/api";

export function ViewHeader({ title, description, aside }: { title: string; description?: ReactNode; aside?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-6 pb-10">
      <div className="max-w-xl">
        <h1 className="font-display text-[34px] font-medium leading-[1.1] tracking-[-0.02em] text-ink">{title}</h1>
        {description && <p className="mt-3 text-[15px] leading-relaxed text-muted">{description}</p>}
      </div>
      {aside}
    </header>
  );
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-5 flex items-baseline justify-between gap-4">
      <h2 className="font-display text-[17px] font-medium tracking-[-0.01em] text-ink">{children}</h2>
      {aside}
    </div>
  );
}

export function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[13px] text-muted">{label}</p>
      <p className="tabular mt-2 font-display text-[40px] font-light leading-none tracking-[-0.03em] text-ink">{value}</p>
      {note && <p className="tabular mt-2 text-[12.5px] text-faint">{note}</p>}
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative h-[22px] w-[38px] shrink-0 rounded-full transition-colors duration-200 ${checked ? "bg-ink" : "bg-[#d6d6d6]"}`}
    >
      <span
        className={`absolute top-[3px] left-0 h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${checked ? "translate-x-[19px]" : "translate-x-[3px]"}`}
      />
    </button>
  );
}

export function TextButton({ children, onClick, active, disabled, className = "" }: { children: ReactNode; onClick?: () => void; active?: boolean; disabled?: boolean; className?: string }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`text-[13px] underline-offset-4 transition-colors hover:text-ink hover:underline disabled:no-underline disabled:hover:text-inherit ${active ? "text-ink" : "text-muted"} ${className}`}
    >
      {children}
    </button>
  );
}

export function PrimaryButton({ children, onClick, type = "button", disabled }: { children: ReactNode; onClick?: () => void; type?: "button" | "submit"; disabled?: boolean }) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className="h-10 shrink-0 rounded-[10px] bg-button px-5 text-[14px] font-medium text-white transition-colors hover:bg-button-hover disabled:bg-[#d6d6d6] disabled:text-white"
    >
      {children}
    </button>
  );
}

export const STAGES = [
  { key: "embedding_time", label: "Embed", color: "bg-stage-1" },
  { key: "search_time", label: "Search", color: "bg-stage-2" },
  { key: "rerank_time", label: "Rerank", color: "bg-stage-3" },
  { key: "llm_time", label: "Generate", color: "bg-stage-4" },
] as const;

type StageTimes = Pick<QueryMetrics, "embedding_time" | "search_time" | "rerank_time" | "llm_time">;

/** Horizontal stacked bar of pipeline stages. */
export function StageBar({ metrics, height = 6, legend = true }: { metrics: StageTimes; height?: number; legend?: boolean }) {
  const [hover, setHover] = useState<string | null>(null);
  const parts = STAGES.map((s) => ({ ...s, value: metrics[s.key] ?? 0 })).filter((p) => p.value > 0);
  const total = parts.reduce((n, p) => n + p.value, 0) || 1;
  return (
    <div>
      <div className="flex w-full gap-[2px]" style={{ height }} onMouseLeave={() => setHover(null)}>
        {parts.map((p, i) => (
          <div
            key={p.key}
            onMouseEnter={() => setHover(p.key)}
            title={`${p.label} ${formatMs(p.value)} · ${Math.round((p.value / total) * 100)}%`}
            className={`${p.color} transition-opacity ${hover && hover !== p.key ? "opacity-35" : ""} ${i === 0 ? "rounded-l-full" : ""} ${i === parts.length - 1 ? "rounded-r-full" : ""}`}
            style={{ width: `${(p.value / total) * 100}%`, minWidth: 3 }}
          />
        ))}
      </div>
      {legend && (
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-[12.5px] text-muted">
          {parts.map((p) => (
            <span key={p.key} className={`flex items-center gap-2 transition-opacity ${hover && hover !== p.key ? "opacity-40" : ""}`}>
              <span className={`h-2 w-2 rounded-[2px] ${p.color}`} />
              {p.label}
              <span className="tabular text-ink">{formatMs(p.value)}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
