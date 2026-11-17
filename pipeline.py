"""
The retrieval pipeline, independent of the web app.

main.py serves it over HTTP; evals/run_evals.py calls it directly, so the numbers
in docs/EVALUATION.md are measured on exactly the code that answers questions.
"""
import time
from typing import Any, Dict, List, Optional

from reranker import Reranker
from vector_db import RAGVectorDB, RETRIEVAL_MODES

RERANK_CANDIDATE_MULTIPLIER = 3  # retrieve top_k * N candidates before reranking


class Retriever:
    def __init__(self, db: RAGVectorDB, reranker: Optional[Reranker] = None, default_mode: str = "hybrid"):
        if default_mode not in RETRIEVAL_MODES:
            raise ValueError(f"RETRIEVAL_MODE must be one of {RETRIEVAL_MODES}")
        self.db = db
        self.reranker = reranker
        self.default_mode = default_mode

    def retrieve(self, query: str, top_k: int = 5, rerank: bool = False, mode: Optional[str] = None) -> Dict[str, Any]:
        """Embed, search (hybrid / dense / keyword) and optionally rerank. Returns results plus per-stage timings."""
        mode = mode or self.default_mode
        if not self.db.hybrid_available:
            mode = "dense"

        t0 = time.perf_counter()
        vector = self.db.embed_query(query)
        embedding_time = time.perf_counter() - t0

        limit = top_k * RERANK_CANDIDATE_MULTIPLIER if rerank else top_k
        t1 = time.perf_counter()
        results = self.db.search(query, vector, limit=limit, mode=mode)
        search_time = time.perf_counter() - t1
        candidates = len(results)

        rerank_time = 0.0
        if rerank and results and self.reranker:
            t2 = time.perf_counter()
            results = self.reranker.rerank(query, results, top_k)
            rerank_time = time.perf_counter() - t2

        return {
            "results": results[:top_k],
            "candidates": candidates,
            "mode": mode,
            "embedding_time": embedding_time,
            "search_time": search_time,
            "rerank_time": rerank_time,
        }


def trim_to_budget(results: List[Dict[str, Any]], max_chars: int) -> List[Dict[str, Any]]:
    """Drop the lowest-ranked chunks once the context would exceed max_chars. Always keeps the best one."""
    kept, used = [], 0
    for r in results:
        size = len((r.get("payload") or {}).get("text", ""))
        if kept and used + size > max_chars:
            break
        kept.append(r)
        used += size
    return kept
