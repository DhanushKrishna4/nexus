"""
Build / seed the ChromaDB collection of instrument failure-state manuals.

In production you'd extract these documents from your private PDFs; here we
seed a few mock entries. Safe to re-run — it upserts rather than duplicating.

RUN THIS ON THE RUNPOD SERVER (not the Mac): seeding documents requires the
embedding model, which lives server-side. The Mac app only ever *reads* via the
REST API (see rag_engine.py), so it doesn't need the chromadb client at all.

    ssh root@<ip> -p <port> -i ~/.ssh/id_ed25519 "python3 /root/build_database.py"
"""
from __future__ import annotations

import chromadb

import config
import embeddings

# Mock private company data. Each doc is paired with its instrument tag so we
# can do precise metadata lookups later.
DOCUMENTS: list[dict[str, str]] = [
    {
        "tag": "PT-101",
        "text": (
            "Failure State Manual for PT-101 (Pressure Transmitter): If PT-101 "
            "fails low, the control system will incorrectly assume a pressure "
            "drop and open the steam inlet valve fully, potentially causing an "
            "overpressure event in T-101."
        ),
    },
    {
        "tag": "LT-104",
        "text": (
            "Failure State Manual for LT-104 (Level Transmitter): If LT-104 "
            "loses power, it defaults to a zero reading. The system will trigger "
            "the low-level alarm and shut down pumps P-102A and P-102B to "
            "prevent cavitation."
        ),
    },
    {
        "tag": "FT-105",
        "text": (
            "Failure State Manual for FT-105 (Flow Transmitter): A clogged "
            "impulse line on FT-105 will freeze the flow reading. The control "
            "loop will fail to respond to actual flow changes, requiring manual "
            "operator override."
        ),
    },
]


def main() -> None:
    client = chromadb.HttpClient(host=config.CHROMA_HOST, port=config.CHROMA_PORT)
    # Recreate the collection so its vector dimension matches the current
    # embedding model (changing embedders changes the dimension).
    try:
        client.delete_collection(config.COLLECTION_NAME)
    except Exception:  # noqa: BLE001
        pass
    collection = client.get_or_create_collection(name=config.COLLECTION_NAME)

    texts = [d["text"] for d in DOCUMENTS]
    print(f"Seeding '{config.COLLECTION_NAME}' with {len(DOCUMENTS)} documents "
          f"(embedding with {config.EMBED_MODEL})…")
    collection.upsert(
        documents=texts,
        embeddings=embeddings.embed_texts(texts),
        metadatas=[{"tag": d["tag"], "source": "(demo data)", "loc": ""}
                   for d in DOCUMENTS],
        ids=[d["tag"] for d in DOCUMENTS],  # stable IDs => idempotent re-runs
    )
    print(f"Done. Collection now holds {collection.count()} documents.")


if __name__ == "__main__":
    main()
