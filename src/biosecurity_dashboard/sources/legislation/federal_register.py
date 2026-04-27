"""FederalRegister.gov API client for Federal Register document ingestion."""

from __future__ import annotations

import html
import json
import re
import socket
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from http.client import IncompleteRead
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from biosecurity_dashboard.sources.legislation.congress import (
    DEFAULT_KEYWORDS,
    DEFAULT_START_DATE,
)


DEFAULT_BASE_URL = "https://www.federalregister.gov/api/v1"
REQUEST_TIMEOUT_SECONDS = 20
REQUEST_RETRIES = 2


class FederalRegisterApiError(RuntimeError):
    """Raised when FederalRegister.gov returns an error or invalid response."""


@dataclass(frozen=True)
class FederalRegisterDocumentSearch:
    """Parameters for Federal Register document ingestion."""

    per_page: int = 1000
    max_pages: int = 1
    max_records: int = 1000
    max_full_text_downloads: int = 1000
    order: str = "newest"
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    start_date: date = DEFAULT_START_DATE
    end_date: date | None = None


def fetch_matching_documents(
    search: FederalRegisterDocumentSearch | None = None,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Fetch Federal Register documents and return keyword matches."""
    search = search or FederalRegisterDocumentSearch()
    end_date = search.end_date or date.today()
    raw_pages: list[dict[str, Any]] = []
    matches_by_id: dict[str, dict[str, Any]] = {}
    total_documents_seen = 0
    full_text_downloads = 0
    errors: list[str] = []
    exhausted_terms: set[str] = set()
    search_terms = build_search_terms(search.keywords)

    for page_number in range(1, search.max_pages + 1):
        active_terms_this_round = 0
        for search_term in search_terms:
            if search_term in exhausted_terms:
                continue
            if (
                total_documents_seen >= search.max_records
                or full_text_downloads >= search.max_full_text_downloads
            ):
                break
            active_terms_this_round += 1
            remaining_records = search.max_records - total_documents_seen
            if remaining_records <= 0:
                break
            try:
                page = _get_json(
                    f"{base_url}/documents.json",
                    {
                        "conditions[term]": search_term,
                        "conditions[publication_date][gte]": search.start_date.isoformat(),
                        "conditions[publication_date][lte]": end_date.isoformat(),
                        "per_page": min(search.per_page, remaining_records),
                        "page": page_number,
                        "order": search.order,
                    },
                )
            except FederalRegisterApiError as exc:
                errors.append(f"{search_term} page {page_number}: {exc}")
                exhausted_terms.add(search_term)
                break
            raw_pages.append(page)
            documents = page.get("results", [])
            if not isinstance(documents, list):
                raise FederalRegisterApiError(
                    "Unexpected FederalRegister.gov response: 'results' was not a list."
                )
            remaining_records = search.max_records - total_documents_seen
            documents = documents[:remaining_records]
            total_documents_seen += len(documents)

            for document in documents:
                if full_text_downloads >= search.max_full_text_downloads:
                    break
                document = enrich_document_with_full_text(document)
                if document.get("selectedTextUrl"):
                    full_text_downloads += 1
                matched_terms = matching_keywords(document, search.keywords)
                if matched_terms:
                    document["matchedKeywords"] = matched_terms
                    matches_by_id[str(document["document_number"])] = document

            if len(documents) < search.per_page:
                exhausted_terms.add(search_term)
        if active_terms_this_round == 0:
            break
        if (
            total_documents_seen >= search.max_records
            or full_text_downloads >= search.max_full_text_downloads
        ):
            break

    matches = list(matches_by_id.values())
    return {
        "metadata": {
            "source": "federalregister.gov",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "per_page": search.per_page,
            "max_pages": search.max_pages,
            "max_records": search.max_records,
            "max_full_text_downloads": search.max_full_text_downloads,
            "full_text_downloads": full_text_downloads,
            "completed": not errors,
            "errors": errors,
            "order": search.order,
            "keywords": list(search.keywords),
            "remote_search_terms": list(search_terms),
            "start_date": search.start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_documents_seen": total_documents_seen,
            "matched_documents": len(matches),
        },
        "matches": matches,
        "raw_pages": raw_pages,
    }


def search_documents(
    term: str,
    start_date: date,
    end_date: date,
    per_page: int = 100,
    max_pages: int = 10,
    base_url: str = DEFAULT_BASE_URL,
) -> list[dict[str, Any]]:
    """Search Federal Register documents by API term and date range."""
    documents: list[dict[str, Any]] = []
    for page_number in range(1, max_pages + 1):
        page = _get_json(
            f"{base_url}/documents.json",
            {
                "conditions[term]": term,
                "conditions[publication_date][gte]": start_date.isoformat(),
                "conditions[publication_date][lte]": end_date.isoformat(),
                "per_page": per_page,
                "page": page_number,
                "order": "newest",
            },
        )
        page_documents = page.get("results", [])
        if not isinstance(page_documents, list):
            raise FederalRegisterApiError(
                "Unexpected FederalRegister.gov response: 'results' was not a list."
            )
        documents.extend(page_documents)
        if len(page_documents) < per_page:
            break
    return documents


def fetch_recent_document(base_url: str = DEFAULT_BASE_URL) -> dict[str, Any]:
    """Fetch one recent Federal Register document."""
    page = _get_json(
        f"{base_url}/documents.json",
        {
            "per_page": 1,
            "page": 1,
            "order": "newest",
        },
    )
    documents = page.get("results", [])
    if not isinstance(documents, list) or not documents:
        raise FederalRegisterApiError("No recent Federal Register documents returned.")
    return enrich_document_with_full_text(documents[0])


def fetch_document(
    document_number: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Fetch one Federal Register document by document number."""
    document = _get_json(f"{base_url}/documents/{document_number}.json", {})
    if not document.get("document_number"):
        raise FederalRegisterApiError(f"No document returned for {document_number}.")
    return enrich_document_with_full_text(document)


def enrich_document_with_full_text(document: dict[str, Any]) -> dict[str, Any]:
    """Attach best-effort full body text to a Federal Register document."""
    text_url = _select_text_url(document)
    if not text_url:
        return {**document, "fullText": "", "selectedTextUrl": ""}
    try:
        full_text = _get_text(text_url)
    except FederalRegisterApiError as exc:
        return {
            **document,
            "fullText": "",
            "selectedTextUrl": text_url,
            "fullTextError": str(exc),
        }
    return {**document, "fullText": full_text, "selectedTextUrl": text_url}


def matching_keywords(document: dict[str, Any], keywords: tuple[str, ...]) -> list[str]:
    """Return keyword expressions that match a Federal Register document."""
    haystack = _document_match_text(document)
    return [keyword for keyword in keywords if _keyword_expression_matches(keyword, haystack)]


def build_or_search_query(keywords: tuple[str, ...]) -> str:
    """Build one broad OR query for the remote search endpoint."""
    terms = []
    for keyword in keywords:
        terms.extend(_keyword_terms(keyword))
    unique_terms = list(dict.fromkeys(term for term in terms if term))
    return " OR ".join(_quote_search_term(term) for term in unique_terms)


def build_search_terms(keywords: tuple[str, ...]) -> tuple[str, ...]:
    """Build individual remote search terms from keyword expressions."""
    terms = []
    for keyword in keywords:
        terms.extend(_keyword_terms(keyword))
    return tuple(dict.fromkeys(term for term in terms if term))


def _document_match_text(document: dict[str, Any]) -> str:
    agencies = document.get("agency_names") or []
    topics = document.get("topics") or []
    parts = [
        document.get("title", ""),
        document.get("abstract", ""),
        document.get("excerpts", ""),
        document.get("action", ""),
        document.get("type", ""),
        document.get("docket_id", ""),
        document.get("fullText", ""),
        " ".join(str(agency) for agency in agencies if agency),
        " ".join(str(topic) for topic in topics if topic),
    ]
    return _clean_text(" ".join(str(part) for part in parts))


def _keyword_expression_matches(keyword: str, haystack: str) -> bool:
    terms = _keyword_terms(keyword)
    return bool(terms) and any(term.casefold() in haystack for term in terms)


def _keyword_terms(keyword: str) -> list[str]:
    return [
        term.strip().strip('"')
        for term in re.split(r"\s+(?:AND|OR)\s+", keyword, flags=re.I)
        if term.strip().strip('"')
    ]


def _quote_search_term(term: str) -> str:
    return f'"{term}"' if " " in term else term


def _clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return re.sub(r"\s+", " ", without_tags).strip().casefold()


def _select_text_url(document: dict[str, Any]) -> str:
    for field_name in (
        "raw_text_url",
        "full_text_xml_url",
        "body_html_url",
        "html_url",
        "pdf_url",
    ):
        value = document.get(field_name)
        if isinstance(value, str) and value:
            return value
    return ""


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    request_url = f"{url}?{urlencode(params)}"
    request = Request(request_url, headers={"User-Agent": "biosecurity-dashboard/0.1"})
    body = _read_request(request, "FederalRegister.gov request")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise FederalRegisterApiError("FederalRegister.gov returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise FederalRegisterApiError("FederalRegister.gov returned an unexpected JSON shape.")
    return parsed


def _get_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "biosecurity-dashboard/0.1"})
    return _read_request(request, "FederalRegister.gov text download")


def _read_request(request: Request, label: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise FederalRegisterApiError(f"{label} failed: {exc.code} {message}") from exc
        except (TimeoutError, socket.timeout, URLError, IncompleteRead) as exc:
            last_error = exc
            if attempt < REQUEST_RETRIES:
                time.sleep(attempt)
                continue
    raise FederalRegisterApiError(f"{label} failed after {REQUEST_RETRIES} attempts: {last_error}")
