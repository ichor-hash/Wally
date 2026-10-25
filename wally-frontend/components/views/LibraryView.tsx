"use client";

import { DragEvent, useRef, useState } from "react";
import { API_BASE, ApiError, DocumentInfo, formatBytes, isRetryable, sleep, timeAgo, uploadFile } from "@/lib/api";
import { useToast } from "../Toaster";
import { ViewHeader } from "../ui";

const MAX_ATTEMPTS = 4;
const ACCEPTED = [".pdf", ".txt", ".md"];

interface UploadJob {
  id: number;
  name: string;
  progress: number;
  attempt: number;
  state: "uploading" | "processing" | "retrying" | "done" | "failed";
  message?: string;
}

interface Props {
  documents: DocumentInfo[];
  recentlyCited: Set<string>;
  onChanged: () => void;
  onOpenDocument: (name: string) => void;
}

const JOB_LABEL: Record<UploadJob["state"], string> = {
  uploading: "Uploading",
  processing: "Embedding",
  retrying: "Retrying",
  done: "Indexed",
  failed: "Failed",
};

export function LibraryView({ documents, recentlyCited, onChanged, onOpenDocument }: Props) {
  const { toast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const nextId = useRef(1);
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [dragging, setDragging] = useState(false);
  const [filter, setFilter] = useState("");
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  const patch = (id: number, update: Partial<UploadJob>) => setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, ...update } : j)));

  // Upload with automatic retry: network errors, 5xx and 429 back off 1s, 2s, 4s.
  const runUpload = async (file: File) => {
    const id = nextId.current++;
    setJobs((prev) => [...prev, { id, name: file.name, progress: 0, attempt: 1, state: "uploading" }]);

    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      patch(id, { attempt, state: "uploading", progress: 0, message: undefined });
      try {
        const result = await uploadFile(file, (pct) => patch(id, { progress: pct, state: pct >= 100 ? "processing" : "uploading" }));
        patch(id, { state: "done", progress: 100 });
        toast(
          "success",
          `${file.name} indexed`,
          `${result.chunks} passages${result.replaced_chunks ? `, replacing ${result.replaced_chunks} from the previous version` : ""}`,
        );
        onChanged();
        setTimeout(() => setJobs((prev) => prev.filter((j) => j.id !== id)), 2500);
        return;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Upload failed";
        if (!isRetryable(err) || attempt === MAX_ATTEMPTS) {
          patch(id, { state: "failed", message });
          toast("error", `Could not upload ${file.name}`, message);
          return;
        }
        const delay = 1000 * 2 ** (attempt - 1);
        patch(id, { state: "retrying", message: `${message}. Next attempt in ${delay / 1000}s.` });
        if (attempt === 1) toast("warning", `Retrying ${file.name}`, message);
        await sleep(delay);
      }
    }
  };

  const enqueue = (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (!ACCEPTED.includes(ext)) {
        toast("error", `${file.name} skipped`, "Only PDF, TXT and Markdown files are supported.");
        continue;
      }
      if (file.size > 50 * 1024 * 1024) {
        toast("error", `${file.name} skipped`, "Files must be under 50 MB.");
        continue;
      }
      void runUpload(file);
    }
    if (inputRef.current) inputRef.current.value = "";
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) enqueue(e.dataTransfer.files);
  };

  const remove = async (name: string) => {
    setPendingDelete(null);
    try {
      const res = await fetch(`${API_BASE}/documents/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (!res.ok) throw new ApiError(`Delete failed (${res.status})`, res.status);
      const data = await res.json();
      toast("success", `Removed ${name}`, data.message);
      onChanged();
    } catch (err) {
      toast("error", `Could not remove ${name}`, err instanceof Error ? err.message : undefined);
    }
  };

  const visible = documents.filter((d) => d.name.toLowerCase().includes(filter.toLowerCase()));
  const totalChunks = documents.reduce((n, d) => n + d.chunks, 0);
  const totalSize = documents.reduce((n, d) => n + d.size, 0);

  return (
    <div className="mx-auto w-full max-w-[960px] px-6 py-12 sm:px-12 sm:py-16">
      <ViewHeader
        title="Library"
        description="The documents Wally answers from. Uploading a file with an existing name replaces the old version."
        aside={
          <p className="tabular text-[13px] text-faint">
            {documents.length} {documents.length === 1 ? "document" : "documents"} · {totalChunks.toLocaleString()} passages · {formatBytes(totalSize)} of text
          </p>
        }
      />

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center justify-center rounded-[16px] border border-dashed px-6 py-14 text-center transition-colors ${
          dragging ? "border-ink bg-subtle" : "border-[#d0d0d0]"
        }`}
      >
        <input ref={inputRef} type="file" multiple accept={ACCEPTED.join(",")} onChange={(e) => e.target.files && enqueue(e.target.files)} className="hidden" />
        <p className="font-display text-[18px] font-medium text-ink">{dragging ? "Release to upload" : "Drop files here"}</p>
        <p className="mt-2 text-[13.5px] text-muted">
          or{" "}
          <button onClick={() => inputRef.current?.click()} className="text-ink underline underline-offset-4">
            browse your computer
          </button>
          . PDF, TXT and Markdown up to 50 MB.
        </p>
      </div>

      {jobs.length > 0 && (
        <ul className="mt-6 space-y-4">
          {jobs.map((j) => (
            <li key={j.id} className="text-[13px]">
              <div className="flex items-baseline justify-between gap-4">
                <span className="truncate text-ink">{j.name}</span>
                <span className={`tabular shrink-0 ${j.state === "failed" ? "text-bad" : j.state === "retrying" ? "text-warn" : "text-muted"}`}>
                  {JOB_LABEL[j.state]}
                  {j.state === "uploading" && ` ${Math.round(j.progress)}%`}
                  {j.state === "retrying" && ` · attempt ${j.attempt} of ${MAX_ATTEMPTS}`}
                </span>
              </div>
              <div className={`mt-2 h-px bg-line ${j.state === "processing" ? "hairline-progress" : ""}`}>
                {j.state !== "processing" && (
                  <div className={`h-px transition-all ${j.state === "failed" ? "bg-bad" : j.state === "retrying" ? "bg-warn" : "bg-ink"}`} style={{ width: `${j.progress}%` }} />
                )}
              </div>
              {j.message && (
                <p className="mt-1.5 text-faint">
                  {j.message}
                  {j.state === "failed" && (
                    <button className="ml-3 text-ink underline underline-offset-4" onClick={() => setJobs((p) => p.filter((x) => x.id !== j.id))}>
                      Dismiss
                    </button>
                  )}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      <section className="mt-14">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-4">
          <h2 className="font-display text-[17px] font-medium text-ink">Documents</h2>
          {documents.length > 5 && (
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter"
              className="w-48 border-b border-line bg-transparent py-1.5 text-[14px] outline-none placeholder:text-faint focus:border-ink"
            />
          )}
        </div>

        {documents.length === 0 ? (
          <p className="border-t border-line-soft py-10 text-[14px] text-muted">No documents yet. Handbooks, policies and wiki exports are a good start.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-[14px]">
              <thead>
                <tr className="text-left text-[12.5px] text-faint">
                  <th className="py-3 pr-4 font-normal">Name</th>
                  <th className="py-3 pr-4 text-right font-normal">Passages</th>
                  <th className="py-3 pr-4 text-right font-normal">Text</th>
                  <th className="py-3 pr-4 text-right font-normal">Citations</th>
                  <th className="py-3 pr-4 text-right font-normal">Added</th>
                  <th className="w-24 py-3" />
                </tr>
              </thead>
              <tbody>
                {visible.map((d) => (
                  <tr key={d.name} className="group border-t border-line-soft">
                    <td className="py-4 pr-4">
                      <button onClick={() => onOpenDocument(d.name)} className="flex min-w-0 items-center gap-3 text-left">
                        <span className="w-9 shrink-0 text-[11px] font-medium uppercase tracking-wide text-faint">
                          {(d.file_type || d.name.slice(d.name.lastIndexOf("."))).replace(".", "")}
                        </span>
                        <span className="truncate text-ink underline-offset-4 group-hover:underline">{d.name}</span>
                        {recentlyCited.has(d.name) && <span className="shrink-0 rounded-full bg-mark px-2 py-0.5 text-[11px] text-ink-2">cited just now</span>}
                      </button>
                    </td>
                    <td className="tabular py-4 pr-4 text-right text-muted">{d.chunks}</td>
                    <td className="tabular py-4 pr-4 text-right text-muted">{formatBytes(d.size)}</td>
                    <td className="tabular py-4 pr-4 text-right text-muted">{d.times_cited || "–"}</td>
                    <td className="py-4 pr-4 text-right text-muted">{d.uploaded_at ? timeAgo(d.uploaded_at) : "–"}</td>
                    <td className="py-4 text-right">
                      {pendingDelete === d.name ? (
                        <span className="flex justify-end gap-3 text-[13px]">
                          <button onClick={() => remove(d.name)} className="text-bad hover:underline">
                            Remove
                          </button>
                          <button onClick={() => setPendingDelete(null)} className="text-muted hover:text-ink">
                            Keep
                          </button>
                        </span>
                      ) : (
                        <button
                          onClick={() => setPendingDelete(d.name)}
                          className="text-[13px] text-faint transition-opacity hover:text-bad focus:opacity-100 group-hover:opacity-100 sm:opacity-0"
                          aria-label={`Remove ${d.name}`}
                        >
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
