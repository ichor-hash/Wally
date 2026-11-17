# Demo guide: Ethan at Apple

A ten-minute live demo. Ethan plays the internal knowledge assistant for Apple's finance and investor-relations team, answering from Apple's real annual report (FY2025 Form 10-K, filed with the SEC on 31 October 2025).

Every question below was run against this exact setup. The expected answers are what Ethan actually returned.

---

## 1. The story in 30 seconds

> Analysts spend hours searching 100-page annual reports. Ethan lets them ask questions in plain English and answers only from the filing, with a citation for every claim, so every number can be checked in one click. It also measures itself: how fast, how many tokens, how well grounded. And it tells the team which questions the documents can't answer yet.

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
| `demo/apple-fy2025-10k-risk-factors.txt` | Item 1A, Risk Factors | 68k characters | 177 |
| `demo/apple-fy2025-10k-mdna.txt` | Item 7, MD&A | 18.5k characters | 53, of which 5 are whole tables |

Both were extracted from the SEC filing (`aapl-20250927.htm`, EDGAR) with page footers removed. Nothing was edited.

### Company context

`.env` contains:

```
COMPANY_NAME=Apple Inc.
COMPANY_PROFILE=Apple Inc. designs, manufactures and markets smartphones, ... fiscal 2025 ended September 27, 2025 ...
```

`COMPANY_NAME` sets who Ethan works for (shown on the Ask screen). `COMPANY_PROFILE` is added to the system prompt as background so Ethan understands "this fiscal year" or "segments". It is marked *not citable*, so facts still have to come from the filing.

---

## 3. Setup checklist

**The night before**
1. Backend, in the project folder (no Docker needed; Qdrant runs inside it):
   ```
   .\venv\Scripts\python.exe -m uvicorn main:app --port 8001
   ```
2. Frontend:
   ```
   cd ethan-frontend
   npm run dev
   ```
3. Do one full rehearsal using section 4, then clear the library (Library → Remove) so you can upload live.
4. Run `.\venv\Scripts\python.exe evals\run_evals.py` so the **Evaluation** page shows a fresh report.

**Ten minutes before**
1. Open <http://localhost:3000> in a **maximised** window. The quota and token panel only shows on wide screens.
2. Check the sidebar foot reads **Online**.
3. **Settings:** search mode **Hybrid**, **Rerank chunks** on (the default), sources per answer **5**, and **Charts and tables** on.
4. Ask one throwaway question to warm everything up, then click **Clear conversation**.
5. Keep File Explorer open at the `demo` folder for drag-and-drop.

---

## 4. Live script

| # | Do | Say | Expect |
|---|---|---|---|
| 1 | Show the Ask screen | "This is Ethan, configured as Apple's internal knowledge assistant. The library is empty." | "Knowledge assistant for Apple Inc." above the heading |
| 2 | **Library** → drag in both `demo` files | "These are two sections of Apple's real 10-K. Each file is split into chunks of about 512 characters along its structure, so every table stays whole. Each chunk gets a 384-number meaning vector and a keyword vector, stored in Qdrant." | 177 and 53 chunks, a few seconds each |
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

**Say:** "Open **Sources**: chunks from MD&A *and* Risk Factors. Ethan combined two sections of the report into one answer."

### Question 4: out of scope

**Ask:** `What is Apple's parental leave policy for employees?`

**Expect:** *Weakly grounded.* "The provided chunks do not include any information about Apple's parental leave policy…"

**Say:** "It refuses instead of making something up. Now look at **Knowledge gaps**." *(Open it.)* "The question was logged automatically, so the documentation team knows what to add next."

### Question 5: the table that used to fail

**Ask:** `Which reportable segment grew fastest in 2025, and by how much?`

**Expect:** *Well grounded.* **Japan, +15%.**

**Say:** "This one is my favourite, because the first version got it wrong. It said Europe, +10%, and labelled that *well grounded*."
*(Library → `apple-fy2025-10k-mdna.txt` → find the segment table.)*
- Fixed-size chunks had cut the segment table in two: the title and two rows in one chunk, Japan's row in the next. The model only saw half the table.
- Now the chunker keeps every table whole, with its caption. "And I know it's fixed because it's in the evaluation set, which runs on every commit."

### Question 6: a chart

**Ask:** `Chart net sales by reportable segment for 2025.` *(Settings → Charts and tables on.)*

**Expect:** a written, cited answer plus a bar chart, drawn with OpenUI from the numbers in the cited chunk.

**Say:** "The model can add a chart when an answer compares numbers. It may only use display components, and only numbers that are in the sources."

### Question 7: an exact term

**Ask:** `ASU 2025-06 effective date`

**Expect:** *First quarter of 2029.* Open **Sources**: the top chunk says *via meaning + keywords*.

**Say:** "Pure vector search is fuzzy with codes like this. Ethan also runs a keyword search and merges the two rankings, which is hybrid retrieval. In the evaluation it found 11 of 11 exact-term questions."

### Question 8: a calculation, with tools

Turn on **Settings → Agent tools**. **Ask:** `What share of total 2025 net sales came from Services?`

**Expect:** about **26.2%**, with **Steps 1** under the answer: `Calculated 109158 / 416161 * 100 = 26.2298`, and *1/1 claims verified*.

**Say:** "The model doesn't do maths in its head. It calls a calculator and shows the call, and then Ethan checks the claim against the source table."

### Finish (1 minute)

1. **Evaluation** tab: "40 questions with known answers, and 31 graded answers. The first version answered 28 of 31 correctly; this one answers all 31, and its own checker verified 34 of 35 cited claims." *(Click the fastest-segment row to show v2's wrong answer next to v3's.)*
2. **Performance** tab: "Embedding and search take milliseconds; almost all the time is the language model. Scroll down: tokens and cost per question, and what the cache saved."
3. Sidebar foot: "Rate limiting per user, plus Groq's own token quota, live. Over the limit, questions queue instead of failing."
4. **Settings**: "Search mode, reranking, charts and source count are all switchable."
5. **Ethan**: click the mascot in the corner, then press **Shift + E**. "And this is Ethan. He hunts hallucinations." He charges across the screen firing lightning. End on a smile.

**Closing line:**
> Ethan answers from the documents, proves every claim, measures itself, admits what it doesn't know, and has the evaluation to show what improved and what still fails.

---

## 5. What changed since the first version, and what is left

| | First version | Now |
|---|---|---|
| Chunking | Fixed 512-character windows; tables cut in half | Structure-aware; each table whole with its caption |
| Retrieval | Vector similarity only | Hybrid: vectors + BM25 keywords, merged by reciprocal rank fusion |
| Reranking | Optional | On by default; drives the grounding label |
| Fastest-segment question | "Europe, +10%", wrong | "Japan, +15%", correct |
| Retrieval | | Corrective re-search when evidence is weak |
| Answers | | Every cited claim verified; rewritten once if a claim fails |
| Arithmetic | In the model's head | Calculator tool, step shown under the answer |
| Evaluation | 7 questions, checked by hand | 40 questions, retrieval and answers graded automatically |

**Still open:** one paraphrased question (*"What is the risk if important employees leave?"*) is missed by every setup; the grounding label measures relevance, not correctness; and numbers that span several tables are still read, not computed. Next steps: a stronger embedding model, an answer-verification step, and XBRL data with a calculator tool for financial questions.

---

## 6. Evaluation

Full details: [EVALUATION.md](EVALUATION.md).

| Retrieval setup | Passed (of 40) | Right chunk first | Unanswerable caught |
|---|---|---|---|
| First version | 33 | 50% | 1 of 4 |
| Hybrid | 31 | 75% | 1 of 4 |
| **Hybrid + context + reranker** | **39** | **83%** | **4 of 4** |

Generated answers, graded automatically on `gpt-oss-120b`: **31 of 31** correct now, 28 of 31 with the first version's pipeline. 34 of 35 cited claims verified by Ethan's own checker.

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
A golden set of 40 questions in five types (paraphrased, exact terms, tables, calculations, unanswerable), scored automatically at two levels: does retrieval find the chunk with the answer, and is the generated answer right and cited. Results are committed with every run, failures included (section 6).

**Which model, and why?**
`gpt-oss-120b`, an open-weight model, served by Groq: free tier and fast. `gpt-oss-20b` is the cheaper, faster option. Each provider sits behind an interface in `llm.py` and `embeddings.py`, so swapping models is a one-line change.

**Does company data leave the machine?**
Embedding, search and reranking run locally. Only the 5 retrieved chunks and the question are sent to Groq to write the answer. For strict confidentiality, swap in a self-hosted model; the interface already supports that.

**What does it cost?**
Zero in this setup: local embeddings and reranking, embedded Qdrant, Groq free tier. A typical question uses about 900 tokens, and repeated questions come from a cache at no cost. With paid prices set, the Performance page shows cost per question; [COSTS.md](COSTS.md) has the formula.

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
Answer verification against cited chunks, XBRL ingestion with a calculator tool for financial questions, a stronger embedding model, and per-team access control.

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
| **Database offline** | Another backend window is holding the embedded database; close it and restart the backend |
| First answer is slow | The reranker loads when the page first opens; ask a warm-up question before the demo. |
| "Rate limit reached" | Wait for the queue; it sends automatically. Mention it as a feature. |
| Token quota not visible | Maximise the window, and ask one question first (it comes from Groq's response) |
| Answer wording differs slightly from this guide | Normal: the model is not deterministic. The cited chunks will be the same. |
