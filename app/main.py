import json
import logging

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage()
        }
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

# Remove default handlers to replace with JSON handler
logging.getLogger().handlers.clear()

json_handler = logging.StreamHandler()
json_handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.INFO, handlers=[json_handler])


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import leads, website_chat, whatsapp_chat
from app.routers.v1 import chat as v1_chat
from app.routers.v1 import conversations as v1_conversations

from app.database import engine, Base
from app import models
# Automatic table creation disabled for production.
# Use Alembic for schema migrations instead: `alembic upgrade head`
# Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Zenfuture Technologies - AI Chatbot Backend",
    description=(
        "Backend powering the website widget and WhatsApp chatbot, backed by a locally-run LLM "
        "(Ollama) and a local knowledge base (ChromaDB). Integrated with Meta WhatsApp Cloud API."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://zenfuture.in", 
        "https://www.zenfuture.in",
        "http://localhost:3000" ,# for local dev
        "http://localhost/zenfuture/",
        "*"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(website_chat.router)
app.include_router(whatsapp_chat.router)
app.include_router(leads.router)

app.include_router(v1_chat.router, prefix="/api/v1")
app.include_router(v1_conversations.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}