import hashlib
import os

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.rag.vectorstore import add_documents

CHUNK_SIZE = 400
CHUNK_OVERLAP = 100


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def _make_id(source: str, chunk_index: int) -> str:
    return hashlib.sha256(f"{source}-{chunk_index}".encode()).hexdigest()[:24]


def ingest_text(text: str, source: str, extra_meta: dict | None = None) -> int:
    chunks = _chunk_text(text)
    if not chunks:
        return 0
    ids = [_make_id(source, i) for i in range(len(chunks))]
    metadatas = [{"source": source, "chunk": i, **(extra_meta or {})} for i in range(len(chunks))]
    add_documents(ids=ids, texts=chunks, metadatas=metadatas)
    return len(chunks)


def ingest_website(url: str) -> int:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    print(f"ingesting {text} from website {url}")
    return ingest_text(text, source=url, extra_meta={"type": "website"})


def ingest_pdf(path: str) -> int:
    reader = PdfReader(path)
    text = " ".join(page.extract_text() or "" for page in reader.pages)
    return ingest_text(text, source=os.path.basename(path), extra_meta={"type": "pdf"})


def ingest_faq_file(path: str) -> int:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return ingest_text(text, source=os.path.basename(path), extra_meta={"type": "faq"})


def ingest_all(website_urls: list[str], documents_dir: str, faqs_dir: str) -> dict:
    """Ingest every configured source. Returns a summary of chunks added per source."""
    summary = {}

    for url in website_urls:
        url = url.strip()
        if not url:
            continue
        try:
            summary[url] = ingest_website(url)
        except requests.RequestException as e:
            summary[url] = f"skipped (network error): {e}"
        except Exception as e:  # noqa: BLE001
            summary[url] = f"error: {e}"

    if os.path.isdir(documents_dir):
        for fname in os.listdir(documents_dir):
            if fname.lower().endswith(".pdf"):
                path = os.path.join(documents_dir, fname)
                try:
                    summary[fname] = ingest_pdf(path)
                except Exception as e:  # noqa: BLE001
                    summary[fname] = f"error: {e}"

    if os.path.isdir(faqs_dir):
        for fname in os.listdir(faqs_dir):
            if fname.lower().endswith((".md", ".txt")):
                path = os.path.join(faqs_dir, fname)
                try:
                    summary[fname] = ingest_faq_file(path)
                except Exception as e:  # noqa: BLE001
                    summary[fname] = f"error: {e}"

    return summary
