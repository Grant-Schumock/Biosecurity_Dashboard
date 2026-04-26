"""Fetch Regulations.gov documents and store matches in the local SQLite database."""

from __future__ import annotations

import argparse
from datetime import date

from biosecurity_dashboard.sources.legislation.congress import DEFAULT_KEYWORDS, DEFAULT_START_DATE
from biosecurity_dashboard.sources.legislation.regulations import (
    RegulationsDocumentSearch,
    fetch_matching_documents,
    get_api_key,
)
from biosecurity_dashboard.storage.legislation_db import upsert_regulations_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE.isoformat())
    parser.add_argument("--end-date", default=None)
    parser.add_argument(
        "--keyword",
        action="append",
        dest="keywords",
        help="Keyword expression to match. Can be repeated. Use 'AND' for required terms.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    keywords = tuple(args.keywords) if args.keywords else DEFAULT_KEYWORDS
    search = RegulationsDocumentSearch(
        limit=args.limit,
        max_pages=args.max_pages,
        keywords=keywords,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date) if args.end_date else None,
    )
    payload = fetch_matching_documents(api_key=get_api_key(), search=search)
    saved_count = upsert_regulations_payload(payload)
    metadata = payload["metadata"]
    print(
        f"Stored {saved_count} matched regulatory documents from "
        f"{metadata['total_documents_seen']} Regulations.gov documents reviewed."
    )


if __name__ == "__main__":
    main()
