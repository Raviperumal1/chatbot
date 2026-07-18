from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import leads, website_chat

app = FastAPI(
    title="Zenfuture Technologies - AI Chatbot Backend",
    description=(
        "Backend powering the website widget, backed by a locally-run LLM "
        "(Ollama) and a local knowledge base (ChromaDB). No external AI API is used."
    ),
    version="0.1.0",
)

# Allow the website (wherever it's hosted) to call this API from the browser widget.
# Restrict this to your actual domain(s) in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(website_chat.router)
app.include_router(leads.router)


@app.get("/health")
def health():
    return {"status": "ok"}
