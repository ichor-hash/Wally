"""
Ethan's evaluation harness.

    python evals/run_evals.py              retrieval evaluation (no API key, about a minute on CPU)
    python evals/run_evals.py --answers    also generate and grade answers with the configured LLM
    python evals/run_evals.py --check      exit 1 if the default setup misses its thresholds

Retrieval: builds in-memory indexes from the demo corpus and runs every golden
question through each configuration, using the same pipeline.py the API serves.

Answers: runs every question with an answer key through answering.Answerer (the
exact code behind /search) at three pipeline levels, and grades each answer:
required facts present, a [n] citation present, unanswerable questions declined.
It also records what the pipeline did: corrective re-searches, tool calls,
claim verification and revisions.

Writes evals/results/latest.json (shown in the app's Evaluation view) and
evals/results/REPORT.md (every case, passed and failed).
"""
import argparse
import json
import os
import platform
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from answering import AnswerConfig, AnswerOptions, Answerer  # noqa: E402
from contextual import build_contexts, with_context  # noqa: E402
from data_loader import DocumentLoader  # noqa: E402
from pipeline import WEAK_DENSE, WEAK_RERANK, Retriever, evidence_of  # noqa: E402
from reranker import Reranker  # noqa: E402
from vector_db import RAGVectorDB  # noqa: E402

RESULTS = ROOT / "evals" / "results"
TOP_K = 5

# name: (chunking, contextual mode, retrieval mode, rerank)
CONFIGS = {
    "baseline-v2": ("fixed", "off", "dense", False),
    "dense": ("structure", "off", "dense", False),
    "keyword": ("structure", "off", "keyword", False),
    "hybrid": ("structure", "off", "hybrid", False),
    "hybrid+rerank": ("structure", "off", "hybrid", True),
    "hybrid+context": ("structure", "header", "hybrid", False),
    "hybrid+context+rerank": ("structure", "header", "hybrid", True),
}
LABELS = {
    "baseline-v2": "v2 baseline: fixed 512-char chunks, dense only",
    "dense": "Structure-aware chunks, dense only",
    "keyword": "Structure-aware chunks, BM25 keyword only",
    "hybrid": "Hybrid (dense + BM25, RRF)",
    "hybrid+rerank": "Hybrid + cross-encoder rerank",
    "hybrid+context": "Hybrid + contextual chunk headers",
    "hybrid+context+rerank": "Hybrid + contextual headers + rerank",
}
DEFAULT_CONFIG = "hybrid+context+rerank"

# name: (retrieval config, AnswerOptions overrides)
ANSWER_LEVELS = {
    "baseline-v2": ("baseline-v2", dict(rerank=False, mode="dense", correct=False, verify=False, agent=False)),
    "v3": (DEFAULT_CONFIG, dict(rerank=True, mode="hybrid", correct=True, verify=True, agent=False)),
    "v3+agent": (DEFAULT_CONFIG, dict(rerank=True, mode="hybrid", correct=True, verify=True, agent=True)),
}
ANSWER_LABELS = {
    "baseline-v2": "v2 pipeline: fixed chunks, dense search, no checks",
    "v3": "v3: hybrid + context + rerank, corrective search, verification",
    "v3+agent": "v3 + agent tools (calculate, search_documents)",
}

# Local regression check (--check). A little below the measured numbers, so a real
# regression fails and run-to-run noise does not.
THRESHOLDS = {DEFAULT_CONFIG: {"hit_at_5": 0.93, "mrr": 0.80, "rejection_rate": 0.75}}


# ---------------------------------------------------------------- helpers
def is_relevant(text: str, groups) -> bool:
    low = text.lower()
    return any(all(p.lower() in low for p in group) for group in groups)


def build_index(strategy: str, context_mode: str, corpus, embedder=None, summarizer=None) -> RAGVectorDB:
    db = RAGVectorDB(url=":memory:", collection=f"eval_{strategy}_{context_mode}", embedder=embedder)
    loader = DocumentLoader(strategy=strategy)
    for rel in corpus:
        path = ROOT / rel
        chunks = loader.load_and_chunk(str(path))
        contexts = build_contexts(chunks, loader.load_file(str(path)), path.name, context_mode, summarizer)
        metadata = [{**c["metadata"], **({"context": ctx} if ctx else {})} for c, ctx in zip(chunks, contexts)]
        db.add_texts([c["text"] for c in chunks], metadata=metadata,
                     index_texts=[with_context(c["text"], ctx) for c, ctx in zip(chunks, contexts)])
    return db


class Console:
    """Prints a readable run log and keeps a copy for the README screenshot."""

    def __init__(self):
        self.lines = []

    def __call__(self, text=""):
        print(text, flush=True)
        self.lines.append(text)


log = Console()


# ---------------------------------------------------------------- retrieval
def evaluate_retrieval(golden):
    indexes, embedder = {}, None
    for strategy, context_mode, _, _ in CONFIGS.values():
        key = (strategy, context_mode)
        if key not in indexes:
            indexes[key] = build_index(strategy, context_mode, golden["corpus"], embedder)
            embedder = indexes[key].embedder
    reranker = Reranker(os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"))

    for case in golden["cases"]:
        for key, db in indexes.items():
            if case["relevant"] and not any(is_relevant((p.payload or {}).get("text", ""), case["relevant"]) for p in db.scroll_all()):
                case.setdefault("unreachable_in", []).append(key[0])

    log("Retrieval: {} questions, top {}".format(len(golden["cases"]), TOP_K))
    log("")
    log(f"  {'configuration':<24}{'passed':>9}{'hit@1':>8}{'hit@5':>8}{'MRR':>7}{'rejects':>9}{'latency':>10}")
    configs = {}
    for name, (strategy, context_mode, mode, rerank) in CONFIGS.items():
        db = indexes[(strategy, context_mode)]
        retriever = Retriever(db, reranker)
        retriever.retrieve("warm up", top_k=TOP_K, rerank=rerank, mode=mode)
        db._query_vectors.clear()  # each configuration pays for its own query embeddings
        cases, latencies = [], []
        for case in golden["cases"]:
            t0 = time.perf_counter()
            out = retriever.retrieve(case["question"], top_k=TOP_K, rerank=rerank, mode=mode)
            latencies.append((time.perf_counter() - t0) * 1000)
            results = out["results"]
            evidence = evidence_of(results, rerank)
            grounded = evidence >= (WEAK_RERANK if rerank else WEAK_DENSE)
            row = {
                "id": case["id"], "category": case["category"], "question": case["question"],
                "evidence_score": round(evidence, 4), "grounded": grounded,
                "top": [
                    {
                        "rank": i, "source_file": r["payload"].get("source_file"), "chunk_index": r["payload"].get("chunk_index"),
                        "matched_by": r.get("matched_by"), "score": round(r["rerank_score"] if rerank else r["vector_score"], 3),
                        "preview": " ".join(r["payload"].get("text", "").split())[:140],
                    }
                    for i, r in enumerate(results[:3], 1)
                ],
            }
            if case["category"] == "unanswerable":
                row.update(rank=None, passed=not grounded,
                           reason="" if not grounded else f"reported grounded (evidence {evidence:.2f}) for a question the corpus cannot answer")
            else:
                rank = next((i for i, r in enumerate(results, 1) if is_relevant(r["payload"].get("text", ""), case["relevant"])), None)
                unreachable = strategy in case.get("unreachable_in", [])
                row.update(rank=rank, passed=rank is not None,
                           reason="" if rank else ("no single chunk holds the needed text with this chunking" if unreachable
                                                   else f"relevant chunk not in the top {TOP_K}"))
            cases.append(row)

        answerable = [c for c in cases if c["category"] != "unanswerable"]
        unanswerable = [c for c in cases if c["category"] == "unanswerable"]

        def hit(k):
            return round(sum(1 for c in answerable if c["rank"] and c["rank"] <= k) / len(answerable), 3)

        by_category = {}
        for category in dict.fromkeys(c["category"] for c in cases):
            rows = [c for c in cases if c["category"] == category]
            by_category[category] = {"passed": sum(c["passed"] for c in rows), "total": len(rows)}

        c = configs[name] = {
            "label": LABELS[name], "chunking": strategy, "contextual": context_mode, "mode": mode, "rerank": rerank,
            "chunks_indexed": db.count(),
            "hit_at_1": hit(1), "hit_at_3": hit(3), "hit_at_5": hit(5),
            "mrr": round(statistics.fmean([1 / c["rank"] if c["rank"] else 0 for c in answerable]), 3),
            "rejection_rate": round(sum(c["passed"] for c in unanswerable) / len(unanswerable), 3) if unanswerable else None,
            "passed": sum(c["passed"] for c in cases), "total": len(cases),
            "by_category": by_category,
            "avg_latency_ms": round(statistics.fmean(latencies), 1),
            "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95) - 1], 1),
            "cases": cases,
        }
        star = " *" if name == DEFAULT_CONFIG else ""
        log(f"  {name + star:<24}{c['passed']:>5}/{c['total']:<3}{c['hit_at_1']:>8.0%}{c['hit_at_5']:>8.0%}{c['mrr']:>7.2f}"
            f"{c['rejection_rate']:>9.0%}{c['avg_latency_ms']:>8.0f} ms")
    log("  * default")
    return configs, indexes, reranker


# ---------------------------------------------------------------- answers
REFUSAL = re.compile(
    r"(do(es)? not|don't|doesn't|no|not|cannot|can't|couldn't|unable)\b.{0,80}"
    r"(contain|include|mention|provide|information|cover|found|find|available|address|specify|state)", re.I | re.S)
CITATION = re.compile(r"\[\d+\]|【\d+")


def normalise(text: str) -> str:
    """Models like typographic characters: narrow spaces in '10 %', curly quotes, non-breaking hyphens."""
    for src, dst in (("‑", "-"), ("‐", "-"), ("’", "'"), ("‘", "'")):
        text = text.replace(src, dst)
    return re.sub(r"[    ]", " ", text)


def grade_answer(case, answer: str):
    answer = normalise(answer)
    spec = case.get("answer", {})
    if spec.get("refuse"):
        ok = bool(REFUSAL.search(answer))
        return ok, "" if ok else "answered instead of saying the documents do not cover it"
    missing = [p for p in spec.get("all", []) if not re.search(p, answer, re.I)]
    if missing:
        return False, f"answer is missing: {', '.join(missing)}"
    if not CITATION.search(answer):
        return False, "no [n] citation in the answer"
    return True, ""


class PatientLLM:
    """Retries rate-limited calls (free tiers limit tokens per minute) so a run never records a 429 as a wrong answer."""

    def __init__(self, llm, attempts: int = 8):
        self.llm, self.attempts = llm, attempts

    def __getattr__(self, name):
        return getattr(self.llm, name)

    def _retry(self, fn, *args, **kwargs):
        for attempt in range(self.attempts):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                text = str(e).lower()
                if attempt == self.attempts - 1 or not any(k in text for k in ("429", "rate", "limit", "timeout", "503", "502")):
                    raise
                time.sleep(min(60, 8 * (attempt + 1)))

    def chat_with_usage(self, *a, **k):
        return self._retry(self.llm.chat_with_usage, *a, **k)

    def chat_with_tools(self, *a, **k):
        return self._retry(self.llm.chat_with_tools, *a, **k)

    def stream_chat(self, *a, **k):
        # Buffer the stream so a rate limit mid-stream can be retried as a whole
        return iter(self._retry(lambda: list(self.llm.stream_chat(*a, **k))))


def evaluate_answers(golden, indexes, reranker, levels, pause: float, only=None, previous=None):
    """
    Grade answers. With `only` (case ids), grade just those cases and merge them into
    `previous` (the last report's answers), so a fix to a few cases can be re-measured
    without spending a full run's tokens. The run log says which cases were re-graded.
    """
    from llm import llm_from_env

    llm = PatientLLM(llm_from_env())
    config = AnswerConfig(
        company_name=os.getenv("COMPANY_NAME", "Apple Inc."), company_profile=os.getenv("COMPANY_PROFILE", ""),
        max_context_chars=int(os.getenv("MAX_CONTEXT_CHARS", "8000")), max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "1024")),
        temperature=0.0,
    )
    cases = [c for c in golden["cases"] if "answer" in c and (not only or c["id"] in only)]
    out = {}
    for name in levels:
        config_name, overrides = ANSWER_LEVELS[name]
        strategy, context_mode, _, _ = CONFIGS[config_name]
        answerer = Answerer(Retriever(indexes[(strategy, context_mode)], reranker), llm, config)
        log("")
        log(f"Answers: {name}  ({ANSWER_LABELS[name]})")
        rows = []
        for case in cases:
            t0 = time.perf_counter()
            try:
                result = answerer.answer(case["question"], AnswerOptions(top_k=TOP_K, **overrides))
            except Exception as e:
                # Never store the provider's raw error: it can include account identifiers
                kind = "rate limit" if any(k in str(e).lower() for k in ("429", "rate")) else type(e).__name__
                result = {"answer": "", "error": kind, "sources": [], "metrics": {}, "verification": None, "steps": [],
                          "correction": None, "revised": None, "confidence": {"level": "none"}}
            seconds = time.perf_counter() - t0
            answer = result["answer"]
            if result.get("error"):
                passed, reason = False, f"request failed ({result['error']}); not graded"
            else:
                passed, reason = grade_answer(case, answer)
            v = result.get("verification") or {}
            m = result.get("metrics") or {}
            correction = result.get("correction") or {}
            row = {
                "id": case["id"], "category": case["category"], "question": case["question"], "passed": passed, "reason": reason,
                "error": result.get("error"),
                "answer": answer.strip(), "confidence": (result.get("confidence") or {}).get("level"),
                "retrieved_relevant": bool(case["relevant"]) and any(is_relevant(s["text"], case["relevant"]) for s in result["sources"]),
                "verification": {k: v.get(k) for k in ("status", "total", "supported", "partial", "unsupported", "score")} if v else None,
                "unsupported_claims": [c["text"] for c in v.get("claims", []) if c.get("verdict") == "UNSUPPORTED"] if v else [],
                "revised": bool(result.get("revised")),
                "corrected_query": correction.get("query") if correction.get("improved") else None,
                "tools": [f"{s['name']}({json.dumps(s['args'])[:80]}) = {s['result']}" for s in result.get("steps") or []],
                "prompt_tokens": m.get("prompt_tokens", 0), "completion_tokens": m.get("completion_tokens", 0),
                "llm_calls": m.get("llm_calls", 0), "seconds": round(seconds, 2),
            }
            rows.append(row)
            extras = []
            if row["tools"]:
                extras.append(f"{len(row['tools'])} tool call(s)")
            if v and v.get("total"):
                extras.append(f"verified {v['supported']}/{v['total']}")
            if row["revised"]:
                extras.append("revised")
            if row["corrected_query"]:
                extras.append("re-searched")
            mark = "PASS" if passed else "FAIL"
            log(f"  {mark}  {case['id']:<4} {case['question'][:64]:<64}  {', '.join(extras)}{'  <- ' + reason if reason else ''}")
            time.sleep(pause)

        if only and previous and name in previous:
            fresh = {r["id"]: r for r in rows}
            rows = [fresh.get(r["id"], r) for r in previous[name]["cases"]]
            log(f"  (re-graded {', '.join(sorted(fresh))}; other cases kept from the previous full run)")
        verified = [r for r in rows if r["verification"] and r["verification"].get("total")]
        out[name] = {
            "label": ANSWER_LABELS[name], "model": llm.model, "provider": llm.provider_name,
            "passed": sum(r["passed"] for r in rows), "total": len(rows), "errors": sum(1 for r in rows if r["error"]),
            "by_category": {cat: {"passed": sum(r["passed"] for r in rows if r["category"] == cat),
                                  "total": sum(1 for r in rows if r["category"] == cat)} for cat in dict.fromkeys(r["category"] for r in rows)},
            "faithfulness": round(statistics.fmean(r["verification"]["score"] for r in verified), 3) if verified else None,
            "claims_checked": sum(r["verification"]["total"] for r in verified),
            "claims_supported": sum(r["verification"]["supported"] for r in verified),
            "revised": sum(r["revised"] for r in rows),
            "corrected": sum(1 for r in rows if r["corrected_query"]),
            "tool_calls": sum(len(r["tools"]) for r in rows),
            "avg_prompt_tokens": round(statistics.fmean(r["prompt_tokens"] for r in rows)),
            "avg_completion_tokens": round(statistics.fmean(r["completion_tokens"] for r in rows)),
            "avg_llm_calls": round(statistics.fmean(r["llm_calls"] for r in rows), 2),
            "avg_seconds": round(statistics.fmean(r["seconds"] for r in rows), 2),
            "cases": rows,
        }
        a = out[name]
        faith = f", {a['claims_supported']}/{a['claims_checked']} claims verified" if a["claims_checked"] else ""
        log(f"  => {a['passed']}/{a['total']} correct{faith}, {a['avg_prompt_tokens'] + a['avg_completion_tokens']} tokens and "
            f"{a['avg_llm_calls']} LLM calls per question")
    return out


# ---------------------------------------------------------------- report
def check_thresholds(configs):
    failures = []
    for name, limits in THRESHOLDS.items():
        for metric, minimum in limits.items():
            if configs[name][metric] < minimum:
                failures.append(f"{name}: {metric} = {configs[name][metric]:.3f}, below {minimum:.2f}")
    return failures


def mark(passed):
    return "✅" if passed else "❌"


def render_report(report) -> str:
    configs = report["retrieval"]
    names = list(configs)
    cats = list(report["golden"]["by_category"])
    lines = [
        "# Evaluation report", "",
        f"Generated {report['generated_at']} on {report['environment']['platform']} (Python {report['environment']['python']}). "
        "Reproduce with `python evals/run_evals.py --answers`.", "",
        f"**{report['golden']['total']} golden questions** over {len(report['golden']['corpus'])} documents: "
        + ", ".join(f"{n} {c}" for c, n in report["golden"]["by_category"].items()) + ".", "",
        "## Retrieval", "",
        "A case passes when a chunk containing the answer is in the top 5, or, for unanswerable questions, "
        "when retrieval reports weak grounding.", "",
        "| Configuration | Passed | Hit@1 | Hit@5 | MRR | Unanswerable rejected | Avg latency |",
        "|---|---|---|---|---|---|---|",
    ]
    for n in names:
        c = configs[n]
        star = " **(default)**" if n == report["default_config"] else ""
        lines.append(f"| {c['label']}{star} | **{c['passed']}/{c['total']}** | {c['hit_at_1']:.0%} | {c['hit_at_5']:.0%} | "
                     f"{c['mrr']:.2f} | {c['rejection_rate']:.0%} | {c['avg_latency_ms']:.0f} ms |")
    lines += ["", "| Passed by type | " + " | ".join(cats) + " |", "|---|" + "---|" * len(cats)]
    for n in names:
        bc = configs[n]["by_category"]
        lines.append(f"| {n} | " + " | ".join(f"{bc[c]['passed']}/{bc[c]['total']}" for c in cats) + " |")
    lines += ["", "<details><summary>Every retrieval case</summary>", "",
              "| # | Type | Question | " + " | ".join(names) + " |", "|---|---|---|" + "---|" * len(names)]
    for i, case in enumerate(configs[names[0]]["cases"]):
        cells = [f"{mark(configs[n]['cases'][i]['passed'])} {configs[n]['cases'][i]['rank'] or ''}".strip() for n in names]
        lines.append(f"| {case['id']} | {case['category']} | {case['question']} | " + " | ".join(cells) + " |")
    lines += ["", "</details>", "", "### Retrieval failures", ""]
    for n in names:
        failed = [c for c in configs[n]["cases"] if not c["passed"]]
        lines.append(f"**{n}**: {len(failed)} failed" + ("." if not failed else ""))
        for c in failed:
            top = c["top"][0] if c["top"] else None
            got = f" Top result: `{top['source_file']}` chunk {top['chunk_index']} ({top['score']:.2f})." if top else ""
            lines.append(f"- `{c['id']}` {c['question']}: {c['reason']}.{got}")
        lines.append("")

    answers = report.get("answers")
    if answers:
        levels = list(answers)
        lines += ["## Answers", "",
                  "Every question with an answer key, run through the full pipeline (`answering.py`, the code behind `/search`) "
                  "and graded automatically: required facts present, a `[n]` citation present, unanswerable questions declined. "
                  "*Claims verified* is the pipeline's own verifier: each cited claim checked against the chunks it cites.", "",
                  "| Pipeline | Model | Correct | Claims verified | Revised | Re-searched | Tool calls | Tokens / question | LLM calls / question |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for n in levels:
            a = answers[n]
            ver = f"{a['claims_supported']}/{a['claims_checked']}" if a["claims_checked"] else "not checked"
            lines.append(f"| {a['label']} | `{a['model']}` | **{a['passed']}/{a['total']}** | {ver} | {a['revised']} | {a['corrected']} | "
                         f"{a['tool_calls']} | {a['avg_prompt_tokens'] + a['avg_completion_tokens']:,} | {a['avg_llm_calls']} |")
        acats = list(answers[levels[0]]["by_category"])
        lines += ["", "| Correct by type | " + " | ".join(acats) + " |", "|---|" + "---|" * len(acats)]
        for n in levels:
            bc = answers[n]["by_category"]
            lines.append(f"| {n} | " + " | ".join(f"{bc[c]['passed']}/{bc[c]['total']}" for c in acats) + " |")
        lines += ["", "| # | Question | " + " | ".join(levels) + " |", "|---|---|" + "---|" * len(levels)]
        for i, case in enumerate(answers[levels[0]]["cases"]):
            lines.append(f"| {case['id']} | {case['question']} | " + " | ".join(mark(answers[n]["cases"][i]["passed"]) for n in levels) + " |")
        lines += ["", "### What the pipeline did", ""]
        for n in levels:
            notable = [r for r in answers[n]["cases"] if r["tools"] or r["revised"] or r["corrected_query"] or r["unsupported_claims"]]
            if not notable:
                continue
            lines.append(f"**{n}**")
            lines.append("")
            for r in notable:
                bits = []
                if r["corrected_query"]:
                    bits.append(f"re-searched as \"{r['corrected_query']}\"")
                if r["tools"]:
                    bits.append("tools: " + "; ".join(f"`{t}`" for t in r["tools"]))
                if r["revised"]:
                    bits.append("revised after verification")
                if r["unsupported_claims"]:
                    bits.append("still unsupported: " + "; ".join(f"\"{t[:100]}\"" for t in r["unsupported_claims"]))
                lines.append(f"- `{r['id']}` {r['question']}: " + ", ".join(bits) + ".")
            lines.append("")
        lines += ["### Answer failures", ""]
        for n in levels:
            failed = [r for r in answers[n]["cases"] if not r["passed"]]
            lines.append(f"**{n}**: {len(failed)} failed" + ("." if not failed else ""))
            for r in failed:
                lines.append(f"- `{r['id']}` {r['question']}: {r['reason']}. Answer began: \"{' '.join(r['answer'].split())[:180]}…\"")
            lines.append("")
    return "\n".join(lines) + "\n"


def main_cli():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", action="store_true", help="also generate and grade answers with the configured LLM")
    ap.add_argument("--levels", default=",".join(ANSWER_LEVELS), help="answer pipeline levels to grade")
    ap.add_argument("--only", default="", help="comma-separated case ids to re-grade, merged into the last report")
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between questions (free-tier token limits)")
    ap.add_argument("--check", action="store_true", help="exit 1 when the default setup misses a threshold")
    ap.add_argument("--no-write", action="store_true", help="print only; leave evals/results untouched")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    golden = json.loads((ROOT / "evals" / "golden.json").read_text(encoding="utf-8"))
    log(f"$ python evals/run_evals.py{' --answers' if args.answers else ''}")
    log("")
    configs, indexes, reranker = evaluate_retrieval(golden)

    by_category = {}
    for case in golden["cases"]:
        by_category[case["category"]] = by_category.get(case["category"], 0) + 1
    failures = check_thresholds(configs)
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "environment": {"python": platform.python_version(), "platform": platform.system(),
                        "embedding_model": indexes[("structure", "off")].embed_model, "reranker_model": reranker.model_name},
        "golden": {"total": len(golden["cases"]), "corpus": golden["corpus"], "by_category": by_category},
        "top_k": TOP_K,
        "default_config": DEFAULT_CONFIG,
        "thresholds": THRESHOLDS,
        "gate": {"passed": not failures, "failures": failures},
        "retrieval": configs,
    }

    previous = RESULTS / "latest.json"
    if args.answers:
        only = {c.strip() for c in args.only.split(",") if c.strip()} or None
        prior = json.loads(previous.read_text(encoding="utf-8")).get("answers") if only and previous.exists() else None
        graded = evaluate_answers(golden, indexes, reranker, args.levels.split(","), args.pause, only, prior)
        # A partial re-grade keeps every level it did not run, in the original order
        report["answers"] = {k: graded.get(k, v) for k, v in prior.items()} if prior else graded
        for k, v in graded.items():
            report["answers"].setdefault(k, v)
    elif previous.exists():
        # Keep the last graded answers: they cost tokens and need a key, the retrieval half does not
        old = json.loads(previous.read_text(encoding="utf-8"))
        if old.get("golden", {}).get("total") == report["golden"]["total"]:
            report["answers"] = old.get("answers")

    log("")
    log("Regression check: " + ("PASS" if not failures else "FAIL"))
    for f in failures:
        log(f"  - {f}")

    if not args.no_write:
        RESULTS.mkdir(parents=True, exist_ok=True)
        previous.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (RESULTS / "REPORT.md").write_text(render_report(report), encoding="utf-8")
        name = ("run-answers-regrade.log" if args.only else "run-answers.log") if args.answers else "run-retrieval.log"
        (RESULTS / name).write_text("\n".join(log.lines) + "\n", encoding="utf-8")
        print(f"\nWrote {previous.relative_to(ROOT)}, {(RESULTS / 'REPORT.md').relative_to(ROOT)} and {(RESULTS / name).relative_to(ROOT)}")
    if args.check and failures:
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
