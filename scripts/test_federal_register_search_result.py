"""Test whether Federal Register API term search returns a document number."""

from __future__ import annotations

import argparse
from datetime import date

from biosecurity_dashboard.sources.legislation.federal_register import (
    FederalRegisterApiError,
    search_documents,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", required=True)
    parser.add_argument("--document-number", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        documents = search_documents(
            term=args.term,
            start_date=date.fromisoformat(args.start_date),
            end_date=date.fromisoformat(args.end_date),
            per_page=args.per_page,
            max_pages=args.max_pages,
        )
    except FederalRegisterApiError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from exc

    document_numbers = {str(document.get("document_number")) for document in documents}
    found = args.document_number in document_numbers
    print(f"Term: {args.term}")
    print(f"Date range: {args.start_date} to {args.end_date}")
    print(f"Documents checked: {len(documents)}")
    print(f"Document number: {args.document_number}")
    print(f"Returned by search: {found}")
    if found:
        match = next(
            document for document in documents if document.get("document_number") == args.document_number
        )
        print(f"Title: {match.get('title', '')}")


if __name__ == "__main__":
    main()
