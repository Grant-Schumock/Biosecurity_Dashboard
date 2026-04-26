"""Streamlit dashboard for local biosecurity data."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import streamlit as st

from biosecurity_dashboard.sources.legislation.congress import (
    DEFAULT_KEYWORDS,
    DEFAULT_START_DATE,
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
    load_bills,
    load_federal_register_documents,
    load_regulatory_documents,
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
        st.caption(f"Congress refresh: {_refresh_label(congress_refresh)}")
        st.caption(f"Regulations.gov refresh: {_refresh_label(regulations_refresh)}")
        st.caption(f"Federal Register refresh: {_refresh_label(federal_register_refresh)}")

        date_range = st.date_input(
            "Dashboard date range",
            value=(default_start, today),
            max_value=today,
        )
        start_date, end_date = _normalize_date_range(date_range, default_start, today)

        source_filter = st.multiselect(
            "Sources",
            ["Congress.gov", "Regulations.gov", "Federal Register"],
            default=["Congress.gov", "Regulations.gov", "Federal Register"],
        )
        keyword_query = st.text_input("Search local database")

        keywords = st.text_area(
            "Refresh keywords",
            value="\n".join(DEFAULT_KEYWORDS),
            height=260,
        )
        max_pages = st.number_input(
            "Max pages per Congress",
            min_value=1,
            max_value=500,
            value=200,
        )
        refresh_congress = st.button("Refresh Congress Data", type="primary", use_container_width=True)
        refresh_regulations = st.button("Refresh Regulations.gov Data", use_container_width=True)
        refresh_federal_register = st.button(
            "Refresh Federal Register Data",
            use_container_width=True,
        )

    if refresh_congress:
        refresh_congress_data(_split_terms(keywords), int(max_pages))
    if refresh_regulations:
        refresh_regulations_data(_split_terms(keywords), int(max_pages))
    if refresh_federal_register:
        refresh_federal_register_data(_split_terms(keywords), int(max_pages))

    with results:
        rows: list[dict[str, Any]] = []
        if "Congress.gov" in source_filter:
            rows.extend(
                _bill_row(bill)
                for bill in load_bills(start_date.isoformat(), end_date.isoformat(), keyword_query)
            )
        if "Regulations.gov" in source_filter:
            rows.extend(
                _regulatory_document_row(document)
                for document in load_regulatory_documents(
                    start_date.isoformat(),
                    end_date.isoformat(),
                    keyword_query,
                )
            )
        if "Federal Register" in source_filter:
            rows.extend(
                _federal_register_document_row(document)
                for document in load_federal_register_documents(
                    start_date.isoformat(),
                    end_date.isoformat(),
                    keyword_query,
                )
            )
        st.caption(f"Showing locally stored legislation for {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}.")
        if not rows:
            st.info("No locally stored bills match these filters.")
            return

        st.dataframe(rows, use_container_width=True)


def refresh_congress_data(keywords: tuple[str, ...], max_pages_per_congress: int) -> None:
    search = CongressBillSearch(
        keywords=keywords,
        max_pages_per_congress=max_pages_per_congress,
        start_date=DEFAULT_START_DATE,
        end_date=date.today(),
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


def refresh_regulations_data(keywords: tuple[str, ...], max_pages: int) -> None:
    search = RegulationsDocumentSearch(
        keywords=keywords,
        max_pages=max_pages,
        start_date=DEFAULT_START_DATE,
        end_date=date.today(),
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


def refresh_federal_register_data(keywords: tuple[str, ...], max_pages: int) -> None:
    search = FederalRegisterDocumentSearch(
        keywords=keywords,
        max_pages=max_pages,
        start_date=DEFAULT_START_DATE,
        end_date=date.today(),
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


def _bill_row(bill: dict[str, Any]) -> dict[str, Any]:
    return {
        "Source": "Congress.gov",
        "Bill": f"{bill['bill_type']} {bill['bill_number']}",
        "Title": bill["title"],
        "Congress": bill["congress"],
        "Introduced": bill["introduced_date"],
        "Updated": bill["update_date"],
        "Posted": "",
        "Agency": "",
        "Docket": "",
        "Document number": "",
        "Document type": "",
        "Latest action": bill["latest_action_text"],
        "Matched keywords": ", ".join(json.loads(bill["matched_keywords"])),
        "API URL": bill["api_url"],
    }


def _regulatory_document_row(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "Source": "Regulations.gov",
        "Bill": "",
        "Title": document["title"],
        "Congress": "",
        "Introduced": "",
        "Updated": "",
        "Posted": document["posted_date"],
        "Agency": document["agency_id"],
        "Docket": document["docket_id"],
        "Document number": document["document_id"],
        "Document type": document["document_type"],
        "Latest action": "",
        "Matched keywords": ", ".join(json.loads(document["matched_keywords"])),
        "API URL": document["api_url"],
    }


def _federal_register_document_row(document: dict[str, Any]) -> dict[str, Any]:
    agency_names = json.loads(document["agency_names"]) if document["agency_names"] else []
    return {
        "Source": "Federal Register",
        "Bill": "",
        "Title": document["title"],
        "Congress": "",
        "Introduced": "",
        "Updated": "",
        "Posted": document["publication_date"],
        "Agency": ", ".join(agency_names),
        "Docket": document["docket_id"],
        "Document number": document["document_number"],
        "Document type": document["document_type"],
        "Latest action": document["action"],
        "Matched keywords": ", ".join(json.loads(document["matched_keywords"])),
        "API URL": document["html_url"],
    }


def _refresh_label(refresh_metadata: dict[str, Any] | None) -> str:
    return refresh_metadata["refreshed_at"] if refresh_metadata else "never"


def _split_terms(value: str) -> tuple[str, ...]:
    return tuple(line.strip().strip('"') for line in value.splitlines() if line.strip())


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
