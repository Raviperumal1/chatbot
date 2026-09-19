from app.rag.vectorstore import query as vector_query


def get_context(question: str, top_k: int = 4) -> str:
    """Fetch the most relevant knowledge base chunks and join them into a context block."""
    msg_lower = question.strip().lower()
    # Retrieval gating: do not fetch context for simple greetings/small-talk
    if msg_lower in {"hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "good morning", "good afternoon", "good evening"}:
        return ""

    hits = vector_query(question, top_k=top_k)
    if not hits:
        return ""
    parts = []
    for h in hits:
        src = h["metadata"].get("source", "unknown")
        parts.append(f"[Source: {src}]\n{h['text']}")
    return "\n\n---\n\n".join(parts)
