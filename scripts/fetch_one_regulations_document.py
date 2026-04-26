"""Fetch one Regulations.gov document and print the full JSON without saving it."""

from __future__ import annotations

import argparse
import json

from biosecurity_dashboard.sources.legislation.regulations import (
    RegulationsApiError,
    fetch_document,
    fetch_recent_document,
    get_api_key,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        api_key = get_api_key()
        document = (
            fetch_document(api_key, args.document_id)
            if args.document_id
            else fetch_recent_document(api_key)
        )
    except RegulationsApiError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from exc

    print(json.dumps(document, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
