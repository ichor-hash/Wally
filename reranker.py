"""
Cross-encoder reranker for RAG retrieval.
Re-scores (query, chunk) pairs jointly, which is far more precise than
bi-encoder cosine similarity. Loaded lazily so startup stays fast.
"""
import math
import threading
from typing import List, Dict, Any

try:
    from sentence_transformers import CrossEncoder
except ImportError:
    CrossEncoder = None


class Reranker:
    """
    Wraps a sentence-transformers CrossEncoder.

    Default model: cross-encoder/ms-marco-MiniLM-L-6-v2 (~90MB, CPU friendly)
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()
        self.load_error = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        if CrossEncoder is None:
            raise ImportError("sentence-transformers not installed. Run: pip install sentence-transformers")
        with self._lock:
            if self._model is None:
                try:
                    self._model = CrossEncoder(self.model_name)
                except Exception as e:
                    self.load_error = str(e)
                    raise
        return self._model

    def rerank(self, query: str, results: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        """
        Re-score retrieval results and return the best top_k.

        Each result keeps its original cosine score as `vector_score` and gets
        `rerank_score` (sigmoid of the cross-encoder logit, 0-1). `score` is
        replaced by the rerank score so downstream code sorts consistently.
        """
        if not results:
            return []

        model = self._ensure_model()
        pairs = [(query, r["payload"].get("text", "")) for r in results]
        logits = model.predict(pairs, convert_to_numpy=True).tolist()

        reranked = []
        for r, logit in zip(results, logits):
            item = dict(r)
            item["vector_score"] = r["score"]
            item["rerank_score"] = 1 / (1 + math.exp(-logit))
            item["score"] = item["rerank_score"]
            reranked.append(item)

        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:top_k]
