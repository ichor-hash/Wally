"""Fast unit tests: no model downloads, no LLM, no Qdrant server."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sparse  # noqa: E402
from costs import AnswerCache, Pricing  # noqa: E402
from data_loader import DocumentLoader  # noqa: E402
from pipeline import trim_to_budget  # noqa: E402
from vector_db import RAGVectorDB, rrf_fuse  # noqa: E402


# ---------------------------------------------------------------- BM25
def test_tokenize_keeps_identifiers_whole_and_split():
    tokens = sparse.tokenize("ASU 2025-06 and the Form 10-K")
    assert "2025-06" in tokens and "10-k" in tokens
    assert "2025" in tokens and "06" in tokens  # parts are indexed too
    assert "the" not in tokens and "and" not in tokens


def test_token_ids_are_stable_across_processes():
    # Python's hash() is salted per process; the sparse index must not be
    import zlib
    assert sparse.encode_query("tariffs")[0] == [zlib.crc32(b"tariffs")]
    assert sparse.encode_query("tariffs") == sparse.encode_query("Tariffs")


def test_document_weights_saturate():
    _, once = sparse.encode_document("tariff")
    _, many = sparse.encode_document(" ".join(["tariff"] * 20))
    assert many[0] > once[0]
    assert many[0] < (sparse.K1 + 1) * 1.01  # BM25 term frequency is bounded by k1 + 1


def test_empty_text_gives_empty_vector():
    assert sparse.encode_document("the and of") == ([], [])


# ---------------------------------------------------------------- fusion
def test_rrf_rewards_agreement():
    fused = rrf_fuse({"dense": ["a", "b", "c"], "keyword": ["c", "a", "d"]})
    assert max(fused, key=fused.get) == "a"  # ranked 1st and 2nd beats 3rd and 1st
    assert fused["d"] < fused["c"]


# ---------------------------------------------------------------- chunking
TABLE_DOC = """Segment Operating Performance

The following table shows net sales by reportable segment for 2025, 2024 and 2023 (dollars in millions):

2025 | Change | 2024

Americas | $ | 178,353 | 7 | %

Europe | 111,032 | 10 | %

Japan | 28,703 | 15 | %

Total net sales | $ | 416,161 | 6 | %

Americas

Americas net sales increased during 2025 compared to 2024 primarily due to higher net sales of iPhone and Services.
"""


def test_structure_chunking_keeps_table_with_caption_and_heading():
    chunks = DocumentLoader(chunk_size=200).chunk_structured(TABLE_DOC)
    tables = [c for c in chunks if c["kind"] == "table"]
    assert len(tables) == 1
    table = tables[0]["text"]
    assert "Segment Operating Performance" in table
    assert "reportable segment" in table
    assert "178,353" in table and "28,703" in table and "416,161" in table


def test_fixed_chunking_splits_the_same_table():
    # The v2 failure this release fixes: a 200-char window cuts the table apart
    chunks = DocumentLoader(chunk_size=200, strategy="fixed").chunk(TABLE_DOC)
    # The caption says what the numbers are; the Japan row holds the answer. They end up apart.
    assert not any("reportable segment" in c["text"] and "28,703" in c["text"] for c in chunks)


def test_fixed_chunking_never_cuts_words():
    text = " ".join(f"word{i}" for i in range(400))
    for chunk in DocumentLoader(chunk_size=100, chunk_overlap=20, strategy="fixed").chunk_text(text):
        for token in chunk.split():
            assert token.startswith("word") and token[4:].isdigit()


def test_tiny_fragments_are_merged():
    text = "Intro\n\nShort line.\n\nAnother short line.\n\n" + "A long paragraph. " * 20
    chunks = DocumentLoader(chunk_size=512).chunk_structured(text)
    assert all(len(c["text"]) >= 30 for c in chunks)


def test_rejects_unknown_strategy():
    with pytest.raises(ValueError):
        DocumentLoader(strategy="semantic")


# ---------------------------------------------------------------- costs
def test_pricing():
    p = Pricing(input_per_m=0.10, output_per_m=0.50)
    assert p.configured
    assert p.cost(1_000_000, 0) == pytest.approx(0.10)
    assert p.cost(800, 200) == pytest.approx(0.00018)
    assert not Pricing(0, 0).configured


def test_answer_cache_lru_and_ttl(monkeypatch):
    cache = AnswerCache(max_entries=2, ttl_seconds=10)
    cache.put("a", {"v": 1})
    cache.put("b", {"v": 2})
    assert cache.get("a") == {"v": 1}
    cache.put("c", {"v": 3})  # evicts b, the least recently used
    assert cache.get("b") is None and cache.get("c") == {"v": 3}

    import costs
    now = costs.time.time()
    monkeypatch.setattr(costs.time, "time", lambda: now + 11)
    assert cache.get("a") is None  # expired
    assert cache.stats()["hits"] == 2


def test_cache_key_changes_with_index_version():
    assert AnswerCache.key(q="x", index=1) != AnswerCache.key(q="x", index=2)
    assert AnswerCache.key(q="x", index=1) == AnswerCache.key(index=1, q="x")


def test_disabled_cache_stores_nothing():
    cache = AnswerCache(ttl_seconds=0)
    cache.put("a", {"v": 1})
    assert cache.get("a") is None


def test_trim_to_budget_keeps_best_chunk():
    results = [{"payload": {"text": "x" * 600}}, {"payload": {"text": "y" * 600}}, {"payload": {"text": "z" * 10}}]
    assert len(trim_to_budget(results, 1000)) == 1
    assert len(trim_to_budget(results, 100)) == 1  # never empty
    assert len(trim_to_budget(results, 5000)) == 3


# ---------------------------------------------------------------- hybrid search, end to end
class FakeEmbedder:
    """Deterministic 4-d 'embeddings' so the test needs no model download."""
    dimension = 4
    TOPICS = ("tariff", "dividend", "vpn", "japan")

    def embed(self, texts):
        out = []
        for t in texts:
            low = t.lower()
            v = [float(low.count(w)) for w in self.TOPICS]
            out.append(v if any(v) else [0.1, 0.1, 0.1, 0.1])
        return out


@pytest.fixture
def db():
    db = RAGVectorDB(url=":memory:", collection="t", embedder=FakeEmbedder())
    db.add_texts(
        [
            "New tariffs were announced on imports.",
            "The quarterly dividend was raised.",
            "Laptops must use the VPN on public networks.",
            "ASU 2025-06 will be effective in 2029.",
        ],
        metadata=[{"source_file": f"doc{i}.txt", "chunk_index": i} for i in range(4)],
    )
    return db


def test_keyword_search_finds_exact_identifier(db):
    results = db.similarity_search("ASU 2025-06", top_k=2, mode="keyword")
    assert results[0]["payload"]["source_file"] == "doc3.txt"
    assert results[0]["matched_by"] == "keyword"


def test_hybrid_reports_how_each_chunk_was_found(db):
    results = db.similarity_search("tariffs on imports", top_k=4, mode="hybrid")
    top = results[0]
    assert top["payload"]["source_file"] == "doc0.txt"
    assert top["matched_by"] == "both"
    assert 0.0 <= top["score"] <= 1.0 and top["keyword_score"] > 0


def test_keyword_only_hits_still_get_a_cosine_score(db):
    results = db.similarity_search("ASU 2025-06", top_k=4, mode="hybrid")
    asu = next(r for r in results if r["payload"]["source_file"] == "doc3.txt")
    assert asu["vector_score"] is not None


def test_writes_bump_version_and_stats(db):
    v = db.version
    assert db.stats() == {"documents": 4, "chunks": 4}
    assert db.delete_by_source("doc0.txt") == 1
    assert db.version > v
    assert db.stats() == {"documents": 3, "chunks": 3}


def test_unknown_mode_is_rejected(db):
    with pytest.raises(ValueError):
        db.similarity_search("x", mode="semantic")
