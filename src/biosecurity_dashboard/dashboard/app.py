"""Streamlit dashboard for local biosecurity data."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import streamlit as st

from biosecurity_dashboard.sources.legislation.congress import (
    DEFAULT_CONGRESS,
    LEGISLATION_CATEGORIES,
    CongressApiError,
    CongressBillSearch,
    fetch_recent_bills,
    get_api_key,
    save_raw_ingest,
)


RAW_CONGRESS_OUTPUT_DIR = Path("Data/raw/legislation/congress")


def main() -> None:
    st.set_page_config(page_title="Biosecurity Dashboard", layout="wide")
    st.title("Biosecurity Dashboard")

    surveillance_tab, legislation_tab, publications_tab = st.tabs(
        ["Surveillance", "Legislation", "Publications"]
    )

    with surveillance_tab:
        st.subheader("Surveillance")
        st.info("Surveillance data controls will go here.")

    with legislation_tab:
        render_legislation_tab()

    with publications_tab:
        st.subheader("Publications")
        st.info("Publication data controls will go here.")


def render_legislation_tab() -> None:
    st.subheader("Legislation")

    today = date.today()
    default_start = today - timedelta(days=30)
    controls, results = st.columns([1, 2], gap="large")

    with controls:
        category = st.selectbox("Category", list(LEGISLATION_CATEGORIES))
        category_config = LEGISLATION_CATEGORIES[category]

        date_range = st.date_input(
            "Date range",
            value=(default_start, today),
            max_value=today,
        )
        start_date, end_date = _normalize_date_range(date_range, default_start, today)

        congress = st.number_input("Congress", min_value=1, max_value=200, value=DEFAULT_CONGRESS)
        max_pages = st.number_input("Pages to fetch", min_value=1, max_value=20, value=5)
        limit = st.number_input("Results per page", min_value=1, max_value=250, value=100)

        keywords = st.text_area(
            "Keywords",
            value="\n".join(category_config["keywords"]),
            height=180,
        )
        exclude_keywords = st.text_area(
            "Exclude words",
            value="\n".join(category_config["exclude_keywords"]),
            height=180,
        )

        run_fetch = st.button("Fetch Congress Bills", type="primary", use_container_width=True)

    with results:
        st.caption(f"Showing candidate legislation for {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}.")
        if run_fetch:
            search = CongressBillSearch(
                congress=int(congress),
                limit=int(limit),
                max_pages=int(max_pages),
                keywords=_split_terms(keywords),
                exclude_keywords=_split_terms(exclude_keywords),
                start_date=start_date,
                end_date=end_date,
            )
            render_congress_results(search)
        else:
            st.info("Choose filters, then fetch Congress bills.")


def render_congress_results(search: CongressBillSearch) -> None:
    try:
        payload = fetch_recent_bills(api_key=get_api_key(), search=search)
    except CongressApiError as exc:
        st.error(str(exc))
        return

    metadata = payload["metadata"]
    matches = payload["matches"]
    if not matches:
        st.warning(
            f"No matching bills found from {metadata['total_bills_seen']} bills. "
            "No JSON file was saved."
        )
        return

    output_path = save_raw_ingest(payload, RAW_CONGRESS_OUTPUT_DIR)
    st.success(
        f"Saved {metadata['matched_bills']} matches from "
        f"{metadata['total_bills_seen']} bills to {output_path}"
    )
    st.dataframe([_bill_row(bill) for bill in matches], use_container_width=True)


def _bill_row(bill: dict[str, Any]) -> dict[str, Any]:
    latest_action = bill.get("latestAction") if isinstance(bill.get("latestAction"), dict) else {}
    return {
        "Bill": f"{bill.get('type', '')} {bill.get('number', '')}".strip(),
        "Title": bill.get("title", ""),
        "Congress": bill.get("congress", ""),
        "Updated": bill.get("updateDate", bill.get("updateDateIncludingText", "")),
        "Latest action": latest_action.get("text", ""),
        "Action date": latest_action.get("actionDate", ""),
        "API URL": bill.get("url", ""),
    }


def _split_terms(value: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in value.splitlines() if line.strip())


def _normalize_date_range(
    value: date | tuple[date, date] | list[date],
    default_start: date,
    default_end: date,
) -> tuple[date, date]:
    if isinstance(value, date):
        return value, value
    if len(value) == 2:
        return value[0], value[1]
    return default_start, default_end


if __name__ == "__main__":
    main()
