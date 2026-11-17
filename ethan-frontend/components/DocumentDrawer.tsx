"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { DocumentChunks, getJson, timeAgo } from "@/lib/api";
import { Toggle } from "./ui";

interface Props {
  docName: string;
  /** chunk id -> number of answers in this session that cited it */
  recentChunkUse: Map<string, number>;
  focusChunkId?: string | null;
  onClose: () => void;
}

export function DocumentDrawer({ docName, recentChunkUse, focusChunkId, onClose }: Props) {
  const [data, setData] = useState<DocumentChunks | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyCited, setOnlyCited] = useState(false);
  const [query, setQuery] = useState("");
  const [hoverBucket, setHoverBucket] = useState<number | null>(null);
  const [flashId, setFlashId] = useState<string | null>(null);
  const chunkRefs = useRef<Map<string, HTMLLIElement>>(new Map());

  useEffect(() => {
    let cancelled = false;
    getJson<DocumentChunks>(`/documents/${encodeURIComponent(docName)}/chunks`)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [docName]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const jumpTo = (id: string) => {
    chunkRefs.current.get(id)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlashId(null);
    setTimeout(() => setFlashId(id), 20);
  };

  useEffect(() => {
    if (data && focusChunkId) {
      const t = setTimeout(() => jumpTo(focusChunkId), 80);
      return () => clearTimeout(t);
    }
  }, [data, focusChunkId]);

  const visible = useMemo(() => {
    if (!data) return [];
    const q = query.toLowerCase();
    return data.chunks.filter((c) => (!onlyCited || c.used_count || recentChunkUse.has(c.id)) && (!q || c.text.toLowerCase().includes(q)));
  }, [data, onlyCited, query, recentChunkUse]);

  const maxUse = data ? Math.max(1, ...data.chunks.map((c) => c.used_count)) : 1;
  const maxBucket = data ? Math.max(1, ...data.size_histogram.map((b) => b.count)) : 1;
  const hb = data && hoverBucket != null ? data.size_histogram[hoverBucket] : null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-[#1a1a1a]/20 backdrop-blur-[2px]" onClick={onClose}>
      <div
        className="drawer-in flex h-full w-full max-w-[760px] flex-col bg-surface shadow-[-24px_0_64px_-32px_rgba(0,0,0,0.3)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Chunks in ${docName}`}
      >
        <div className="flex items-start justify-between gap-6 px-8 pt-10 pb-8 sm:px-12">
          <div className="min-w-0">
            <p className="text-[13px] text-faint">Document</p>
            <h2 className="mt-1 truncate font-display text-[26px] font-medium tracking-[-0.02em] text-ink">{docName}</h2>
          </div>
          <button onClick={onClose} className="mt-1 text-[13px] text-muted hover:text-ink">
            Close
          </button>
        </div>

        {error && <p className="px-8 text-[14px] text-bad sm:px-12">Could not load chunks: {error}</p>}
        {!data && !error && <p className="px-8 text-[14px] text-muted sm:px-12">Loading chunks</p>}

        {data && (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <dl className="tabular mx-8 grid grid-cols-2 gap-x-8 gap-y-6 border-y border-line-soft py-7 sm:mx-12 sm:grid-cols-4">
              {(
                [
                  ["Chunks", data.total_chunks.toLocaleString()],
                  ["Average length", `${data.average_chunk_size}`],
                  ["Shortest / longest", `${data.min_chunk_size} / ${data.max_chunk_size}`],
                  ["Ever cited", `${data.chunks_used} of ${data.total_chunks}`],
                ] as const
              ).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-[12.5px] text-faint">{k}</dt>
                  <dd className="mt-1.5 font-display text-[22px] font-light tracking-[-0.02em] text-ink">{v}</dd>
                </div>
              ))}
            </dl>

            <div className="grid gap-10 px-8 pt-8 sm:grid-cols-2 sm:px-12">
              <section>
                <p className="text-[13px] font-medium text-ink">Citation map</p>
                <p className="mt-1 text-[12.5px] text-faint">Each mark is a chunk in reading order. Darker means cited more.</p>
                <div className="mt-4 flex flex-wrap gap-[3px]">
                  {data.chunks.map((c) => {
                    const recent = recentChunkUse.get(c.id) ?? 0;
                    const shade = c.used_count ? 25 + Math.round(75 * (c.used_count / maxUse)) : 0;
                    return (
                      <button
                        key={c.id}
                        onClick={() => jumpTo(c.id)}
                        title={`Chunk ${c.chunk_index}, cited ${c.used_count}×${recent ? `, ${recent} in this session` : ""}`}
                        className={`h-[18px] w-[10px] rounded-[2px] transition-transform hover:scale-y-110 ${recent ? "ring-1 ring-ink ring-offset-1" : ""}`}
                        style={{ background: c.used_count ? `color-mix(in srgb, #1a1a1a ${shade}%, #ececec)` : "#ececec" }}
                      />
                    );
                  })}
                </div>
              </section>

              <section>
                <div className="flex items-baseline justify-between gap-4">
                  <p className="text-[13px] font-medium text-ink">Chunk length</p>
                  <p className="tabular text-[12.5px] text-faint">{hb ? `${hb.bucket_start}–${hb.bucket_end} chars: ${hb.count}` : "characters"}</p>
                </div>
                <div className="mt-4 flex h-16 items-end gap-[2px]" onMouseLeave={() => setHoverBucket(null)}>
                  {data.size_histogram.map((b, i) => (
                    <div key={b.bucket_start} className="flex h-full flex-1 flex-col justify-end" onMouseEnter={() => setHoverBucket(i)}>
                      <div
                        className={`rounded-t-[3px] bg-stage-3 transition-opacity ${hoverBucket != null && hoverBucket !== i ? "opacity-30" : ""}`}
                        style={{ height: `${Math.max(4, (b.count / maxBucket) * 100)}%` }}
                      />
                    </div>
                  ))}
                </div>
                <div className="tabular mt-1.5 flex justify-between text-[11px] text-faint">
                  <span>{data.size_histogram[0]?.bucket_start ?? 0}</span>
                  <span>{data.size_histogram[data.size_histogram.length - 1]?.bucket_end ?? 0}</span>
                </div>
              </section>
            </div>

            <div className="sticky top-0 z-10 mt-10 flex items-center gap-6 border-y border-line-soft bg-surface/95 px-8 py-4 backdrop-blur sm:px-12">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search this document"
                aria-label="Search this document"
                className="min-w-0 flex-1 bg-transparent text-[14px] outline-none placeholder:text-faint"
              />
              <span className="flex items-center gap-3 text-[13px] text-muted">
                Cited only
                <Toggle label="Cited only" checked={onlyCited} onChange={setOnlyCited} />
              </span>
            </div>

            <ol className="px-8 pb-16 sm:px-12">
              {visible.length === 0 && <li className="py-10 text-[14px] text-muted">No chunks match.</li>}
              {visible.map((c) => {
                const recent = recentChunkUse.get(c.id) ?? 0;
                return (
                  <li
                    key={c.id}
                    ref={(el) => {
                      if (el) chunkRefs.current.set(c.id, el);
                      else chunkRefs.current.delete(c.id);
                    }}
                    className={`-mx-4 grid grid-cols-[44px_1fr] gap-x-4 rounded-[12px] border-b border-line-soft px-4 py-6 last:border-b-0 ${
                      recent ? "bg-mark" : ""
                    } ${flashId === c.id ? "flash" : ""}`}
                  >
                    <span className="tabular pt-0.5 text-[12.5px] text-faint">{c.chunk_index}</span>
                    <div className="min-w-0">
                      <p className="whitespace-pre-wrap text-[14.5px] leading-[1.7] text-ink-2">{c.text}</p>
                      <p className="tabular mt-3 text-[12px] text-faint">
                        {c.char_count} characters
                        {recent > 0 && <span className="text-ink"> · used in {recent} recent {recent === 1 ? "answer" : "answers"}</span>}
                        {c.used_count > 0 && ` · cited ${c.used_count}× overall${c.last_used ? `, last ${timeAgo(c.last_used)}` : ""}`}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}
