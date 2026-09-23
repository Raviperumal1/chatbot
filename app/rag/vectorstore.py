"""
Local, embedded vector store using ChromaDB with a local sentence-transformers
embedding function. Nothing here calls an external API.
"""
import chromadb
from chromadb.utils import embedding_functions

import os

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_store")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "zenfuture_kb")

from chromadb.config import Settings

_client = chromadb.PersistentClient(
    path=CHROMA_PERSIST_DIR,
    settings=Settings(anonymized_telemetry=False)
)

_embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=EMBEDDING_MODEL
)

_collection = _client.get_or_create_collection(
    name=CHROMA_COLLECTION,
    embedding_function=_embedder,
    metadata={"hnsw:space": "cosine"},
)


def add_documents(ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
    """Add (or upsert) chunks into the knowledge base."""
    _collection.upsert(ids=ids, documents=texts, metadatas=metadatas)


def query(text: str, top_k: int = 4) -> list[dict]:
    """Return the top_k most relevant chunks for a query."""
    results = _collection.query(query_texts=[text], n_results=top_k)
    hits = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        hits.append({"text": doc, "metadata": meta, "distance": dist})
    return hits


def collection_count() -> int:
    return _collection.count()
