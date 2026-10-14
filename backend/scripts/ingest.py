import json
import sys
import time
from collections import Counter
from pathlib import Path

from app.config import settings
from app.rag.chunking import chunk_text, embedding_text
from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStoreService

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def build_rows() -> list[dict]:
    rows = []
    for path in sorted(RAW_DIR.glob("*.json")):
        opening = json.loads(path.read_text())
        for doc in opening["documents"]:
            for chunk in chunk_text(doc["text"], max_chars=settings.chunk_max_chars):
                rows.append(
                    {
                        "opening_slug": opening["slug"],
                        "opening_name": opening["name"],
                        "eco": opening["eco"],
                        "fen": opening["fen"],
                        "section": chunk.section[:512],
                        "source": doc["source"],
                        "lang": doc["lang"],
                        "url": doc["url"],
                        "text": chunk.text,
                        "_embed": embedding_text(opening["name"], opening["eco"], chunk.section, chunk.text),
                    }
                )
    return rows


def main() -> int:
    rows = build_rows()
    if not rows:
        print(f"Aucun article dans {RAW_DIR} : lancer d'abord scripts.fetch_wikichess", file=sys.stderr)
        return 1
    per_opening = Counter(r["opening_slug"] for r in rows)
    print(f"{len(rows)} chunks ({', '.join(f'{k}={v}' for k, v in sorted(per_opening.items()))})")

    start = time.perf_counter()
    embedder = EmbeddingService(settings.embedding_model, settings.embedding_batch_size, settings.embedding_threads)
    vectors = embedder.embed_documents([r.pop("_embed") for r in rows])
    print(f"Embeddings calculés (dim={embedder.dimension}) en {time.perf_counter() - start:.0f} s")

    store = VectorStoreService(settings.milvus_uri, settings.milvus_collection)
    store.recreate_collection(embedder.dimension)
    inserted = store.insert([{**row, "vector": vec} for row, vec in zip(rows, vectors)])
    store.client.flush(settings.milvus_collection)
    print(f"{inserted} chunks indexés dans la collection '{settings.milvus_collection}' ({store.count()} au total)")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
