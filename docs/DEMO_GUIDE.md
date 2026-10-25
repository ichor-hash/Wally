# Demo guide

A ten-minute walkthrough of Wally, with the points worth making at each step and short answers to likely questions.

## Before the demo

```bash
docker start wally-qdrant                                   # or the docker run command in the README
venv\Scripts\python.exe -m uvicorn main:app --port 8001     # backend
cd wally-frontend && npm run dev                             # frontend, http://localhost:3000
```

Check the sidebar foot reads **Online**. Turn **Rerank passages** on once in Settings so the model is already loaded. Keep one PDF ready to upload, plus the sample policy in `docs/samples/remote-work-policy.md`.

## The one-sentence pitch

> Wally answers questions about company documents, shows exactly which passages each answer came from, measures every step of the pipeline, and tells you what your documentation is missing.

## Walkthrough

| # | Do | Say |
|---|---|---|
| 1 | **Library** → drag in both files | Files are parsed, split into ~512-character overlapping chunks, embedded locally into 384-d vectors and stored in Qdrant. Re-uploading a file replaces the old version. |
| 2 | Click a document | Every passage, its length distribution, and a citation map. This is the exact text the model will see. |
| 3 | **Ask** a specific question, e.g. *"How many days can I work remotely?"* | The answer streams token by token. Retrieval finishes in under 100 ms; most of the time is generation. |
| 4 | Click a citation number, then **Sources** | Every claim is traceable. *Match* is cosine similarity; *relevance* is the reranker's score. |
| 5 | Click **Timing** | Real numbers: embed, search, rerank, generate, time to first token, and exact token counts from the provider. |
| 6 | Ask a follow-up, e.g. *"Who approves exceptions?"* | The last three exchanges go with the question, so follow-ups work. |
| 7 | Ask something not in the documents, e.g. *"What is the pet holiday policy?"* | The model says it does not know instead of inventing an answer. The label shows *weakly grounded*. |
| 8 | **Knowledge gaps** | That question was logged automatically. This is the to-do list for whoever owns the documentation. |
| 9 | **Performance** | Median and 95th-percentile latency, and a per-question breakdown of where time goes. |
| 10 | **Settings** → toggle reranking, ask the same question | Retrieve 3× candidates with fast vector search, then re-score them with a slower but more precise cross-encoder. |

## Key concepts, briefly

- **RAG.** Retrieve relevant passages first, then have the LLM answer only from them. This reduces hallucination and keeps answers current without retraining.
- **Embeddings.** A neural network maps text to a vector; similar meaning gives nearby vectors. Similarity is the cosine of the angle between them.
- **HNSW.** Qdrant's graph index finds approximate nearest neighbours in roughly logarithmic time instead of comparing against every vector.
- **Bi-encoder vs cross-encoder.** The embedder encodes question and passage separately (fast, approximate). The reranker reads them together (slow, precise). Using both is the standard two-stage retrieval pattern.
- **Chunk overlap.** 50 shared characters between neighbouring chunks keep sentences that cross a boundary intact.
- **Streaming (SSE).** The server pushes tokens as they are generated, so perceived latency is time to first token, not total time.

## Likely questions

**Why not fine-tune the model on company documents?**
Fine-tuning is expensive, has to be repeated whenever a document changes, and cannot cite sources. RAG updates the moment a file is uploaded, and every answer is traceable.

**How do you reduce hallucination?**
Three ways. The prompt restricts the model to the numbered passages and requires citations. A grounding label warns when retrieval was weak. Weak cases are logged as knowledge gaps.

**Why these models?**
MiniLM embeddings and the MiniLM cross-encoder are free, small, and run on a CPU. `gpt-oss-20b` on Groq is free and very fast. Each provider sits behind an interface in `embeddings.py` and `llm.py`, so swapping one is a single-line change.

**How does it scale?**
Qdrant handles millions of vectors with HNSW. The API is stateless apart from in-memory metrics, which would move to Redis. Embedding can be batched or moved to a GPU.

**What are the limitations?**
No access control per document, no OCR for scanned PDFs, metrics reset on restart, and grounding is score-based rather than a true fact check. See the README's final section.

**How is rate limiting done?**
A sliding 60-second window per client IP. Responses carry `X-RateLimit-*` and `Retry-After` headers, and the UI queues questions instead of failing.
