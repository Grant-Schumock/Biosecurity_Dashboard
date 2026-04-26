"""Fetch one recent Congress.gov bill and print a preview without saving it."""

from __future__ import annotations

import argparse
import json

from biosecurity_dashboard.sources.legislation.congress import (
    CongressApiError,
    fetch_recent_bill,
    get_api_key,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--congress", type=int, default=119)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        bill = fetch_recent_bill(get_api_key(), congress=args.congress)
    except CongressApiError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from exc

    print(json.dumps(bill, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
