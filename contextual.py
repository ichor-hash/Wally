"""
Contextual retrieval: index each chunk together with where it comes from.

A chunk like "Japan net sales increased during 2025 ... iPhone, Services and iPad"
never says it is from Apple's annual report, or which section it sits in. The
embedding and keyword index only see what is in the chunk. Prefixing a short
context ("Apple Inc. Annual Report on Form 10-K ... > Segment Operating
Performance") gives both indexes that missing signal.

The prefix is used for indexing and reranking only. The stored and displayed
chunk text, and what the LLM is shown as a source, stay exactly as written.

Modes (CONTEXTUAL_RETRIEVAL):
- "off"     no prefix
- "header"  document title + section heading. Free, deterministic. (default)
- "llm"     header + a two-sentence document summary written by the LLM,
            one call per document (not per chunk), so it stays cheap.

The "llm" mode is a lighter take on Anthropic's contextual retrieval, which
writes a context per chunk with the full document in the prompt; that costs
one long LLM call per chunk.
"""
import re
from pathlib import Path
from typing import Callable, List, Optional

MODES = ("off", "header", "llm")
TITLE_CHARS = 120

SUMMARY_PROMPT = (
    "Summarise what this document is and what it covers in at most two short sentences, "
    "naming the organisation, document type and period if stated. Plain text only.\n\n"
)


def document_title(text: str, filename: str) -> str:
    """First meaningful line of the document, else the file name."""
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if len(line) >= 4:
            line = re.sub(r"^(source|title)\s*:\s*", "", line, flags=re.I)
            if len(line) > TITLE_CHARS:
                line = line[:TITLE_CHARS].rsplit(" ", 1)[0] + "…"
            return line
    return Path(filename).stem.replace("-", " ").replace("_", " ")


def summarize_document(text: str, llm, max_chars: int = 6000) -> str:
    """One LLM call per document. Returns '' on failure so ingestion never breaks."""
    try:
        summary, _ = llm.chat_with_usage(
            [{"role": "user", "content": SUMMARY_PROMPT + text[:max_chars]}], temperature=0.0, max_tokens=300
        )
        return " ".join(summary.split())[:400]
    except Exception:
        return ""


def build_contexts(
    chunks: List[dict],
    full_text: str,
    filename: str,
    mode: str = "header",
    summarizer: Optional[Callable[[str], str]] = None,
    title: Optional[str] = None,
) -> List[str]:
    """
    One context string per chunk ('' when mode is off). Works for any uploaded
    file: `title` is the file's declared title (PDF metadata) when it has one,
    otherwise the first meaningful line, otherwise the file name.
    """
    if mode not in MODES:
        raise ValueError(f"CONTEXTUAL_RETRIEVAL must be one of {MODES}")
    if mode == "off":
        return ["" for _ in chunks]
    title = (title or "").strip() or document_title(full_text, filename)
    summary = summarizer(full_text) if mode == "llm" and summarizer else ""
    contexts = []
    for chunk in chunks:
        section = (chunk.get("metadata", {}).get("section") or "").strip()
        parts = [title]
        if summary:
            parts.append(summary)
        if section and section.lower() not in title.lower():
            parts.append(f"Section: {section}")
        contexts.append(" | ".join(parts))
    return contexts


def with_context(text: str, context: str) -> str:
    return f"{context}\n\n{text}" if context else text
