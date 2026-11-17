import hashlib
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

from answering import AnswerConfig, AnswerOptions, Answerer, EMPTY_ANSWER
from contextual import MODES as CONTEXT_MODES, build_contexts, summarize_document, with_context
from costs import AnswerCache, Pricing
from data_loader import DocumentLoader
from llm import llm_from_env
from pipeline import Retriever
from reranker import Reranker
from telemetry import Telemetry, RateLimiter
from vector_db import RAGVectorDB

log = logging.getLogger("uvicorn")
ROOT = Path(__file__).parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ============================================================
# CONFIG
# ============================================================
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "ethan_docs")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_PATH = os.getenv("QDRANT_PATH", "").strip()  # set to run Qdrant embedded, with no server
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "hybrid")
RATE_LIMIT = int(os.getenv("RATE_LIMIT", "30"))  # queries per minute per client
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
CHUNK_STRATEGY = os.getenv("CHUNK_STRATEGY", "structure")
CONTEXTUAL_RETRIEVAL = os.getenv("CONTEXTUAL_RETRIEVAL", "header").strip().lower()
# Answer quality (docs/EVALUATION.md); each can be overridden per request
VERIFY_ANSWERS = env_bool("VERIFY_ANSWERS", True)
REVISE_ANSWERS = env_bool("REVISE_ANSWERS", True)
CORRECTIVE_RETRIEVAL = env_bool("CORRECTIVE_RETRIEVAL", True)
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
GAP_THRESHOLD = float(os.getenv("GAP_THRESHOLD", "0.25"))
COMPANY_NAME = os.getenv("COMPANY_NAME", "your company")
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Ethan")
COMPANY_PROFILE = os.getenv("COMPANY_PROFILE", "").strip()
# Cost controls (docs/COSTS.md)
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "8000"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1024"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
ANSWER_CACHE_TTL = float(os.getenv("ANSWER_CACHE_TTL", "3600"))
ANSWER_CACHE_SIZE = int(os.getenv("ANSWER_CACHE_SIZE", "256"))
# Deployment (docs/HOSTING.md)
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
ALLOW_DIRECTORY_INGEST = env_bool("ALLOW_DIRECTORY_INGEST")
INNGEST_ENABLED = env_bool("INNGEST_ENABLED")

if CONTEXTUAL_RETRIEVAL not in CONTEXT_MODES:
    raise ValueError(f"CONTEXTUAL_RETRIEVAL must be one of {CONTEXT_MODES}")

SUPPORTED_EXTENSIONS = [".pdf", ".txt", ".md"]
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

app = FastAPI(title=f"{ASSISTANT_NAME} - Company Knowledge Assistant", version="3.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After"],
)

rag_db = RAGVectorDB(
    url=QDRANT_URL, path=QDRANT_PATH or None, api_key=os.getenv("QDRANT_API_KEY"),
    collection=COLLECTION_NAME, embed_model=EMBED_MODEL,
)
reranker = Reranker(RERANK_MODEL)
retriever = Retriever(rag_db, reranker, default_mode=RETRIEVAL_MODE)
telemetry = Telemetry(gap_threshold=GAP_THRESHOLD)
rate_limiter = RateLimiter(RATE_LIMIT)
pricing = Pricing()
answer_cache = AnswerCache(max_entries=ANSWER_CACHE_SIZE, ttl_seconds=ANSWER_CACHE_TTL)

# The API still starts without an LLM key, so the library and health check work
# and the UI can say what is missing instead of showing "API offline".
try:
    llm = llm_from_env()
    llm_error = None
except Exception as e:  # missing key, missing package
    llm, llm_error = None, str(e)
    log.warning("LLM unavailable: %s", e)

try:
    VISUALS_PROMPT = (ROOT / "prompts" / "openui.txt").read_text(encoding="utf-8").strip()
except FileNotFoundError:
    VISUALS_PROMPT = ""

answerer = Answerer(
    retriever, llm,
    AnswerConfig(
        assistant_name=ASSISTANT_NAME, company_name=COMPANY_NAME, company_profile=COMPANY_PROFILE,
        visuals_prompt=VISUALS_PROMPT, max_context_chars=MAX_CONTEXT_CHARS, max_output_tokens=MAX_OUTPUT_TOKENS,
        temperature=LLM_TEMPERATURE, gap_threshold=GAP_THRESHOLD, revise=REVISE_ANSWERS,
    ),
    pricing,
)


# ============================================================
# MODELS
# ============================================================
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(5, ge=1, le=20)
    rerank: bool = True
    mode: Optional[Literal["hybrid", "dense", "keyword"]] = None  # default: RETRIEVAL_MODE
    visuals: bool = False   # let the model add an OpenUI chart or table
    agent: bool = False     # tools: calculate and search_documents
    verify: Optional[bool] = None   # check cited claims; default VERIFY_ANSWERS
    correct: Optional[bool] = None  # re-search weak retrievals; default CORRECTIVE_RETRIEVAL
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
    # Behind a reverse proxy the socket address is the proxy; trust the first forwarded hop
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
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
    if llm is None:
        raise HTTPException(status_code=503, detail=f"No language model configured: {llm_error}")


def options_for(req: SearchRequest) -> AnswerOptions:
    return AnswerOptions(
        top_k=req.top_k, rerank=req.rerank, mode=req.mode,
        visuals=req.visuals and bool(VISUALS_PROMPT), agent=req.agent,
        verify=VERIFY_ANSWERS if req.verify is None else req.verify,
        correct=CORRECTIVE_RETRIEVAL if req.correct is None else req.correct,
        history=[t.model_dump() for t in req.history],
    )


def cache_key_for(req: SearchRequest, opts: AnswerOptions) -> str:
    return AnswerCache.key(
        q=" ".join(req.query.lower().split()), k=opts.top_k, rerank=opts.rerank, mode=opts.mode or RETRIEVAL_MODE,
        visuals=opts.visuals, agent=opts.agent, verify=opts.verify, correct=opts.correct,
        history=[(t["role"], t["content"]) for t in opts.history[-6:]],
        index=rag_db.version, model=llm.model if llm else None,
    )


def cached_result(entry: Dict[str, Any], total_time: float) -> Dict[str, Any]:
    """A cached answer: same content, but no model time, no tokens and no cost this time."""
    metrics = {
        **{k: 0.0 for k in ("embedding_time", "search_time", "retrieval_time", "rerank_time", "rewrite_time", "llm_time", "verify_time")},
        "total_time": round(total_time, 3), "ttft": round(total_time, 3),
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "llm_calls": 0, "cost_usd": 0.0,
        "candidates": 0, "mode": entry["metrics"]["mode"], "agent_steps": entry["metrics"].get("agent_steps", 0),
        "cached": True, "tokens_saved": entry["metrics"]["total_tokens"], "cost_saved_usd": entry["metrics"]["cost_usd"],
    }
    return {**entry, "metrics": metrics}


def remember(key: str, result: Dict[str, Any]):
    if result["answer"].strip() and result["answer"] != EMPTY_ANSWER and result["sources"]:
        answer_cache.put(key, result)


# ============================================================
# STATUS ENDPOINTS
# ============================================================
@app.get("/")
async def root():
    return {"status": "ok", "service": f"{ASSISTANT_NAME} Company Knowledge Assistant"}


@app.get("/health")
def health():
    db_ok = True
    stats = {"documents": 0, "chunks": 0}
    try:
        stats = rag_db.stats()
    except Exception:
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "database_status": "connected" if db_ok else "disconnected",
        "assistant_name": ASSISTANT_NAME,
        "company_name": COMPANY_NAME,
        "total_documents": stats["documents"],
        "total_chunks": stats["chunks"],
        "embedding_model": rag_db.embed_model,
        "embedding_provider": rag_db.embed_provider,
        "llm_model": llm.model if llm else None,
        "llm_provider": llm.provider_name if llm else None,
        "llm_error": llm_error,
        "reranker_model": RERANK_MODEL,
        "reranker_loaded": reranker.loaded,
        "retrieval_mode": retriever.default_mode if rag_db.hybrid_available else "dense",
        "hybrid_available": rag_db.hybrid_available,
        "visuals_available": bool(VISUALS_PROMPT),
        "contextual_retrieval": CONTEXTUAL_RETRIEVAL,
        "verify_answers": VERIFY_ANSWERS,
        "revise_answers": REVISE_ANSWERS,
        "corrective_retrieval": CORRECTIVE_RETRIEVAL,
        "agent_available": llm is not None and hasattr(llm, "chat_with_tools"),
        "collection": rag_db.collection,
        "dimension": rag_db.dimension,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "chunk_strategy": CHUNK_STRATEGY,
        "similarity_metric": "Cosine similarity + BM25, fused by reciprocal rank" if rag_db.hybrid_available else "Cosine similarity",
        "qdrant_url": rag_db.location,
        "pricing": pricing.as_dict(),
        "answer_cache": answer_cache.stats(),
        "max_context_chars": MAX_CONTEXT_CHARS,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "timestamp": time.time(),
    }


@app.get("/rate-limit")
async def get_rate_limit(request: Request):
    """Current client's quota plus the latest upstream LLM quota reported by the provider."""
    return {**rate_limiter.status(client_key(request)), "upstream": llm.upstream_limits if llm else {}}


@app.get("/metrics")
async def get_metrics():
    return {**telemetry.summary(), "pricing": pricing.as_dict(), "answer_cache": answer_cache.stats()}


@app.get("/evals")
def get_evals():
    """Latest retrieval evaluation report (written by `python evals/run_evals.py`)."""
    path = ROOT / "evals" / "results" / "latest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No evaluation has been run yet. Run: python evals/run_evals.py")
    return json.loads(path.read_text(encoding="utf-8"))


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
    loader = DocumentLoader(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, strategy=CHUNK_STRATEGY)
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

    # Contextual retrieval: index each chunk with its document title and section (contextual.py)
    full_text = loader.load_file(file_path)
    summarizer = (lambda text: summarize_document(text, llm)) if CONTEXTUAL_RETRIEVAL == "llm" and llm else None
    contexts = build_contexts(chunks, full_text, display_name, CONTEXTUAL_RETRIEVAL, summarizer, title=loader.file_title(file_path))
    for chunk, context in zip(chunks, contexts):
        if context:
            chunk["metadata"]["context"] = context

    replaced = rag_db.delete_by_source(display_name)
    t0 = time.perf_counter()
    ids = rag_db.add_texts(
        [c["text"] for c in chunks], metadata=[c["metadata"] for c in chunks],
        index_texts=[with_context(c["text"], ctx) for c, ctx in zip(chunks, contexts)],
    )
    return {
        "status": "ok",
        "file": display_name,
        "chunks": len(ids),
        "tables": sum(1 for c in chunks if c["metadata"].get("kind") == "table"),
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
        result = await run_in_threadpool(ingest_file_path, temp_path, Path(file.filename).name)
        result["size_bytes"] = len(content)
        return result
    except HTTPException:
        raise
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Text file is not valid UTF-8")
    except Exception as e:
        log.exception("Error ingesting file")
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
    Ingest all supported files from a server-side directory.

    Off by default: it lets any caller read files from the server's disk.
    Enable with ALLOW_DIRECTORY_INGEST=true on a trusted network only.
    """
    if not ALLOW_DIRECTORY_INGEST:
        raise HTTPException(status_code=403, detail="Directory ingestion is disabled. Set ALLOW_DIRECTORY_INGEST=true to enable it.")
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
_documents_cache: Dict[str, Any] = {"version": -1, "docs": {}}


def _document_index() -> Dict[str, Dict[str, Any]]:
    """Per-document totals. One full scan per index change instead of one per request."""
    if _documents_cache["version"] != rag_db.version:
        version = rag_db.version
        docs: Dict[str, Dict[str, Any]] = {}
        for point in rag_db.scroll_all(with_payload=["source_file", "file_type", "uploaded_at", "char_count", "kind"]):
            payload = point.payload or {}
            name = payload.get("source_file", "Unknown")
            doc = docs.setdefault(name, {
                "name": name, "status": "Indexed", "size": 0, "chunks": 0, "tables": 0,
                "file_type": payload.get("file_type", Path(name).suffix),
                "uploaded_at": payload.get("uploaded_at"), "ids": [],
            })
            doc["chunks"] += 1
            doc["size"] += payload.get("char_count", 0)
            doc["tables"] += payload.get("kind") == "table"
            doc["ids"].append(str(point.id))
        _documents_cache.update(version=version, docs=docs)
    return _documents_cache["docs"]


@app.get("/documents")
def list_documents():
    """List all stored documents with chunk counts and sizes."""
    try:
        documents = [
            {**{k: v for k, v in doc.items() if k != "ids"}, "times_cited": sum(telemetry.chunk_usage.get(i, 0) for i in doc["ids"])}
            for doc in _document_index().values()
        ]
        documents.sort(key=lambda d: d["uploaded_at"] or 0, reverse=True)
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
    try:
        points = list(rag_db.scroll_all(scroll_filter=rag_db.source_filter(doc_name)))
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
            "section": payload.get("section", ""),
            "kind": payload.get("kind", "text"),
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
    Retrieve, answer, verify. Returns answer, sources, grounding label, verification,
    agent steps and a latency/token/cost breakdown in one response.
    """
    client = enforce_rate_limit(request)
    validate_query(req)
    opts = options_for(req)
    start = time.perf_counter()
    query_id = uuid.uuid4().hex
    key = cache_key_for(req, opts)

    cached = answer_cache.get(key)
    if cached:
        result = cached_result(cached, time.perf_counter() - start)
    else:
        try:
            result = answerer.answer(req.query, opts)
        except Exception as e:
            log.exception("Search error")
            raise HTTPException(status_code=500, detail=f"Error during search: {str(e)}")
        remember(key, result)

    telemetry.record_query(query_id, req.query, {**result["metrics"], **verification_metrics(result)}, result["sources"])
    return JSONResponse(
        {"query_id": query_id, "reranked": opts.rerank, **result},
        headers=rate_limit_headers(client),
    )


def verification_metrics(result: Dict[str, Any]) -> Dict[str, Any]:
    v = result.get("verification") or {}
    return {
        "verified": v.get("status") == "ok",
        "claims": v.get("total", 0),
        "claims_supported": v.get("supported", 0),
        "faithfulness": v.get("score"),
        "revised": bool(result.get("revised")),
        "corrected": bool((result.get("correction") or {}).get("improved")),
    }


def sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/search/stream")
def search_stream(req: SearchRequest, request: Request):
    """
    Same pipeline as /search, streamed as Server-Sent Events.

    Events: stage, sources, token, tool, verification, revision, complete, error
    """
    client = enforce_rate_limit(request)
    validate_query(req)
    opts = options_for(req)
    query_id = uuid.uuid4().hex
    key = cache_key_for(req, opts)

    # A sync generator: Starlette iterates it in a threadpool, so blocking
    # model calls don't stall the event loop.
    def generate():
        start = time.perf_counter()
        try:
            yield sse("stage", {"stage": "retrieving", "query_id": query_id})
            cached = answer_cache.get(key)
            if cached:
                result = cached_result(cached, time.perf_counter() - start)
                yield sse("stage", {"stage": "retrieved", "cached": True, "results_found": len(result["sources"])})
                yield sse("sources", {"sources": result["sources"], "confidence": result["confidence"], "reranked": opts.rerank})
                for step in result.get("steps") or []:
                    yield sse("tool", step)
                yield sse("token", {"token": result["answer"]})
                if result.get("verification"):
                    yield sse("verification", result["verification"])
            else:
                result = {}
                for kind, data in answerer.run(req.query, opts):
                    if kind == "complete":
                        result = data
                    elif kind == "stage" and data.get("stage") == "retrieving":
                        continue
                    else:
                        yield sse(kind, data)
                remember(key, result)

            telemetry.record_query(query_id, req.query, {**result["metrics"], **verification_metrics(result)}, result["sources"])
            yield sse("complete", {
                "query_id": query_id, "metrics": result["metrics"], "rate_limit": rate_limiter.status(client),
                "correction": result.get("correction"), "revised": result.get("revised"),
            })
        except Exception as e:
            log.exception("Streaming search error")
            yield sse("error", {"error": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={**rate_limit_headers(client), "Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# INNGEST (optional, INNGEST_ENABLED=true)
# ============================================================
# Event-driven ingestion and search for background jobs. Off by default so the
# API exposes no extra endpoint and needs no extra dependency.
#
#   rag/ingest_file   {"file_path": "/path/to/file.pdf", "metadata": {}}
#   rag/ingest_texts  {"texts": ["text1", "text2"], "metadata": [{}]}
#   rag/search        {"query": "your question", "top_k": 5, "rerank": false}
#
# Install with: pip install -r requirements-optional.txt
# Set INNGEST_PRODUCTION=true (and the Inngest signing key) outside local development.
if INNGEST_ENABLED:
    import inngest
    import inngest.fast_api

    inngest_client = inngest.Inngest(
        app_id="ethan",
        logger=log,
        is_production=env_bool("INNGEST_PRODUCTION"),
        serializer=inngest.PydanticSerializer(),
    )

    @inngest_client.create_function(fn_id="RAG: Ingest File", trigger=inngest.TriggerEvent(event="rag/ingest_file"))
    async def rag_ingest_file(ctx: inngest.Context):
        file_path = ctx.event.data.get("file_path")
        if not file_path:
            return {"error": "file_path is required"}
        return await run_in_threadpool(ingest_file_path, file_path, Path(file_path).name, ctx.event.data.get("metadata", {}))

    @inngest_client.create_function(fn_id="RAG: Ingest Texts", trigger=inngest.TriggerEvent(event="rag/ingest_texts"))
    async def rag_ingest_texts(ctx: inngest.Context):
        texts = ctx.event.data.get("texts", [])
        if not texts:
            return {"error": "texts array is required"}
        ids = await run_in_threadpool(rag_db.add_texts, texts, None, ctx.event.data.get("metadata"))
        return {"status": "ok", "ingested": len(ids), "ids": ids}

    @inngest_client.create_function(fn_id="RAG: Search", trigger=inngest.TriggerEvent(event="rag/search"))
    async def rag_search(ctx: inngest.Context):
        data = ctx.event.data
        query = data.get("query")
        if not query:
            return {"error": "query is required"}
        if llm is None:
            return {"error": f"No language model configured: {llm_error}"}

        def run():
            opts = AnswerOptions(top_k=data.get("top_k", 5), rerank=data.get("rerank", True), mode=data.get("mode"),
                                 verify=VERIFY_ANSWERS, correct=CORRECTIVE_RETRIEVAL)
            result = answerer.answer(query, opts)
            return {
                "answer": result["answer"], "metrics": result["metrics"], "verification": result["verification"],
                "sources": [{"id": s["id"], "score": s["score"]} for s in result["sources"]],
            }

        return await run_in_threadpool(run)

    inngest.fast_api.serve(app, inngest_client, [rag_ingest_file, rag_ingest_texts, rag_search])
