"""
Run to (re)build the shared knowledge base from the website, PDFs and FAQs:
    python -m scripts.ingest_knowledge_base

Add/remove PDFs in data/documents/, FAQ files in data/faqs/, and list
website URLs to crawl in .env under COMPANY_WEBSITE_URLS (comma-separated).
"""
from app.config import settings
from app.rag.ingest import ingest_all


def main():
    urls = [u.strip() for u in settings.company_website_urls.split(",") if u.strip()]
    summary = ingest_all(
        website_urls=urls,
        documents_dir="data/documents",
        faqs_dir="data/faqs",
    )
    print("Ingestion summary:")

    visible_results = [
        (source, result)
        for source, result in summary.items()
        if not (isinstance(result, str) and result.startswith("skipped"))
    ]

    if not visible_results:
        print("  - No new content ingested from reachable sources.")
    else:
        for source, result in visible_results:
            print(f"  - {source}: {result}")


if __name__ == "__main__":
    main()
