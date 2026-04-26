"""Fetch one Federal Register document and print the full JSON without saving it."""

from __future__ import annotations

import argparse
import json

from biosecurity_dashboard.sources.legislation.federal_register import (
    FederalRegisterApiError,
    fetch_document,
    fetch_recent_document,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-number", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        document = (
            fetch_document(args.document_number)
            if args.document_number
            else fetch_recent_document()
        )
    except FederalRegisterApiError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from exc

    print(json.dumps(document, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
