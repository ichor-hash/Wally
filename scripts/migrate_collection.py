"""
Copy a pre-3.0 collection (one unnamed dense vector) into a hybrid collection
(named dense vector + BM25 sparse vector), without re-uploading any files.

    python scripts/migrate_collection.py                  docs -> ethan_docs
    python scripts/migrate_collection.py --source docs --target ethan_docs

Chunk text and metadata are copied as they are; dense vectors are reused, so no
embedding model runs. Chunks keep their old boundaries: re-upload a document
if you also want structure-aware chunking. The source collection is left
untouched; delete it yourself once the new one works.

Reads QDRANT_URL / QDRANT_PATH / QDRANT_API_KEY from .env like the API does.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client import models as qm  # noqa: E402

import sparse  # noqa: E402
from vector_db import DENSE, SPARSE  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="docs", help="old collection (default: docs, the v2 default)")
    ap.add_argument("--target", default=os.getenv("QDRANT_COLLECTION", "ethan_docs"))
    ap.add_argument("--batch", type=int, default=256)
    args = ap.parse_args()

    path = os.getenv("QDRANT_PATH", "").strip()
    client = QdrantClient(path=path) if path else QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"), api_key=os.getenv("QDRANT_API_KEY") or None)

    if not client.collection_exists(args.source):
        sys.exit(f"Source collection {args.source!r} does not exist.")
    if client.collection_exists(args.target) and client.count(args.target, exact=True).count:
        sys.exit(f"Target collection {args.target!r} already has points. Choose another --target or delete it first.")

    params = client.get_collection(args.source).config.params
    if isinstance(params.vectors, dict):
        sys.exit(f"{args.source!r} already uses named vectors; nothing to migrate.")
    size = params.vectors.size

    if not client.collection_exists(args.target):
        client.create_collection(
            args.target,
            vectors_config={DENSE: qm.VectorParams(size=size, distance=qm.Distance.COSINE)},
            sparse_vectors_config={SPARSE: qm.SparseVectorParams(modifier=qm.Modifier.IDF)},
        )
    if not path:
        client.create_payload_index(args.target, field_name="source_file", field_schema=qm.PayloadSchemaType.KEYWORD)

    copied, offset = 0, None
    while True:
        points, offset = client.scroll(args.source, limit=args.batch, offset=offset, with_payload=True, with_vectors=True)
        batch = []
        for p in points:
            indices, values = sparse.encode_document((p.payload or {}).get("text", ""))
            batch.append(qm.PointStruct(
                id=p.id, payload=p.payload,
                vector={DENSE: p.vector, SPARSE: qm.SparseVector(indices=indices, values=values)},
            ))
        if batch:
            client.upsert(args.target, points=batch)
            copied += len(batch)
            print(f"  copied {copied} chunks", end="\r")
        if offset is None:
            break

    print(f"\nDone: {copied} chunks from {args.source!r} into {args.target!r} with BM25 vectors.")
    print(f"Set QDRANT_COLLECTION={args.target} in .env and restart the API.")


if __name__ == "__main__":
    main()
