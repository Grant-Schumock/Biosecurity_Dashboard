"""Regulations.gov API client for regulatory document ingestion."""

from __future__ import annotations

import html
import json
import os
import re
import socket
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from biosecurity_dashboard.sources.legislation.congress import (
    DEFAULT_KEYWORDS,
    DEFAULT_START_DATE,
)


DEFAULT_BASE_URL = "https://api.regulations.gov/v4"
REQUEST_TIMEOUT_SECONDS = 20
REQUEST_RETRIES = 2


class RegulationsApiError(RuntimeError):
    """Raised when Regulations.gov returns an error or invalid response."""


@dataclass(frozen=True)
class RegulationsDocumentSearch:
    """Parameters for Regulations.gov document ingestion."""

    limit: int = 250
    max_pages: int = 200
    max_records: int = 1000
    max_api_calls: int = 4000
    sort: str = "-postedDate"
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    start_date: date = DEFAULT_START_DATE
    end_date: date | None = None


def get_api_key(env_var: str = "REGULATIONS_API_KEY") -> str:
    """Read the Regulations.gov API key from the environment."""
    api_key = os.environ.get(env_var, "").strip() or _get_windows_user_env(env_var)
    if not api_key:
        raise RegulationsApiError(
            f"{env_var} is not set. Open a new terminal after running setx, "
            "or set it for the current session before running ingestion."
        )
    return api_key


def fetch_matching_documents(
    api_key: str,
    search: RegulationsDocumentSearch | None = None,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Fetch Regulations.gov documents and return keyword matches."""
    search = search or RegulationsDocumentSearch()
    end_date = search.end_date or date.today()
    raw_pages: list[dict[str, Any]] = []
    matches_by_id: dict[str, dict[str, Any]] = {}
    total_documents_seen = 0
    api_calls = 0
    errors: list[str] = []
    exhausted_terms: set[str] = set()
    search_terms = build_search_terms(search.keywords)

    for page_number in range(1, search.max_pages + 1):
        active_terms_this_round = 0
        for search_term in search_terms:
            if search_term in exhausted_terms:
                continue
            active_terms_this_round += 1
            if total_documents_seen >= search.max_records or api_calls >= search.max_api_calls:
                break
            remaining_records = search.max_records - total_documents_seen
            api_calls += 1
            try:
                page = _get_json(
                    f"{base_url}/documents",
                    {
                        "filter[searchTerm]": search_term,
                        "filter[postedDate][ge]": search.start_date.isoformat(),
                        "filter[postedDate][le]": end_date.isoformat(),
                        "page[size]": max(5, min(search.limit, remaining_records)),
                        "page[number]": page_number,
                        "sort": search.sort,
                    },
                    api_key,
                )
            except RegulationsApiError as exc:
                errors.append(f"{search_term} page {page_number}: {exc}")
                exhausted_terms.add(search_term)
                break
            raw_pages.append(page)
            documents = page.get("data", [])
            if not isinstance(documents, list):
                raise RegulationsApiError("Unexpected Regulations.gov response: 'data' was not a list.")
            remaining_records = search.max_records - total_documents_seen
            documents = documents[:remaining_records]
            total_documents_seen += len(documents)

            for document in documents:
                if api_calls >= search.max_api_calls:
                    break
                api_calls += 1
                try:
                    enriched = fetch_document_detail(api_key, document, base_url=base_url)
                except RegulationsApiError as exc:
                    enriched = {**document, "detailError": str(exc)}
                matched_terms = matching_keywords(enriched, search.keywords)
                if matched_terms:
                    enriched["matchedKeywords"] = matched_terms
                    matches_by_id[str(enriched["id"])] = enriched

            if len(documents) < search.limit:
                exhausted_terms.add(search_term)
        if active_terms_this_round == 0:
            break
        if total_documents_seen >= search.max_records or api_calls >= search.max_api_calls:
            break

    matches = list(matches_by_id.values())
    return {
        "metadata": {
            "source": "regulations.gov",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "limit": search.limit,
            "max_pages": search.max_pages,
            "max_records": search.max_records,
            "max_api_calls": search.max_api_calls,
            "api_calls_used": api_calls,
            "completed": not errors,
            "errors": errors,
            "sort": search.sort,
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


def fetch_recent_document(
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Fetch one recent Regulations.gov document and enrich it with details."""
    page = _get_json(
        f"{base_url}/documents",
        {
            "page[size]": 5,
            "page[number]": 1,
            "sort": "-postedDate",
        },
        api_key,
    )
    documents = page.get("data", [])
    if not isinstance(documents, list) or not documents:
        raise RegulationsApiError("No recent Regulations.gov documents returned.")
    return fetch_document_detail(api_key, documents[0], base_url=base_url)


def fetch_document(
    api_key: str,
    document_id: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Fetch one Regulations.gov document by ID."""
    detail = _get_json(f"{base_url}/documents/{document_id}", {}, api_key)
    data = detail.get("data")
    if not isinstance(data, dict):
        raise RegulationsApiError(f"No document returned for {document_id}.")
    return data


def fetch_document_detail(
    api_key: str,
    document: dict[str, Any],
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Fetch a detailed Regulations.gov document record."""
    document_id = document.get("id")
    if not document_id:
        return document
    detail = _get_json(f"{base_url}/documents/{document_id}", {}, api_key)
    data = detail.get("data")
    return data if isinstance(data, dict) else document


def matching_keywords(document: dict[str, Any], keywords: tuple[str, ...]) -> list[str]:
    """Return keyword expressions that match a document title or abstract."""
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
    attributes = document.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}
    parts = [
        attributes.get("title", ""),
        attributes.get("docAbstract", ""),
        attributes.get("subject", ""),
        attributes.get("documentType", ""),
        attributes.get("agencyId", ""),
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


def _get_windows_user_env(env_var: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, env_var)
            return str(value).strip()
    except OSError:
        return ""


def _get_json(url: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    request_url = f"{url}?{urlencode(params)}" if params else url
    request = Request(
        request_url,
        headers={
            "User-Agent": "biosecurity-dashboard/0.1",
            "X-Api-Key": api_key,
        },
    )
    body = _read_request(request, "Regulations.gov request")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RegulationsApiError("Regulations.gov returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise RegulationsApiError("Regulations.gov returned an unexpected JSON shape.")
    return parsed


def _read_request(request: Request, label: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RegulationsApiError(f"{label} failed: {exc.code} {message}") from exc
        except (TimeoutError, socket.timeout, URLError) as exc:
            last_error = exc
            if attempt < REQUEST_RETRIES:
                time.sleep(attempt)
                continue
    raise RegulationsApiError(f"{label} failed after {REQUEST_RETRIES} attempts: {last_error}")
