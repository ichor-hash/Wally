"""
Qdrant storage for Ethan: one dense vector and one BM25 sparse vector per chunk.

Three ways to run Qdrant, chosen by environment (see docs/HOSTING.md):
- QDRANT_URL=http://host:6333   a Qdrant server (Docker, VM or Qdrant Cloud)
- QDRANT_PATH=./ethan_data/qdrant   embedded, on disk, no server process at all
- QDRANT_URL=:memory:           embedded, in memory (tests and evaluations)
"""
import logging
import math
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Iterator, List, Optional

from qdrant_client import QdrantClient
from qdrant_client import models as qm

import sparse
from embeddings import get_embedding_provider

log = logging.getLogger("ethan.vector_db")

DENSE = "dense"
SPARSE = "bm25"
RRF_K = 60  # standard reciprocal-rank-fusion constant
RETRIEVAL_MODES = ("hybrid", "dense", "keyword")


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def rrf_fuse(rankings: Dict[str, List[Any]], weights: Optional[Dict[str, float]] = None) -> Dict[Any, float]:
    """Reciprocal rank fusion: score(id) = sum over rankings of weight / (k + rank)."""
    fused: Dict[Any, float] = {}
    for name, ids in rankings.items():
        w = (weights or {}).get(name, 1.0)
        for rank, pid in enumerate(ids, 1):
            fused[pid] = fused.get(pid, 0.0) + w / (RRF_K + rank)
    return fused


class RAGVectorDB:
    """Qdrant collection with built-in embedding, hybrid search and per-document helpers."""

    def __init__(
        self,
        url: Optional[str] = "http://localhost:6333",
        collection: str = "ethan_docs",
        path: Optional[str] = None,
        api_key: Optional[str] = None,
        embed_provider: str = "huggingface",
        embed_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        embedder=None,
        **embed_kwargs,
    ):
        key = "model" if embed_provider == "groq" else "model_name"
        # Pass an existing embedder to share one loaded model between several collections
        self.embedder = embedder or get_embedding_provider(embed_provider, **{key: embed_model}, **embed_kwargs)
        self.embed_provider = embed_provider
        self.embed_model = embed_model
        self.dimension = self.embedder.dimension
        self.collection = collection

        self.embedded = bool(path) or url == ":memory:"
        if path:
            self.client = QdrantClient(path=path)
            self.location = f"embedded ({path})"
        elif url == ":memory:":
            self.client = QdrantClient(":memory:")
            self.location = "embedded (in memory)"
        else:
            self.client = QdrantClient(url=url, api_key=api_key or None, timeout=30)
            self.location = url

        # Bumped on every write; caches (document list, answers) key on it.
        self.version = 0
        self._lock = threading.Lock()
        self._query_vectors: "OrderedDict[str, List[float]]" = OrderedDict()
        self._stats_cache: Optional[tuple] = None
        self._id_seq = 0

        self.legacy = False  # True for pre-3.0 collections: one unnamed dense vector, no BM25
        self._ensure_collection()

    # ---------------- setup ----------------
    def _ensure_collection(self):
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config={DENSE: qm.VectorParams(size=self.dimension, distance=qm.Distance.COSINE)},
                sparse_vectors_config={SPARSE: qm.SparseVectorParams(modifier=qm.Modifier.IDF)},
            )
        else:
            params = self.client.get_collection(self.collection).config.params
            self.legacy = not isinstance(params.vectors, dict) or not (params.sparse_vectors or {}).get(SPARSE)
            if self.legacy:
                log.warning(
                    "Collection %r was created before hybrid retrieval and has no BM25 vectors. "
                    "Serving dense-only. Run `python scripts/migrate_collection.py` to upgrade it.",
                    self.collection,
                )
        if not self.embedded:  # embedded Qdrant scans in process and has no payload indexes
            try:
                # Keyword index keeps per-document filters, deletes and facet counts fast
                self.client.create_payload_index(self.collection, field_name="source_file", field_schema=qm.PayloadSchemaType.KEYWORD)
            except Exception:
                pass

    @property
    def hybrid_available(self) -> bool:
        return not self.legacy

    def _touch(self):
        self.version += 1
        self._stats_cache = None

    # ---------------- write ----------------
    def _next_ids(self, n: int) -> List[int]:
        with self._lock:
            base = max(int(time.time() * 1_000_000), self._id_seq + 1)
            self._id_seq = base + n
        return [base + i for i in range(n)]

    def add_texts(self, texts: List[str], ids: Optional[list] = None, metadata: Optional[List[dict]] = None, batch_size: int = 256):
        """Embed texts (dense + BM25) and store them. Returns the point ids."""
        if not texts:
            return []
        ids = ids or self._next_ids(len(texts))
        payloads = [{**(metadata[i] if metadata else {}), "text": text} for i, text in enumerate(texts)]
        vectors = self.embedder.embed(texts)

        points = []
        for pid, dense, text, payload in zip(ids, vectors, texts, payloads):
            if self.legacy:
                vector: Any = dense
            else:
                indices, values = sparse.encode_document(text)
                vector = {DENSE: dense, SPARSE: qm.SparseVector(indices=indices, values=values)}
            points.append(qm.PointStruct(id=pid, vector=vector, payload=payload))

        for i in range(0, len(points), batch_size):
            self.client.upsert(collection_name=self.collection, points=points[i:i + batch_size])
        self._touch()
        return ids

    def delete_by_source(self, source_file: str) -> int:
        """Delete every chunk belonging to a source file. Returns the number deleted."""
        source_filter = self.source_filter(source_file)
        count = self.client.count(collection_name=self.collection, count_filter=source_filter, exact=True).count
        if count:
            self.client.delete(collection_name=self.collection, points_selector=qm.FilterSelector(filter=source_filter))
            self._touch()
        return count

    # ---------------- read ----------------
    @staticmethod
    def source_filter(source_file: str) -> qm.Filter:
        return qm.Filter(must=[qm.FieldCondition(key="source_file", match=qm.MatchValue(value=source_file))])

    def embed_query(self, query: str) -> List[float]:
        """Embed a query, with a small LRU so repeated questions skip the model."""
        key = query.strip()
        with self._lock:
            if key in self._query_vectors:
                self._query_vectors.move_to_end(key)
                return self._query_vectors[key]
        vector = self.embedder.embed([key])[0]
        with self._lock:
            self._query_vectors[key] = vector
            while len(self._query_vectors) > 512:
                self._query_vectors.popitem(last=False)
        return vector

    def search(
        self,
        query: str,
        query_vector: List[float],
        limit: int = 5,
        mode: str = "hybrid",
        query_filter: Optional[qm.Filter] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve chunks by meaning (dense), by exact terms (keyword/BM25) or both (hybrid).

        Hybrid sends both searches to Qdrant in one round trip and merges the two
        rankings with reciprocal rank fusion. Every result reports how it was found:

            score          cosine similarity to the question (0-1), comparable across modes
            vector_score   same value, kept under an explicit name
            keyword_score  BM25 score, None if the chunk had no term overlap in the candidate pool
            fusion_score   the RRF score the hybrid ordering is based on
            matched_by     "both" | "dense" | "keyword"
        """
        if mode not in RETRIEVAL_MODES:
            raise ValueError(f"Unknown retrieval mode {mode!r}. Choose from {RETRIEVAL_MODES}")
        if self.legacy:
            mode = "dense"

        requests, names = [], []
        if mode in ("hybrid", "dense"):
            requests.append(qm.QueryRequest(
                query=query_vector, using=None if self.legacy else DENSE, limit=limit, filter=query_filter, with_payload=True,
            ))
            names.append("dense")
        if mode in ("hybrid", "keyword"):
            indices, values = sparse.encode_query(query)
            if indices:
                requests.append(qm.QueryRequest(
                    query=qm.SparseVector(indices=indices, values=values), using=SPARSE, limit=limit,
                    filter=query_filter, with_payload=True, with_vector=[DENSE],
                ))
                names.append("keyword")
        if not requests:
            return []

        responses = self.client.query_batch_points(collection_name=self.collection, requests=requests)
        hits: Dict[Any, Dict[str, Any]] = {}
        rankings: Dict[str, List[Any]] = {}
        for name, response in zip(names, responses):
            rankings[name] = [p.id for p in response.points]
            for rank, p in enumerate(response.points, 1):
                hit = hits.setdefault(p.id, {"id": p.id, "payload": p.payload or {}, "vector_score": None, "keyword_score": None})
                hit[f"{name}_rank"] = rank
                if name == "dense":
                    hit["vector_score"] = p.score
                else:
                    hit["keyword_score"] = p.score
                    if hit["vector_score"] is None and isinstance(p.vector, dict) and p.vector.get(DENSE):
                        # Found by keywords only: compute its cosine so scores stay comparable
                        hit["vector_score"] = _cosine(query_vector, p.vector[DENSE])

        fused = rrf_fuse(rankings)
        results = []
        for pid, hit in hits.items():
            hit["vector_score"] = max(0.0, hit["vector_score"] or 0.0)
            hit["score"] = hit["vector_score"]
            hit["fusion_score"] = fused[pid]
            hit["matched_by"] = "both" if "dense_rank" in hit and "keyword_rank" in hit else "dense" if "dense_rank" in hit else "keyword"
            results.append(hit)
        results.sort(key=lambda h: (h["fusion_score"], h["vector_score"]), reverse=True)
        return results[:limit]

    def similarity_search(self, query: str, top_k: int = 5, mode: str = "hybrid"):
        """Search by text (embeds the query for you)."""
        return self.search(query, self.embed_query(query), limit=top_k, mode=mode)

    def scroll_all(self, with_payload=True, scroll_filter=None, page_size: int = 1000, with_vectors=False) -> Iterator[Any]:
        """Iterate over every point in the collection (paginates past Qdrant's page limit)."""
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection, limit=page_size, offset=offset,
                with_payload=with_payload, with_vectors=with_vectors, scroll_filter=scroll_filter,
            )
            yield from points
            if offset is None:
                break

    def count(self) -> int:
        return self.client.count(collection_name=self.collection, exact=True).count

    def stats(self) -> Dict[str, int]:
        """Document and chunk totals. Cached until the next write: /health polls this every few seconds."""
        if self._stats_cache and self._stats_cache[0] == self.version:
            return self._stats_cache[1]
        chunks = self.count()
        try:
            # One indexed aggregation instead of scrolling every payload
            docs = len(self.client.facet(self.collection, key="source_file", limit=100_000, exact=True).hits)
        except Exception:
            docs = len({(p.payload or {}).get("source_file", "Unknown") for p in self.scroll_all(with_payload=["source_file"])})
        result = {"documents": docs, "chunks": chunks}
        self._stats_cache = (self.version, result)
        return result
