"use client";

import { ReactNode } from "react";
import { Health, RetrievalMode, formatUsd } from "@/lib/api";
import { SectionTitle, Toggle, ViewHeader } from "../ui";

export interface Settings {
  streaming: boolean;
  rerank: boolean;
  topK: number;
  mode: RetrievalMode;
  visuals: boolean;
}

const MODES: { id: RetrievalMode; label: string; hint: string }[] = [
  { id: "hybrid", label: "Hybrid", hint: "Meaning and exact terms, merged. Best overall." },
  { id: "dense", label: "Meaning", hint: "Vector similarity only. Good for paraphrased questions." },
  { id: "keyword", label: "Keywords", hint: "BM25 only. Good for codes, names and exact phrases." },
];

function Row({ title, description, control }: { title: string; description: ReactNode; control: ReactNode }) {
  return (
    <div className="flex flex-col gap-4 border-b border-line-soft py-7 sm:flex-row sm:items-start sm:justify-between sm:gap-10">
      <div className="max-w-lg">
        <p className="text-[15px] font-medium text-ink">{title}</p>
        <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">{description}</p>
      </div>
      <div className="pt-0.5">{control}</div>
    </div>
  );
}

interface Props {
  settings: Settings;
  onChange: (s: Settings) => void;
  health: Health | null;
  rerankerWarming: boolean;
}

export function SettingsView({ settings, onChange, health, rerankerWarming }: Props) {
  const rerankModel = health?.reranker_model.split("/").pop() ?? "ms-marco-MiniLM-L-6-v2";
  const hybridOff = health ? !health.hybrid_available : false;
  const mode = hybridOff ? "dense" : settings.mode;
  const price = health?.pricing;
  const cache = health?.answer_cache;

  const system: [string, string | number][] = health
    ? [
        ["API", health.status === "healthy" ? "Healthy" : "Degraded"],
        ["Vector database", `Qdrant, ${health.database_status} (${health.qdrant_url})`],
        ["Collection", health.collection],
        ["Indexed", `${health.total_documents} ${health.total_documents === 1 ? "document" : "documents"}, ${health.total_chunks.toLocaleString()} chunks`],
        ["Embedding model", `${health.embedding_model.split("/").pop()} (${health.dimension} dimensions)`],
        ["Language model", health.llm_model ? `${health.llm_model} via ${health.llm_provider}` : `Not configured: ${health.llm_error}`],
        ["Reranker", `${rerankModel}, ${health.reranker_loaded ? "loaded" : "loads on first use"}`],
        ["Chunking", `${health.chunk_strategy === "structure" ? "Structure-aware" : "Fixed window"}, ${health.chunk_size} characters, ${health.chunk_overlap} overlap`],
        ["Retrieval", health.similarity_metric],
        ["Token price", price?.configured ? `${formatUsd(price.input_per_m)} in / ${formatUsd(price.output_per_m)} out per million` : "Not set (free tier or local model)"],
        ["Answer cache", cache?.enabled ? `${cache.entries} of ${cache.max_entries} entries, kept ${Math.round(cache.ttl_seconds / 60)} min` : "Off"],
        ["Budgets", `${health.max_context_chars.toLocaleString()} context characters, ${health.max_output_tokens} output tokens`],
      ]
    : [];

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 py-12 sm:px-12 sm:py-16">
      <ViewHeader title="Settings" description="Saved in this browser. They apply to the next question you ask." />

      <section>
        <SectionTitle>Retrieval</SectionTitle>
        <div className="border-t border-line-soft">
          <Row
            title="Search mode"
            description={
              hybridOff ? (
                <>This collection was indexed before hybrid search existed, so only meaning search is available. Re-upload the documents to enable keywords.</>
              ) : (
                <>{MODES.find((m) => m.id === mode)?.hint}</>
              )
            }
            control={
              <div role="radiogroup" aria-label="Search mode" className="flex rounded-[10px] bg-subtle p-[3px] ring-1 ring-line-soft">
                {MODES.map((m) => (
                  <button
                    key={m.id}
                    role="radio"
                    aria-checked={mode === m.id}
                    disabled={hybridOff && m.id !== "dense"}
                    onClick={() => onChange({ ...settings, mode: m.id })}
                    className={`rounded-[8px] px-3 py-1.5 text-[13px] transition-colors disabled:opacity-40 ${
                      mode === m.id ? "bg-surface font-medium text-ink shadow-[0_1px_2px_rgba(0,0,0,0.08)]" : "text-muted hover:text-ink"
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            }
          />
          <Row
            title="Rerank chunks"
            description={
              <>
                Fetch {settings.topK * 3} candidate chunks, then re-score each one against the question with a cross-encoder ({rerankModel}). It finds
                the right chunk more often and is what makes the grounding label trustworthy; see Evaluation. Adds about a quarter of a second.
                {rerankerWarming && <span className="text-ink"> Loading the model.</span>}
              </>
            }
            control={<Toggle label="Rerank chunks" checked={settings.rerank} onChange={(v) => onChange({ ...settings, rerank: v })} />}
          />
          <Row
            title="Sources per answer"
            description="How many chunks the model reads. More context can help broad questions but costs tokens."
            control={
              <div className="flex w-40 items-center gap-4">
                <input
                  type="range"
                  min={1}
                  max={15}
                  value={settings.topK}
                  onChange={(e) => onChange({ ...settings, topK: Number(e.target.value) })}
                  className="w-full accent-[#1a1a1a]"
                  aria-label="Sources per answer"
                />
                <span className="tabular w-5 text-right text-[14px] text-ink">{settings.topK}</span>
              </div>
            }
          />
        </div>
      </section>

      <section className="mt-16">
        <SectionTitle>Answers</SectionTitle>
        <div className="border-t border-line-soft">
          <Row
            title="Stream responses"
            description="Show the answer as it is written instead of waiting for the full response."
            control={<Toggle label="Stream responses" checked={settings.streaming} onChange={(v) => onChange({ ...settings, streaming: v })} />}
          />
          <Row
            title="Charts and tables"
            description={
              health && !health.visuals_available ? (
                <>Unavailable: the server has no visuals prompt. Run npm run gen:prompt in the frontend folder and restart the API.</>
              ) : (
                <>
                  When an answer compares several numbers, let the model draw them as a chart or table (rendered with OpenUI). Adds roughly 700 prompt
                  tokens to each question.
                </>
              )
            }
            control={
              <Toggle
                label="Charts and tables"
                checked={settings.visuals && (health?.visuals_available ?? true)}
                onChange={(v) => onChange({ ...settings, visuals: v })}
              />
            }
          />
        </div>
      </section>

      <section className="mt-16">
        <SectionTitle>System</SectionTitle>
        {health ? (
          <dl className="border-t border-line-soft text-[14px]">
            {system.map(([k, v]) => (
              <div key={k} className="flex flex-col gap-1 border-b border-line-soft py-4 sm:flex-row sm:justify-between sm:gap-8">
                <dt className="shrink-0 text-muted">{k}</dt>
                <dd className="break-words text-ink sm:text-right">{v}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-[14px] text-muted">System details are unavailable while the API is offline.</p>
        )}
      </section>
    </div>
  );
}
