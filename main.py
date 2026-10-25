import hashlib
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal

import inngest
import inngest.fast_api
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

# Import RAG components
from vector_db import RAGVectorDB
from llm import get_llm_provider
from data_loader import DocumentLoader
from reranker import Reranker
from telemetry import Telemetry, RateLimiter

# ============================================================
# CONFIG
# ============================================================
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "docs")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
RATE_LIMIT = int(os.getenv("RATE_LIMIT", "30"))  # queries per minute per client
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RERANK_CANDIDATE_MULTIPLIER = 3  # retrieve top_k * N candidates before reranking
GAP_THRESHOLD = float(os.getenv("GAP_THRESHOLD", "0.25"))
COMPANY_NAME = os.getenv("COMPANY_NAME", "your company")
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Wally")
SUPPORTED_EXTENSIONS = [".pdf", ".txt", ".md"]
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

app = FastAPI(title=f"{ASSISTANT_NAME} - Company Knowledge Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After"],
)

rag_db = RAGVectorDB(url=QDRANT_URL, collection=COLLECTION_NAME)
llm = get_llm_provider("groq")
reranker = Reranker(RERANK_MODEL)
telemetry = Telemetry(gap_threshold=GAP_THRESHOLD)
rate_limiter = RateLimiter(RATE_LIMIT)


# ============================================================
# MODELS
# ============================================================
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(5, ge=1, le=20)
    rerank: bool = False
    history: List[ChatTurn] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    query_id: str
    query: str
    rating: Literal["up", "down"]
    comment: Optional[str] = None


# ============================================================
# HELPERS
# ============================================================
def client_key(request: Request) -> str:
    return request.client.host if request.client else "anonymous"


def rate_limit_headers(client: str) -> Dict[str, str]:
    status = rate_limiter.status(client)
    return {
        "X-RateLimit-Limit": str(status["limit"]),
        "X-RateLimit-Remaining": str(status["remaining"]),
        "X-RateLimit-Reset": str(status["reset_in_seconds"]),
    }


def enforce_rate_limit(request: Request) -> str:
    client = client_key(request)
    if not rate_limiter.hit(client):
        status = rate_limiter.status(client)
        retry_after = max(1, int(status["reset_in_seconds"] + 0.999))
        raise HTTPException(
            status_code=429,
            detail={"message": "Rate limit exceeded. Your request will be retried shortly.", **status},
            headers={**rate_limit_headers(client), "Retry-After": str(retry_after)},
        )
    return client


def validate_query(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    if len(req.query) > 2000:
        raise HTTPException(status_code=400, detail="Query too long. Max 2000 characters.")


def retrieve(query: str, top_k: int, use_rerank: bool) -> Dict[str, Any]:
    """Embed, search and optionally rerank. Returns results plus per-stage timings."""
    t0 = time.perf_counter()
    vector = rag_db.embed_query(query)
    embedding_time = time.perf_counter() - t0

    candidates = top_k * RERANK_CANDIDATE_MULTIPLIER if use_rerank else top_k
    t1 = time.perf_counter()
    results = rag_db.search_by_vector(vector, top_k=candidates)
    search_time = time.perf_counter() - t1
    candidate_count = len(results)

    rerank_time = 0.0
    if use_rerank and results:
        t2 = time.perf_counter()
        results = reranker.rerank(query, results, top_k)
        rerank_time = time.perf_counter() - t2

    return {
        "results": results,
        "candidates": candidate_count,
        "embedding_time": embedding_time,
        "search_time": search_time,
        "rerank_time": rerank_time,
    }


def format_sources(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sources = []
    for i, r in enumerate(results, 1):
        payload = r["payload"] or {}
        sources.append({
            "ref": i,
            "id": str(r["id"]),
            "score": round(r["score"], 4),
            "vector_score": round(r.get("vector_score", r["score"]), 4),
            "rerank_score": round(r["rerank_score"], 4) if "rerank_score" in r else None,
            "text": payload.get("text", ""),
            "source_file": payload.get("source_file", "Unknown"),
            "chunk_index": payload.get("chunk_index", 0),
            "metadata": {k: v for k, v in payload.items() if k != "text"},
        })
    return sources


def confidence_for(sources: List[Dict[str, Any]], reranked: bool) -> Dict[str, Any]:
    """Grounding confidence from retrieval scores, so users know when to double-check."""
    if not sources:
        return {"level": "none", "score": 0.0}
    top = sources[0]["score"]
    high, medium = (0.7, 0.3) if reranked else (0.5, GAP_THRESHOLD)
    level = "high" if top >= high else "medium" if top >= medium else "low"
    return {"level": level, "score": round(top, 4)}


def build_messages(query: str, sources: List[Dict[str, Any]], history: List[ChatTurn]) -> List[dict]:
    context = "\n\n".join(
        f"[{s['ref']}] (source: {s['source_file']}, chunk {s['chunk_index']})\n{s['text']}" for s in sources
    )
    system = (
        f"You are {ASSISTANT_NAME}, the internal knowledge assistant for {COMPANY_NAME}. "
        "Answer employee questions using ONLY the numbered context passages provided. "
        "Cite every factual claim with its passage number in square brackets, e.g. [1] or [2][3]. "
        "If the context does not contain the answer, say so plainly and suggest what document "
        "or team might have it - never invent policies, numbers or names. "
        "Be concise and use short paragraphs or bullet lists where it helps readability."
    )
    messages = [{"role": "system", "content": system}]
    # Keep a short window of prior turns so follow-up questions make sense
    for turn in history[-6:]:
        messages.append({"role": turn.role, "content": turn.content[:2000]})
    messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"})
    return messages


def build_metrics(timings: Dict[str, Any], llm_time: float, total_time: float,
                  usage: Dict[str, int], ttft: Optional[float] = None) -> Dict[str, Any]:
    return {
        "total_time": round(total_time, 3),
        "embedding_time": round(timings["embedding_time"], 3),
        "search_time": round(timings["search_time"], 3),
        "retrieval_time": round(timings["embedding_time"] + timings["search_time"], 3),
        "rerank_time": round(timings["rerank_time"], 3),
        "llm_time": round(llm_time, 3),
        "ttft": round(ttft, 3) if ttft is not None else None,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "candidates": timings["candidates"],
    }


NO_RESULTS_ANSWER = (
    "I couldn't find anything relevant in the knowledge base. "
    "This question has been logged as a knowledge gap so the team can add the missing documentation."
)


# ============================================================
# STATUS ENDPOINTS
# ============================================================
@app.get("/")
async def root():
    return {"status": "ok", "service": f"{ASSISTANT_NAME} Company Knowledge Assistant"}


@app.get("/health")
def health():
    db_ok = True
    total_docs = total_chunks = 0
    try:
        total_chunks = rag_db.client.count(collection_name=COLLECTION_NAME, exact=True).count
        total_docs = len({p.payload.get("source_file", "Unknown") for p in rag_db.scroll_all()})
    except Exception:
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "database_status": "connected" if db_ok else "disconnected",
        "assistant_name": ASSISTANT_NAME,
        "company_name": COMPANY_NAME,
        "total_documents": total_docs,
        "total_chunks": total_chunks,
        "embedding_model": rag_db.embed_model,
        "embedding_provider": rag_db.embed_provider,
        "llm_model": llm.model,
        "llm_provider": llm.provider_name,
        "reranker_model": RERANK_MODEL,
        "reranker_loaded": reranker.loaded,
        "collection": rag_db.collection,
        "dimension": rag_db.dimension,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "similarity_metric": "Cosine Similarity",
        "qdrant_url": QDRANT_URL,
        "timestamp": time.time(),
    }


@app.get("/rate-limit")
async def get_rate_limit(request: Request):
    """Current client's quota plus the latest upstream LLM quota reported by the provider."""
    return {**rate_limiter.status(client_key(request)), "upstream": llm.upstream_limits}


@app.get("/metrics")
async def get_metrics():
    return telemetry.summary()


@app.get("/insights")
async def get_insights():
    """Knowledge gaps and answer feedback - what the knowledge base is missing."""
    return {
        "gaps": telemetry.list_gaps(),
        "feedback": telemetry.feedback_summary(),
        "gap_threshold": GAP_THRESHOLD,
    }


@app.delete("/insights/gaps")
async def resolve_gap(normalized: str):
    if not telemetry.resolve_gap(normalized):
        raise HTTPException(status_code=404, detail="Gap not found")
    return {"status": "ok"}


@app.post("/feedback")
async def feedback(req: FeedbackRequest):
    telemetry.add_feedback(req.query_id, req.query, req.rating, req.comment)
    return {"status": "ok"}


@app.post("/reranker/warmup")
def warmup_reranker():
    """Load the cross-encoder ahead of the first reranked query."""
    try:
        t0 = time.perf_counter()
        reranker._ensure_model()
        return {"status": "ok", "model": RERANK_MODEL, "load_time": round(time.perf_counter() - t0, 3)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load reranker: {e}")


# ============================================================
# INGESTION
# ============================================================
def ingest_file_path(file_path: str, display_name: str, metadata: Optional[dict] = None) -> Dict[str, Any]:
    """Chunk and embed a file, replacing any previous version with the same name."""
    loader = DocumentLoader(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = loader.load_and_chunk_with_metadata(file_path=file_path, file_metadata=metadata or {})
    if not chunks:
        raise HTTPException(status_code=400, detail="No text content found in file")

    content_hash = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()[:16]
    uploaded_at = time.time()
    for chunk in chunks:
        chunk["metadata"].update({
            "source_file": display_name,
            "uploaded_at": uploaded_at,
            "content_hash": content_hash,
            "char_count": len(chunk["text"]),
        })

    replaced = rag_db.delete_by_source(display_name)
    t0 = time.perf_counter()
    ids = rag_db.add_texts([c["text"] for c in chunks], metadata=[c["metadata"] for c in chunks])
    return {
        "status": "ok",
        "file": display_name,
        "chunks": len(ids),
        "replaced_chunks": replaced,
        "embedding_time": round(time.perf_counter() - t0, 3),
        "ids": ids[:10],
    }


@app.post("/ingest/texts")
def ingest_texts(texts: List[str], metadata: List[dict] = None):
    """
    Ingest text strings into the vector database.

    Body:
        texts: List of text strings to embed and store
        metadata: Optional list of metadata dicts
    """
    if not texts:
        raise HTTPException(status_code=400, detail="texts cannot be empty")
    if len(texts) > 1000:
        raise HTTPException(status_code=413, detail="Too many texts. Max 1000 at a time.")
    try:
        ids = rag_db.add_texts(texts, metadata=metadata)
        return {"status": "ok", "ingested": len(ids), "ids": ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ingesting texts: {str(e)}")


@app.post("/ingest/pdf")
async def ingest_pdf(file: UploadFile = File(...)):
    """
    Upload and ingest a PDF or text file.

    Re-uploading a file with the same name replaces its previous chunks.
    Supports: .pdf, .txt, .md
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Invalid file")

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}. Supported: .pdf, .txt, .md")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Max 50MB.")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        result = await run_in_threadpool(ingest_file_path, temp_path, file.filename)
        result["size_bytes"] = len(content)
        return result
    except HTTPException:
        raise
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Text file is not valid UTF-8")
    except Exception as e:
        logging.getLogger("uvicorn").exception("Error ingesting file")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


@app.post("/ingest/directory")
def ingest_directory(directory: str, glob_pattern: str = "*.*"):
    """
    Ingest all supported files from a directory.

    Query params:
        directory: Path to directory containing files
        glob_pattern: Glob pattern to match files (default: *.* for all)
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")

    files = [f for f in dir_path.glob(glob_pattern) if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
    ingested, failed = [], []
    for f in files:
        try:
            ingested.append(ingest_file_path(str(f), f.name))
        except Exception as e:
            failed.append({"file": f.name, "error": str(getattr(e, "detail", e))})

    return {
        "status": "ok",
        "directory": str(dir_path),
        "files_matched": len(files),
        "chunks": sum(r["chunks"] for r in ingested),
        "ingested": [r["file"] for r in ingested],
        "failed": failed,
    }


# ============================================================
# DOCUMENTS
# ============================================================
@app.get("/documents")
def list_documents():
    """List all stored documents with chunk counts and sizes."""
    try:
        docs_map: Dict[str, Dict[str, Any]] = {}
        for point in rag_db.scroll_all():
            payload = point.payload or {}
            name = payload.get("source_file", "Unknown")
            doc = docs_map.setdefault(name, {
                "name": name,
                "status": "Indexed",
                "size": 0,
                "chunks": 0,
                "file_type": payload.get("file_type", Path(name).suffix),
                "uploaded_at": payload.get("uploaded_at"),
                "times_cited": 0,
            })
            doc["chunks"] += 1
            doc["size"] += len(payload.get("text", ""))
            doc["times_cited"] += telemetry.chunk_usage.get(str(point.id), 0)

        documents = sorted(docs_map.values(), key=lambda d: d["uploaded_at"] or 0, reverse=True)
        return {"documents": documents, "total": len(documents)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching documents: {str(e)}")


@app.delete("/documents/{doc_name}")
def delete_document(doc_name: str):
    """Delete all chunks for a specific document."""
    try:
        deleted = rag_db.delete_by_source(doc_name)
        message = f"Deleted {deleted} chunks from {doc_name}" if deleted else f"No chunks found for {doc_name}"
        return {"message": message, "deleted_count": deleted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")


@app.get("/documents/{doc_name}/chunks")
def get_document_chunks(doc_name: str):
    """Get all chunks for a document with usage counts and size statistics."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    try:
        source_filter = Filter(must=[FieldCondition(key="source_file", match=MatchValue(value=doc_name))])
        points = list(rag_db.scroll_all(scroll_filter=source_filter))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching chunks: {str(e)}")

    usage = telemetry.usage_for([str(p.id) for p in points])
    chunks = []
    for point in points:
        payload = point.payload or {}
        cid = str(point.id)
        chunks.append({
            "id": cid,
            "text": payload.get("text", ""),
            "chunk_index": payload.get("chunk_index", 0),
            "char_count": len(payload.get("text", "")),
            "used_count": usage[cid]["count"],
            "last_used": usage[cid]["last_used"],
        })
    chunks.sort(key=lambda c: c["chunk_index"])

    sizes = [c["char_count"] for c in chunks]
    bucket = 100
    histogram: Dict[int, int] = {}
    for size in sizes:
        histogram[(size // bucket) * bucket] = histogram.get((size // bucket) * bucket, 0) + 1

    return {
        "document": doc_name,
        "total_chunks": len(chunks),
        "total_characters": sum(sizes),
        "average_chunk_size": sum(sizes) // len(sizes) if sizes else 0,
        "min_chunk_size": min(sizes) if sizes else 0,
        "max_chunk_size": max(sizes) if sizes else 0,
        "chunks_used": sum(1 for c in chunks if c["used_count"]),
        "size_histogram": [{"bucket_start": k, "bucket_end": k + bucket, "count": v} for k, v in sorted(histogram.items())],
        "chunks": chunks,
    }


# ============================================================
# SEARCH
# ============================================================
@app.post("/search")
def search(req: SearchRequest, request: Request):
    """
    Retrieve relevant chunks and generate a cited answer (non-streaming).

    Returns answer, sources, confidence and a latency/token breakdown.
    """
    client = enforce_rate_limit(request)
    validate_query(req)
    start = time.perf_counter()
    query_id = uuid.uuid4().hex

    try:
        timings = retrieve(req.query, req.top_k, req.rerank)
        sources = format_sources(timings["results"])

        if not sources:
            answer, usage, llm_time = NO_RESULTS_ANSWER, {}, 0.0
        else:
            t0 = time.perf_counter()
            answer, usage = llm.chat_with_usage(build_messages(req.query, sources, req.history))
            llm_time = time.perf_counter() - t0
    except Exception as e:
        logging.getLogger("uvicorn").exception("Search error")
        raise HTTPException(status_code=500, detail=f"Error during search: {str(e)}")

    metrics = build_metrics(timings, llm_time, time.perf_counter() - start, usage)
    telemetry.record_query(query_id, req.query, metrics, sources)

    return JSONResponse(
        {
            "query_id": query_id,
            "answer": answer,
            "sources": sources,
            "confidence": confidence_for(sources, req.rerank),
            "reranked": req.rerank,
            "metrics": metrics,
        },
        headers=rate_limit_headers(client),
    )


def sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/search/stream")
def search_stream(req: SearchRequest, request: Request):
    """
    Same pipeline as /search, streamed as Server-Sent Events.

    Events: stage, sources, token, complete, error
    """
    client = enforce_rate_limit(request)
    validate_query(req)
    query_id = uuid.uuid4().hex

    # A sync generator: Starlette iterates it in a threadpool, so blocking
    # model calls don't stall the event loop.
    def generate():
        start = time.perf_counter()
        try:
            yield sse("stage", {"stage": "retrieving", "query_id": query_id})
            timings = retrieve(req.query, req.top_k, req.rerank)
            sources = format_sources(timings["results"])
            yield sse("stage", {
                "stage": "retrieved",
                "embedding_time": round(timings["embedding_time"], 3),
                "search_time": round(timings["search_time"], 3),
                "rerank_time": round(timings["rerank_time"], 3),
                "results_found": len(sources),
            })
            yield sse("sources", {
                "sources": sources,
                "confidence": confidence_for(sources, req.rerank),
                "reranked": req.rerank,
            })

            usage, llm_time, ttft = {}, 0.0, None
            if not sources:
                yield sse("token", {"token": NO_RESULTS_ANSWER})
            else:
                yield sse("stage", {"stage": "generating"})
                t0 = time.perf_counter()
                for kind, value in llm.stream_chat(build_messages(req.query, sources, req.history)):
                    if kind == "token":
                        if ttft is None:
                            ttft = time.perf_counter() - start
                        yield sse("token", {"token": value})
                    elif kind == "usage":
                        usage = value
                llm_time = time.perf_counter() - t0

            metrics = build_metrics(timings, llm_time, time.perf_counter() - start, usage, ttft)
            telemetry.record_query(query_id, req.query, metrics, sources)
            yield sse("complete", {"query_id": query_id, "metrics": metrics, "rate_limit": rate_limiter.status(client)})
        except Exception as e:
            logging.getLogger("uvicorn").exception("Streaming search error")
            yield sse("error", {"error": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={**rate_limit_headers(client), "Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# INNGEST FUNCTIONS
# ============================================================
# Inngest handles event-driven workflows. Functions are triggered
# by events sent to the Inngest platform.
#
# EVENTS YOU CAN TRIGGER:
# ------------------------
# 1. rag/ingest_file  - Trigger file ingestion from a file path
#    Payload: {"file_path": "/path/to/file.pdf"}
#
# 2. rag/ingest_texts - Trigger text ingestion
#    Payload: {"texts": ["text1", "text2"], "metadata": [{}]}
#
# 3. rag/search       - Trigger RAG search
#    Payload: {"query": "your question", "top_k": 5}
#
# HOW TO SEND EVENTS (from your frontend or external system):
# -----------------------------------------------------------
# Using curl:
#   curl -X POST https://your-inngest-url/-/events \
#     -H "Content-Type: application/json" \
#     -d '{"name": "rag/ingest_file", "data": {"file_path": "/path/to.pdf"}}'
#
# Using Python:
#   import inngest
#   client = inngest.Inngest(app_id="rag_app")
#   client.send_event("rag/ingest_file", {"file_path": "/path/to.pdf"})
#
# DEVELOPMENT VS PRODUCTION:
# --------------------------
# - is_production=False in Inngest client = dev mode (local/webhook testing)
# - Set is_production=True when deploying to production
#
# ============================================================

inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=False,  # Set to True in production
    serializer=inngest.PydanticSerializer(),
)


@inngest_client.create_function(
    fn_id="RAG: Ingest File",
    trigger=inngest.TriggerEvent(event="rag/ingest_file"),
)
async def rag_ingest_file(ctx: inngest.Context):
    """
    Ingest a file (PDF or text) from a file path.

    Event: rag/ingest_file
    Payload: {"file_path": "/path/to/document.pdf", "metadata": {}}
    """
    event_data = ctx.event.data
    file_path = event_data.get("file_path")
    if not file_path:
        return {"error": "file_path is required"}

    return await run_in_threadpool(ingest_file_path, file_path, Path(file_path).name, event_data.get("metadata", {}))


@inngest_client.create_function(
    fn_id="RAG: Ingest Texts",
    trigger=inngest.TriggerEvent(event="rag/ingest_texts"),
)
async def rag_ingest_texts(ctx: inngest.Context):
    """
    Ingest text strings into the vector database.

    Event: rag/ingest_texts
    Payload: {"texts": ["text1", "text2"], "metadata": [{}]}
    """
    event_data = ctx.event.data
    texts = event_data.get("texts", [])
    if not texts:
        return {"error": "texts array is required"}

    ids = await run_in_threadpool(rag_db.add_texts, texts, None, event_data.get("metadata"))
    return {"status": "ok", "ingested": len(ids), "ids": ids}


@inngest_client.create_function(
    fn_id="RAG: Search",
    trigger=inngest.TriggerEvent(event="rag/search"),
)
async def rag_search(ctx: inngest.Context):
    """
    Perform RAG search and return answer.

    Event: rag/search
    Payload: {"query": "your question", "top_k": 5, "rerank": false}
    """
    event_data = ctx.event.data
    query = event_data.get("query")
    if not query:
        return {"error": "query is required"}

    def run():
        timings = retrieve(query, event_data.get("top_k", 5), event_data.get("rerank", False))
        sources = format_sources(timings["results"])
        if not sources:
            return {"answer": NO_RESULTS_ANSWER, "sources": []}
        answer, usage = llm.chat_with_usage(build_messages(query, sources, []))
        return {"answer": answer, "usage": usage, "sources": [{"id": s["id"], "score": s["score"]} for s in sources]}

    return await run_in_threadpool(run)


# Serve the FastAPI app with Inngest
inngest.fast_api.serve(app, inngest_client, [
    rag_ingest_file,
    rag_ingest_texts,
    rag_search
])
