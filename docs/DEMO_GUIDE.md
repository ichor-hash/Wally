# Demo guide: Wally at Apple

A ten-minute live demo. Wally plays the internal knowledge assistant for Apple's finance and investor-relations team, answering from Apple's real annual report (FY2025 Form 10-K, filed with the SEC on 31 October 2025).

Every question below was run against this exact setup. The expected answers are what Wally actually returned.

---

## 1. The story in 30 seconds

> Analysts spend hours searching 100-page annual reports. Wally lets them ask questions in plain English and answers only from the filing, with a citation for every claim, so every number can be checked in one click. It also measures itself: how fast, how many tokens, how well grounded. And it tells the team which questions the documents can't answer yet.

---

## 2. What you are showing, in plain words

| Term | Meaning |
|---|---|
| **SEC** | The US Securities and Exchange Commission. Every listed US company must file reports with it, and they are public. |
| **Form 10-K** | A company's official **annual report** to the SEC. It is long (Apple's is about 60 pages) and follows a fixed layout of numbered "Items". |
| **Item 1A, Risk Factors** | The company lists everything that could seriously hurt its business: supply chain, competition, regulation, tariffs, cybersecurity. Written by lawyers, mostly text. |
| **Item 7, MD&A** | *Management's Discussion and Analysis*: management explains **what happened this year and why**, such as "Greater China sales fell because of lower iPhone sales". Text plus tables of numbers. |
| **Fiscal year** | Apple's year ends on the last Saturday of September. **FY2025 = 29 Sep 2024 to 27 Sep 2025.** |
| **Reportable segments** | How Apple splits its sales by region: Americas, Europe, Greater China, Japan, Rest of Asia Pacific. |

**Why this is a good RAG use case:** the documents are long, factual, change every year, and must be cited exactly. That's precisely what retrieval-augmented generation is for.

### Files used

| File | What it is | Size | Chunks |
|---|---|---|---|
| `demo/apple-fy2025-10k-risk-factors.txt` | Item 1A, Risk Factors | 68k characters | 145 |
| `demo/apple-fy2025-10k-mdna.txt` | Item 7, MD&A | 18.5k characters | 39 |

Both were extracted from the SEC filing (`aapl-20250927.htm`, EDGAR) with page footers removed. Nothing was edited.

### Company context

`.env` contains:

```
COMPANY_NAME=Apple Inc.
COMPANY_PROFILE=Apple Inc. designs, manufactures and markets smartphones, ... fiscal 2025 ended September 27, 2025 ...
```

`COMPANY_NAME` sets who Wally works for (shown on the Ask screen). `COMPANY_PROFILE` is added to the system prompt as background so Wally understands "this fiscal year" or "segments". It is marked *not citable*, so facts still have to come from the filing.

---

## 3. Setup checklist

**The night before**
1. Start Docker Desktop.
2. Start Qdrant: `docker start eager_leavitt` (your existing container). Check <http://localhost:6333/dashboard>.
3. Backend, in the project folder:
   ```
   .\venv\Scripts\python.exe -m uvicorn main:app --port 8001
   ```
4. Frontend:
   ```
   cd wally-frontend
   npm run dev
   ```
5. Do one full rehearsal using section 4, then clear the library (Library → Remove) so you can upload live.

**Ten minutes before**
1. Open <http://localhost:3000> in a **maximised** window. The quota and token panel only shows on wide screens.
2. Check the sidebar foot reads **Online**.
3. **Settings:** turn **Rerank chunks** on (loads the model now, not during the demo) and leave sources per answer at **5**.
4. Ask one throwaway question to warm everything up, then click **Clear conversation**.
5. Keep File Explorer open at the `demo` folder for drag-and-drop.

---

## 4. Live script

| # | Do | Say | Expect |
|---|---|---|---|
| 1 | Show the Ask screen | "This is Wally, configured as Apple's internal knowledge assistant. The library is empty." | "Knowledge assistant for Apple Inc." above the heading |
| 2 | **Library** → drag in both `demo` files | "These are two sections of Apple's real 10-K. Each file is split into overlapping ~512-character chunks, embedded locally into 384-number vectors, and stored in Qdrant." | 145 and 39 chunks, about 2 seconds each |
| 3 | Click `apple-fy2025-10k-mdna.txt` | "This is exactly what the model gets to see: every chunk, its length, and later which chunks get cited." | Document preview |

### Question 1: Risk Factors

**Ask:** `What risks does Apple face from relying on outsourcing partners and single-source suppliers?`

**Expect:** *Well grounded.* Manufacturing is concentrated with outsourcing partners mainly in China, India, Japan, South Korea, Taiwan and Vietnam; it relies on single-source suppliers; supply can be disrupted.

**Say:** "Every bullet carries a citation number. Click one." *(Click a number; the source chunk opens.)* "That's the original 10-K text. Nothing is invented."

### Question 2: MD&A, the "why"

**Ask:** `Why did Greater China net sales decline in 2025?`

**Expect:** *Well grounded (about 100% relevance).* "Mainly because of lower iPhone sales, partially offset by higher Mac sales." That matches the filing word for word.

**Say:** "This is the explanation management wrote in MD&A. Click **Timing**: retrieval took about 0.1 s, and generation about 1 s. These are exact token counts reported by the model provider, not estimates."

### Question 3: across both documents

**Ask:** `How did U.S. tariffs affect Apple in fiscal 2025?`

**Expect:** *Well grounded.* Tariffs announced from the second quarter of 2025 on imports from China, India, Japan, South Korea, Taiwan, Vietnam and the EU; impact on the supply chain and results. **Sources come from both files.**

**Say:** "Open **Sources**: chunks from MD&A *and* Risk Factors. Wally combined two sections of the report into one answer."

### Question 4: out of scope

**Ask:** `What is Apple's parental leave policy for employees?`

**Expect:** *Weakly grounded.* "The provided chunks do not include any information about Apple's parental leave policy…"

**Say:** "It refuses instead of making something up. Now look at **Knowledge gaps**." *(Open it.)* "The question was logged automatically, so the documentation team knows what to add next."

### Question 5: the limitation (tables)

**Ask:** `Which reportable segment grew fastest in 2025, and by how much?`

**Expect:** Wally says **Europe, +10%**, labelled *Well grounded*. **This is wrong.** The correct answer is **Japan, +15%**.

**Say:** "This is the most important slide. It looks confident, but it's wrong. Let me show you why."
*(Library → `apple-fy2025-10k-mdna.txt` → search **Japan**.)*

**Explain, then continue with section 5:**
- The segment table was split across **two chunks**. Chunk 8 has the table title and only the Americas and Europe rows. Chunk 9 has Japan (+15%) but no title.
- Retrieval matched the question to the chunk with the title, so the model only saw two rows and picked the larger.
- The grounding label measures *retrieval relevance*, not *answer correctness*, so it can't catch this.

### Finish (1 minute)

1. **Performance** tab: "Median response about 1.1 s. Embedding and search take milliseconds; almost all the time is the language model."
2. Sidebar foot: "Rate limiting per user, plus Groq's own token quota, live. Over the limit, questions queue instead of failing."
3. **Settings**: "Reranking, streaming and source count are all switchable."
4. **Wally**: click the mascot in the corner, then press **Shift + W**. "And this is Wally. He hunts hallucinations." He charges across the screen firing lightning. End on a smile.

**Closing line:**
> Wally answers from the documents, proves every claim, measures itself, admits what it doesn't know, and I can show you exactly where it still fails and how I'd fix it.

---

## 5. The limitation, and how to fix it

| | |
|---|---|
| **What happened** | A table was split across chunks. Retrieval found the half with the title, the model answered from incomplete data, and the confidence label stayed high. |
| **Root cause** | Character-based chunking treats a table like prose, and plain-text extraction keeps the numbers but loses the column headers. |
| **Fix 1: structure-aware chunking** | Never split inside a table; keep each table, with its title and column headers, as one chunk. |
| **Fix 2: structured data** | Every 10-K also ships as **XBRL**, machine-readable financial data. Load the tables into a database and let the model query it (text-to-SQL) instead of reading flattened text. |
| **Fix 3: compute, don't guess** | For "fastest", "growth" or "ratio" questions, have the model call a calculator or Python tool on the extracted numbers. |
| **Fix 4: better confidence** | Add an answer-checking step (an LLM judge or an NLI model) that verifies each claim against its cited chunk, instead of relying only on retrieval scores. |

---

## 6. Evaluation: what I tested

Seven questions with answers checked by hand against the filing:

| Question | Grounding | Correct? |
|---|---|---|
| Outsourcing and single-source supplier risks | Well (0.76) | ✓ |
| Why Greater China net sales declined | Well (1.00) | ✓ |
| How U.S. tariffs affected Apple | Well (0.99) | ✓ |
| Why Services gross margin % increased | Well (1.00) | ✓ |
| Share repurchases and dividends in 2025 | Well (0.99) | ✓ ($89.3B repurchased, $15.4B dividends) |
| Parental leave policy (not in documents) | Weak (0.00) | ✓ refused correctly |
| Fastest-growing segment (table) | Well (0.81) | ✗ said Europe +10%, actually Japan +15% |

**6 of 7 correct (86%).** The failure is systematic (tables), not random, which is why it can be fixed.

Backup questions if you have time: *"Why did the Services gross margin percentage increase in 2025?"* and *"What drove Japan's net sales increase in 2025?"* (iPhone, Services and iPad).

---

## 7. Questions you may be asked

**What is RAG, and why not just ask ChatGPT?**
A general model has never read this filing, or read an older one, and can't cite sources. RAG first retrieves the relevant chunks from *our* documents, then the model answers only from them. The answers are current, specific and verifiable.

**Why not fine-tune a model on the 10-K?**
Fine-tuning is expensive, has to be redone every year, blends facts into the model's weights so they can't be cited, and still hallucinates. With RAG, a new filing is searchable the moment it's uploaded.

**How do embeddings work?**
A neural network (MiniLM, 384 dimensions) maps text to a vector so that similar meanings land close together. The question is embedded the same way, and the closest chunks are retrieved.

**Why cosine similarity?**
It compares direction, not length, so a short question can match a long chunk with the same meaning.

**What is HNSW?**
The index Qdrant uses: a layered graph that finds approximate nearest neighbours in roughly logarithmic time instead of comparing against every vector.

**Why 512-character chunks with 50 overlap?**
Small enough to be specific, big enough to hold a complete thought. The overlap keeps a sentence that crosses a boundary in both chunks. The table failure shows the trade-off: fixed sizes don't respect document structure.

**What does the reranker add?**
The embedder encodes question and chunk *separately*: fast but approximate. The cross-encoder reads them *together*: slow but precise. So we take 3× more candidates cheaply, then rerank to keep the best 5. You can see it in the relevance scores: near 100% for the right chunk, near 0% for the rest.

**How do you prevent hallucination?**
Three layers. (1) The prompt allows only the numbered chunks and requires a citation for every claim. (2) A grounding label warns when retrieval was weak. (3) Weak questions are logged as knowledge gaps. The table case shows the remaining risk, and the fix is answer verification (section 5).

**How did you evaluate it?**
A hand-checked test set (section 6): 6 of 7 correct, with a systematic failure on tables. Next step: a larger test set scored automatically with RAGAS metrics (faithfulness, answer relevance, context recall).

**Which model, and why?**
`gpt-oss-20b`, an open-weight model, served by Groq: free tier and very fast (about 1 second per answer). Each provider sits behind an interface in `llm.py` and `embeddings.py`, so swapping models is a one-line change.

**Does company data leave the machine?**
Embedding, search and reranking run locally. Only the 5 retrieved chunks and the question are sent to Groq to write the answer. For strict confidentiality, swap in a self-hosted model; the interface already supports that.

**What does it cost?**
Zero in this setup: local embeddings, self-hosted Qdrant, Groq free tier. A typical question uses about 1,000–1,500 tokens.

**How fast is it?**
About 1–2 seconds end to end. Measured on this laptop over 10 questions: embedding about 20 ms, search about 25 ms, reranking about 0.3 s, generation about 0.9 s, total median 1.1 s. With streaming, the first words appear in about 1 second.

**What are the token counts for?**
Cost and capacity. Groq's free tier allows 8,000 tokens per minute; the sidebar shows what's left, and the per-answer timing panel shows prompt versus completion tokens.

**How does it scale?**
Qdrant handles millions of vectors. The API is stateless apart from in-memory metrics, which would move to Redis. Embedding can be batched or moved to a GPU, and more users means more API workers behind a load balancer.

**What about security, for example prompt injection inside a document?**
A malicious document could contain instructions. The prompt restricts the model to answering from chunks, and citations make odd answers visible, but it isn't fully solved. In production, add document access control and input filtering.

**Why not LangChain or LlamaIndex?**
The pipeline is small enough to write directly, which makes every step visible and measurable. Each stage is timed separately, which a framework would hide. The first version did use LlamaIndex for PDF parsing; it was replaced with pypdf to remove heavy dependencies.

**What was the hardest part?**
Making the system honest about itself: real streaming with exact token usage, per-stage timing, and finding the table failure and tracing it to chunking.

**What would you build next?**
Table-aware chunking and XBRL ingestion, automated evaluation with RAGAS, hybrid keyword-plus-vector search for exact terms, and per-team access control.

---

## 8. Numbers cheat sheet (Apple FY2025, from the MD&A)

| | FY2025 | Change |
|---|---|---|
| Total net sales | $416.2B | +6% |
| iPhone | $209.6B | +4% |
| Mac | $33.7B | +12% |
| iPad | $28.0B | +5% |
| Gross margin | 46.9% | from 46.2% |
| Services gross margin | 75.4% | from 73.9% |
| R&D | $34.6B | +10% |
| Fastest-growing segment | Japan | +15% |
| Greater China | $64.4B | −4% |
| Share repurchases | $89.3B | |
| Dividends paid | $15.4B | quarterly dividend raised to $0.26 in May 2025 |
| Cash and marketable securities | $132.4B | at 27 Sep 2025 |

---

## 9. If something goes wrong

| Symptom | Fix |
|---|---|
| Sidebar says **API offline** | Restart the backend (section 3, step 3) |
| **Database offline** | Docker Desktop is running? `docker start eager_leavitt` |
| First reranked answer is slow | The reranker was loading. Toggle it on in Settings before the demo. |
| "Rate limit reached" | Wait for the queue; it sends automatically. Mention it as a feature. |
| Token quota not visible | Maximise the window, and ask one question first (it comes from Groq's response) |
| Answer wording differs slightly from this guide | Normal: the model is not deterministic. The cited chunks will be the same. |
