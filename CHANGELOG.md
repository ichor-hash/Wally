# Changelog

## v2.0.0 — Company knowledge assistant

### Added
- **Streaming answers.** Real token-by-token streaming from Groq over Server-Sent Events (`POST /search/stream`) with stage events, time to first token and a Stop control.
- **Cross-encoder reranking.** `cross-encoder/ms-marco-MiniLM-L-6-v2` re-scores 3×top_k candidates; switch it on in Settings. It loads lazily, and `POST /reranker/warmup` preloads it.
- **Performance metrics.** Separate embed, search, rerank and generation timings; exact prompt and completion tokens from the provider; median, 95th-percentile and per-question history (`GET /metrics`).
- **Citations and grounding.** Numbered passages in the prompt, clickable `[n]` citations, and a grounding label on every answer.
- **Document preview.** Every passage of a document with length statistics, a histogram, a citation map and highlighting of passages used in recent answers (`GET /documents/{name}/chunks`).
- **Knowledge gaps and feedback.** Weakly matched questions and answers marked not helpful are persisted and listed (`GET /insights`, `POST /feedback`).
- **Rate limiting.** Per-client sliding window with standard headers; the UI shows remaining quota and the provider's token quota, and queues questions automatically.
- **Resilience.** Toast notifications, a live connection indicator with automatic re-checks, and upload retries with exponential back-off.
- **Follow-up context.** The last three exchanges are sent with each question.
- **New interface.** A spacious, light design with sidebar navigation (Ask, Library, Performance, Knowledge gaps, Settings) and Satoshi + Figtree typography.

### Changed
- Re-uploading a file replaces its previous passages instead of duplicating them.
- Files are stored under their real name (previously the temporary upload name).
- `/documents`, `/health` and deletion paginate through the whole collection instead of the first 1,000 points.
- Deletion and per-document queries use a Qdrant payload filter backed by a keyword index on `source_file`.
- Blocking model calls no longer run on the async event loop.
- `requirements.txt` and `pyproject.toml` pinned to tested versions; `.env.example` added.

### Fixed
- Chunk overlap was never applied because of an always-true guard in `chunk_text`.
- The `rerank` request flag was silently dropped by the TypedDict request model.
- Removed unreachable code after `get_document_chunks`.
- The backend failed to start because `sse-starlette` was imported but not installed; streaming now uses FastAPI's built-in `StreamingResponse`.

## v1.1.0

- Replaced llama-index with pypdf for PDF parsing; custom sentence-aware chunking.
- Fixed the embedding provider parameter mismatch in `vector_db.py`.
- Local HuggingFace embeddings as the default.

## v1.0.0

- Initial RAG pipeline: PDF ingestion, Qdrant vector search, Groq answers, Streamlit UI.
