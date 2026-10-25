"""
Runtime telemetry for Wally: query metrics, chunk usage, knowledge gaps,
answer feedback and per-client rate limiting.

Query metrics and rate-limit windows live in memory. Knowledge gaps and
feedback are persisted to a small JSON file so the "what is our knowledge
base missing?" signal survives restarts.
"""
import json
import os
import statistics
import threading
import time
from collections import Counter, deque
from pathlib import Path
from typing import Dict, Any, List, Optional

DATA_DIR = Path(os.getenv("WALLY_DATA_DIR", Path(__file__).parent / "wally_data"))
INSIGHTS_FILE = DATA_DIR / "insights.json"


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


class Telemetry:
    def __init__(self, history_size: int = 200, gap_threshold: float = 0.35):
        self._lock = threading.Lock()
        self.queries = deque(maxlen=history_size)
        self.chunk_usage: Counter = Counter()
        self.chunk_last_used: Dict[str, float] = {}
        self.gap_threshold = gap_threshold
        self.gaps: List[Dict[str, Any]] = []
        self.feedback: List[Dict[str, Any]] = []
        self.upstream_limits: Dict[str, Any] = {}
        self._load()

    # ---------------- persistence ----------------
    def _load(self):
        try:
            data = json.loads(INSIGHTS_FILE.read_text(encoding="utf-8"))
            self.gaps = data.get("gaps", [])
            self.feedback = data.get("feedback", [])
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            INSIGHTS_FILE.write_text(
                json.dumps({"gaps": self.gaps[-500:], "feedback": self.feedback[-1000:]}, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            print(f"Could not persist insights: {e}")

    # ---------------- queries ----------------
    def record_query(self, query_id: str, query: str, metrics: Dict[str, Any], sources: List[Dict[str, Any]]):
        """Store metrics for a completed query and bump usage for the chunks it cited."""
        now = time.time()
        top_score = max((s.get("score", 0) for s in sources), default=0.0)
        with self._lock:
            self.queries.append({
                "id": query_id,
                "query": query[:200],
                "timestamp": now,
                "top_score": round(top_score, 4),
                "source_count": len(sources),
                **metrics,
            })
            for s in sources:
                cid = str(s.get("id"))
                self.chunk_usage[cid] += 1
                self.chunk_last_used[cid] = now

            if not sources or top_score < self.gap_threshold:
                self._add_gap(query, "low_relevance" if sources else "no_results", top_score)

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
        totals = [q["total_time"] for q in recent]
        ttft = [q["ttft"] for q in recent if q.get("ttft")]
        return {
            "count": len(recent),
            "avg_total_time": round(statistics.fmean(totals), 3) if totals else 0,
            "p50_total_time": round(_percentile(totals, 50), 3),
            "p95_total_time": round(_percentile(totals, 95), 3),
            "avg_ttft": round(statistics.fmean(ttft), 3) if ttft else 0,
            "avg_embedding_time": round(statistics.fmean([q["embedding_time"] for q in recent]), 3) if recent else 0,
            "avg_search_time": round(statistics.fmean([q["search_time"] for q in recent]), 3) if recent else 0,
            "avg_rerank_time": round(statistics.fmean([q["rerank_time"] for q in recent]), 3) if recent else 0,
            "avg_llm_time": round(statistics.fmean([q["llm_time"] for q in recent]), 3) if recent else 0,
            "total_tokens": sum(q.get("total_tokens", 0) for q in recent),
            "avg_tokens": round(statistics.fmean([q.get("total_tokens", 0) for q in recent])) if recent else 0,
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
