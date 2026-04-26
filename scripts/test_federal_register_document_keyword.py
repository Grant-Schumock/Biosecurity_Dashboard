"""Test whether one Federal Register document matches a keyword expression."""

from __future__ import annotations

import argparse

from biosecurity_dashboard.sources.legislation.federal_register import (
    FederalRegisterApiError,
    fetch_document,
    matching_keywords,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-number", required=True)
    parser.add_argument("--keyword", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        document = fetch_document(args.document_number)
    except FederalRegisterApiError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from exc

    keyword = args.keyword.strip()
    matches = matching_keywords(document, (keyword,))
    print(f"Document number: {document.get('document_number')}")
    print(f"Title: {document.get('title', '')}")
    print(f"Keyword: {keyword}")
    print(f"Matched: {bool(matches)}")
    print("Matched fields are title, abstract, excerpts, action, type, docket_id, agency_names, and topics.")


if __name__ == "__main__":
    main()
