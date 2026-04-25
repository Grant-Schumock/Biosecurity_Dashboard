"""Fetch recent Congress.gov bills and store the raw response locally."""

from __future__ import annotations

import argparse
from pathlib import Path

from biosecurity_dashboard.sources.legislation.congress import (
    DEFAULT_CONGRESS,
    DEFAULT_KEYWORDS,
    CongressBillSearch,
    fetch_recent_bills,
    get_api_key,
    save_raw_ingest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--congress", type=int, default=DEFAULT_CONGRESS)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument(
        "--keyword",
        action="append",
        dest="keywords",
        help="Keyword to match locally. Can be repeated. Defaults to biosecurity terms.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("Data/raw/legislation/congress"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    keywords = tuple(args.keywords) if args.keywords else DEFAULT_KEYWORDS
    search = CongressBillSearch(
        congress=args.congress,
        limit=args.limit,
        max_pages=args.max_pages,
        keywords=keywords,
    )
    payload = fetch_recent_bills(api_key=get_api_key(), search=search)
    metadata = payload["metadata"]
    if not payload["matches"]:
        print(
            f"No matches found from {metadata['total_bills_seen']} bills. "
            "No JSON file was saved."
        )
        return

    output_path = save_raw_ingest(payload, args.output_dir)
    print(
        f"Saved {metadata['matched_bills']} matches from "
        f"{metadata['total_bills_seen']} bills to {output_path}"
    )


if __name__ == "__main__":
    main()
