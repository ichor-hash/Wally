"""Unit tests for the answer pipeline: tools, verification, agent loop, corrective search, context. No LLM or network."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from answering import AnswerConfig, AnswerOptions, Answerer, tidy  # noqa: E402
from contextual import build_contexts, document_title, with_context  # noqa: E402
from pipeline import Retriever  # noqa: E402
from tools import CalculationError, calculate, format_number  # noqa: E402
from vector_db import RAGVectorDB  # noqa: E402
from verify import extract_claims, verify_answer  # noqa: E402

from test_retrieval import FakeEmbedder  # noqa: E402


# ---------------------------------------------------------------- calculator
@pytest.mark.parametrize("expr,expected", [
    ("(416161 - 391035) / 391035 * 100", 6.4255),
    ("109,158 / 416,161 * 100", 26.2298),
    ("33708 + 28023", 61731),
    ("round(2 ** 10 / 3, 2)", 341.33),
    ("50% * 200", 100),
    ("max(1, 5, 3) - abs(-2)", 3),
])
def test_calculate(expr, expected):
    assert calculate(expr) == pytest.approx(expected, rel=1e-4)


@pytest.mark.parametrize("expr", ["__import__('os').system('x')", "open('f')", "1/0", "2 ** 1000", "[1, 2]", "a + 1", "x" * 400])
def test_calculate_rejects_anything_but_arithmetic(expr):
    with pytest.raises(CalculationError):
        calculate(expr)


def test_format_number():
    assert format_number(61731.0) == "61,731"
    assert format_number(26.229838) == "26.2298"


# ---------------------------------------------------------------- claims
def test_extract_claims_splits_sentences_and_attaches_citation_lines():
    answer = (
        "Japan grew fastest, up 15% [1]. Europe rose 10% [1][2].\n"
        "- Services hit a record [3]\n"
        "[4]\n"
        "This sentence has no citation.\n"
        "```openui\nroot = Stack([c])\n```"
    )
    claims = extract_claims(answer)
    assert [c["refs"] for c in claims] == [[1], [1, 2], [3, 4]]
    assert claims[0]["text"].startswith("Japan grew fastest")
    assert all("openui" not in c["text"] for c in claims)


def test_extract_claims_handles_ranges_and_fullwidth_brackets():
    claims = extract_claims("Revenue rose sharply [1-3]. Margin fell slightly 【4】.")
    assert claims[0]["refs"] == [1, 2, 3] and claims[1]["refs"] == [4]


class ScriptedLLM:
    """Returns queued replies; records what it was asked."""
    model = "fake"
    provider_name = "Fake"

    def __init__(self, replies=None, tool_replies=None):
        self.replies = list(replies or [])
        self.tool_replies = list(tool_replies or [])
        self.calls = []

    def chat_with_usage(self, messages, model=None, temperature=0.0, max_tokens=100):
        self.calls.append(("chat", messages))
        return self.replies.pop(0), {"prompt_tokens": 10, "completion_tokens": 5}

    def stream_chat(self, messages, model=None, temperature=0.0, max_tokens=100):
        self.calls.append(("stream", messages))
        yield "token", self.replies.pop(0)
        yield "usage", {"prompt_tokens": 100, "completion_tokens": 20}

    def chat_with_tools(self, messages, tools, tool_choice="auto", temperature=0.0, max_tokens=100):
        self.calls.append(("tools", [dict(m) for m in messages]))
        return self.tool_replies.pop(0), {"prompt_tokens": 50, "completion_tokens": 10}


SOURCES = [{"ref": 1, "text": "Japan net sales were 28,703, up 15%."}, {"ref": 2, "text": "Europe net sales rose 10%."}]


def test_verify_answer_parses_verdicts_and_flags_missing_refs():
    llm = ScriptedLLM(replies=[json.dumps({"claims": [
        {"id": 1, "verdict": "SUPPORTED", "reason": "stated"},
        {"id": 2, "verdict": "UNSUPPORTED", "reason": "says 10%"},
    ]})])
    result, usage = verify_answer(llm, "Japan grew 15% [1]. Europe grew 12% [2]. Mars grew 5% [9].", SOURCES)
    assert result["status"] == "ok" and result["total"] == 3
    assert [c["verdict"] for c in result["claims"]] == ["SUPPORTED", "UNSUPPORTED", "UNSUPPORTED"]
    assert result["claims"][2]["reason"].startswith("Cites a chunk")
    assert result["score"] == pytest.approx(1 / 3, abs=1e-3)
    assert usage["prompt_tokens"] == 10


def test_verify_answer_survives_bad_json():
    result, _ = verify_answer(ScriptedLLM(replies=["not json"]), "Japan grew 15% [1].", SOURCES)
    assert result["status"] == "error"


def test_verify_skips_answers_without_citations():
    result, usage = verify_answer(ScriptedLLM(), "The documents do not cover this.", SOURCES)
    assert result["status"] == "no_claims" and usage == {}


def test_tidy_removes_model_artifacts():
    assert tidy("Share \\(26.2\\%\\)【commentary】 [1] 【2】 [(3)]") == "Share 26.2% [1] 【2】 [3]"


def test_block_citation_covers_the_list_above_it():
    claims = extract_claims("Announced in Q4:\n- iPhone 17\n- AirPods Pro 3\n\n[1]")
    assert len(claims) == 1 and claims[0]["refs"] == [1]
    assert "iPhone 17" in claims[0]["text"] and "AirPods Pro 3" in claims[0]["text"]


# ---------------------------------------------------------------- end-to-end with a fake model
@pytest.fixture
def answerer_factory():
    db = RAGVectorDB(url=":memory:", collection="a", embedder=FakeEmbedder())
    db.add_texts(
        ["New tariffs were announced on imports.", "Japan net sales were 28,703 and Americas 178,353.", "Laptops must use the VPN."],
        metadata=[{"source_file": f"d{i}.txt", "chunk_index": i} for i in range(3)],
    )

    def make(llm):
        return Answerer(Retriever(db), llm, AnswerConfig(company_name="Acme"))

    return make


def test_pipeline_streams_then_verifies_then_revises(answerer_factory):
    llm = ScriptedLLM(replies=[
        "Japan sold 99,999 [1].",                                                         # streamed draft
        json.dumps({"claims": [{"id": 1, "verdict": "UNSUPPORTED", "reason": "chunk says 28,703"}]}),
        "Japan sold 28,703 [1].",                                                         # revision
        json.dumps({"claims": [{"id": 1, "verdict": "SUPPORTED", "reason": "stated"}]}),
    ])
    events = list(answerer_factory(llm).run("japan sales", AnswerOptions(rerank=False, correct=False)))
    kinds = [k for k, _ in events]
    assert kinds.index("sources") < kinds.index("token") < kinds.index("revision") < kinds.index("verification")
    result = events[-1][1]
    assert result["answer"] == "Japan sold 28,703 [1]."
    assert result["revised"]["before"]["unsupported"] == 1
    assert result["verification"]["supported"] == 1
    assert result["metrics"]["llm_calls"] == 4


def test_agent_calls_calculator_and_answers(answerer_factory):
    llm = ScriptedLLM(
        tool_replies=[
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "calculate", "arguments": json.dumps({"expression": "28703 + 178353"})}},
            ]},
            {"role": "assistant", "content": "Together they sold 207,056 [1]."},
        ],
    )
    result = answerer_factory(llm).answer("japan and americas combined", AnswerOptions(rerank=False, correct=False, verify=False, agent=True))
    assert result["answer"] == "Together they sold 207,056 [1]."
    assert result["steps"][0]["name"] == "calculate" and result["steps"][0]["result"] == "207,056"
    # The tool result went back to the model
    second_call = llm.calls[1][1]
    assert any(m.get("role") == "tool" and m["content"] == "207,056" for m in second_call)


def test_agent_search_adds_numbered_sources(answerer_factory):
    llm = ScriptedLLM(tool_replies=[
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "s1", "type": "function", "function": {"name": "search_documents", "arguments": json.dumps({"query": "VPN"})}},
        ]},
        {"role": "assistant", "content": "Use the VPN [2]."},
    ])
    result = answerer_factory(llm).answer("tariffs", AnswerOptions(top_k=1, rerank=False, correct=False, verify=False, agent=True))
    added = result["sources"][1:]
    assert added and [x["ref"] for x in added] == list(range(2, 2 + len(added)))
    assert any("VPN" in x["text"] for x in added)
    assert result["steps"][0]["refs"] == [x["ref"] for x in added]


class AxisEmbedder:
    """'zzz' points one way, everything else another: a query that matches nothing, then one that matches."""
    dimension = 2

    def embed(self, texts):
        return [[1.0, 0.0] if "zzz" in t else [0.0, 1.0] for t in texts]


def test_corrective_search_rewrites_weak_queries():
    db = RAGVectorDB(url=":memory:", collection="c", embedder=AxisEmbedder())
    db.add_texts(["Laptops must use the VPN on public networks."], metadata=[{"source_file": "p.md", "chunk_index": 0}])
    asked = []

    def rewriter(q):
        asked.append(q)
        return "VPN rule"

    out = Retriever(db).retrieve("zzz qqq", top_k=1, rerank=False, mode="dense", rewriter=rewriter)
    assert asked == ["zzz qqq"]
    assert out["correction"]["query"] == "VPN rule"
    assert out["correction"]["improved"] and out["results"][0]["payload"]["source_file"] == "p.md"


def test_strong_queries_are_not_rewritten():
    db = RAGVectorDB(url=":memory:", collection="d", embedder=FakeEmbedder())
    db.add_texts(["New tariffs were announced."], metadata=[{"source_file": "t.txt", "chunk_index": 0}])
    out = Retriever(db).retrieve("tariffs", top_k=1, rerank=False, rewriter=lambda q: pytest.fail("should not rewrite"))
    assert out["correction"] is None


# ---------------------------------------------------------------- contextual retrieval
def test_document_title_and_contexts():
    text = "Source: Apple Inc. Annual Report on Form 10-K\n\nItem 7\n\nJapan net sales increased."
    assert document_title(text, "x.txt") == "Apple Inc. Annual Report on Form 10-K"
    chunks = [{"metadata": {"section": "Japan"}}, {"metadata": {"section": ""}}]
    contexts = build_contexts(chunks, text, "x.txt", "header")
    assert contexts == ["Apple Inc. Annual Report on Form 10-K | Section: Japan", "Apple Inc. Annual Report on Form 10-K"]
    assert build_contexts(chunks, text, "x.txt", "off") == ["", ""]
    assert with_context("body", "ctx") == "ctx\n\nbody" and with_context("body", "") == "body"


def test_llm_context_mode_summarises_once_per_document():
    calls = []
    contexts = build_contexts([{"metadata": {}}] * 3, "Doc", "d.md", "llm", lambda t: calls.append(t) or "A policy.")
    assert len(calls) == 1 and all("A policy." in c for c in contexts)


def test_index_texts_are_searched_but_text_is_stored():
    db = RAGVectorDB(url=":memory:", collection="e", embedder=FakeEmbedder())
    db.add_texts(["Revenue grew."], metadata=[{"source_file": "r.txt", "chunk_index": 0}], index_texts=["VPN handbook\n\nRevenue grew."])
    hit = db.similarity_search("VPN", top_k=1, mode="keyword")[0]
    assert hit["payload"]["text"] == "Revenue grew."


def test_cited_line_keeps_the_uncited_line_above_it():
    claims = extract_claims("- Fastest-growing segment in 2025: Japan\n- Growth rate: 15% year-over-year [1].")
    assert len(claims) == 1 and "Japan" in claims[0]["text"] and "15%" in claims[0]["text"]
