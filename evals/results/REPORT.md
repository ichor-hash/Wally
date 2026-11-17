# Evaluation report

Generated 2026-11-17 12:02 UTC on Windows (Python 3.12.10). Reproduce with `python evals/run_evals.py --answers`.

**40 golden questions** over 3 documents: 17 semantic, 11 keyword, 4 table, 4 calculation, 4 unanswerable.

## Retrieval

A case passes when a chunk containing the answer is in the top 5, or, for unanswerable questions, when retrieval reports weak grounding.

| Configuration | Passed | Hit@1 | Hit@5 | MRR | Unanswerable rejected | Avg latency |
|---|---|---|---|---|---|---|
| v2 baseline: fixed 512-char chunks, dense only | **33/40** | 50% | 89% | 0.65 | 25% | 21 ms |
| Structure-aware chunks, dense only | **32/40** | 61% | 86% | 0.71 | 25% | 25 ms |
| Structure-aware chunks, BM25 keyword only | **33/40** | 58% | 86% | 0.70 | 50% | 24 ms |
| Hybrid (dense + BM25, RRF) | **35/40** | 67% | 94% | 0.78 | 25% | 34 ms |
| Hybrid + cross-encoder rerank | **39/40** | 83% | 97% | 0.87 | 100% | 488 ms |
| Hybrid + contextual chunk headers | **36/40** | 72% | 97% | 0.82 | 25% | 34 ms |
| Hybrid + contextual headers + rerank **(default)** | **39/40** | 83% | 97% | 0.87 | 100% | 520 ms |

| Passed by type | semantic | keyword | table | calculation | unanswerable |
|---|---|---|---|---|---|
| baseline-v2 | 16/17 | 10/11 | 2/4 | 4/4 | 1/4 |
| dense | 15/17 | 10/11 | 2/4 | 4/4 | 1/4 |
| keyword | 14/17 | 11/11 | 3/4 | 3/4 | 2/4 |
| hybrid | 16/17 | 11/11 | 3/4 | 4/4 | 1/4 |
| hybrid+rerank | 16/17 | 11/11 | 4/4 | 4/4 | 4/4 |
| hybrid+context | 16/17 | 11/11 | 4/4 | 4/4 | 1/4 |
| hybrid+context+rerank | 16/17 | 11/11 | 4/4 | 4/4 | 4/4 |

<details><summary>Every retrieval case</summary>

| # | Type | Question | baseline-v2 | dense | keyword | hybrid | hybrid+rerank | hybrid+context | hybrid+context+rerank |
|---|---|---|---|---|---|---|---|---|---|
| s01 | semantic | What risks does Apple face from relying on outsourcing partners and single-source suppliers? | ✅ 3 | ❌ | ✅ 1 | ✅ 3 | ✅ 1 | ✅ 1 | ✅ 1 |
| s02 | semantic | Why did Greater China net sales decline in 2025? | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s03 | semantic | How did U.S. tariffs affect Apple in fiscal 2025? | ✅ 1 | ✅ 1 | ✅ 3 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s04 | semantic | Why did the Services gross margin percentage go up? | ✅ 1 | ✅ 1 | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s05 | semantic | How much stock did Apple buy back and how much did it return in dividends during 2025? | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s06 | semantic | What drove the sales increase in Japan? | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s07 | semantic | How much cash and marketable securities does the company hold? | ✅ 2 | ✅ 1 | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s08 | semantic | Why was the effective tax rate below the statutory rate? | ✅ 2 | ✅ 3 | ✅ 2 | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 |
| s09 | semantic | What could happen if hackers break into the company's systems? | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s10 | semantic | How does a strong dollar hurt the company's results? | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s11 | semantic | Does Apple depend on mobile operators to sell its phones? | ✅ 1 | ✅ 1 | ❌ | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s12 | semantic | What is the risk if important employees leave? | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| s13 | semantic | How could natural disasters or a changing climate disrupt operations? | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s14 | semantic | How many days a week can staff work from home? | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s15 | semantic | What allowance do I get for home office furniture? | ✅ 5 | ✅ 1 | ❌ | ✅ 2 | ✅ 1 | ✅ 3 | ✅ 1 |
| s16 | semantic | What made research and development spending grow? | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| s17 | semantic | Which new products were announced in the fourth quarter? | ✅ 1 | ✅ 1 | ✅ 5 | ✅ 1 | ✅ 1 | ✅ 2 | ✅ 1 |
| k01 | keyword | ASU 2025-06 effective date | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| k02 | keyword | Section 232 investigation | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| k03 | keyword | DMA compliance changes | ✅ 3 | ✅ 3 | ✅ 4 | ✅ 3 | ✅ 3 | ✅ 3 | ✅ 3 |
| k04 | keyword | TCJA deemed repatriation tax payable balance | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| k05 | keyword | When will ASU 2023-09 be adopted? | ✅ 3 | ✅ 2 | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| k06 | keyword | State Aid Decision impact | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| k07 | keyword | commercial paper outstanding | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| k08 | keyword | Google LLC search licensing arrangement | ✅ 1 | ✅ 2 | ✅ 1 | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 |
| k09 | keyword | VPN rule | ✅ 4 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| k10 | keyword | iPhone 16e | ❌ | ❌ | ✅ 1 | ✅ 3 | ✅ 1 | ✅ 2 | ✅ 1 |
| k11 | keyword | manufacturing purchase obligations | ✅ 2 | ✅ 1 | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| t01 | table | Which reportable segment grew fastest in 2025, and by how much? | ❌ | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| t02 | table | What were Mac and iPad net sales in 2025? | ✅ 2 | ❌ | ❌ | ❌ | ✅ 3 | ✅ 3 | ✅ 3 |
| t03 | table | What was the total gross margin percentage in 2025 compared with 2024? | ✅ 1 | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 2 | ✅ 1 |
| t04 | table | How much did Apple spend on research and development in 2025, 2024 and 2023? | ❌ | ❌ | ✅ 1 | ✅ 3 | ✅ 1 | ✅ 4 | ✅ 1 |
| c01 | calculation | By how much did total net sales grow from 2024 to 2025, in dollars? | ✅ 3 | ✅ 3 | ✅ 2 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 |
| c02 | calculation | What share of total 2025 net sales came from Services? | ✅ 5 | ✅ 2 | ✅ 3 | ✅ 2 | ✅ 4 | ✅ 1 | ✅ 4 |
| c03 | calculation | What were Mac and iPad net sales combined in 2025? | ✅ 2 | ✅ 4 | ❌ | ✅ 5 | ✅ 5 | ✅ 3 | ✅ 5 |
| c04 | calculation | By what percentage did total gross margin increase from 2024 to 2025? | ✅ 1 | ✅ 3 | ✅ 1 | ✅ 2 | ✅ 3 | ✅ 2 | ✅ 3 |
| u01 | unanswerable | What is Apple's parental leave policy for employees? | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| u02 | unanswerable | Who is the CEO of Microsoft? | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ |
| u03 | unanswerable | What is the office dress code? | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| u04 | unanswerable | How many vacation days do new hires get? | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |

</details>

### Retrieval failures

**baseline-v2**: 7 failed
- `s12` What is the risk if important employees leave?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 17 (0.55).
- `k10` iPhone 16e: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-mdna.txt` chunk 12 (0.38).
- `t01` Which reportable segment grew fastest in 2025, and by how much?: no single chunk holds the needed text with this chunking. Top result: `apple-fy2025-10k-mdna.txt` chunk 8 (0.63).
- `t04` How much did Apple spend on research and development in 2025, 2024 and 2023?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-mdna.txt` chunk 0 (0.64).
- `u01` What is Apple's parental leave policy for employees?: reported grounded (evidence 0.42) for a question the corpus cannot answer. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 0 (0.41).
- `u02` Who is the CEO of Microsoft?: reported grounded (evidence 0.38) for a question the corpus cannot answer. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 64 (0.38).
- `u04` How many vacation days do new hires get?: reported grounded (evidence 0.31) for a question the corpus cannot answer. Top result: `remote-work-policy.md` chunk 0 (0.31).

**dense**: 8 failed
- `s01` What risks does Apple face from relying on outsourcing partners and single-source suppliers?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 71 (0.55).
- `s12` What is the risk if important employees leave?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 20 (0.58).
- `k10` iPhone 16e: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 130 (0.34).
- `t02` What were Mac and iPad net sales in 2025?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-mdna.txt` chunk 19 (0.74).
- `t04` How much did Apple spend on research and development in 2025, 2024 and 2023?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-mdna.txt` chunk 3 (0.63).
- `u01` What is Apple's parental leave policy for employees?: reported grounded (evidence 0.39) for a question the corpus cannot answer. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 0 (0.39).
- `u02` Who is the CEO of Microsoft?: reported grounded (evidence 0.38) for a question the corpus cannot answer. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 82 (0.38).
- `u04` How many vacation days do new hires get?: reported grounded (evidence 0.43) for a question the corpus cannot answer. Top result: `remote-work-policy.md` chunk 1 (0.43).

**keyword**: 7 failed
- `s11` Does Apple depend on mobile operators to sell its phones?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-mdna.txt` chunk 4 (0.19).
- `s12` What is the risk if important employees leave?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 62 (0.41).
- `s15` What allowance do I get for home office furniture?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-mdna.txt` chunk 20 (0.19).
- `t02` What were Mac and iPad net sales in 2025?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-mdna.txt` chunk 19 (0.74).
- `c03` What were Mac and iPad net sales combined in 2025?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-mdna.txt` chunk 19 (0.73).
- `u01` What is Apple's parental leave policy for employees?: reported grounded (evidence 0.39) for a question the corpus cannot answer. Top result: `remote-work-policy.md` chunk 0 (0.35).
- `u04` How many vacation days do new hires get?: reported grounded (evidence 0.43) for a question the corpus cannot answer. Top result: `remote-work-policy.md` chunk 1 (0.43).

**hybrid**: 5 failed
- `s12` What is the risk if important employees leave?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 20 (0.58).
- `t02` What were Mac and iPad net sales in 2025?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-mdna.txt` chunk 19 (0.74).
- `u01` What is Apple's parental leave policy for employees?: reported grounded (evidence 0.39) for a question the corpus cannot answer. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 0 (0.39).
- `u02` Who is the CEO of Microsoft?: reported grounded (evidence 0.38) for a question the corpus cannot answer. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 82 (0.38).
- `u04` How many vacation days do new hires get?: reported grounded (evidence 0.43) for a question the corpus cannot answer. Top result: `remote-work-policy.md` chunk 1 (0.43).

**hybrid+rerank**: 1 failed
- `s12` What is the risk if important employees leave?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 20 (0.01).

**hybrid+context**: 4 failed
- `s12` What is the risk if important employees leave?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 84 (0.33).
- `u01` What is Apple's parental leave policy for employees?: reported grounded (evidence 0.53) for a question the corpus cannot answer. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 150 (0.53).
- `u02` Who is the CEO of Microsoft?: reported grounded (evidence 0.37) for a question the corpus cannot answer. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 82 (0.37).
- `u04` How many vacation days do new hires get?: reported grounded (evidence 0.45) for a question the corpus cannot answer. Top result: `remote-work-policy.md` chunk 1 (0.45).

**hybrid+context+rerank**: 1 failed
- `s12` What is the risk if important employees leave?: relevant chunk not in the top 5. Top result: `apple-fy2025-10k-risk-factors.txt` chunk 62 (0.00).

## Answers

Every question with an answer key, run through the full pipeline (`answering.py`, the code behind `/search`) and graded automatically: required facts present, a `[n]` citation present, unanswerable questions declined. *Claims verified* is the pipeline's own verifier: each cited claim checked against the chunks it cites.

| Pipeline | Model | Correct | Claims verified | Revised | Re-searched | Tool calls | Tokens / question | LLM calls / question |
|---|---|---|---|---|---|---|---|---|
| v2 pipeline: fixed chunks, dense search, no checks | `openai/gpt-oss-120b` | **28/31** | not checked | 0 | 0 | 0 | 1,127 | 1.0 |
| v3: hybrid + context + rerank, corrective search, verification | `openai/gpt-oss-120b` | **31/31** | 34/35 | 4 | 3 | 0 | 1,679 | 2.29 |
| v3 + agent tools (calculate, search_documents) | `openai/gpt-oss-120b` | **31/31** | 32/32 | 4 | 3 | 4 | 2,090 | 2.42 |

| Correct by type | semantic | keyword | table | calculation | unanswerable |
|---|---|---|---|---|---|
| baseline-v2 | 10/11 | 8/8 | 2/4 | 4/4 | 4/4 |
| v3 | 11/11 | 8/8 | 4/4 | 4/4 | 4/4 |
| v3+agent | 11/11 | 8/8 | 4/4 | 4/4 | 4/4 |

| # | Question | baseline-v2 | v3 | v3+agent |
|---|---|---|---|---|
| s02 | Why did Greater China net sales decline in 2025? | ✅ | ✅ | ✅ |
| s03 | How did U.S. tariffs affect Apple in fiscal 2025? | ✅ | ✅ | ✅ |
| s04 | Why did the Services gross margin percentage go up? | ✅ | ✅ | ✅ |
| s05 | How much stock did Apple buy back and how much did it return in dividends during 2025? | ✅ | ✅ | ✅ |
| s06 | What drove the sales increase in Japan? | ✅ | ✅ | ✅ |
| s07 | How much cash and marketable securities does the company hold? | ✅ | ✅ | ✅ |
| s08 | Why was the effective tax rate below the statutory rate? | ✅ | ✅ | ✅ |
| s14 | How many days a week can staff work from home? | ✅ | ✅ | ✅ |
| s15 | What allowance do I get for home office furniture? | ✅ | ✅ | ✅ |
| s16 | What made research and development spending grow? | ✅ | ✅ | ✅ |
| s17 | Which new products were announced in the fourth quarter? | ❌ | ✅ | ✅ |
| k01 | ASU 2025-06 effective date | ✅ | ✅ | ✅ |
| k02 | Section 232 investigation | ✅ | ✅ | ✅ |
| k04 | TCJA deemed repatriation tax payable balance | ✅ | ✅ | ✅ |
| k05 | When will ASU 2023-09 be adopted? | ✅ | ✅ | ✅ |
| k06 | State Aid Decision impact | ✅ | ✅ | ✅ |
| k07 | commercial paper outstanding | ✅ | ✅ | ✅ |
| k09 | VPN rule | ✅ | ✅ | ✅ |
| k11 | manufacturing purchase obligations | ✅ | ✅ | ✅ |
| t01 | Which reportable segment grew fastest in 2025, and by how much? | ❌ | ✅ | ✅ |
| t02 | What were Mac and iPad net sales in 2025? | ✅ | ✅ | ✅ |
| t03 | What was the total gross margin percentage in 2025 compared with 2024? | ✅ | ✅ | ✅ |
| t04 | How much did Apple spend on research and development in 2025, 2024 and 2023? | ❌ | ✅ | ✅ |
| c01 | By how much did total net sales grow from 2024 to 2025, in dollars? | ✅ | ✅ | ✅ |
| c02 | What share of total 2025 net sales came from Services? | ✅ | ✅ | ✅ |
| c03 | What were Mac and iPad net sales combined in 2025? | ✅ | ✅ | ✅ |
| c04 | By what percentage did total gross margin increase from 2024 to 2025? | ✅ | ✅ | ✅ |
| u01 | What is Apple's parental leave policy for employees? | ✅ | ✅ | ✅ |
| u02 | Who is the CEO of Microsoft? | ✅ | ✅ | ✅ |
| u03 | What is the office dress code? | ✅ | ✅ | ✅ |
| u04 | How many vacation days do new hires get? | ✅ | ✅ | ✅ |

### What the pipeline did

**v3**

- `s05` How much stock did Apple buy back and how much did it return in dividends during 2025?: revised after verification.
- `k01` ASU 2025-06 effective date: revised after verification.
- `k02` Section 232 investigation: revised after verification.
- `k05` When will ASU 2023-09 be adopted?: revised after verification.
- `u02` Who is the CEO of Microsoft?: re-searched as "Microsoft Corporation Chief Executive Officer".
- `u03` What is the office dress code?: re-searched as "Corporate Office Dress Code Policy".
- `u04` How many vacation days do new hires get?: re-searched as "New hire vacation days entitlement".

**v3+agent**

- `s08` Why was the effective tax rate below the statutory rate?: revised after verification.
- `s17` Which new products were announced in the fourth quarter?: revised after verification.
- `k01` ASU 2025-06 effective date: revised after verification.
- `k05` When will ASU 2023-09 be adopted?: revised after verification.
- `c01` By how much did total net sales grow from 2024 to 2025, in dollars?: tools: `calculate({"expression": "416161 - 391035"}) = 25,126`.
- `c02` What share of total 2025 net sales came from Services?: tools: `calculate({"expression": "109158 / 416161 * 100"}) = 26.2298`.
- `c03` What were Mac and iPad net sales combined in 2025?: tools: `calculate({"expression": "33708 + 28023"}) = 61,731`.
- `c04` By what percentage did total gross margin increase from 2024 to 2025?: tools: `calculate({"expression": "(195201 - 180683) / 180683 * 100"}) = 8.0351`.
- `u02` Who is the CEO of Microsoft?: re-searched as "Microsoft Corporation Chief Executive Officer".
- `u03` What is the office dress code?: re-searched as "Corporate Office Dress Code Policy".
- `u04` How many vacation days do new hires get?: re-searched as "New hire vacation days entitlement".

### Answer failures

**baseline-v2**: 3 failed
- `s17` Which new products were announced in the fourth quarter?: answer is missing: AirPods Pro 3. Answer began: "**New products announced in the fourth quarter of fiscal 2025** - iPhone 17 - iPhone Air - iPhone 17 Pro - iPhone 17 Pro Max - Apple Watch Series 11 - Apple Watch SE 3 - Apple Watc…"
- `t01` Which reportable segment grew fastest in 2025, and by how much?: answer is missing: 15. Answer began: "The 10‑K excerpt provides net‑sales figures and year‑over‑year change percentages only for the **Americas** segment (7 % growth) and partially for **Europe** (10 % growth) [1]. The…"
- `t04` How much did Apple spend on research and development in 2025, 2024 and 2023?: answer is missing: 34[.,]5, 31[.,]3, 29[.,]9. Answer began: "The provided excerpts do not contain any figures for Apple’s research and development expenditures for fiscal 2025, 2024, or 2023. Those amounts are disclosed in the “Consolidated …"

**v3**: 0 failed.

**v3+agent**: 0 failed.

