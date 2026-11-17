# Evaluation report

Generated 2026-11-17 09:39 UTC on Windows (Python 3.12.10). Reproduce with `python evals/run_evals.py`.

**36 golden questions** over 3 documents: 17 semantic, 11 keyword, 4 table, 4 unanswerable.

## Retrieval: which configuration finds the right chunk

A case passes when a chunk containing the answer is in the top 5 or, for unanswerable questions, when retrieval reports weak grounding so the UI warns the user and logs a knowledge gap.

| Configuration | Passed | Hit@1 | Hit@5 | MRR | Unanswerable rejected | Avg latency |
|---|---|---|---|---|---|---|
| v2 baseline: fixed 512-char chunks, dense only | **29/36** | 53% | 88% | 0.67 | 25% | 10 ms |
| Structure-aware chunks, dense only | **28/36** | 66% | 84% | 0.74 | 25% | 10 ms |
| Structure-aware chunks, BM25 keyword only | **31/36** | 62% | 91% | 0.73 | 50% | 12 ms |
| Structure-aware chunks, hybrid (dense + BM25, RRF) | **31/36** | 75% | 94% | 0.82 | 25% | 13 ms |
| Structure-aware chunks, hybrid + cross-encoder rerank **(default)** | **35/36** | 91% | 97% | 0.93 | 100% | 251 ms |

### Passed by category

| Configuration | semantic | keyword | table | unanswerable |
|---|---|---|---|---|
| baseline-v2 | 16/17 | 10/11 | 2/4 | 1/4 |
| dense | 15/17 | 10/11 | 2/4 | 1/4 |
| keyword | 15/17 | 11/11 | 3/4 | 2/4 |
| hybrid | 16/17 | 11/11 | 3/4 | 1/4 |
| hybrid+rerank | 16/17 | 11/11 | 4/4 | 4/4 |

### Every case

Rank of the first relevant chunk (✅ n) or ❌. Unanswerable rows show whether weak grounding was reported.

| # | Category | Question | baseline-v2 | dense | keyword | hybrid | hybrid+rerank |
|---|---|---|---|---|---|---|---|
| s01 | semantic | What risks does Apple face from relying on outsourcing partners and single-source suppliers? | ✅ 3 | ❌ | ✅ 1 | ✅ 3 | ✅ 1 |
| s02 | semantic | Why did Greater China net sales decline in 2025? | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s03 | semantic | How did U.S. tariffs affect Apple in fiscal 2025? | ✅ 1 | ✅ 1 | ✅ 3 | ✅ 1 | ✅ 1 |
| s04 | semantic | Why did the Services gross margin percentage go up? | ✅ 1 | ✅ 1 | ✅ 2 | ✅ 1 | ✅ 1 |
| s05 | semantic | How much stock did Apple buy back and how much did it return in dividends during 2025? | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s06 | semantic | What drove the sales increase in Japan? | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s07 | semantic | How much cash and marketable securities does the company hold? | ✅ 2 | ✅ 1 | ✅ 2 | ✅ 1 | ✅ 1 |
| s08 | semantic | Why was the effective tax rate below the statutory rate? | ✅ 2 | ✅ 3 | ✅ 2 | ✅ 2 | ✅ 1 |
| s09 | semantic | What could happen if hackers break into the company's systems? | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s10 | semantic | How does a strong dollar hurt the company's results? | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s11 | semantic | Does Apple depend on mobile operators to sell its phones? | ✅ 1 | ✅ 1 | ❌ | ✅ 1 | ✅ 1 |
| s12 | semantic | What is the risk if important employees leave? | ❌ | ❌ | ❌ | ❌ | ❌ |
| s13 | semantic | How could natural disasters or a changing climate disrupt operations? | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s14 | semantic | How many days a week can staff work from home? | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s15 | semantic | What allowance do I get for home office furniture? | ✅ 5 | ✅ 1 | ✅ 4 | ✅ 1 | ✅ 1 |
| s16 | semantic | What made research and development spending grow? | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s17 | semantic | Which new products were announced in the fourth quarter? | ✅ 1 | ✅ 1 | ✅ 5 | ✅ 1 | ✅ 1 |
| k01 | keyword | ASU 2025-06 effective date | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| k02 | keyword | Section 232 investigation | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| k03 | keyword | DMA compliance changes | ✅ 3 | ✅ 3 | ✅ 4 | ✅ 3 | ✅ 3 |
| k04 | keyword | TCJA deemed repatriation tax payable balance | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| k05 | keyword | When will ASU 2023-09 be adopted? | ✅ 3 | ✅ 2 | ✅ 2 | ✅ 1 | ✅ 1 |
| k06 | keyword | State Aid Decision impact | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| k07 | keyword | commercial paper outstanding | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| k08 | keyword | Google LLC search licensing arrangement | ✅ 1 | ✅ 2 | ✅ 1 | ✅ 2 | ✅ 1 |
| k09 | keyword | VPN rule | ✅ 4 | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 |
| k10 | keyword | iPhone 16e | ❌ | ❌ | ✅ 1 | ✅ 3 | ✅ 1 |
| k11 | keyword | manufacturing purchase obligations | ✅ 2 | ✅ 1 | ✅ 2 | ✅ 1 | ✅ 1 |
| t01 | table | Which reportable segment grew fastest in 2025, and by how much? | ❌ | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| t02 | table | What were Mac and iPad net sales in 2025? | ✅ 2 | ❌ | ❌ | ❌ | ✅ 3 |
| t03 | table | What was the total gross margin percentage in 2025 compared with 2024? | ✅ 1 | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 |
| t04 | table | How much did Apple spend on research and development in 2025, 2024 and 2023? | ❌ | ❌ | ✅ 1 | ✅ 3 | ✅ 1 |
| u01 | unanswerable | What is Apple's parental leave policy for employees? | ❌ | ❌ | ❌ | ❌ | ✅ |
| u02 | unanswerable | Who is the CEO of Microsoft? | ❌ | ❌ | ✅ | ❌ | ✅ |
| u03 | unanswerable | What is the office dress code? | ✅ | ✅ | ✅ | ✅ | ✅ |
| u04 | unanswerable | How many vacation days do new hires get? | ❌ | ❌ | ❌ | ❌ | ✅ |

### Failures in detail

**baseline-v2**: 7 failed

- `s12` What is the risk if important employees leave?: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 17 (0.55), "more frequently or with more intense effects. In addition, the Company’s and its suppliers…"
- `k10` iPhone 16e: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-mdna.txt` chunk 12 (0.38), "29,984 | 2 | % | 29,357 iPad | 28,023 | 5 | % | 26,694 | (6) | % | 28,300 Wearables, Home …"
- `t01` Which reportable segment grew fastest in 2025, and by how much?: no single chunk holds the needed text with this chunking. Top result instead: `apple-fy2025-10k-mdna.txt` chunk 8 (0.63), "environment and result in shifts and reductions in consumer spending and negative consumer…"
- `t04` How much did Apple spend on research and development in 2025, 2024 and 2023?: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-mdna.txt` chunk 0 (0.64), "Source: Apple Inc. Annual Report on Form 10-K for the fiscal year ended September 27, 2025…"
- `u01` What is Apple's parental leave policy for employees?: reported grounded (evidence 0.42) for a question the corpus cannot answer. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 0 (0.41), "Source: Apple Inc. Annual Report on Form 10-K for the fiscal year ended September 27, 2025…"
- `u02` Who is the CEO of Microsoft?: reported grounded (evidence 0.38) for a question the corpus cannot answer. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 64 (0.38), "nurture its distinctive and inclusive culture. Much of the Company’s future success depend…"
- `u04` How many vacation days do new hires get?: reported grounded (evidence 0.31) for a question the corpus cannot answer. Top result instead: `remote-work-policy.md` chunk 0 (0.31), "# Remote Work Policy ## Eligibility All full-time employees who have completed their proba…"

**dense**: 8 failed

- `s01` What risks does Apple face from relying on outsourcing partners and single-source suppliers?: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 71 (0.55), "products or services and expose the Company to significant licensing costs, all of which c…"
- `s12` What is the risk if important employees leave?: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 20 (0.58), "are subject to the risk of interruption by fire, power shortages, nuclear power plant acci…"
- `k10` iPhone 16e: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 130 (0.34), "From time to time, the Company has made changes to its business, including actions taken i…"
- `t02` What were Mac and iPad net sales in 2025?: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-mdna.txt` chunk 19 (0.74), "iPad iPad net sales increased during 2025 compared to 2024 primarily due to higher net sal…"
- `t04` How much did Apple spend on research and development in 2025, 2024 and 2023?: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-mdna.txt` chunk 3 (0.63), "Product, Service and Software Announcements The Company announces new product, service and…"
- `u01` What is Apple's parental leave policy for employees?: reported grounded (evidence 0.39) for a question the corpus cannot answer. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 0 (0.39), "Source: Apple Inc. Annual Report on Form 10-K for the fiscal year ended September 27, 2025…"
- `u02` Who is the CEO of Microsoft?: reported grounded (evidence 0.38) for a question the corpus cannot answer. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 82 (0.38), "Much of the Company’s future success depends on the talents and efforts of its team member…"
- `u04` How many vacation days do new hires get?: reported grounded (evidence 0.36) for a question the corpus cannot answer. Top result instead: `apple-fy2025-10k-mdna.txt` chunk 5 (0.36), "Fiscal Period The Company’s fiscal year is the 52- or 53-week period that ends on the last…"

**keyword**: 5 failed

- `s11` Does Apple depend on mobile operators to sell its phones?: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-mdna.txt` chunk 4 (0.19), "Fourth Quarter 2025: •iPhone 17, iPhone Air, iPhone 17 Pro and iPhone 17 Pro Max •Apple Wa…"
- `s12` What is the risk if important employees leave?: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 62 (0.41), "The Company is exposed to the risk of write-downs on the value of its inventory and other …"
- `t02` What were Mac and iPad net sales in 2025?: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-mdna.txt` chunk 19 (0.74), "iPad iPad net sales increased during 2025 compared to 2024 primarily due to higher net sal…"
- `u01` What is Apple's parental leave policy for employees?: reported grounded (evidence 0.39) for a question the corpus cannot answer. Top result instead: `remote-work-policy.md` chunk 0 (0.25), "# Remote Work Policy ## Eligibility All full-time employees who have completed their proba…"
- `u04` How many vacation days do new hires get?: reported grounded (evidence 0.32) for a question the corpus cannot answer. Top result instead: `remote-work-policy.md` chunk 0 (0.32), "# Remote Work Policy ## Eligibility All full-time employees who have completed their proba…"

**hybrid**: 5 failed

- `s12` What is the risk if important employees leave?: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 20 (0.58), "are subject to the risk of interruption by fire, power shortages, nuclear power plant acci…"
- `t02` What were Mac and iPad net sales in 2025?: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-mdna.txt` chunk 19 (0.74), "iPad iPad net sales increased during 2025 compared to 2024 primarily due to higher net sal…"
- `u01` What is Apple's parental leave policy for employees?: reported grounded (evidence 0.39) for a question the corpus cannot answer. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 0 (0.39), "Source: Apple Inc. Annual Report on Form 10-K for the fiscal year ended September 27, 2025…"
- `u02` Who is the CEO of Microsoft?: reported grounded (evidence 0.38) for a question the corpus cannot answer. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 82 (0.38), "Much of the Company’s future success depends on the talents and efforts of its team member…"
- `u04` How many vacation days do new hires get?: reported grounded (evidence 0.36) for a question the corpus cannot answer. Top result instead: `remote-work-policy.md` chunk 0 (0.32), "# Remote Work Policy ## Eligibility All full-time employees who have completed their proba…"

**hybrid+rerank**: 1 failed

- `s12` What is the risk if important employees leave?: relevant chunk not in the top 5. Top result instead: `apple-fy2025-10k-risk-factors.txt` chunk 20 (0.01), "are subject to the risk of interruption by fire, power shortages, nuclear power plant acci…"

## Answers: is the generated answer right

Graded automatically: required facts must appear (regex), answerable questions must carry a `[n]` citation, and unanswerable questions must be declined.

| Configuration | Model | Passed | Avg prompt tokens | Avg completion tokens |
|---|---|---|---|---|
| v2 baseline: fixed 512-char chunks, dense only | `openai/gpt-oss-20b` via Groq | **24/27** | 954 | 84 |
| Structure-aware chunks, hybrid + cross-encoder rerank | `openai/gpt-oss-20b` via Groq | **27/27** | 826 | 78 |

| # | Question | baseline-v2 | hybrid+rerank |
|---|---|---|---|
| s02 | Why did Greater China net sales decline in 2025? | ✅ | ✅ |
| s03 | How did U.S. tariffs affect Apple in fiscal 2025? | ✅ | ✅ |
| s04 | Why did the Services gross margin percentage go up? | ✅ | ✅ |
| s05 | How much stock did Apple buy back and how much did it return in dividends during 2025? | ✅ | ✅ |
| s06 | What drove the sales increase in Japan? | ✅ | ✅ |
| s07 | How much cash and marketable securities does the company hold? | ✅ | ✅ |
| s08 | Why was the effective tax rate below the statutory rate? | ✅ | ✅ |
| s14 | How many days a week can staff work from home? | ✅ | ✅ |
| s15 | What allowance do I get for home office furniture? | ✅ | ✅ |
| s16 | What made research and development spending grow? | ✅ | ✅ |
| s17 | Which new products were announced in the fourth quarter? | ❌ | ✅ |
| k01 | ASU 2025-06 effective date | ✅ | ✅ |
| k02 | Section 232 investigation | ✅ | ✅ |
| k04 | TCJA deemed repatriation tax payable balance | ✅ | ✅ |
| k05 | When will ASU 2023-09 be adopted? | ✅ | ✅ |
| k06 | State Aid Decision impact | ✅ | ✅ |
| k07 | commercial paper outstanding | ✅ | ✅ |
| k09 | VPN rule | ✅ | ✅ |
| k11 | manufacturing purchase obligations | ✅ | ✅ |
| t01 | Which reportable segment grew fastest in 2025, and by how much? | ❌ | ✅ |
| t02 | What were Mac and iPad net sales in 2025? | ✅ | ✅ |
| t03 | What was the total gross margin percentage in 2025 compared with 2024? | ✅ | ✅ |
| t04 | How much did Apple spend on research and development in 2025, 2024 and 2023? | ❌ | ✅ |
| u01 | What is Apple's parental leave policy for employees? | ✅ | ✅ |
| u02 | Who is the CEO of Microsoft? | ✅ | ✅ |
| u03 | What is the office dress code? | ✅ | ✅ |
| u04 | How many vacation days do new hires get? | ✅ | ✅ |

**baseline-v2**: 3 failed

- `s17` Which new products were announced in the fourth quarter?: answer is missing: AirPods Pro 3. Grounding label was *high*. Answer began: "The new products announced in the fourth quarter of fiscal 2025 were: - iPhone 17, iPhone Air, iPhone 17 Pro, and iPhone 17 Pro Max - Apple Watch Series 11, App…"
- `t01` Which reportable segment grew fastest in 2025, and by how much?: answer is missing: Japan, 15. Grounding label was *high*. Answer began: "The reportable segment that grew fastest in 2025 was **Europe**, with a net‑sales increase of **10 %** over 2024. [1]…"
- `t04` How much did Apple spend on research and development in 2025, 2024 and 2023?: answer is missing: 34[.,]5, 31[.,]3, 29[.,]9. Grounding label was *high*. Answer began: "I’m sorry, but the provided context does not contain the information on Apple’s research and development expenditures for 2025, 2024, or 2023. You can find thos…"

**hybrid+rerank**: 0 failed. Nothing to report.

## CI gate

Status: **PASS**

| Configuration | Metric | Required | Measured |
|---|---|---|---|
| hybrid | hit_at_5 | ≥ 0.90 | 0.938 ✅ |
| hybrid | mrr | ≥ 0.70 | 0.823 ✅ |
| hybrid+rerank | hit_at_5 | ≥ 0.93 | 0.969 ✅ |
| hybrid+rerank | mrr | ≥ 0.80 | 0.927 ✅ |
| hybrid+rerank | rejection_rate | ≥ 0.75 | 1.000 ✅ |
