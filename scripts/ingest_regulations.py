"""Fetch Regulations.gov documents and store matches in the local SQLite database."""

from __future__ import annotations

import argparse
import json
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
    parser.add_argument("--max-records", type=int, default=1000)
    parser.add_argument("--max-api-calls", type=int, default=4000)
    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE.isoformat(),
        help="Earliest posted date to fetch, in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Latest posted date to fetch, in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print matched documents instead of writing them to SQLite.",
    )
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
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date) if args.end_date else date.today()
    if start_date > end_date:
        raise SystemExit("--start-date must be on or before --end-date.")

    search = RegulationsDocumentSearch(
        limit=args.limit,
        max_pages=args.max_pages,
        max_records=args.max_records,
        max_api_calls=args.max_api_calls,
        keywords=keywords,
        start_date=start_date,
        end_date=end_date,
    )
    payload = fetch_matching_documents(api_key=get_api_key(), search=search)
    if args.print_only:
        metadata = payload["metadata"]
        print(
            f"Matched {metadata['matched_documents']} Regulations.gov documents from "
            f"{metadata['total_documents_seen']} documents reviewed "
            f"from {metadata['start_date']} to {metadata['end_date']}."
        )
        print(json.dumps(payload["matches"], indent=2, sort_keys=True))
        return

    saved_count = upsert_regulations_payload(payload)
    metadata = payload["metadata"]
    print(
        f"Stored {saved_count} matched regulatory documents from "
        f"{metadata['total_documents_seen']} Regulations.gov documents reviewed "
        f"from {metadata['start_date']} to {metadata['end_date']} "
        f"using {metadata['api_calls_used']} API calls."
    )
    if not metadata.get("completed", True):
        print("Run stopped early; partial data was saved.")
        for error in metadata.get("errors", []):
            print(f"- {error}")


if __name__ == "__main__":
    main()
