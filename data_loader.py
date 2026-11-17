"""
Document loading and chunking (PDF, TXT, Markdown) with pypdf, no framework.

Two chunking strategies:

- "structure" (default): split on blank lines, keep each table together with its
  caption, keep a heading with the text under it, and pack paragraphs up to the
  chunk size. Long paragraphs fall back to sentence-aware splitting.
- "fixed": the original sliding window of chunk_size characters with overlap.

Structure-aware chunking exists because of a measured failure: a fixed window cut
Apple's segment table in half, the model saw two of five rows and answered
confidently and wrongly. See docs/EVALUATION.md.
"""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

TEXT_SUFFIXES = (".txt", ".md", ".markdown", ".text")
MIN_CHUNK_CHARS = 120
TABLE_MAX_FACTOR = 4  # a table may grow to this many chunk sizes before it is split by rows


def _is_row(block: str) -> bool:
    return " | " in block or block.lstrip().startswith("|")


def _is_heading(block: str) -> bool:
    """A short single line without sentence punctuation: 'Gross Margin', '## Equipment'."""
    if "\n" in block or len(block) > 90:
        return False
    if block.startswith("#"):
        return True
    if re.match(r"\s*([•\-*–]|\d+[.)])\s*\S", block):  # a list item, not a heading
        return False
    return not re.search(r"[.!?:;,]$", block)


def _inline_heading(line: str, previous: str) -> bool:
    """
    A heading inside a block of text, as PDFs produce: no blank line around it.
    Short, starts with a capital or a number, no sentence punctuation at the end,
    and the line before it (if any) finished a sentence. Wrapped sentence lines
    rarely pass all four tests.
    """
    line = line.strip()
    if not line or len(line) > 80 or not _is_heading(line) or _is_row(line):
        return False
    if not (line[0].isupper() or line[0].isdigit() or line.startswith("#")):
        return False
    if len(line.split()) > 10:
        return False
    return not previous or bool(re.search(r"[.!?:;]$|^#", previous.strip()))


def _split_inline_headings(block: str) -> List[str]:
    """Split a block wherever a heading line sits inside it, keeping the heading as its own block."""
    lines = block.split("\n")
    if len(lines) < 2:
        return [block]
    out: List[str] = []
    current: List[str] = []
    for i, line in enumerate(lines):
        previous = lines[i - 1] if i else ""
        has_body_after = i + 1 < len(lines)
        if has_body_after and _inline_heading(line, previous):
            if current:
                out.append("\n".join(current).strip())
            out.append(line.strip())
            current = []
        else:
            current.append(line)
    if current:
        out.append("\n".join(current).strip())
    return [b for b in out if b]


class DocumentLoader:
    """Loads PDF and text files and chunks them. Supports .pdf, .txt, .md"""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50, sentence_splitter: bool = True, strategy: str = "structure"):
        if strategy not in ("structure", "fixed"):
            raise ValueError("strategy must be 'structure' or 'fixed'")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.sentence_splitter = sentence_splitter
        self.strategy = strategy

    # ---------------- loading ----------------
    def load_text_file(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Text file not found: {file_path}")
        return path.read_text(encoding="utf-8")

    def load_pdf(self, file_path: str) -> str:
        if PdfReader is None:
            raise ImportError("pypdf not installed. Run: pip install pypdf")
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")
        pages = (page.extract_text() for page in PdfReader(str(path)).pages)
        return "\n\n".join(text for text in pages if text)

    def file_title(self, file_path: str) -> str:
        """The document's own title when the file declares one (PDF metadata), else ''."""
        if Path(file_path).suffix.lower() != ".pdf" or PdfReader is None:
            return ""
        try:
            meta = PdfReader(str(file_path)).metadata
            title = (meta.title if meta else "") or ""
            return title.strip() if len(title.strip()) >= 4 and not title.lower().startswith(("microsoft word", "untitled")) else ""
        except Exception:
            return ""

    def load_file(self, file_path: str) -> str:
        suffix = Path(file_path).suffix.lower()
        if suffix == ".pdf":
            return self.load_pdf(file_path)
        if suffix in TEXT_SUFFIXES:
            return self.load_text_file(file_path)
        raise ValueError(f"Unsupported file type: {suffix}. Supported: .pdf, .txt, .md")

    # ---------------- chunking ----------------
    def chunk_text(self, text: str) -> List[str]:
        """Sliding window of chunk_size characters with overlap, ending on sentence boundaries."""
        if not text:
            return []
        chunks, start, text_len = [], 0, len(text)
        while start < text_len:
            end = start + self.chunk_size
            if self.sentence_splitter and end < text_len:
                search_start = max(start, end - 100)
                portion = text[search_start:min(text_len, end + 100)]
                sentence_ends = [m.end() for m in re.finditer(r"[.!?]\s+", portion)]
                if sentence_ends:
                    end = search_start + sentence_ends[-1]
                else:
                    space = text.rfind(" ", start + 1, end)  # never cut inside a word
                    if space > start:
                        end = space + 1
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= text_len:
                break
            next_start = end - self.chunk_overlap
            if next_start > start:
                space = text.find(" ", next_start, end)  # start the overlap on a word boundary
                start = space + 1 if space != -1 else next_start
            else:
                start = end  # always move forward
        return chunks

    def _blocks(self, text: str) -> List[Dict[str, Any]]:
        """Split into paragraphs, merging table rows (and their caption) into single blocks."""
        raw = []
        for b in re.split(r"\n\s*\n", text.replace("\r", "")):
            b = b.strip()
            if b:
                # Tables keep their rows together; prose blocks may hide headings (PDFs)
                raw.extend([b] if _is_row(b) else _split_inline_headings(b))
        blocks: List[Dict[str, Any]] = []
        i = 0
        while i < len(raw):
            if not _is_row(raw[i]):
                blocks.append({"text": raw[i], "kind": "heading" if _is_heading(raw[i]) else "text"})
                i += 1
                continue
            rows = []
            while i < len(raw):
                # Short label lines inside a table ("Gross margin:") stay with it
                label = len(raw[i]) < 60 and i + 1 < len(raw) and _is_row(raw[i + 1])
                if not (_is_row(raw[i]) or label):
                    break
                rows.append(raw[i])
                i += 1
            caption = ""
            if blocks and blocks[-1]["kind"] == "text" and blocks[-1]["text"].endswith(":") and len(blocks[-1]["text"]) < 300:
                caption = blocks.pop()["text"]
            blocks.append({"text": "\n".join(([caption] if caption else []) + rows), "kind": "table", "caption": caption, "rows": rows})
        return blocks

    def chunk_structured(self, text: str) -> List[Dict[str, Any]]:
        """Structure-aware chunks: [{"text", "section", "kind"}]."""
        chunks: List[Dict[str, Any]] = []
        buffer: List[str] = []
        section = ""
        buffer_section = ""

        def flush():
            nonlocal buffer
            if buffer:
                chunks.append({"text": "\n\n".join(buffer), "section": buffer_section, "kind": "text"})
                buffer = []

        blocks = self._blocks(text)
        for idx, block in enumerate(blocks):
            body = block["text"]
            if block["kind"] == "heading":
                # A heading starts a new chunk and travels with what follows.
                # Stacked headings (section, then sub-section) stay together.
                if not (buffer and all(_is_heading(b) for b in buffer)):
                    flush()
                section = body.lstrip("# ").strip()
                buffer, buffer_section = buffer + [body], section
                continue

            if block["kind"] == "table":
                heading = buffer if buffer and all(_is_heading(b) for b in buffer) else []
                if not heading:
                    flush()
                prefix = "\n\n".join(heading)
                buffer = []
                if len(body) <= self.chunk_size * TABLE_MAX_FACTOR:
                    pieces = [body]
                else:
                    # Oversized table: split by rows, repeating the caption so every piece is self-describing
                    pieces, current = [], [block["caption"]] if block["caption"] else []
                    for row in block["rows"]:
                        if current and sum(len(r) + 1 for r in current) + len(row) > self.chunk_size * 2:
                            pieces.append("\n".join(current))
                            current = [block["caption"]] if block["caption"] else []
                        current.append(row)
                    pieces.append("\n".join(current))
                for n, piece in enumerate(pieces):
                    chunks.append({"text": f"{prefix}\n\n{piece}" if prefix and n == 0 else piece, "section": section, "kind": "table"})
                continue

            if len(body) > self.chunk_size:
                heading = buffer if buffer and all(_is_heading(b) for b in buffer) else []
                if not heading:
                    flush()
                buffer = []
                for n, piece in enumerate(self.chunk_text(body)):
                    lead = "\n\n".join(heading) + "\n\n" if heading and n == 0 else ""
                    chunks.append({"text": lead + piece, "section": section, "kind": "text"})
                continue

            if buffer and sum(len(b) + 2 for b in buffer) + len(body) > self.chunk_size:
                # A trailing label ("Fourth Quarter 2025:") belongs with the list it introduces
                label = buffer.pop() if len(buffer) > 1 and buffer[-1].endswith(":") and len(buffer[-1]) < 80 else None
                flush()
                if label:
                    buffer, buffer_section = [label], section
            if not buffer:
                buffer_section = section
            buffer.append(body)
        flush()

        # Fold fragments too small to mean anything on their own into a neighbour
        merged: List[Dict[str, Any]] = []
        for c in chunks:
            if not c["text"].strip():
                continue
            prev = merged[-1] if merged else None
            # A very short section (under MIN_CHUNK_CHARS) joins its neighbour; its heading
            # text stays in the chunk, so it is still found by keyword and meaning search.
            small = prev and min(len(prev["text"]), len(c["text"])) < MIN_CHUNK_CHARS
            if small and prev["kind"] == c["kind"] == "text" and len(prev["text"]) + len(c["text"]) <= self.chunk_size * 1.5:
                prev["text"] += "\n\n" + c["text"]
            else:
                merged.append(c)
        return merged

    def chunk(self, text: str) -> List[Dict[str, Any]]:
        if self.strategy == "structure":
            return self.chunk_structured(text)
        return [{"text": t, "section": "", "kind": "text"} for t in self.chunk_text(text)]

    # ---------------- load + chunk ----------------
    def _chunks_for(self, path: Path) -> List[Dict[str, Any]]:
        return [
            {
                "text": c["text"],
                "metadata": {
                    "source_file": path.name,
                    "file_type": path.suffix,
                    "chunk_index": i,
                    "section": c["section"],
                    "kind": c["kind"],
                },
            }
            for i, c in enumerate(self.chunk(self.load_file(str(path))))
        ]

    def load_and_chunk(self, file_path: Optional[str] = None, directory: Optional[str] = None, glob_pattern: str = "*.*") -> List[Dict[str, Any]]:
        """Load one file or every supported file in a directory. Returns [{"text", "metadata"}]."""
        if file_path:
            return self._chunks_for(Path(file_path))
        if not directory:
            raise ValueError("Either file_path or directory must be provided")
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        results: List[Dict[str, Any]] = []
        for path in sorted(dir_path.glob(glob_pattern)):
            if path.is_dir():
                continue
            try:
                results.extend(self._chunks_for(path))
            except Exception as e:
                print(f"Skipping {path.name}: {e}")
        return results

    def load_and_chunk_with_metadata(
        self,
        file_path: Optional[str] = None,
        directory: Optional[str] = None,
        glob_pattern: str = "*.*",
        file_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        results = self.load_and_chunk(file_path=file_path, directory=directory, glob_pattern=glob_pattern)
        for result in results:
            result["metadata"].update(file_metadata or {})
        return results


# Old names, kept so existing scripts keep working
PDFDataLoader = DocumentLoader


def load_documents(source: str, chunk_size: int = 512, chunk_overlap: int = 50, is_directory: bool = False, glob_pattern: str = "*.*") -> List[Dict[str, Any]]:
    """Quick helper: load_documents("policy.pdf") or load_documents("./docs", is_directory=True)."""
    loader = DocumentLoader(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if is_directory:
        return loader.load_and_chunk_with_metadata(directory=source, glob_pattern=glob_pattern)
    return loader.load_and_chunk_with_metadata(file_path=source)


load_pdfs = load_documents


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        chunks = load_documents(sys.argv[1], is_directory=len(sys.argv) > 2 and sys.argv[2] == "--dir")
        print(f"Loaded {len(chunks)} chunks")
        for i, chunk in enumerate(chunks[:3]):
            print(f"\n--- Chunk {i} ({chunk['metadata']['kind']}, {len(chunk['text'])} chars) ---\n{chunk['text'][:300]}")
    else:
        print("Usage: python data_loader.py <file_or_directory> [--dir]")
