"""
Ethan's evaluation harness.

    python evals/run_evals.py                 retrieval evaluation (no API key, ~1 minute on CPU)
    python evals/run_evals.py --answers       also grade generated answers (needs an LLM key)
    python evals/run_evals.py --check         exit 1 if the default configuration misses its thresholds (CI)

It builds an in-memory Qdrant index from the demo corpus, runs every golden
question through each retrieval configuration using the same pipeline.py the
API serves, and writes:

    evals/results/latest.json   machine-readable, shown in the app's Evaluation view
    evals/results/REPORT.md     every case, passed and failed, per configuration

Nothing is hidden: failures are listed with what was retrieved instead.
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

from data_loader import DocumentLoader  # noqa: E402
from pipeline import Retriever  # noqa: E402
from reranker import Reranker  # noqa: E402
from vector_db import RAGVectorDB  # noqa: E402

RESULTS = ROOT / "evals" / "results"
TOP_K = 5
GAP_THRESHOLD = 0.25      # cosine below this = "weakly grounded" (same default as the API)
RERANK_THRESHOLD = 0.30   # rerank relevance below this = "weakly grounded"

# name, chunking strategy, retrieval mode, rerank
CONFIGS = [
    ("baseline-v2", "fixed", "dense", False),
    ("dense", "structure", "dense", False),
    ("keyword", "structure", "keyword", False),
    ("hybrid", "structure", "hybrid", False),
    ("hybrid+rerank", "structure", "hybrid", True),
]
CONFIG_LABELS = {
    "baseline-v2": "v2 baseline: fixed 512-char chunks, dense only",
    "dense": "Structure-aware chunks, dense only",
    "keyword": "Structure-aware chunks, BM25 keyword only",
    "hybrid": "Structure-aware chunks, hybrid (dense + BM25, RRF)",
    "hybrid+rerank": "Structure-aware chunks, hybrid + cross-encoder rerank",
}
DEFAULT_CONFIG = "hybrid+rerank"

# The CI gate. Deliberately a little below the measured numbers so that a real
# regression fails the build while run-to-run noise does not.
THRESHOLDS = {
    "hybrid": {"hit_at_5": 0.90, "mrr": 0.70},
    "hybrid+rerank": {"hit_at_5": 0.93, "mrr": 0.80, "rejection_rate": 0.75},
}


def is_relevant(text: str, groups) -> bool:
    low = text.lower()
    return any(all(p.lower() in low for p in group) for group in groups)


def build_index(strategy: str, corpus, embedder=None) -> RAGVectorDB:
    db = RAGVectorDB(url=":memory:", collection=f"eval_{strategy}", embedder=embedder)
    loader = DocumentLoader(strategy=strategy)
    for rel in corpus:
        chunks = loader.load_and_chunk(str(ROOT / rel))
        db.add_texts([c["text"] for c in chunks], metadata=[c["metadata"] for c in chunks])
    return db


def evaluate_retrieval(golden, quiet=False):
    indexes, embedder = {}, None
    for strategy in sorted({c[1] for c in CONFIGS}):
        indexes[strategy] = build_index(strategy, golden["corpus"], embedder)
        embedder = indexes[strategy].embedder
    reranker = Reranker(os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"))

    # A label nobody can satisfy is a bug in the golden set, not a retrieval failure
    for case in golden["cases"]:
        for strategy, db in indexes.items():
            if case["relevant"] and not any(is_relevant((p.payload or {}).get("text", ""), case["relevant"]) for p in db.scroll_all()):
                case.setdefault("unreachable_in", []).append(strategy)

    configs = {}
    for name, strategy, mode, rerank in CONFIGS:
        db = indexes[strategy]
        retriever = Retriever(db, reranker)
        retriever.retrieve("warm up", top_k=TOP_K, rerank=rerank, mode=mode)  # load models outside the timings
        db._query_vectors.clear()  # every configuration pays for its own query embeddings
        cases, latencies = [], []
        for case in golden["cases"]:
            t0 = time.perf_counter()
            out = retriever.retrieve(case["question"], top_k=TOP_K, rerank=rerank, mode=mode)
            latencies.append((time.perf_counter() - t0) * 1000)
            results = out["results"]
            evidence = max((r["rerank_score"] if rerank else r["vector_score"] for r in results), default=0.0)
            grounded = evidence >= (RERANK_THRESHOLD if rerank else GAP_THRESHOLD)
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
                # Pass = retrieval admits it found nothing solid, so the UI warns and logs a knowledge gap
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

        def hit(k, rows=answerable):
            return round(sum(1 for c in rows if c["rank"] and c["rank"] <= k) / len(rows), 3) if rows else 0.0

        by_category = {}
        for category in sorted({c["category"] for c in cases}):
            rows = [c for c in cases if c["category"] == category]
            by_category[category] = {"passed": sum(c["passed"] for c in rows), "total": len(rows)}

        configs[name] = {
            "label": CONFIG_LABELS[name], "chunking": strategy, "mode": mode, "rerank": rerank,
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
        if not quiet:
            c = configs[name]
            print(f"{name:<15} passed {c['passed']:>2}/{c['total']}  hit@1 {c['hit_at_1']:.2f}  hit@5 {c['hit_at_5']:.2f}  "
                  f"MRR {c['mrr']:.2f}  rejects {c['rejection_rate']:.2f}  {c['avg_latency_ms']:.0f} ms")
    return configs, indexes, reranker


# ---------------------------------------------------------------- answers
REFUSAL = re.compile(
    r"(do(es)? not|don't|doesn't|no|not|cannot|can't|couldn't|unable)\b.{0,80}"
    r"(contain|include|mention|provide|information|cover|found|find|available|address|specify|state)", re.I | re.S)
CITATION = re.compile(r"\[\d+\]|【\d+")


def normalise(text: str) -> str:
    """Models like typographic characters: narrow spaces in '10 %', curly quotes, non-breaking hyphens."""
    for src, dst in (("\u2011", "-"), ("\u2010", "-"), ("\u2019", "'"), ("\u2018", "'")):
        text = text.replace(src, dst)
    return re.sub(r"[\u00a0\u2007\u2009\u202f]", " ", text)


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


def evaluate_answers(golden, indexes, reranker, config_names, pause: float):
    # Reuse the API's own prompt builder and LLM settings, without needing a Qdrant server
    os.environ["QDRANT_URL"] = ":memory:"
    os.environ["QDRANT_PATH"] = ""
    import main

    if main.llm is None:
        raise SystemExit(f"--answers needs a language model: {main.llm_error}")
    cases = [c for c in golden["cases"] if "answer" in c]
    out = {}
    for name in config_names:
        _, strategy, mode, rerank = next(c for c in CONFIGS if c[0] == name)
        retriever = Retriever(indexes[strategy], reranker)
        rows = []
        for case in cases:
            results = main.trim_to_budget(retriever.retrieve(case["question"], TOP_K, rerank, mode)["results"], main.MAX_CONTEXT_CHARS)
            sources = main.format_sources(results)
            answer, usage = "", {}
            for attempt in range(6):
                try:
                    answer, usage = main.llm.chat_with_usage(
                        main.build_messages(case["question"], sources, []), temperature=0.0, max_tokens=main.MAX_OUTPUT_TOKENS)
                    break
                except Exception as e:  # free tiers rate-limit by tokens per minute
                    if attempt == 5:
                        answer = f"(error: {e})"
                    time.sleep(12 * (attempt + 1))
            passed, reason = grade_answer(case, answer)
            rows.append({
                "id": case["id"], "category": case["category"], "question": case["question"], "passed": passed, "reason": reason,
                "confidence": main.confidence_for(sources, rerank)["level"], "answer": answer.strip(),
                "prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0),
            })
            print(f"  [{name}] {case['id']} {'PASS' if passed else 'FAIL'} {reason}")
            time.sleep(pause)
        out[name] = {
            "label": CONFIG_LABELS[name], "model": main.llm.model, "provider": main.llm.provider_name,
            "passed": sum(r["passed"] for r in rows), "total": len(rows),
            "avg_prompt_tokens": round(statistics.fmean(r["prompt_tokens"] for r in rows)),
            "avg_completion_tokens": round(statistics.fmean(r["completion_tokens"] for r in rows)),
            "cases": rows,
        }
    return out


# ---------------------------------------------------------------- report
def check_thresholds(configs):
    failures = []
    for name, limits in THRESHOLDS.items():
        for metric, minimum in limits.items():
            value = configs[name][metric]
            if value < minimum:
                failures.append(f"{name}: {metric} = {value:.3f}, below the required {minimum:.2f}")
    return failures


def mark(passed):
    return "✅" if passed else "❌"


def render_report(report) -> str:
    configs, names = report["retrieval"], [c[0] for c in CONFIGS]
    lines = [
        "# Evaluation report",
        "",
        f"Generated {report['generated_at']} on {report['environment']['platform']} "
        f"(Python {report['environment']['python']}). Reproduce with `python evals/run_evals.py`.",
        "",
        f"**{report['golden']['total']} golden questions** over {len(report['golden']['corpus'])} documents: "
        + ", ".join(f"{n} {c}" for c, n in report["golden"]["by_category"].items()) + ".",
        "",
        "## Retrieval: which configuration finds the right chunk",
        "",
        "A case passes when a chunk containing the answer is in the top 5 or, for unanswerable questions, "
        "when retrieval reports weak grounding so the UI warns the user and logs a knowledge gap.",
        "",
        "| Configuration | Passed | Hit@1 | Hit@5 | MRR | Unanswerable rejected | Avg latency |",
        "|---|---|---|---|---|---|---|",
    ]
    for n in names:
        c = configs[n]
        star = " **(default)**" if n == DEFAULT_CONFIG else ""
        lines.append(f"| {c['label']}{star} | **{c['passed']}/{c['total']}** | {c['hit_at_1']:.0%} | {c['hit_at_5']:.0%} | "
                     f"{c['mrr']:.2f} | {c['rejection_rate']:.0%} | {c['avg_latency_ms']:.0f} ms |")

    lines += ["", "### Passed by category", "", "| Configuration | " + " | ".join(report["golden"]["by_category"]) + " |",
              "|---|" + "---|" * len(report["golden"]["by_category"])]
    for n in names:
        cats = configs[n]["by_category"]
        lines.append(f"| {n} | " + " | ".join(f"{cats[c]['passed']}/{cats[c]['total']}" for c in report["golden"]["by_category"]) + " |")

    lines += ["", "### Every case", "", "Rank of the first relevant chunk (✅ n) or ❌. Unanswerable rows show whether weak grounding was reported.",
              "", "| # | Category | Question | " + " | ".join(names) + " |", "|---|---|---|" + "---|" * len(names)]
    for i, case in enumerate(configs[names[0]]["cases"]):
        cells = []
        for n in names:
            row = configs[n]["cases"][i]
            cells.append(f"{mark(row['passed'])} {row['rank']}" if row["rank"] else mark(row["passed"]))
        lines.append(f"| {case['id']} | {case['category']} | {case['question']} | " + " | ".join(cells) + " |")

    lines += ["", "### Failures in detail", ""]
    for n in names:
        failed = [c for c in configs[n]["cases"] if not c["passed"]]
        lines.append(f"**{n}**: {len(failed)} failed" + ("" if failed else ". Nothing to report."))
        lines.append("")
        for c in failed:
            top = c["top"][0] if c["top"] else None
            got = f" Top result instead: `{top['source_file']}` chunk {top['chunk_index']} ({top['score']:.2f}), \"{top['preview'][:90]}…\"" if top else ""
            lines.append(f"- `{c['id']}` {c['question']}: {c['reason']}.{got}")
        if failed:
            lines.append("")

    if report.get("answers"):
        lines += ["## Answers: is the generated answer right", "",
                  "Graded automatically: required facts must appear (regex), answerable questions must carry a `[n]` citation, "
                  "and unanswerable questions must be declined.", "",
                  "| Configuration | Model | Passed | Avg prompt tokens | Avg completion tokens |", "|---|---|---|---|---|"]
        for n, a in report["answers"].items():
            lines.append(f"| {a['label']} | `{a['model']}` via {a['provider']} | **{a['passed']}/{a['total']}** | {a['avg_prompt_tokens']} | {a['avg_completion_tokens']} |")
        answer_names = list(report["answers"])
        lines += ["", "| # | Question | " + " | ".join(answer_names) + " |", "|---|---|" + "---|" * len(answer_names)]
        for i, case in enumerate(report["answers"][answer_names[0]]["cases"]):
            lines.append(f"| {case['id']} | {case['question']} | " + " | ".join(mark(report["answers"][n]["cases"][i]["passed"]) for n in answer_names) + " |")
        lines.append("")
        for n in answer_names:
            failed = [c for c in report["answers"][n]["cases"] if not c["passed"]]
            lines.append(f"**{n}**: {len(failed)} failed" + ("" if failed else ". Nothing to report."))
            lines.append("")
            for c in failed:
                lines.append(f"- `{c['id']}` {c['question']}: {c['reason']}. Grounding label was *{c['confidence']}*. "
                             f"Answer began: \"{' '.join(c['answer'].split())[:160]}…\"")
            if failed:
                lines.append("")

    gate = report["gate"]
    lines += ["## CI gate", "", f"Status: **{'PASS' if gate['passed'] else 'FAIL'}**", "",
              "| Configuration | Metric | Required | Measured |", "|---|---|---|---|"]
    for name, limits in THRESHOLDS.items():
        for metric, minimum in limits.items():
            lines.append(f"| {name} | {metric} | ≥ {minimum:.2f} | {configs[name][metric]:.3f} {mark(configs[name][metric] >= minimum)} |")
    return "\n".join(lines) + "\n"


def main_cli():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", action="store_true", help="also generate and grade answers with the configured LLM")
    ap.add_argument("--answer-configs", default="baseline-v2,hybrid+rerank", help="comma-separated configurations to grade answers for")
    ap.add_argument("--pause", type=float, default=4.0, help="seconds between LLM calls (free-tier token limits)")
    ap.add_argument("--check", action="store_true", help="exit 1 when a threshold is missed")
    ap.add_argument("--no-write", action="store_true", help="print only; leave evals/results untouched")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    golden = json.loads((ROOT / "evals" / "golden.json").read_text(encoding="utf-8"))
    configs, indexes, reranker = evaluate_retrieval(golden)

    by_category = {}
    for case in golden["cases"]:
        by_category[case["category"]] = by_category.get(case["category"], 0) + 1
    failures = check_thresholds(configs)
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "environment": {"python": platform.python_version(), "platform": platform.system(),
                        "embedding_model": indexes["structure"].embed_model, "reranker_model": reranker.model_name},
        "golden": {"total": len(golden["cases"]), "corpus": golden["corpus"], "by_category": by_category},
        "top_k": TOP_K,
        "default_config": DEFAULT_CONFIG,
        "thresholds": THRESHOLDS,
        "gate": {"passed": not failures, "failures": failures},
        "retrieval": configs,
    }

    previous = RESULTS / "latest.json"
    if args.answers:
        report["answers"] = evaluate_answers(golden, indexes, reranker, args.answer_configs.split(","), args.pause)
    elif previous.exists():
        # Keep the last graded answers: they cost tokens and need a key, the retrieval half does not
        report["answers"] = json.loads(previous.read_text(encoding="utf-8")).get("answers")

    markdown = render_report(report)
    if not args.no_write:
        RESULTS.mkdir(parents=True, exist_ok=True)
        previous.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (RESULTS / "REPORT.md").write_text(markdown, encoding="utf-8")
        print(f"\nWrote {previous.relative_to(ROOT)} and {(RESULTS / 'REPORT.md').relative_to(ROOT)}")

    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(markdown)

    print("\nGate:", "PASS" if not failures else "FAIL")
    for failure in failures:
        print("  -", failure)
    if args.check and failures:
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
