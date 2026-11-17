"""
How Ethan answers a question, end to end, as a stream of events.

    retrieve (hybrid, rerank, optional corrective re-search)
      -> generate (streamed, or an agent loop with calculate / search_documents tools)
      -> verify each cited claim against its chunks (Self-RAG style)
      -> revise once if a claim is unsupported, and verify the revision

The API turns these events into Server-Sent Events (/search/stream) or one JSON
response (/search). evals/run_evals.py consumes the same generator, so the
evaluation measures exactly what users get.
"""
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

from costs import Pricing
from pipeline import Retriever, trim_to_budget
from tools import AGENT_INSTRUCTIONS, TOOLS, CalculationError, calculate, format_number
from verify import problems_for, revision_messages, verify_answer

NO_RESULTS_ANSWER = (
    "I couldn't find anything relevant in the knowledge base. "
    "This question has been logged as a knowledge gap so the team can add the missing documentation."
)
EMPTY_ANSWER = (
    "The model used its whole output budget before writing an answer. "
    "Ask again, or raise MAX_OUTPUT_TOKENS on the server."
)
REWRITE_PROMPT = (
    "Rewrite the question below as one short search query, using the formal wording a company document "
    "(annual report, policy, handbook) would use for the same idea. Keep names, numbers and codes. "
    "Return only the query.\n\nQuestion: "
)
MAX_AGENT_STEPS = 4
AGENT_SEARCH_K = 3

Event = Tuple[str, Dict[str, Any]]


@dataclass
class AnswerOptions:
    top_k: int = 5
    rerank: bool = True
    mode: Optional[str] = None
    visuals: bool = False
    agent: bool = False
    verify: bool = True
    correct: bool = True
    history: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class AnswerConfig:
    assistant_name: str = "Ethan"
    company_name: str = "your company"
    company_profile: str = ""
    visuals_prompt: str = ""
    max_context_chars: int = 8000
    max_output_tokens: int = 1024
    temperature: float = 0.2
    gap_threshold: float = 0.25
    revise: bool = True


# ---------------------------------------------------------------- formatting
def format_source(r: Dict[str, Any], ref: int) -> Dict[str, Any]:
    payload = r.get("payload") or {}
    keyword = r.get("keyword_score")
    return {
        "ref": ref,
        "id": str(r["id"]),
        "score": round(r.get("score", 0.0), 4),
        "vector_score": round(r.get("vector_score") or r.get("score", 0.0), 4),
        "keyword_score": round(keyword, 3) if keyword is not None else None,
        "rerank_score": round(r["rerank_score"], 4) if r.get("rerank_score") is not None else None,
        "matched_by": r.get("matched_by", "dense"),
        "text": payload.get("text", ""),
        "source_file": payload.get("source_file", "Unknown"),
        "chunk_index": payload.get("chunk_index", 0),
        "section": payload.get("section", ""),
        "metadata": {k: v for k, v in payload.items() if k not in ("text", "context")},
    }


def format_sources(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [format_source(r, i) for i, r in enumerate(results, 1)]


def confidence_for(sources: List[Dict[str, Any]], reranked: bool, gap_threshold: float = 0.25) -> Dict[str, Any]:
    """Grounding confidence from retrieval scores, so users know when to double-check."""
    if not sources:
        return {"level": "none", "score": 0.0}
    top = max(s["rerank_score"] if reranked and s["rerank_score"] is not None else s["vector_score"] for s in sources)
    high, medium = (0.7, 0.3) if reranked else (0.5, gap_threshold)
    level = "high" if top >= high else "medium" if top >= medium else "low"
    return {"level": level, "score": round(top, 4)}


def context_block(sources: List[Dict[str, Any]]) -> str:
    return "\n\n".join(f"[{s['ref']}] (source: {s['source_file']}, chunk {s['chunk_index']})\n{s['text']}" for s in sources)


def tidy(text: str) -> str:
    r"""Remove gpt-oss channel markers like 【commentary】 and unwrap LaTeX \( ... \) the UI cannot render."""
    text = re.sub(r"【(?!\d)[^】]*】", "", text)
    text = re.sub(r"\[\((\d+)\)\]", r"[\1]", text)  # "[(3)]" -> "[3]"
    text = re.sub(r"\\[()]", "", text)
    return text.replace("\\%", "%")


def add_usage(total: Dict[str, int], usage: Dict[str, int]):
    for k in ("prompt_tokens", "completion_tokens"):
        total[k] = total.get(k, 0) + (usage.get(k) or 0)
    total["calls"] = total.get("calls", 0) + 1


class Answerer:
    def __init__(self, retriever: Retriever, llm, config: AnswerConfig, pricing: Optional[Pricing] = None):
        self.retriever = retriever
        self.llm = llm
        self.config = config
        self.pricing = pricing or Pricing(0, 0)

    # ---------------------------------------------------------------- prompt
    def build_messages(self, query: str, sources: List[Dict[str, Any]], history: List[Dict[str, str]],
                       visuals: bool = False, agent: bool = False) -> List[dict]:
        c = self.config
        system = (
            f"You are {c.assistant_name}, the internal knowledge assistant for {c.company_name}. "
            "Answer employee questions using ONLY the numbered context chunks provided. "
            "Cite every factual claim with its chunk number in square brackets, e.g. [1] or [2][3]. "
            "If the context answers only part of the question, answer that part with citations and say what is missing. "
            "If it does not contain the answer at all, say so plainly and suggest what document "
            "or team might have it - never invent policies, numbers or names. "
            "When a chunk contains a table, read every row before comparing values. "
            "Be concise and use short paragraphs or bullet lists where it helps readability."
        )
        if c.company_profile:
            # Background only: lets the assistant interpret "this fiscal year"; facts must still come from chunks
            system += f"\n\nBackground on {c.company_name} (for interpreting questions, not a citable source): {c.company_profile}"
        if agent:
            system += "\n\n" + AGENT_INSTRUCTIONS
        if visuals and c.visuals_prompt:
            system += "\n\n" + c.visuals_prompt
        messages = [{"role": "system", "content": system}]
        for turn in history[-6:]:
            messages.append({"role": turn["role"], "content": turn["content"][:2000]})
        messages.append({"role": "user", "content": f"Context:\n{context_block(sources)}\n\nQuestion: {query}"})
        return messages

    # ---------------------------------------------------------------- steps
    def rewrite(self, query: str, usage: Dict[str, int]) -> str:
        try:
            text, u = self.llm.chat_with_usage([{"role": "user", "content": REWRITE_PROMPT + query}], temperature=0.0, max_tokens=300)
            add_usage(usage, u)
            return text.strip().strip('"').splitlines()[0][:300] if text.strip() else ""
        except Exception:
            return ""

    def _agent(self, messages: List[dict], sources: List[Dict[str, Any]], opts: AnswerOptions,
               usage: Dict[str, int]) -> Iterator[Event]:
        """Tool loop. Yields tool/sources events; the final answer arrives as ('final', {'text': ...})."""
        seen = {s["id"] for s in sources}
        for step in range(1, MAX_AGENT_STEPS + 2):
            last = step > MAX_AGENT_STEPS
            message, u = self.llm.chat_with_tools(
                messages, TOOLS, tool_choice="none" if last else "auto",
                temperature=self.config.temperature, max_tokens=self.config.max_output_tokens,
            )
            add_usage(usage, u)
            calls = message.get("tool_calls") or []
            if not calls:
                yield "final", {"text": message.get("content") or ""}
                return
            messages.append(message)
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                t0 = time.perf_counter()
                ok, result, new_sources = True, "", []
                if name == "calculate":
                    try:
                        result = format_number(calculate(str(args.get("expression", ""))))
                    except CalculationError as e:
                        ok, result = False, f"Error: {e}"
                elif name == "search_documents":
                    found = self.retriever.retrieve(str(args.get("query", ""))[:300], top_k=AGENT_SEARCH_K, rerank=opts.rerank, mode=opts.mode)
                    for r in trim_to_budget(found["results"], self.config.max_context_chars // 2):
                        if str(r["id"]) not in seen:
                            seen.add(str(r["id"]))
                            new_sources.append(format_source(r, len(sources) + len(new_sources) + 1))
                    result = context_block(new_sources) if new_sources else "No new chunks found."
                else:
                    ok, result = False, f"Error: unknown tool {name}"
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                if new_sources:
                    sources.extend(new_sources)
                    yield "sources_added", {"sources": new_sources}
                yield "tool", {
                    "step": step, "name": name, "args": args, "ok": ok,
                    "result": result if name == "calculate" else f"{len(new_sources)} new chunk(s)",
                    "refs": [s["ref"] for s in new_sources], "time": round(time.perf_counter() - t0, 3),
                }

    # ---------------------------------------------------------------- main
    def run(self, query: str, opts: AnswerOptions) -> Iterator[Event]:
        start = time.perf_counter()
        usage: Dict[str, int] = {}
        times = {"llm_time": 0.0, "verify_time": 0.0, "rewrite_time": 0.0}
        yield "stage", {"stage": "retrieving"}

        rewriter = (lambda q: self.rewrite(q, usage)) if opts.correct else None
        retrieval = self.retriever.retrieve(query, top_k=opts.top_k, rerank=opts.rerank, mode=opts.mode, rewriter=rewriter)
        if retrieval["correction"]:
            times["rewrite_time"] = retrieval["correction"]["rewrite_time"]
        sources = format_sources(trim_to_budget(retrieval["results"], self.config.max_context_chars))
        confidence = confidence_for(sources, opts.rerank, self.config.gap_threshold)
        yield "stage", {
            "stage": "retrieved", "mode": retrieval["mode"], "results_found": len(sources),
            "embedding_time": round(retrieval["embedding_time"], 3), "search_time": round(retrieval["search_time"], 3),
            "rerank_time": round(retrieval["rerank_time"], 3), "correction": retrieval["correction"],
        }
        yield "sources", {"sources": sources, "confidence": confidence, "reranked": opts.rerank}

        steps: List[Dict[str, Any]] = []
        verification = None
        revised = None
        ttft = None
        if not sources:
            answer = NO_RESULTS_ANSWER
            yield "token", {"token": answer}
        else:
            yield "stage", {"stage": "generating"}
            messages = self.build_messages(query, sources, opts.history, opts.visuals, opts.agent)
            t0 = time.perf_counter()
            parts: List[str] = []
            if opts.agent:
                for kind, data in self._agent(messages, sources, opts, usage):
                    if kind == "final":
                        parts.append(data["text"])
                    elif kind == "tool":
                        steps.append(data)
                        yield "tool", data
                    elif kind == "sources_added":
                        yield "sources", {"sources": sources, "confidence": confidence, "reranked": opts.rerank}
                if parts and parts[0]:
                    parts[0] = tidy(parts[0])
                    ttft = time.perf_counter() - start
                    yield "token", {"token": parts[0]}
            else:
                stream_usage: Dict[str, int] = {}
                for kind, value in self.llm.stream_chat(messages, temperature=self.config.temperature, max_tokens=self.config.max_output_tokens):
                    if kind == "token":
                        if ttft is None:
                            ttft = time.perf_counter() - start
                        parts.append(value)
                        yield "token", {"token": value}
                    elif kind == "usage":
                        stream_usage = value
                add_usage(usage, stream_usage)
            times["llm_time"] = time.perf_counter() - t0
            answer = tidy("".join(parts))
            if not answer.strip():
                answer = EMPTY_ANSWER
                yield "token", {"token": answer}

            if opts.verify and answer != EMPTY_ANSWER:
                yield "stage", {"stage": "verifying"}
                t1 = time.perf_counter()
                verification, u = verify_answer(self.llm, answer, sources, self.config.max_output_tokens)
                if u:
                    add_usage(usage, u)
                problems = problems_for(verification)
                if problems and self.config.revise:
                    # Self-correction: rewrite once with the checker's findings, then check the rewrite
                    yield "stage", {"stage": "revising"}
                    try:
                        text, u2 = self.llm.chat_with_usage(
                            revision_messages(messages, answer, problems),
                            temperature=self.config.temperature, max_tokens=self.config.max_output_tokens,
                        )
                        add_usage(usage, u2)
                        text = tidy(text)
                        if text.strip():
                            second, u3 = verify_answer(self.llm, text, sources, self.config.max_output_tokens)
                            if u3:
                                add_usage(usage, u3)
                            revised = {
                                "original": answer, "problems": problems,
                                "before": {k: verification[k] for k in ("supported", "partial", "unsupported", "total", "score")},
                            }
                            answer, verification = text, second
                            yield "revision", {"answer": answer, "revised": revised}
                    except Exception:
                        pass
                times["verify_time"] = time.perf_counter() - t1
                yield "verification", verification

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        metrics = {
            "total_time": round(time.perf_counter() - start, 3),
            "embedding_time": round(retrieval["embedding_time"], 3),
            "search_time": round(retrieval["search_time"], 3),
            "retrieval_time": round(retrieval["embedding_time"] + retrieval["search_time"], 3),
            "rerank_time": round(retrieval["rerank_time"], 3),
            "rewrite_time": round(times["rewrite_time"], 3),
            "llm_time": round(times["llm_time"], 3),
            "verify_time": round(times["verify_time"], 3),
            "ttft": round(ttft, 3) if ttft is not None else None,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "llm_calls": usage.get("calls", 0),
            "cost_usd": round(self.pricing.cost(prompt_tokens, completion_tokens), 6),
            "candidates": retrieval["candidates"],
            "mode": retrieval["mode"],
            "agent_steps": len(steps),
            "cached": False,
            "tokens_saved": 0,
        }
        yield "complete", {
            "answer": answer, "sources": sources, "confidence": confidence, "metrics": metrics,
            "verification": verification, "steps": steps, "correction": retrieval["correction"], "revised": revised,
        }

    def answer(self, query: str, opts: AnswerOptions) -> Dict[str, Any]:
        """Run to completion and return the final result (non-streaming callers, evaluation)."""
        result: Dict[str, Any] = {}
        for kind, data in self.run(query, opts):
            if kind == "complete":
                result = data
        return result
