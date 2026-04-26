"""Streamlit dashboard for local biosecurity data."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import streamlit as st

from biosecurity_dashboard.sources.legislation.congress import (
    DEFAULT_KEYWORDS,
    CongressApiError,
    CongressBillSearch,
    fetch_matching_bills,
    get_api_key,
)
from biosecurity_dashboard.sources.legislation.federal_register import (
    FederalRegisterApiError,
    FederalRegisterDocumentSearch,
    fetch_matching_documents as fetch_matching_federal_register_documents,
)
from biosecurity_dashboard.sources.legislation.regulations import (
    RegulationsApiError,
    RegulationsDocumentSearch,
    fetch_matching_documents,
    get_api_key as get_regulations_api_key,
)
from biosecurity_dashboard.storage.legislation_db import (
    get_refresh_metadata,
    load_grouped_records,
    upsert_congress_payload,
    upsert_federal_register_payload,
    upsert_regulations_payload,
)


def main() -> None:
    st.set_page_config(page_title="Biosecurity Dashboard", layout="wide")
    st.title("Biosecurity Dashboard")

    render_legislation_tab()


def render_legislation_tab() -> None:
    st.subheader("Legislation")

    today = date.today()
    default_start = today - timedelta(days=30)
    controls, results = st.columns([1, 2], gap="large")

    with controls:
        congress_refresh = get_refresh_metadata("congress.gov")
        regulations_refresh = get_refresh_metadata("regulations.gov")
        federal_register_refresh = get_refresh_metadata("federalregister.gov")
        refresh_button_column, refresh_info_column = st.columns([1, 1.4], gap="small")
        with refresh_button_column:
            refresh_all = st.button("Refresh Data", type="primary", use_container_width=True)
        with refresh_info_column:
            st.info(
                "Last Data Refresh\n\n"
                f"Congress: {_refresh_label(congress_refresh)}\n\n"
                f"Regulations.gov: {_refresh_label(regulations_refresh)}\n\n"
                f"Federal Register: {_refresh_label(federal_register_refresh)}"
            )

        st.markdown("**Date Range**")
        start_date = st.date_input("Start", value=default_start, max_value=today)
        end_date = st.date_input("End", value=today, max_value=today)
        if start_date > end_date:
            st.warning("Start date is after end date; swapping them for this query.")
            start_date, end_date = end_date, start_date

        source_filter = st.multiselect(
            "Sources",
            ["Congress.gov", "Regulations.gov", "Federal Register"],
            default=["Congress.gov", "Regulations.gov", "Federal Register"],
        )
        keyword_query = st.text_input("Search local database")

        max_pages = st.number_input(
            "Max pages per source",
            min_value=1,
            max_value=500,
            value=200,
        )

    if refresh_all:
        refresh_all_data(int(max_pages), start_date, end_date)

    with results:
        groups = load_grouped_records(
            tuple(source_filter),
            start_date.isoformat(),
            end_date.isoformat(),
            keyword_query,
        )
        st.caption(f"Showing locally stored legislation for {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}.")
        if not groups:
            st.info("No locally stored bills match these filters.")
            return

        st.dataframe([_group_row(group) for group in groups], use_container_width=True)
        for group in groups:
            with st.expander(f"{group['docket'] or group['title']} ({group['record_count']} entries)"):
                st.dataframe(
                    [_source_record_row(record) for record in group["records"]],
                    use_container_width=True,
                )


def refresh_all_data(max_pages: int, start_date: date, end_date: date) -> None:
    keywords = DEFAULT_KEYWORDS
    refresh_congress_data(keywords, max_pages, start_date, end_date)
    refresh_regulations_data(keywords, max_pages, start_date, end_date)
    refresh_federal_register_data(keywords, max_pages, start_date, end_date)


def refresh_congress_data(
    keywords: tuple[str, ...],
    max_pages_per_congress: int,
    start_date: date,
    end_date: date,
) -> None:
    search = CongressBillSearch(
        keywords=keywords,
        max_pages_per_congress=max_pages_per_congress,
        start_date=start_date,
        end_date=end_date,
    )
    try:
        payload = fetch_matching_bills(api_key=get_api_key(), search=search)
    except CongressApiError as exc:
        st.error(str(exc))
        return

    saved_count = upsert_congress_payload(payload)
    metadata = payload["metadata"]
    st.success(
        f"Refresh complete. Stored {saved_count} matched bills from "
        f"{metadata['total_bills_seen']} bills reviewed."
    )


def refresh_regulations_data(
    keywords: tuple[str, ...],
    max_pages: int,
    start_date: date,
    end_date: date,
) -> None:
    search = RegulationsDocumentSearch(
        keywords=keywords,
        max_pages=max_pages,
        start_date=start_date,
        end_date=end_date,
    )
    try:
        payload = fetch_matching_documents(api_key=get_regulations_api_key(), search=search)
    except RegulationsApiError as exc:
        st.error(str(exc))
        return

    saved_count = upsert_regulations_payload(payload)
    metadata = payload["metadata"]
    st.success(
        f"Refresh complete. Stored {saved_count} matched regulatory documents from "
        f"{metadata['total_documents_seen']} documents reviewed."
    )


def refresh_federal_register_data(
    keywords: tuple[str, ...],
    max_pages: int,
    start_date: date,
    end_date: date,
) -> None:
    search = FederalRegisterDocumentSearch(
        keywords=keywords,
        max_pages=max_pages,
        start_date=start_date,
        end_date=end_date,
    )
    try:
        payload = fetch_matching_federal_register_documents(search=search)
    except FederalRegisterApiError as exc:
        st.error(str(exc))
        return

    saved_count = upsert_federal_register_payload(payload)
    metadata = payload["metadata"]
    st.success(
        f"Refresh complete. Stored {saved_count} matched Federal Register documents from "
        f"{metadata['total_documents_seen']} documents reviewed."
    )


def _group_row(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "Docket": group["docket"],
        "Title": group["title"],
        "Sources": ", ".join(group["sources"]),
        "Entries": group["record_count"],
        "Latest date": group["latest_date"],
        "Matched keywords": ", ".join(group["matched_keywords"]),
    }


def _source_record_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "Source": record["source"],
        "ID": record["detail"],
        "Title": record["title"],
        "Date": record["date"],
        "Agency": record["agency"],
        "Docket": record["docket_id"],
        "Document type": record["document_type"],
        "Matched keywords": ", ".join(record["matched_keywords"]),
        "URL": record["url"],
    }


def _refresh_label(refresh_metadata: dict[str, Any] | None) -> str:
    return refresh_metadata["refreshed_at"] if refresh_metadata else "never"


if __name__ == "__main__":
    main()
