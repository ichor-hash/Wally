"""
The retrieval pipeline, independent of the web app.

main.py serves it over HTTP; evals/run_evals.py calls it directly, so the numbers
in docs/EVALUATION.md are measured on exactly the code that answers questions.
"""
import time
from typing import Any, Callable, Dict, List, Optional

from reranker import Reranker
from vector_db import RAGVectorDB, RETRIEVAL_MODES

RERANK_CANDIDATE_MULTIPLIER = 3  # retrieve top_k * N candidates before reranking
WEAK_RERANK = 0.30   # best rerank relevance below this = weak evidence
WEAK_DENSE = 0.25    # best cosine below this = weak evidence (no reranker)


def evidence_of(results: List[Dict[str, Any]], reranked: bool) -> float:
    """Strength of the best evidence found: rerank relevance if available, else cosine."""
    if not results:
        return 0.0
    key = "rerank_score" if reranked else "vector_score"
    return max((r.get(key) or 0.0) for r in results)


class Retriever:
    def __init__(self, db: RAGVectorDB, reranker: Optional[Reranker] = None, default_mode: str = "hybrid"):
        if default_mode not in RETRIEVAL_MODES:
            raise ValueError(f"RETRIEVAL_MODE must be one of {RETRIEVAL_MODES}")
        self.db = db
        self.reranker = reranker
        self.default_mode = default_mode

    def _search(self, query: str, limit: int, mode: str):
        t0 = time.perf_counter()
        vector = self.db.embed_query(query)
        embedding_time = time.perf_counter() - t0
        t1 = time.perf_counter()
        results = self.db.search(query, vector, limit=limit, mode=mode)
        return results, embedding_time, time.perf_counter() - t1

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        rerank: bool = False,
        mode: Optional[str] = None,
        rewriter: Optional[Callable[[str], str]] = None,
    ) -> Dict[str, Any]:
        """
        Embed, search (hybrid / dense / keyword), optionally rerank, and optionally
        correct a weak search. Returns results plus per-stage timings.

        Corrective retrieval (a CRAG-style step): when the best evidence is weak,
        `rewriter` turns the question into a search query in the documents' own
        vocabulary ("important employees leave" -> "key personnel retention risk"),
        the rewritten query is searched too, and both candidate pools are reranked
        together. Each chunk keeps the better of its two relevance scores, against
        the question or against the rewrite.
        """
        mode = mode or self.default_mode
        if not self.db.hybrid_available:
            mode = "dense"
        use_rerank = rerank and self.reranker is not None
        limit = top_k * RERANK_CANDIDATE_MULTIPLIER if use_rerank else top_k

        results, embedding_time, search_time = self._search(query, limit, mode)
        candidates = len(results)

        rerank_time = 0.0
        if use_rerank and results:
            t2 = time.perf_counter()
            results = self.reranker.rerank(query, results, len(results))
            rerank_time += time.perf_counter() - t2

        correction = None
        evidence = evidence_of(results[:top_k], use_rerank)
        if rewriter and evidence < (WEAK_RERANK if use_rerank else WEAK_DENSE):
            t3 = time.perf_counter()
            rewritten = (rewriter(query) or "").strip()
            rewrite_time = time.perf_counter() - t3
            correction = {"query": rewritten, "evidence_before": round(evidence, 4), "rewrite_time": round(rewrite_time, 3), "improved": False}
            if rewritten and rewritten.lower() != query.strip().lower():
                more, e_time, s_time = self._search(rewritten, limit, mode)
                embedding_time += e_time
                search_time += s_time
                pool = {r["id"]: r for r in results}
                for r in more:
                    # A chunk found by both searches keeps its better similarity
                    if r["id"] not in pool or (r.get("vector_score") or 0) > (pool[r["id"]].get("vector_score") or 0):
                        pool[r["id"]] = r
                merged = list(pool.values())
                candidates = len(merged)
                if use_rerank:
                    t4 = time.perf_counter()
                    by_question = {r["id"]: r for r in self.reranker.rerank(query, merged, len(merged))}
                    by_rewrite = {r["id"]: r for r in self.reranker.rerank(rewritten, merged, len(merged))}
                    rerank_time += time.perf_counter() - t4
                    merged = []
                    for pid, r in by_question.items():
                        best = max(r, by_rewrite[pid], key=lambda x: x["rerank_score"])
                        merged.append(best)
                    merged.sort(key=lambda r: r["rerank_score"], reverse=True)
                else:
                    merged.sort(key=lambda r: r.get("vector_score") or 0.0, reverse=True)
                after = evidence_of(merged[:top_k], use_rerank)
                correction.update(evidence_after=round(after, 4), improved=after > evidence)
                if after > evidence:
                    results = merged

        return {
            "results": results[:top_k],
            "candidates": candidates,
            "mode": mode,
            "embedding_time": embedding_time,
            "search_time": search_time,
            "rerank_time": rerank_time,
            "correction": correction,
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
