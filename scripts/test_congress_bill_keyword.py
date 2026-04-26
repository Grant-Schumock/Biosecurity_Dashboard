"""Test whether one Congress.gov bill title or summary matches a keyword expression."""

from __future__ import annotations

import argparse

from biosecurity_dashboard.sources.legislation.congress import (
    CongressApiError,
    fetch_bill,
    get_api_key,
    matching_keywords,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--congress", type=int, required=True)
    parser.add_argument("--bill-type", required=True)
    parser.add_argument("--bill-number", required=True)
    parser.add_argument("--keyword", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        bill = fetch_bill(
            get_api_key(),
            congress=args.congress,
            bill_type=args.bill_type,
            bill_number=args.bill_number,
        )
    except CongressApiError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from exc

    keyword = args.keyword.strip()
    matches = matching_keywords(bill, (keyword,))
    summaries = bill.get("summaries", [])

    print(f"Bill: {bill.get('type')} {bill.get('number')}")
    print(f"Congress: {bill.get('congress')}")
    print(f"Title: {bill.get('title')}")
    print(f"Keyword: {keyword}")
    print(f"Matched: {bool(matches)}")
    print(f"Summary count: {len(summaries) if isinstance(summaries, list) else 0}")

    if isinstance(summaries, list):
        for index, summary in enumerate(summaries, start=1):
            if not isinstance(summary, dict):
                continue
            text = str(summary.get("text", ""))
            contains_keyword = keyword.casefold() in text.casefold()
            print()
            print(f"Summary {index}")
            print(f"Action date: {summary.get('actionDate', '')}")
            print(f"Action: {summary.get('actionDesc', '')}")
            print(f"Contains keyword literally: {contains_keyword}")
            print(text)


if __name__ == "__main__":
    main()
