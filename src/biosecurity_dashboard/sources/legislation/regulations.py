"""Regulations.gov API client for regulatory document ingestion."""

from __future__ import annotations

import html
import json
import os
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


DEFAULT_BASE_URL = "https://api.regulations.gov/v4"


class RegulationsApiError(RuntimeError):
    """Raised when Regulations.gov returns an error or invalid response."""


@dataclass(frozen=True)
class RegulationsDocumentSearch:
    """Parameters for Regulations.gov document ingestion."""

    limit: int = 250
    max_pages: int = 200
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

    for keyword in search.keywords:
        for page_number in range(1, search.max_pages + 1):
            page = _get_json(
                f"{base_url}/documents",
                {
                    "filter[searchTerm]": keyword,
                    "filter[postedDate][ge]": search.start_date.isoformat(),
                    "filter[postedDate][le]": end_date.isoformat(),
                    "page[size]": search.limit,
                    "page[number]": page_number,
                    "sort": search.sort,
                },
                api_key,
            )
            raw_pages.append(page)
            documents = page.get("data", [])
            if not isinstance(documents, list):
                raise RegulationsApiError("Unexpected Regulations.gov response: 'data' was not a list.")
            total_documents_seen += len(documents)

            for document in documents:
                enriched = fetch_document_detail(api_key, document, base_url=base_url)
                matched_terms = matching_keywords(enriched, search.keywords)
                if matched_terms:
                    enriched["matchedKeywords"] = matched_terms
                    matches_by_id[str(enriched["id"])] = enriched

            if len(documents) < search.limit:
                break

    matches = list(matches_by_id.values())
    return {
        "metadata": {
            "source": "regulations.gov",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "limit": search.limit,
            "max_pages": search.max_pages,
            "sort": search.sort,
            "keywords": list(search.keywords),
            "start_date": search.start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_documents_seen": total_documents_seen,
            "matched_documents": len(matches),
        },
        "matches": matches,
        "raw_pages": raw_pages,
    }


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
    terms = [term.strip().casefold() for term in re.split(r"\s+AND\s+", keyword, flags=re.I)]
    terms = [term for term in terms if term]
    return bool(terms) and all(term in haystack for term in terms)


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
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RegulationsApiError(f"Regulations.gov request failed: {exc.code} {message}") from exc
    except URLError as exc:
        raise RegulationsApiError(f"Regulations.gov request failed: {exc.reason}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RegulationsApiError("Regulations.gov returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise RegulationsApiError("Regulations.gov returned an unexpected JSON shape.")
    return parsed
