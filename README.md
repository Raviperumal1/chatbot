# Zenfuture Chatbot Platform

Zenfuture Chatbot Platform is a local-first AI assistant for websites and customer support workflows. It combines a FastAPI backend, a local Ollama-powered LLM, ChromaDB for retrieval, and PostgreSQL for lead and conversation storage. No external AI API is required.

## Overview

This project is designed to support:
- A website chatbot widget for customer support
- Retrieval-augmented generation (RAG) from internal knowledge sources
- Lead capture and follow-up tracking
- Local deployment with no dependency on third-party AI APIs

## Architecture

The platform is composed of three main layers:
- Frontend: a lightweight HTML demo interface and an embeddable chat widget
- Backend: FastAPI application that handles chat requests, lead capture, and API routing
- Data layer: PostgreSQL for structured data and ChromaDB for local vector search

```text
Website / Widget
        │
        ▼
FastAPI Backend (app/main.py)
        ├── Chat Engine
        ├── RAG Pipeline
        └── Lead Management
        │
        ├── PostgreSQL (leads, conversations, messages)
        └── ChromaDB + Ollama (local knowledge retrieval + LLM)
```

## Project Structure

```text
zenfuture_chatbot/
├── app/
│   ├── main.py                  # FastAPI entry point
│   ├── config.py                # Application settings from environment variables
│   ├── database.py              # SQLAlchemy engine and session setup
│   ├── models.py                # Database models for leads/conversations/messages
│   ├── schemas.py               # Request/response schemas
│   ├── chat/
│   │   ├── engine.py            # Main chat orchestration logic
│   │   └── lead_capture.py      # Lead capture state machine
│   ├── llm/
│   │   └── ollama_client.py     # Ollama client wrapper
│   ├── rag/
│   │   ├── ingest.py            # Knowledge ingestion from PDFs/FAQ/URLs
│   │   ├── retriever.py        # RAG retrieval flow
│   │   └── vectorstore.py      # ChromaDB integration
│   └── routers/
│       ├── website_chat.py      # Chat endpoint
│       └── leads.py            # Lead management endpoint
├── frontend/
│   └── index.html               # Demo frontend for testing the UI
├── widget/
│   └── chat-widget.html         # Embeddable website widget snippet
├── data/
│   ├── documents/               # PDF or text documents for ingestion
│   ├── faqs/                    # FAQ markdown files
│   └── knowledge_base/          # Reserved for raw/processed knowledge content
├── scripts/
│   ├── init_db.py               # Creates database tables
│   └── ingest_knowledge_base.py # Builds the local knowledge base
├── docker-compose.yml           # PostgreSQL container configuration
├── requirements.txt             # Python dependencies
└── chroma_store/                # Local vector database storage
```

## Technology Stack

- Python 3.10+
- FastAPI for the backend API
- SQLAlchemy for database access
- PostgreSQL for persistent storage
- ChromaDB for vector search
- sentence-transformers for embeddings
- Ollama for local LLM inference
- Plain HTML/CSS/JavaScript for the frontend demo and widget

## Prerequisites

Before starting, make sure you have:
- Python 3.10 or newer installed
- Docker Desktop installed and running
- Ollama installed locally
- A terminal with access to the project folder

## Setup Instructions

### 1. Clone the project

```bash
git clone <your-repository-url>
cd zenfuture_chatbot
```

### 2. Create a Python virtual environment

```bash
python -m venv venv
```

On Windows:
```bash
venv\Scripts\activate
```

On macOS/Linux:
```bash
source venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a file named `.env` in the project root and add the following values:

```env
DATABASE_URL=postgresql://zenfuture:zenfuture@localhost:5432/zenfuture_chatbot
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3
CHROMA_PERSIST_DIR=./chroma_store
CHROMA_COLLECTION=zenfuture_kb
EMBEDDING_MODEL=all-MiniLM-L6-v2
COMPANY_NAME=Zenfuture Technologies
COMPANY_WEBSITE_URLS=https://zenfuture.in
ADMIN_API_KEY=change_me
```

### 5. Start PostgreSQL with Docker

```bash
docker compose up -d
```

### 6. Initialize the database

```bash
python -m scripts.init_db
```

### 7. Start Ollama and pull a model

If Ollama is not installed yet, install it from https://ollama.com.

```bash
ollama pull llama3
ollama serve
```

### 8. Build the knowledge base

Add content to the following folders before ingestion:
- PDFs or text files in `data/documents/`
- FAQ markdown files in `data/faqs/`
- Website URLs in `COMPANY_WEBSITE_URLS` (comma-separated if needed)

Then run:

```bash
python -m scripts.ingest_knowledge_base
```

## Running the Backend

Start the FastAPI server:

```bash
uvicorn app.main:app --reload --port 8000
```

Once running, you can access:
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Running the Frontend

The frontend is a simple static HTML interface and does not require a build step.

### Demo frontend

```bash
cd frontend
python -m http.server 5500
```

Then open:
- http://localhost:5500

### Embeddable widget

To use the widget on a website, copy the contents of `widget/chat-widget.html` into the target page before the closing `</body>` tag. Update the API base URL inside the widget script if your backend is hosted elsewhere.

## API Endpoints

The backend exposes the following main endpoints:
- `GET /health` — health check
- `POST /api/chat/website` — chat with the website assistant
- `GET /api/leads` — fetch stored leads (admin use)

## Notes

- All chatbot responses are generated locally through Ollama and retrieved from the local knowledge base.
- Conversations, leads, and messages are persisted in PostgreSQL for follow-up and reporting.
- For production, replace wildcard CORS settings and secure the admin API key.