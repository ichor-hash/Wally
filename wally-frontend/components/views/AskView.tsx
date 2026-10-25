"use client";

import { FormEvent, KeyboardEvent, RefObject } from "react";
import { DocumentInfo, RateLimit, Source } from "@/lib/api";
import { Exchange, ExchangeView } from "../Exchange";
import { Connection } from "../Sidebar";
import { Settings } from "./SettingsView";
import { PrimaryButton, TextButton } from "../ui";

interface Props {
  exchanges: Exchange[];
  documents: DocumentInfo[];
  companyName?: string;
  input: string;
  onInput: (v: string) => void;
  onAsk: (q: string) => void;
  onStop: () => void;
  onClear: () => void;
  busy: boolean;
  queued: number;
  settings: Settings;
  rateLimit: RateLimit | null;
  connection: Connection;
  scrollRef: RefObject<HTMLDivElement | null>;
  onScroll: () => void;
  onOpenSource: (s: Source) => void;
  onFeedback: (ex: Exchange, rating: "up" | "down") => void;
  onRetry: (ex: Exchange) => void;
  onOpenSettings: () => void;
  onOpenLibrary: () => void;
}

export function AskView({ scrollRef, ...p }: Props) {
  const totalChunks = p.documents.reduce((n, d) => n + d.chunks, 0);
  const low = p.rateLimit && p.rateLimit.remaining > 0 && p.rateLimit.remaining <= Math.ceil(p.rateLimit.limit * 0.2);
  const empty = p.exchanges.length === 0;

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!p.input.trim()) return;
    p.onAsk(p.input);
    p.onInput("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const suggestions = [
    ...p.documents.slice(0, 2).map((d) => `Summarize the key points of ${d.name}`),
    "Which topics does the knowledge base cover?",
    "What should a new team member read first?",
  ].slice(0, 3);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scrollRef} onScroll={p.onScroll} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[720px] px-6 sm:px-10">
          {empty ? (
            <div className="flex min-h-[60vh] flex-col justify-center py-16">
              {p.companyName && <p className="mb-5 text-[13px] text-faint">Knowledge assistant for {p.companyName}</p>}
              <h1 className="font-display text-[44px] font-medium leading-[1.05] tracking-[-0.03em] text-ink sm:text-[52px]">
                Ask your documents.
              </h1>
              <p className="mt-5 max-w-md text-[16px] leading-relaxed text-muted">
                Every answer is written from your own files and points to the exact passages it used.
              </p>

              {p.documents.length > 0 ? (
                <>
                  <p className="tabular mt-10 text-[13px] text-faint">
                    {p.documents.length} {p.documents.length === 1 ? "document" : "documents"} · {totalChunks.toLocaleString()} passages indexed
                  </p>
                  <ul className="mt-4 border-t border-line-soft">
                    {suggestions.map((s) => (
                      <li key={s} className="border-b border-line-soft">
                        <button
                          onClick={() => p.onAsk(s)}
                          className="group flex w-full items-center justify-between gap-6 py-4 text-left text-[15px] text-ink-2 transition-colors hover:text-ink"
                        >
                          <span className="truncate">{s}</span>
                          <span className="text-[13px] text-faint opacity-0 transition-opacity group-hover:opacity-100">Ask</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="mt-10 text-[14px] text-muted">
                  Nothing indexed yet.{" "}
                  <button onClick={p.onOpenLibrary} className="text-ink underline underline-offset-4">
                    Add documents to the library
                  </button>{" "}
                  to get started.
                </p>
              )}
            </div>
          ) : (
            <div className="pt-10 pb-6">
              <div className="flex justify-end">
                <TextButton onClick={p.onClear}>Clear conversation</TextButton>
              </div>
              {p.exchanges.map((ex) => (
                <ExchangeView key={ex.id} ex={ex} onOpenSource={p.onOpenSource} onFeedback={p.onFeedback} onRetry={p.onRetry} />
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="shrink-0 bg-gradient-to-t from-surface from-60% to-transparent pt-4 pb-6 sm:pb-8">
        <form onSubmit={submit} className="mx-auto w-full max-w-[720px] px-6 sm:px-10">
          {(low || p.queued > 0) && (
            <p className="mb-3 text-[12.5px] text-warn">
              {p.queued > 0
                ? `${p.queued} ${p.queued === 1 ? "question" : "questions"} waiting for quota. ${p.rateLimit?.remaining === 0 ? `Resumes in ${Math.ceil(p.rateLimit.reset_in_seconds)}s.` : ""}`
                : `${p.rateLimit?.remaining} queries left this minute. Extra questions will wait their turn.`}
            </p>
          )}
          <div className="flex items-end gap-3 rounded-[14px] border border-line bg-surface p-2 pl-4 shadow-[0_1px_2px_rgba(0,0,0,0.03),0_8px_24px_-16px_rgba(0,0,0,0.12)] transition-colors focus-within:border-[#bdbdbd]">
            <textarea
              value={p.input}
              onChange={(e) => p.onInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={1}
              maxLength={2000}
              aria-label="Your question"
              placeholder={p.connection === "offline" ? "Waiting for the API to come back" : "Ask a question"}
              className="max-h-40 min-h-10 flex-1 resize-none bg-transparent py-2.5 text-[15px] text-ink outline-none placeholder:text-faint [field-sizing:content]"
            />
            {p.busy && p.settings.streaming ? (
              <button
                type="button"
                onClick={p.onStop}
                className="h-10 shrink-0 rounded-[10px] border border-line px-5 text-[14px] text-ink transition-colors hover:bg-subtle"
              >
                Stop
              </button>
            ) : (
              <PrimaryButton type="submit" disabled={!p.input.trim()}>
                Ask
              </PrimaryButton>
            )}
          </div>
          <div className="mt-3 flex flex-wrap justify-between gap-2 px-1 text-[12px] text-faint">
            <span>Enter to send, Shift + Enter for a new line</span>
            <button onClick={p.onOpenSettings} type="button" className="hover:text-ink">
              {p.settings.topK} sources · {p.settings.rerank ? "reranked" : "vector search"} · {p.settings.streaming ? "streaming" : "single response"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
