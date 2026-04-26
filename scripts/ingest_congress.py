"""Fetch Congress.gov bills and store matches in the local SQLite database."""

from __future__ import annotations

import argparse
from datetime import date
from biosecurity_dashboard.sources.legislation.congress import (
    DEFAULT_KEYWORDS,
    DEFAULT_START_DATE,
    CongressBillSearch,
    fetch_matching_bills,
    get_api_key,
)
from biosecurity_dashboard.storage.legislation_db import upsert_congress_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--max-bills", type=int, default=1000)
    parser.add_argument("--max-pages-per-congress", type=int, default=200)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE.isoformat())
    parser.add_argument("--end-date", default=None)
    parser.add_argument(
        "--skip-full-text",
        action="store_true",
        help="Only fetch bill details and summaries, not full bill text.",
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
    search = CongressBillSearch(
        limit=args.limit,
        max_bills=args.max_bills,
        max_pages_per_congress=args.max_pages_per_congress,
        keywords=keywords,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date) if args.end_date else None,
        include_full_text=not args.skip_full_text,
    )
    payload = fetch_matching_bills(api_key=get_api_key(), search=search)
    metadata = payload["metadata"]
    saved_count = upsert_congress_payload(payload)
    print(
        f"Stored {saved_count} matched bills from "
        f"{metadata['total_bills_seen']} Congress.gov bills reviewed."
    )


if __name__ == "__main__":
    main()
