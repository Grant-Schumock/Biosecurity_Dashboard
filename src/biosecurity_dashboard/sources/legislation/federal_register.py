"""FederalRegister.gov API client for Federal Register document ingestion."""

from __future__ import annotations

import html
import json
import re
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


DEFAULT_BASE_URL = "https://www.federalregister.gov/api/v1"


class FederalRegisterApiError(RuntimeError):
    """Raised when FederalRegister.gov returns an error or invalid response."""


@dataclass(frozen=True)
class FederalRegisterDocumentSearch:
    """Parameters for Federal Register document ingestion."""

    per_page: int = 1000
    max_pages: int = 200
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

    for keyword in search.keywords:
        for page_number in range(1, search.max_pages + 1):
            page = _get_json(
                f"{base_url}/documents.json",
                {
                    "conditions[term]": keyword,
                    "conditions[publication_date][gte]": search.start_date.isoformat(),
                    "conditions[publication_date][lte]": end_date.isoformat(),
                    "per_page": search.per_page,
                    "page": page_number,
                    "order": search.order,
                },
            )
            raw_pages.append(page)
            documents = page.get("results", [])
            if not isinstance(documents, list):
                raise FederalRegisterApiError(
                    "Unexpected FederalRegister.gov response: 'results' was not a list."
                )
            total_documents_seen += len(documents)

            for document in documents:
                matched_terms = matching_keywords(document, search.keywords)
                if matched_terms:
                    document["matchedKeywords"] = matched_terms
                    matches_by_id[str(document["document_number"])] = document

            if len(documents) < search.per_page:
                break

    matches = list(matches_by_id.values())
    return {
        "metadata": {
            "source": "federalregister.gov",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "per_page": search.per_page,
            "max_pages": search.max_pages,
            "order": search.order,
            "keywords": list(search.keywords),
            "start_date": search.start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_documents_seen": total_documents_seen,
            "matched_documents": len(matches),
        },
        "matches": matches,
        "raw_pages": raw_pages,
    }


def matching_keywords(document: dict[str, Any], keywords: tuple[str, ...]) -> list[str]:
    """Return keyword expressions that match a Federal Register document."""
    haystack = _document_match_text(document)
    return [keyword for keyword in keywords if _keyword_expression_matches(keyword, haystack)]


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
        " ".join(str(agency) for agency in agencies if agency),
        " ".join(str(topic) for topic in topics if topic),
    ]
    return _clean_text(" ".join(str(part) for part in parts))


def _keyword_expression_matches(keyword: str, haystack: str) -> bool:
    terms = [term.strip().casefold() for term in re.split(r"\s+AND\s+", keyword, flags=re.I)]
    terms = [term for term in terms if term]
    return bool(terms) and all(term in haystack for term in terms)


def _clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return re.sub(r"\s+", " ", without_tags).strip().casefold()


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    request_url = f"{url}?{urlencode(params)}"
    request = Request(request_url, headers={"User-Agent": "biosecurity-dashboard/0.1"})
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise FederalRegisterApiError(
            f"FederalRegister.gov request failed: {exc.code} {message}"
        ) from exc
    except URLError as exc:
        raise FederalRegisterApiError(f"FederalRegister.gov request failed: {exc.reason}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise FederalRegisterApiError("FederalRegister.gov returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise FederalRegisterApiError("FederalRegister.gov returned an unexpected JSON shape.")
    return parsed
