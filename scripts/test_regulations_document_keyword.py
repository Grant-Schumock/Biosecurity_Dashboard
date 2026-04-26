"""Test whether one Regulations.gov document matches a keyword expression."""

from __future__ import annotations

import argparse

from biosecurity_dashboard.sources.legislation.regulations import (
    RegulationsApiError,
    fetch_document,
    get_api_key,
    matching_keywords,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--keyword", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        document = fetch_document(get_api_key(), args.document_id)
    except RegulationsApiError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from exc

    keyword = args.keyword.strip()
    matches = matching_keywords(document, (keyword,))
    attributes = document.get("attributes") if isinstance(document.get("attributes"), dict) else {}
    print(f"Document ID: {document.get('id')}")
    print(f"Title: {attributes.get('title', '')}")
    print(f"Keyword: {keyword}")
    print(f"Matched: {bool(matches)}")
    print("Matched fields are title, docAbstract, subject, documentType, and agencyId.")


if __name__ == "__main__":
    main()
