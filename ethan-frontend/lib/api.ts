export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

export interface Source {
  ref: number;
  id: string;
  score: number;
  vector_score: number;
  keyword_score: number | null;
  rerank_score: number | null;
  matched_by: "both" | "dense" | "keyword";
  text: string;
  source_file: string;
  chunk_index: number;
  section?: string;
  metadata?: Record<string, unknown>;
}

export interface Confidence {
  level: "high" | "medium" | "low" | "none";
  score: number;
}

export interface QueryMetrics {
  total_time: number;
  embedding_time: number;
  search_time: number;
  retrieval_time: number;
  rerank_time: number;
  llm_time: number;
  ttft: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  candidates: number;
  mode: RetrievalMode;
  cached: boolean;
  tokens_saved: number;
  cost_saved_usd?: number;
}

export type RetrievalMode = "hybrid" | "dense" | "keyword";

export interface Pricing {
  input_per_m: number;
  output_per_m: number;
  configured: boolean;
}

export interface AnswerCacheStats {
  enabled: boolean;
  entries: number;
  max_entries: number;
  ttl_seconds: number;
  hits: number;
  misses: number;
  hit_rate: number;
}

export interface RecentQuery extends QueryMetrics {
  id: string;
  query: string;
  timestamp: number;
  top_score: number;
  source_count: number;
}

export interface MetricsSummary {
  count: number;
  avg_total_time: number;
  p50_total_time: number;
  p95_total_time: number;
  avg_ttft: number;
  avg_embedding_time: number;
  avg_search_time: number;
  avg_rerank_time: number;
  avg_llm_time: number;
  total_tokens: number;
  avg_tokens: number;
  avg_prompt_tokens: number;
  avg_completion_tokens: number;
  avg_cost_usd: number;
  cost_per_1k_queries_usd: number;
  cache_hits: number;
  modes: Record<string, number>;
  lifetime: {
    queries: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost_usd: number;
    cache_hits: number;
    tokens_saved: number;
    cache_hit_rate: number;
  };
  pricing: Pricing;
  answer_cache: AnswerCacheStats;
  recent: RecentQuery[];
}

export interface DocumentInfo {
  name: string;
  status: string;
  size: number;
  chunks: number;
  tables?: number;
  file_type?: string;
  uploaded_at?: number | null;
  times_cited: number;
}

export interface Chunk {
  id: string;
  text: string;
  chunk_index: number;
  section?: string;
  kind?: "text" | "table";
  char_count: number;
  used_count: number;
  last_used: number | null;
}

export interface DocumentChunks {
  document: string;
  total_chunks: number;
  total_characters: number;
  average_chunk_size: number;
  min_chunk_size: number;
  max_chunk_size: number;
  chunks_used: number;
  size_histogram: { bucket_start: number; bucket_end: number; count: number }[];
  chunks: Chunk[];
}

export interface Health {
  status: "healthy" | "degraded";
  database_status: string;
  assistant_name: string;
  company_name: string;
  total_documents: number;
  total_chunks: number;
  embedding_model: string;
  embedding_provider: string;
  llm_model: string | null;
  llm_provider: string | null;
  llm_error: string | null;
  reranker_model: string;
  reranker_loaded: boolean;
  retrieval_mode: RetrievalMode;
  hybrid_available: boolean;
  visuals_available: boolean;
  collection: string;
  dimension: number;
  chunk_size: number;
  chunk_overlap: number;
  chunk_strategy: string;
  similarity_metric: string;
  qdrant_url: string;
  pricing: Pricing;
  answer_cache: AnswerCacheStats;
  max_context_chars: number;
  max_output_tokens: number;
}

export interface EvalCase {
  id: string;
  category: string;
  question: string;
  passed: boolean;
  rank?: number | null;
  reason: string;
}

export interface EvalRetrievalConfig {
  label: string;
  chunking: string;
  mode: RetrievalMode;
  rerank: boolean;
  hit_at_1: number;
  hit_at_3: number;
  hit_at_5: number;
  mrr: number;
  rejection_rate: number | null;
  passed: number;
  total: number;
  by_category: Record<string, { passed: number; total: number }>;
  avg_latency_ms: number;
  cases: EvalCase[];
}

export interface EvalAnswerConfig {
  label: string;
  model: string;
  provider: string;
  passed: number;
  total: number;
  avg_prompt_tokens: number;
  avg_completion_tokens: number;
  cases: (EvalCase & { answer: string; confidence: string })[];
}

export interface EvalReport {
  generated_at: string;
  golden: { total: number; corpus: string[]; by_category: Record<string, number> };
  top_k: number;
  default_config: string;
  gate: { passed: boolean; failures: string[] };
  retrieval: Record<string, EvalRetrievalConfig>;
  answers?: Record<string, EvalAnswerConfig> | null;
}

export interface SearchBody {
  query: string;
  top_k: number;
  rerank: boolean;
  mode: RetrievalMode;
  visuals: boolean;
  history: ChatTurn[];
}

export interface RateLimit {
  limit: number;
  used: number;
  remaining: number;
  reset_in_seconds: number;
  window_seconds: number;
  upstream?: {
    limit_requests?: number;
    remaining_requests?: number;
    reset_requests?: string;
    limit_tokens?: number;
    remaining_tokens?: number;
    reset_tokens?: string;
  };
}

export interface KnowledgeGap {
  query: string;
  normalized: string;
  reason: "low_relevance" | "no_results" | "negative_feedback";
  top_score: number;
  count: number;
  first_seen: number;
  last_seen: number;
}

export interface Insights {
  gaps: KnowledgeGap[];
  feedback: { up: number; down: number };
  gap_threshold: number;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export class ApiError extends Error {
  constructor(message: string, public status: number, public retryAfter?: number) {
    super(message);
  }
}

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  }
  return fallback;
}

async function toApiError(res: Response): Promise<ApiError> {
  const body = await res.json().catch(() => null);
  const retryAfter = Number(res.headers.get("Retry-After")) || undefined;
  return new ApiError(errorMessage(body, `Request failed (${res.status})`), res.status, retryAfter);
}

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) throw await toApiError(res);
  return res.json() as Promise<T>;
}

export interface StreamHandlers {
  onStage?: (stage: string, data: Record<string, unknown>) => void;
  onSources?: (sources: Source[], confidence: Confidence) => void;
  onToken?: (token: string) => void;
  onComplete?: (queryId: string, metrics: QueryMetrics, rateLimit?: RateLimit) => void;
}

/** POSTs to /search/stream and dispatches Server-Sent Events as they arrive. */
export async function streamSearch(
  body: SearchBody,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/search/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw await toApiError(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (event: string, data: Record<string, unknown>) => {
    switch (event) {
      case "stage":
        handlers.onStage?.(String(data.stage), data);
        break;
      case "sources":
        handlers.onSources?.(data.sources as Source[], data.confidence as Confidence);
        break;
      case "token":
        handlers.onToken?.(String(data.token));
        break;
      case "complete":
        handlers.onComplete?.(String(data.query_id), data.metrics as QueryMetrics, data.rate_limit as RateLimit);
        break;
      case "error":
        throw new ApiError(String(data.error), 500);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) dispatch(event, JSON.parse(data));
    }
  }
}

/** Non-streaming search, used when streaming is turned off in settings. */
export async function search(body: SearchBody) {
  return getJson<{
    query_id: string;
    answer: string;
    sources: Source[];
    confidence: Confidence;
    metrics: QueryMetrics;
  }>("/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Upload with XHR (for progress events). Rejects with ApiError; status 0 means network failure. */
export function uploadFile(file: File, onProgress: (pct: number) => void): Promise<{ chunks: number; replaced_chunks: number }> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) onProgress((e.loaded / e.total) * 100);
    });
    xhr.addEventListener("load", () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as { chunks: number; replaced_chunks: number });
      else reject(new ApiError(errorMessage(body, `Upload failed (${xhr.status})`), xhr.status));
    });
    xhr.addEventListener("error", () => reject(new ApiError("Network error - backend unreachable", 0)));
    xhr.addEventListener("timeout", () => reject(new ApiError("Upload timed out", 0)));
    xhr.timeout = 5 * 60 * 1000;
    xhr.open("POST", `${API_BASE}/ingest/pdf`);
    xhr.send(form);
  });
}

/** Network failures, 5xx and 429 are worth retrying; other 4xx are the user's to fix. */
export function isRetryable(err: unknown): boolean {
  if (!(err instanceof ApiError)) return true;
  return err.status === 0 || err.status === 429 || err.status >= 500;
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function formatBytes(bytes: number) {
  if (!bytes) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${Math.round((bytes / Math.pow(k, i)) * 10) / 10} ${sizes[i]}`;
}

export function formatMs(seconds: number | null | undefined) {
  if (seconds == null) return "-";
  return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(2)} s`;
}

/** Dollars with enough precision for fractions of a cent. */
export function formatUsd(value: number | null | undefined) {
  if (value == null) return "-";
  if (value === 0) return "$0";
  if (value < 0.01) return `$${value.toFixed(5).replace(/0+$/, "")}`;
  return `$${value.toFixed(value < 1 ? 3 : 2)}`;
}

export function timeAgo(ts: number | null | undefined) {
  if (!ts) return "";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
