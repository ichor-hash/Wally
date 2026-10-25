"use client";

import { ReactNode } from "react";
import { Health } from "@/lib/api";
import { SectionTitle, Toggle, ViewHeader } from "../ui";

export interface Settings {
  streaming: boolean;
  rerank: boolean;
  topK: number;
}

function Row({ title, description, control }: { title: string; description: ReactNode; control: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-10 border-b border-line-soft py-7">
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

  const system: [string, string | number][] = health
    ? [
        ["API", health.status === "healthy" ? "Healthy" : "Degraded"],
        ["Vector database", `Qdrant, ${health.database_status}`],
        ["Collection", health.collection],
        ["Indexed", `${health.total_documents} ${health.total_documents === 1 ? "document" : "documents"}, ${health.total_chunks.toLocaleString()} chunks`],
        ["Embedding model", `${health.embedding_model.split("/").pop()} (${health.dimension} dimensions)`],
        ["Language model", `${health.llm_model} via ${health.llm_provider}`],
        ["Reranker", `${rerankModel}, ${health.reranker_loaded ? "loaded" : "loads on first use"}`],
        ["Chunking", `${health.chunk_size} characters, ${health.chunk_overlap} overlap`],
        ["Similarity", health.similarity_metric],
      ]
    : [];

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 py-12 sm:px-12 sm:py-16">
      <ViewHeader title="Settings" description="Saved in this browser. They apply to the next question you ask." />

      <section>
        <SectionTitle>Answers</SectionTitle>
        <div className="border-t border-line-soft">
          <Row
            title="Stream responses"
            description="Show the answer as it is written instead of waiting for the full response."
            control={<Toggle label="Stream responses" checked={settings.streaming} onChange={(v) => onChange({ ...settings, streaming: v })} />}
          />
          <Row
            title="Rerank chunks"
            description={
              <>
                Fetch {settings.topK * 3} candidate chunks, then re-score each one against the question with a cross-encoder ({rerankModel}). More precise,
                slightly slower.
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
        <SectionTitle>System</SectionTitle>
        {health ? (
          <dl className="border-t border-line-soft text-[14px]">
            {system.map(([k, v]) => (
              <div key={k} className="flex flex-col gap-1 border-b border-line-soft py-4 sm:flex-row sm:justify-between sm:gap-8">
                <dt className="text-muted">{k}</dt>
                <dd className="break-all text-ink sm:text-right">{v}</dd>
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
