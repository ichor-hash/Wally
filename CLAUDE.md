# CLAUDE.md

Guidance for AI coding assistants (and new contributors) working on Ethan. It records how the system works, the decisions behind it and the conventions to keep. Plans and research for what comes next are in [docs/FUTURE.md](docs/FUTURE.md).

## What Ethan is

A company-knowledge RAG assistant. Employees ask questions and get answers that cite the source chunks. Every cited claim is fact-checked against the chunks it cites. Python/FastAPI backend, Next.js frontend, Qdrant vector store. Everything except the language model runs locally on CPU: embeddings, BM25, reranking and the safe calculator. The project was named Wally before v3, and the GitHub repository still uses that name.

## Layout

| Path | What it is |
|---|---|
| `main.py` | FastAPI app: config from env, `/search`, `/search/stream` (SSE), upload/ingest, `/health`, `/metrics`, `/evals`. |
| `answering.py` | `Answerer.run()`: the whole answer pipeline as an event generator. The API and the eval both call it, so the eval measures what users get. |
| `pipeline.py` | `Retriever`: hybrid search, rerank, corrective re-search; `prune_context`, `trim_to_budget`. |
| `vector_db.py` | Qdrant wrapper: named vectors `dense` (MiniLM-L6, 384-d) + `bm25` sparse with `Modifier.IDF`, RRF fusion (k=60), embedded mode via `QDRANT_PATH`. |
| `sparse.py` | BM25 document/query encoding (no model, no corpus statistics in process). |
| `reranker.py` | Cross-encoder `ms-marco-MiniLM-L-6-v2`. Reads plain chunk text, not the contextual header. |
| `verify.py` | Claim extraction and the LLM fact-check (SUPPORTED / PARTIAL / UNSUPPORTED), revision prompt. |
| `tools.py` | Agent tools: AST-whitelisted `calculate`, `search_documents`. |
| `contextual.py` | Contextual chunk headers (`off` / `header` / `llm`). |
| `data_loader.py` | Structure-aware chunking: tables kept whole, inline headings detected, PDF metadata titles. |
| `llm.py` | Providers: Groq (default `openai/gpt-oss-120b`), OpenRouter, any OpenAI-compatible server (Ollama, vLLM). |
| `costs.py` | `Pricing`, `AnswerCache`, `normalize_question`. |
| `telemetry.py` | Per-query metrics, knowledge gaps, rate limiter; persisted in `ethan_data/`. |
| `evals/` | `golden.json` (40 cases), `run_evals.py`, committed `results/`. |
| `scripts/` | `reindex_context.py` (backfill contextual headers), `migrate_collection.py` (v2 to hybrid). |
| `ethan-frontend/` | Next.js 16 app; OpenUI renders charts in answers. |
| `docs/` | `EVALUATION.md`, `COSTS.md`, `HOSTING.md`, `RUNBOOK.md`, `DEMO_GUIDE.md`, `TECHNICAL_OVERVIEW.md`, `FUTURE.md`, screenshots. |

## Running and checking

```bash
# backend (embedded Qdrant, no Docker needed when QDRANT_PATH is set in .env)
venv/Scripts/python.exe -m uvicorn main:app --port 8001
# frontend
cd ethan-frontend && npm run dev            # or: npm run build && npx next start -p 3000

# before finishing a change
venv/Scripts/python.exe -m pytest -q tests  # fake models, no network
cd ethan-frontend && npm run lint && npm run typecheck && npm run build
python evals/run_evals.py                   # retrieval eval, free, about a minute
python evals/run_evals.py --answers         # answer grading, spends LLM tokens
python evals/run_evals.py --answers --levels v3 --only s08,k02   # re-grade a few cases
```

Set `HF_HUB_OFFLINE=1` once the two local models are cached. Embedded Qdrant can be opened by only one process, so stop the API before running `scripts/*.py` against the same `QDRANT_PATH`. The eval builds its own in-memory indexes and does not need that.

## The answer pipeline

1. **Retrieve.** Hybrid dense + BM25 with RRF, then top_k × 3 candidates are reranked by the cross-encoder.
2. **Correct.** If the best rerank score is below 0.30 (dense: below 0.25), the LLM rewrites the question in document wording and Ethan searches again. Both pools are reranked, and each chunk keeps its better score.
3. **Prune.** When the best score is strong, chunks below `CONTEXT_PRUNE_RATIO` (1%) of it are dropped, keeping at least 2. Then `MAX_CONTEXT_CHARS` caps the rest.
4. **Generate.** The answer is streamed with `[n]` citations, or produced by an agent loop with tools (max 4 steps).
5. **Verify.** Cited claims are extracted. An uncited lead line is attached to the cited line below it, and a citation-only line covers the list above it. One LLM call returns a verdict per claim. It can run on `CHECK_MODEL`.
6. **Revise.** If any claim is UNSUPPORTED, the answer is rewritten once and verified again.
7. **Complete.** Metrics are reported: per-stage timings, tokens, cost summed per call at that call's model price, and chunks pruned.

## Measured results (keep these honest)

From `evals/results/` (gpt-oss-120b, 2026-11-17):

- **Retrieval, default (hybrid + context + rerank):** 39/40, hit@1 83%, hit@5 97%, MRR 0.87, rejection 100%. The v2 baseline was 33/40, 50%, 89%, 0.65 and 25%.
- **Answers:**
  - v2: 28/31, 1,127 tokens.
  - v3: 31/31, 34/35 claims verified, 1,679 tokens, 2.3 calls, 9.1 s.
  - v3 + agent: 31/31, 32/32 claims verified, 2,090 tokens.
- **Context pruning:** −16% prompt tokens and −11% cost per answer, 30/30 correct. The live run used a 2% cutoff; the default is 1%.
- **Contextual headers:** they help without the reranker and have no effect with it. The docs say so.
- **The one retrieval miss** is s12 ("risk if important employees leave"). Corrective re-search rescues it.

## Decisions and why

- **The reranker reads plain text.** Feeding it the contextual header cost a top-1 hit.
- **No similarity-based answer cache.** "Net sales in 2024" and "in 2023" are 0.977 similar with MiniLM, so a similarity cache would return the wrong year. The cache normalises only case, punctuation, articles and was/were.
- **Pruning applies only when evidence is strong.** With weak scores the right chunk can score 0.000 (s15).
- **gpt-oss-120b is the default with `reasoning_effort=low`.** The default effort wasted output on hidden reasoning and once returned an empty answer. 120b also has its own Groq daily quota, separate from 20b's.
- **No CI workflows.** The owner wants evaluations shown as README tables, terminal screenshots and the in-app Evaluation view, not GitHub Actions.
- **No Streamlit UI.** It was removed in v3.1; the Next.js app is the only UI.
- **Contextual headers apply to every uploaded file,** not just the demo corpus. `scripts/reindex_context.py` backfills older documents.
- **OpenUI charts can't be themed** (genui-lib bundles its own ThemeContext). Don't add a ThemeProvider.

## Conventions

- **Never store or publish raw provider error messages.** They can contain account or org identifiers. The eval records only the error kind.
- **`.env` stays gitignored.** Never commit keys. Prices are configuration (`LLM_PRICE_*`, `CHECK_PRICE_*`), not constants.
- **Report evaluation results faithfully.**
  - If a change moves cases, re-grade them with `--only` and say so in `docs/EVALUATION.md`.
  - Never hand-edit results.
  - A partial run without `--only` overwrites other levels, so back up `evals/results` first.
- **Groq free tier:** 8k tokens per minute and 200k per day per model. A full answer run (3 levels × 31 questions) uses most of a day's quota. Check it before a run.
- **The owner pushes straight to `master`,** the repo's main branch, when they ask for a push.
- **Tests use fake models** (`ScriptedLLM`, `FakeEmbedder`, `AxisEmbedder`). Add a test for each behaviour change.
- **Docs style:** plain, measured claims with numbers, and state limitations openly.

## Where the project is going

The full plan is [docs/FUTURE.md](docs/FUTURE.md). In short:

- **Chosen architecture: Audited System 1.** Non-generative "System 1" checks run before the LLM fact-check, cheapest first:
  1. an exact-key claim ledger tied to chunk `sha256` hashes;
  2. a deterministic check that the claim's numbers and key terms appear verbatim in the cited chunk;
  3. a local int8 NLI verifier (HHEM-2.1-Open or FactCG), with Jev as an optional backend.
- **Only unresolved claims go to the LLM.** A random audit at probability ε, which is logged as the propensity, keeps an unbiased error estimate, re-certifies the threshold and supplies training labels. Re-certification is split by chunk hash after uploads, so only decisions touching changed chunks are re-certified.
- **What we may claim is new:** the integration, re-certification split by chunk hash, and claim-level invalidation of past answers. The mechanisms (IPW audits, Learn-then-Test, cascades) are prior work. Do not overclaim.
- **Build order:**
  - Phase 0: keep the labels (`decisions.jsonl`, `chunk_sha`).
  - Phase 1: shadow mode.
  - Phase 2: gate.
  - Phase 3: ledger and outdated-answer alerts.
  - Phase 4: more decision types.
  - Each phase sits behind `S1_*` flags, off by default, and is tested with fakes.
- **Certifying needs human labels.** That means about 200–250 per decision type; the LLM judge only gives agreement. The golden set certifies nothing.
- **Jev** (TypeSafe AI, `POST /v1/systemone`, typed bool/choice/score answers):
  - only as an opt-in backend;
  - hosted in the US, with no data processing agreement;
  - weak on numbers;
  - its confidence was not shown to beat random routing.
  - Never send confidential collections to it.

## Decisions log (from the build sessions with the owner)

- **v3.1** (2026-11-17):
  - rename Wally → Ethan;
  - hybrid retrieval, reranker, contextual headers for every uploaded file;
  - CRAG re-search, Self-RAG verification and revision, agent tools;
  - OpenUI charts;
  - evaluations shown as screenshots and tables, not CI;
  - Streamlit removed.
- **Cost round** (2026-11-17): context pruning, `CHECK_MODEL`, normalised cache key; the similarity cache was rejected.
- **System 1 research** (2026-11-17):
  - four researchers: JEPA, dual-process/cascades, latent memory/verifiers, Jev;
  - then a tribunal: novelty prosecutor, engineering judge, statistics judge;
  - verdict above.
- **Novel ideas raised earlier and kept in the backlog:**
  - deterministic claim pre-check;
  - sentence-level compression;
  - adaptive stage skipping;
  - outdated-answer alerts;
  - contradiction check at upload;
  - knowledge-gap drafting.
