"""
Runtime telemetry for Ethan: query metrics, cost, chunk usage, knowledge gaps,
answer feedback and per-client rate limiting.

Everything worth keeping survives a restart in ETHAN_DATA_DIR (default ./ethan_data):
- insights.json   knowledge gaps, feedback and lifetime totals (queries, tokens, cost)
- queries.jsonl   one line per answered question, trimmed to the recent window on start

Rate-limit windows stay in memory: they are 60 seconds long.
"""
import json
import os
import statistics
import threading
import time
from collections import Counter, deque
from pathlib import Path
from typing import Dict, Any, List, Optional

DATA_DIR = Path(os.getenv("ETHAN_DATA_DIR", Path(__file__).parent / "ethan_data"))
INSIGHTS_FILE = DATA_DIR / "insights.json"
QUERIES_FILE = DATA_DIR / "queries.jsonl"

EMPTY_TOTALS = {"queries": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "cache_hits": 0, "tokens_saved": 0}


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


def _mean(values: List[float], digits: int = 3) -> float:
    return round(statistics.fmean(values), digits) if values else 0


class Telemetry:
    def __init__(self, history_size: int = 200, gap_threshold: float = 0.35, persist: bool = True):
        self._lock = threading.Lock()
        self.persist = persist
        self.queries = deque(maxlen=history_size)
        self.chunk_usage: Counter = Counter()
        self.chunk_last_used: Dict[str, float] = {}
        self.gap_threshold = gap_threshold
        self.gaps: List[Dict[str, Any]] = []
        self.feedback: List[Dict[str, Any]] = []
        self.totals: Dict[str, Any] = dict(EMPTY_TOTALS)
        if persist:
            self._load()

    # ---------------- persistence ----------------
    def _load(self):
        try:
            data = json.loads(INSIGHTS_FILE.read_text(encoding="utf-8"))
            self.gaps = data.get("gaps", [])
            self.feedback = data.get("feedback", [])
            self.totals = {**EMPTY_TOTALS, **data.get("totals", {})}
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        try:
            lines = QUERIES_FILE.read_text(encoding="utf-8").splitlines()[-self.queries.maxlen:]
            for line in lines:
                try:
                    self.queries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            # Compact on start so the log never grows past the window
            QUERIES_FILE.write_text("".join(json.dumps(q) + "\n" for q in self.queries), encoding="utf-8")
        except (FileNotFoundError, OSError):
            pass

    def _save(self):
        if not self.persist:
            return
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            INSIGHTS_FILE.write_text(
                json.dumps({"gaps": self.gaps[-500:], "feedback": self.feedback[-1000:], "totals": self.totals}, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            print(f"Could not persist insights: {e}")

    def _append_query(self, record: Dict[str, Any]):
        if not self.persist:
            return
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with QUERIES_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            print(f"Could not persist query log: {e}")

    # ---------------- queries ----------------
    def record_query(self, query_id: str, query: str, metrics: Dict[str, Any], sources: List[Dict[str, Any]]):
        """Store metrics for a completed query and bump usage for the chunks it cited."""
        now = time.time()
        top_score = max((s.get("score", 0) for s in sources), default=0.0)
        record = {
            "id": query_id,
            "query": query[:200],
            "timestamp": now,
            "top_score": round(top_score, 4),
            "source_count": len(sources),
            **metrics,
        }
        with self._lock:
            self.queries.append(record)
            for s in sources:
                cid = str(s.get("id"))
                self.chunk_usage[cid] += 1
                self.chunk_last_used[cid] = now

            t = self.totals
            t["queries"] += 1
            t["prompt_tokens"] += metrics.get("prompt_tokens", 0)
            t["completion_tokens"] += metrics.get("completion_tokens", 0)
            t["cost_usd"] = round(t["cost_usd"] + metrics.get("cost_usd", 0.0), 8)
            if metrics.get("cached"):
                t["cache_hits"] += 1
                t["tokens_saved"] += metrics.get("tokens_saved", 0)

            self._append_query(record)
            if not sources or top_score < self.gap_threshold:
                self._add_gap(query, "low_relevance" if sources else "no_results", top_score)
            else:
                self._save()

    def _add_gap(self, query: str, reason: str, top_score: float):
        normalized = query.strip().lower()
        for gap in self.gaps:
            if gap["normalized"] == normalized:
                gap["count"] += 1
                gap["last_seen"] = time.time()
                gap["top_score"] = round(top_score, 4)
                self._save()
                return
        self.gaps.append({
            "query": query[:300],
            "normalized": normalized,
            "reason": reason,
            "top_score": round(top_score, 4),
            "count": 1,
            "first_seen": time.time(),
            "last_seen": time.time(),
        })
        self._save()

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            recent = list(self.queries)
            totals = dict(self.totals)
        live = [q for q in recent if not q.get("cached")]  # cache hits would flatter the latency numbers
        times = [q["total_time"] for q in live]
        ttft = [q["ttft"] for q in live if q.get("ttft")]
        costs = [q.get("cost_usd", 0.0) for q in live]
        modes = Counter(q.get("mode", "dense") + ("+rerank" if q.get("rerank_time") else "") for q in live)
        lifetime_queries = totals["queries"] or 1
        return {
            "count": len(recent),
            "avg_total_time": _mean(times),
            "p50_total_time": round(_percentile(times, 50), 3),
            "p95_total_time": round(_percentile(times, 95), 3),
            "avg_ttft": _mean(ttft),
            "avg_embedding_time": _mean([q["embedding_time"] for q in live]),
            "avg_search_time": _mean([q["search_time"] for q in live]),
            "avg_rerank_time": _mean([q["rerank_time"] for q in live]),
            "avg_rewrite_time": _mean([q.get("rewrite_time", 0.0) for q in live]),
            "avg_llm_time": _mean([q["llm_time"] for q in live]),
            "avg_verify_time": _mean([q.get("verify_time", 0.0) for q in live]),
            "faithfulness": _mean([q["faithfulness"] for q in live if q.get("faithfulness") is not None]) or None,
            "verified_answers": sum(1 for q in live if q.get("verified")),
            "revised_answers": sum(1 for q in live if q.get("revised")),
            "corrected_searches": sum(1 for q in live if q.get("corrected")),
            "total_tokens": sum(q.get("total_tokens", 0) for q in recent),
            "avg_tokens": round(statistics.fmean([q.get("total_tokens", 0) for q in live])) if live else 0,
            "avg_prompt_tokens": round(statistics.fmean([q.get("prompt_tokens", 0) for q in live])) if live else 0,
            "avg_completion_tokens": round(statistics.fmean([q.get("completion_tokens", 0) for q in live])) if live else 0,
            "avg_cost_usd": _mean(costs, 6),
            "cost_per_1k_queries_usd": round(statistics.fmean(costs) * 1000, 4) if costs else 0,
            "cache_hits": sum(1 for q in recent if q.get("cached")),
            "modes": dict(modes),
            "lifetime": {
                **totals,
                "cost_usd": round(totals["cost_usd"], 6),
                "cache_hit_rate": round(totals["cache_hits"] / lifetime_queries, 3),
            },
            "recent": recent[-30:],
        }

    def usage_for(self, chunk_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {
                cid: {"count": self.chunk_usage.get(cid, 0), "last_used": self.chunk_last_used.get(cid)}
                for cid in chunk_ids
            }

    # ---------------- gaps & feedback ----------------
    def list_gaps(self) -> List[Dict[str, Any]]:
        return sorted(self.gaps, key=lambda g: (g["count"], g["last_seen"]), reverse=True)

    def resolve_gap(self, normalized: str) -> bool:
        before = len(self.gaps)
        self.gaps = [g for g in self.gaps if g["normalized"] != normalized]
        self._save()
        return len(self.gaps) < before

    def add_feedback(self, query_id: str, query: str, rating: str, comment: Optional[str] = None):
        self.feedback.append({
            "query_id": query_id,
            "query": query[:300],
            "rating": rating,
            "comment": (comment or "")[:500],
            "timestamp": time.time(),
        })
        if rating == "down":
            self._add_gap(query, "negative_feedback", 0.0)
        else:
            self._save()

    def feedback_summary(self) -> Dict[str, int]:
        up = sum(1 for f in self.feedback if f["rating"] == "up")
        return {"up": up, "down": len(self.feedback) - up}


class RateLimiter:
    """Sliding-window limiter keyed by client (IP)."""

    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds
        self._hits: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def _prune(self, hits: deque, now: float):
        while hits and hits[0] <= now - self.window:
            hits.popleft()

    def status(self, client: str) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            hits = self._hits.setdefault(client, deque())
            self._prune(hits, now)
            reset = (hits[0] + self.window - now) if hits else 0
            return {
                "limit": self.limit,
                "used": len(hits),
                "remaining": max(0, self.limit - len(hits)),
                "reset_in_seconds": round(max(0, reset), 1),
                "window_seconds": self.window,
            }

    def hit(self, client: str) -> bool:
        """Record a request. Returns False if the client is over its limit."""
        now = time.time()
        with self._lock:
            hits = self._hits.setdefault(client, deque())
            self._prune(hits, now)
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True
