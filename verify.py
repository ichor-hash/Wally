"""
Answer verification (Self-RAG style): check every cited claim against the
chunks it cites, and revise the answer when a claim is not supported.

The grounding label says whether retrieval found relevant text. It cannot say
whether the answer then used that text faithfully: a model can cite the right
chunk and still misread a number. Verification closes that gap with one extra
LLM call that sees each claim next to only the chunks it cites.

    SUPPORTED     every fact in the claim is in, or follows arithmetically from, the cited chunks
    PARTIAL       the main point is supported, a detail is not
    UNSUPPORTED   the cited chunks do not say this, or contradict it
"""
import json
import re
from typing import Any, Dict, List, Optional, Tuple

CITE = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]|【(\d+)[^】]*】")
FENCE = re.compile(r"```.*?(```|$)", re.S)
VERDICTS = ("SUPPORTED", "PARTIAL", "UNSUPPORTED")
MAX_CLAIMS = 12

VERIFY_SYSTEM = (
    "You are a strict fact-checker. For each numbered claim, compare it ONLY with the source passages it cites.\n"
    "SUPPORTED: every fact in the claim (numbers, names, dates, direction of change) is stated in the cited passages, "
    "or follows from them by correct arithmetic.\n"
    "PARTIAL: the main point is supported but some detail is not.\n"
    "UNSUPPORTED: the cited passages do not state it, or contradict it.\n"
    'Reply with JSON only: {"claims": [{"id": 1, "verdict": "SUPPORTED", "reason": "short reason"}]}'
)

REVISE_INSTRUCTION = (
    "A fact-check of your answer against the cited chunks found problems:\n{problems}\n\n"
    "Rewrite the answer so that every claim is supported by the chunks: correct or remove the problem claims, "
    "keep everything that was fine, and keep the [n] citations. Return only the revised answer."
)


def _refs(text: str) -> List[int]:
    refs = []
    for m in CITE.finditer(text):
        group = m.group(1) or m.group(2)
        for part in re.split(r"\s*,\s*", group):
            if re.search(r"[–-]", part):
                a, b = [int(x) for x in re.split(r"\s*[–-]\s*", part)]
                refs.extend(range(a, b + 1))
            else:
                refs.append(int(part))
    return sorted(set(refs))


def _clean(text: str) -> str:
    text = CITE.sub("", text)
    text = re.sub(r"[*_`#>|]", "", text)
    return " ".join(text.split()).strip(" -•:")


def extract_claims(answer: str) -> List[Dict[str, Any]]:
    """
    Sentences and list items that carry citations.

    Models often cite a whole block once, e.g. eight bullet points and then "[1]"
    on its own line. A citation-only line therefore covers the uncited lines
    since the previous claim, as one claim; with nothing uncited before it, it
    adds its references to the previous claim.
    """
    body = FENCE.sub("", answer)
    pieces: List[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line or re.fullmatch(r"\|?[\s:|-]+\|?", line):
            continue
        pieces.extend(p for p in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9*\"(])", line) if p.strip())

    claims: List[Dict[str, Any]] = []
    pending: List[str] = []  # uncited text since the last claim
    for piece in pieces:
        refs = _refs(piece)
        text = _clean(piece)
        if not refs:
            if text:
                pending.append(text)
            continue
        if len(text) < 8:  # "[1][2]" on its own line
            if pending:
                claims.append({"id": len(claims) + 1, "text": "; ".join(pending)[:400], "refs": refs})
            elif claims:
                claims[-1]["refs"] = sorted(set(claims[-1]["refs"]) | set(refs))
        else:
            # Uncited lines just above a cited one are its context: "Fastest-growing segment: Japan"
            # followed by "Growth rate: 15% [1]" is one claim, not a bare "15%".
            lead = "; ".join(pending[-2:])
            claim = f"{lead}; {text}" if lead and len(lead) < 200 else text
            claims.append({"id": len(claims) + 1, "text": claim[:400], "refs": refs})
        pending = []
    return claims[:MAX_CLAIMS]


def _parse(raw: str) -> Dict[int, Tuple[str, str]]:
    start, end = raw.find("{"), raw.rfind("}")
    data = json.loads(raw[start:end + 1])
    out = {}
    for item in data.get("claims", []):
        verdict = str(item.get("verdict", "")).upper().strip()
        if verdict in VERDICTS:
            out[int(item["id"])] = (verdict, str(item.get("reason", ""))[:200])
    return out


def summarize(claims: List[Dict[str, Any]], status: str = "ok", error: Optional[str] = None) -> Dict[str, Any]:
    counts = {v: sum(1 for c in claims if c.get("verdict") == v) for v in VERDICTS}
    total = len(claims)
    score = (counts["SUPPORTED"] + 0.5 * counts["PARTIAL"]) / total if total else None
    return {
        "status": status, "error": error, "claims": claims, "total": total,
        "supported": counts["SUPPORTED"], "partial": counts["PARTIAL"], "unsupported": counts["UNSUPPORTED"],
        "score": round(score, 3) if score is not None else None,
    }


def verify_answer(llm, answer: str, sources: List[Dict[str, Any]], max_tokens: int = 1024) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """Returns (verification, token usage). Never raises: failures come back as status 'error'."""
    claims = extract_claims(answer)
    if not claims:
        return summarize([], status="no_claims"), {}
    by_ref = {s["ref"]: s for s in sources}
    cited = sorted({r for c in claims for r in c["refs"] if r in by_ref})
    passages = "\n\n".join(f"[{r}] {by_ref[r]['text']}" for r in cited)
    listed = "\n".join(f"{c['id']}. {c['text']} (cites {', '.join(f'[{r}]' for r in c['refs'])})" for c in claims)
    messages = [
        {"role": "system", "content": VERIFY_SYSTEM},
        {"role": "user", "content": f"Source passages:\n{passages}\n\nClaims:\n{listed}"},
    ]
    try:
        raw, usage = llm.chat_with_usage(messages, temperature=0.0, max_tokens=max_tokens)
        verdicts = _parse(raw)
    except Exception as e:  # network, rate limit, malformed JSON
        return summarize(claims, status="error", error=str(e)[:200]), {}
    for c in claims:
        verdict, reason = verdicts.get(c["id"], ("PARTIAL", "The checker returned no verdict for this claim."))
        if any(r not in by_ref for r in c["refs"]):
            verdict, reason = "UNSUPPORTED", "Cites a chunk number that does not exist."
        c["verdict"], c["reason"] = verdict, reason
    return summarize(claims), usage


def problems_for(verification: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [c for c in verification.get("claims", []) if c.get("verdict") == "UNSUPPORTED"]


def revision_messages(messages: List[dict], answer: str, problems: List[Dict[str, Any]]) -> List[dict]:
    listed = "\n".join(f"- \"{c['text']}\": {c['reason']}" for c in problems)
    return messages + [
        {"role": "assistant", "content": answer},
        {"role": "user", "content": REVISE_INSTRUCTION.format(problems=listed)},
    ]
