"""
Local, embedded vector store using ChromaDB with a local sentence-transformers
embedding function. Nothing here calls an external API.
"""
import chromadb
from chromadb.utils import embedding_functions

from app.config import settings

_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)

_embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=settings.embedding_model
)

_collection = _client.get_or_create_collection(
    name=settings.chroma_collection,
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
