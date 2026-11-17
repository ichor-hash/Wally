# Changelog

## v3.1.0: self-checking answers

### Added
- **Answer verification (Self-RAG style).** Every cited claim is checked against only the chunks it cites. An unsupported claim triggers one rewrite, which is checked again. The UI shows "3/3 claims verified", a **Checks** panel with the verdict and reason for each claim, and the first draft when an answer was revised.
- **Corrective re-search (CRAG style).** When the reranker finds only weak evidence, the LLM rewrites the question in the documents' own wording, Ethan searches again, and both pools are reranked together.
- **Agent tools.** `calculate` (a safe arithmetic evaluator that cannot run code) and `search_documents` (a follow-up search with new numbered sources). Each step is shown under the answer. On per user in Settings.
- **Contextual chunk headers.** Every chunk of every uploaded file is indexed with its document title and section. PDFs use their embedded title, and headings are found even when a PDF or Markdown file has no blank lines around them. The `llm` mode adds a one-call-per-document summary. `scripts/reindex_context.py` upgrades documents already in the library.
- **Answer grading** in the evaluation: 31 questions at three pipeline levels, recording verification, revisions, re-searches and tool calls per question. Results are shown in the app's Evaluation view, as committed run logs, and as screenshots in the README.
- Four calculation questions in the golden set (40 in total).
- `--only` and `--levels` in `evals/run_evals.py` to re-grade selected cases without a full run.
- Settings for verification, re-search and agent tools; Re-search and Verify stages in the timing charts; a claims-verified figure on the Performance page.
- 32 more unit tests (52 in total), using fake models.

### Changed
- Default model is `openai/gpt-oss-120b`; `gpt-oss-20b` remains available with `LLM_MODEL`.
- The prompt now asks the model to answer the supported part of a question and say what is missing, instead of refusing outright.
- The reranker reads plain chunk text. Reading the contextual header too cost one top-1 hit in the evaluation.
- Next.js 16.4.3 → 16.4.6 (security advisory), zod 4.6.7; `npm audit fix` applied.

### Fixed
- Corrective re-search without the reranker ignored a better score from the rewritten query.
- Citation markers on their own line after a list were dropped by the claim extractor, which under-counted verified claims.
- `gpt-oss` artefacts such as `【commentary】`, LaTeX `\(...\)` and `[(3)]` citations are cleaned from answers.
- Evaluation runs never store provider error messages, which can include account identifiers, and record failed requests as errors rather than wrong answers.

### Removed
- The GitHub Actions workflows. Evaluations are shown in the README and the app instead.
- The legacy Streamlit UI (`app.py`) and the `streamlit` optional dependency; the Next.js app replaced it in v2.

### Results
- Answers: 28/31 (v2 pipeline) → **31/31**.
- Claims verified: **34/35** (1 partly supported).
- Retrieval: 39/40, right chunk first 83%, unanswerable questions caught 4/4.


## v3.0.0: Ethan

Wally is now **Ethan**. This release changes retrieval, measures it, and makes the result cheaper to run and easier to host.

### Retrieval
- **Hybrid search.** Each chunk stores a BM25 sparse vector next to its dense vector. Queries run both searches in one Qdrant round trip and merge them with reciprocal rank fusion. Search mode (hybrid, meaning, keywords) is selectable per question.
- **Reranking on by default.** The cross-encoder's relevance score now drives the grounding label. The reranker loads in the background when the app opens.
- **Structure-aware chunking.** Tables stay whole with their caption and section heading, headings travel with their text, list labels stay with their list, small fragments are merged, and the fixed window no longer cuts words. `CHUNK_STRATEGY=fixed` keeps the old behaviour.
- Sources report how they were found (meaning, keywords or both), their section, and match and relevance scores.

### Evaluation
- A golden set of 36 questions: semantic, exact-term, table and unanswerable.
- `evals/run_evals.py` compares five retrieval configurations and optionally grades generated answers. It writes `evals/results/REPORT.md` with every pass and failure.
- Results: retrieval **29 → 35 of 36**, right chunk first **53% → 91%**, unanswerable questions caught **1 → 4 of 4**. Generated answers **24 → 27 of 27**.
- A new **Evaluation** view in the app.
- GitHub Actions CI: unit tests, the retrieval evaluation as a quality gate, and frontend lint, typecheck and build. The answer evaluation can be run on demand.

### Charts and tables (OpenUI)
- Answers that compare numbers can include a bar, line, area or pie chart, or a table, written by the model in OpenUI Lang and rendered with `@openuidev/react-lang`. Off by default; toggle in Settings.
- The component set is display-only. The model's instructions are generated from the same library the browser renders (`npm run gen:prompt`), and CI checks they are in sync.
- The Performance and Evaluation views draw their charts through the same renderer.

### Cost
- Per-answer tokens and cost, from configurable prices. Lifetime totals and the query log persist across restarts.
- An answer cache keyed on the question, settings, history and index version, so any library change invalidates it.
- Context and output budgets, temperature 0.2, and `reasoning_effort=low` for `gpt-oss` models. Completion tokens fell 65% with no loss of accuracy, and empty answers caused by the reasoning budget are gone.
- An `openai_compatible` LLM provider for Ollama, LM Studio, vLLM and llama.cpp: free, private answers.
- Faster `/health` and `/documents`: cached aggregates instead of a full scan on every poll.

### Hosting
- Qdrant can run embedded (`QDRANT_PATH`), so local use needs no Docker.
- A CPU-only API Dockerfile with the models baked in, a web Dockerfile, and `docker-compose.yml`.
- `docs/HOSTING.md` covers five deployment options and a security checklist. `docs/COSTS.md` covers token economics.
- `CORS_ORIGINS` is configurable, and the client IP is taken from `X-Forwarded-For` behind a proxy.
- `/ingest/directory` is now off unless `ALLOW_DIRECTORY_INGEST=true`. Inngest is off unless `INNGEST_ENABLED=true`, and is no longer a required dependency.
- `scripts/migrate_collection.py` upgrades a v2 collection without re-uploading. Old collections keep working dense-only.

### Renamed
- `wally-frontend/` → `ethan-frontend/`, `wally_data/` → `ethan_data/`, `WALLY_DATA_DIR` → `ETHAN_DATA_DIR`, mascot shortcut **Shift + E**, default collection `ethan_docs`.


## v2.2.0 — Ethan the mascot

### Added
- Pixel-art mascot built from the Stormhead sprite sheets (idle, run, attack, damaged, death), merged into one atlas and stepped with CSS transforms.
- Peeks from the screen corner; click reactions with typed pixel speech bubbles; a four-click faint and respawn.
- Page-change cameos with page-specific lines, followed by a sprint or a lightning beam back to the corner.
- Random rampages across the screen firing lightning, plus a **Shift + W** shortcut.
- Respects `prefers-reduced-motion`; never triggers while the user is typing.

## v2.1.0 — Apple 10-K demo

### Added
- `COMPANY_PROFILE` setting: company background injected into the system prompt (not citable); the company name is shown on the Ask screen.
- `demo/` with Risk Factors (Item 1A) and MD&A (Item 7) from Apple's FY2025 Form 10-K, extracted from SEC EDGAR.
- `docs/DEMO_GUIDE.md` rewritten around the Apple scenario: setup checklist, live script with tested questions, a hand-checked evaluation (6 of 7 correct), root-cause analysis of the table failure with four fixes, prepared answers and a figures cheat sheet.

## v2.0.0 — Company knowledge assistant

### Added
- **Streaming answers.** Real token-by-token streaming from Groq over Server-Sent Events (`POST /search/stream`) with stage events, time to first token and a Stop control.
- **Cross-encoder reranking.** `cross-encoder/ms-marco-MiniLM-L-6-v2` re-scores 3×top_k candidates; switch it on in Settings. It loads lazily, and `POST /reranker/warmup` preloads it.
- **Performance metrics.** Separate embed, search, rerank and generation timings; exact prompt and completion tokens from the provider; median, 95th-percentile and per-question history (`GET /metrics`).
- **Citations and grounding.** Numbered chunks in the prompt, clickable `[n]` citations, and a grounding label on every answer.
- **Document preview.** Every chunk of a document with length statistics, a histogram, a citation map and highlighting of chunks used in recent answers (`GET /documents/{name}/chunks`).
- **Knowledge gaps and feedback.** Weakly matched questions and answers marked not helpful are persisted and listed (`GET /insights`, `POST /feedback`).
- **Rate limiting.** Per-client sliding window with standard headers; the UI shows remaining quota and the provider's token quota, and queues questions automatically.
- **Resilience.** Toast notifications, a live connection indicator with automatic re-checks, and upload retries with exponential back-off.
- **Follow-up context.** The last three exchanges are sent with each question.
- **New interface.** A spacious, light design with sidebar navigation (Ask, Library, Performance, Knowledge gaps, Settings) and Satoshi + Figtree typography.

### Changed
- Re-uploading a file replaces its previous chunks instead of duplicating them.
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
