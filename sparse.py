"""
BM25 sparse vectors for the keyword half of hybrid retrieval.

Dense embeddings match meaning but blur exact terms: "ASU 2025-06", "Section 232",
a product code, a surname. BM25 matches those tokens literally. Ethan stores one
sparse vector per chunk next to the dense one and lets Qdrant apply the IDF part
(`Modifier.IDF` on the collection), so no corpus statistics live in this process
and nothing needs refitting when documents are added or removed.

Document side: saturated term frequency with length normalisation.
Query side:    1.0 per distinct term.
Qdrant:        multiplies by IDF and takes the dot product = BM25.

No model, no download, no extra dependency: about 20 microseconds per chunk.
"""
import re
import zlib
from collections import Counter
from typing import Dict, List, Tuple

TOKEN = re.compile(r"[a-z0-9]+(?:[-'’.][a-z0-9]+)*")

# Small on purpose: IDF already down-weights common words; this only keeps
# pure function words from inflating the postings lists.
STOPWORDS = frozenset(
    "a an and are as at be been but by can could did do does for from had has have how if in into is it its "
    "of on or so than that the their them then there these they this to was were what when where which who why "
    "will with would you your our we i me my".split()
)

K1 = 1.2
B = 0.75
AVG_TOKENS = 64  # typical chunk at the default 512-character size, after stopword removal


def tokenize(text: str) -> List[str]:
    """Lowercase word tokens. Keeps internal hyphens/dots so `2025-06` and `10-k` stay whole."""
    tokens = []
    for tok in TOKEN.findall(text.lower()):
        if tok in STOPWORDS:
            continue
        tokens.append(tok)
        # Also index the parts of compound tokens, so "10-k" matches "10 k" and "k"
        if any(c in tok for c in "-'’."):
            tokens.extend(p for p in re.split(r"[-'’.]", tok) if len(p) > 1 and p not in STOPWORDS)
    return tokens


def _index(token: str) -> int:
    """Stable 32-bit id for a token (Python's hash() is salted per process)."""
    return zlib.crc32(token.encode("utf-8"))


def _to_vector(weights: Dict[int, float]) -> Tuple[List[int], List[float]]:
    items = sorted(weights.items())
    return [i for i, _ in items], [v for _, v in items]


def encode_document(text: str) -> Tuple[List[int], List[float]]:
    """(indices, values) for a chunk: BM25 term-frequency component, IDF applied by Qdrant."""
    tokens = tokenize(text)
    if not tokens:
        return [], []
    norm = K1 * (1 - B + B * len(tokens) / AVG_TOKENS)
    weights: Dict[int, float] = {}
    for token, tf in Counter(tokens).items():
        weights[_index(token)] = tf * (K1 + 1) / (tf + norm)
    return _to_vector(weights)


def encode_query(text: str) -> Tuple[List[int], List[float]]:
    """(indices, values) for a query: each distinct term counts once."""
    return _to_vector({_index(t): 1.0 for t in set(tokenize(text))})
