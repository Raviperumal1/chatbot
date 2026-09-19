
import os
from app.rag.ingest import ingest_all

COMPANY_WEBSITE_URLS = os.getenv("COMPANY_WEBSITE_URLS", "https://zenfuture.in")


def main():
    urls = [u.strip() for u in COMPANY_WEBSITE_URLS.split(",") if u.strip()]
    summary = ingest_all(
        website_urls=urls,
        documents_dir="data/documents",
        faqs_dir="data/faqs",
    )

    visible_results = [
        (source, result)
        for source, result in summary.items()
        if not (isinstance(result, str) and result.startswith("skipped"))
    ]

    if not visible_results:
        print("  - No new content ingested from reachable sources.")
    else:
        for source, result in visible_results:
            print(f" source - {source}: {result}")


if __name__ == "__main__":
    main()
