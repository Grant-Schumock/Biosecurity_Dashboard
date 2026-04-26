"""Fetch Federal Register documents and store matches in the local SQLite database."""

from __future__ import annotations

import argparse
from datetime import date

from biosecurity_dashboard.sources.legislation.congress import DEFAULT_KEYWORDS, DEFAULT_START_DATE
from biosecurity_dashboard.sources.legislation.federal_register import (
    FederalRegisterDocumentSearch,
    fetch_matching_documents,
)
from biosecurity_dashboard.storage.legislation_db import upsert_federal_register_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-page", type=int, default=1000)
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
    search = FederalRegisterDocumentSearch(
        per_page=args.per_page,
        max_pages=args.max_pages,
        keywords=keywords,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date) if args.end_date else None,
    )
    payload = fetch_matching_documents(search=search)
    saved_count = upsert_federal_register_payload(payload)
    metadata = payload["metadata"]
    print(
        f"Stored {saved_count} matched Federal Register documents from "
        f"{metadata['total_documents_seen']} documents reviewed."
    )


if __name__ == "__main__":
    main()
