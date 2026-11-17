"""
Add contextual headers to documents that are already in the library.

New uploads get them automatically (contextual.py). Documents uploaded before
contextual retrieval existed have chunks indexed without their document title
and section. This rebuilds the context from what is stored, re-embeds each
chunk with it and updates the vectors in place. The original files are not
needed, chunk ids and payloads are kept, and the shown chunk text is unchanged.

    python scripts/reindex_context.py              every document missing a context
    python scripts/reindex_context.py --all        every document, e.g. after changing the format
    python scripts/reindex_context.py --dry-run    show what would change

Stop the API first when using embedded Qdrant (QDRANT_PATH): only one process
can open it. Reads the same .env as the API.
"""
import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from qdrant_client import models as qm  # noqa: E402

import sparse  # noqa: E402
from contextual import build_contexts, with_context  # noqa: E402
from vector_db import DENSE, SPARSE, RAGVectorDB  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="re-index documents that already have a context too")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    mode = os.getenv("CONTEXTUAL_RETRIEVAL", "header").strip().lower()
    if mode == "off":
        sys.exit("CONTEXTUAL_RETRIEVAL is off; nothing to do.")
    if mode == "llm":
        print("Note: rebuilding with title + section only; re-upload a file to add an LLM summary.")

    db = RAGVectorDB(
        url=os.getenv("QDRANT_URL", "http://localhost:6333"), path=os.getenv("QDRANT_PATH", "").strip() or None,
        api_key=os.getenv("QDRANT_API_KEY"), collection=os.getenv("QDRANT_COLLECTION", "ethan_docs"),
        embed_model=os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
    )
    if db.legacy:
        sys.exit("This collection has no BM25 vectors yet. Run scripts/migrate_collection.py first.")

    documents = defaultdict(list)
    for point in db.scroll_all():
        documents[(point.payload or {}).get("source_file", "Unknown")].append(point)

    updated = 0
    for name, points in sorted(documents.items()):
        if not args.all and all((p.payload or {}).get("context") for p in points):
            continue
        points.sort(key=lambda p: (p.payload or {}).get("chunk_index", 0))
        texts = [(p.payload or {}).get("text", "") for p in points]
        chunks = [{"metadata": {"section": (p.payload or {}).get("section", "")}} for p in points]
        # The first chunks stand in for the document's opening lines, where the title usually is
        contexts = build_contexts(chunks, "\n\n".join(texts[:3]), name, "header")
        print(f"{name}: {len(points)} chunks, e.g. \"{contexts[0]}\"")
        if args.dry_run:
            continue
        index_texts = [with_context(t, c) for t, c in zip(texts, contexts)]
        vectors = db.embedder.embed(index_texts)
        batch = []
        for p, dense, text, context in zip(points, vectors, index_texts, contexts):
            indices, values = sparse.encode_document(text)
            batch.append(qm.PointStruct(
                id=p.id, payload={**(p.payload or {}), "context": context},
                vector={DENSE: dense, SPARSE: qm.SparseVector(indices=indices, values=values)},
            ))
        for i in range(0, len(batch), 256):
            db.client.upsert(db.collection, points=batch[i:i + 256])
        updated += len(batch)

    print(f"\n{'Would update' if args.dry_run else 'Updated'} {updated if not args.dry_run else sum(len(v) for v in documents.values())} chunks.")


if __name__ == "__main__":
    main()
