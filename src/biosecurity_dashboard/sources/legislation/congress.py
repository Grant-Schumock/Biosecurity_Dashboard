"""Congress.gov API client for legislation ingestion."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://api.congress.gov/v3"
DEFAULT_CONGRESS = 119
DEFAULT_KEYWORDS = (
    "biosecurity",
    "biodefense",
    "biosafety",
    "pandemic preparedness",
    "infectious disease",
    "public health emergency",
    "pathogen",
    "dual use research",
    "gain of function",
)
DEFAULT_EXCLUDE_KEYWORDS = (
    "animal biosecurity",
    "livestock",
    "poultry",
    "cattle",
    "swine",
    "aquaculture",
    "plant pest",
    "invasive species",
    "weapons supply chain",
    "munitions",
    "ammunition",
    "shipbuilding",
    "semiconductor supply chain",
)


LEGISLATION_CATEGORIES: dict[str, dict[str, tuple[str, ...]]] = {
    "DNA Synthesis": {
        "keywords": (
            "dna synthesis",
            "gene synthesis",
            "synthetic biology",
            "nucleic acid synthesis",
            "sequence screening",
            "screening framework guidance",
        ),
        "exclude_keywords": DEFAULT_EXCLUDE_KEYWORDS,
    },
    "AI x Bio": {
        "keywords": (
            "artificial intelligence biology",
            "ai biosecurity",
            "biological design tools",
            "biotechnology artificial intelligence",
            "computational biology security",
            "dual use artificial intelligence",
        ),
        "exclude_keywords": DEFAULT_EXCLUDE_KEYWORDS,
    },
    "Detection": {
        "keywords": (
            "pathogen detection",
            "biosurveillance",
            "infectious disease surveillance",
            "wastewater surveillance",
            "genomic surveillance",
            "early warning",
        ),
        "exclude_keywords": DEFAULT_EXCLUDE_KEYWORDS,
    },
    "Non-pharmaceutical Interventions": {
        "keywords": (
            "non-pharmaceutical intervention",
            "public health emergency",
            "quarantine",
            "isolation",
            "contact tracing",
            "mask",
            "ventilation",
        ),
        "exclude_keywords": DEFAULT_EXCLUDE_KEYWORDS,
    },
    "Supply Chain": {
        "keywords": (
            "medical supply chain",
            "public health supply chain",
            "pharmaceutical supply chain",
            "personal protective equipment",
            "diagnostic supply",
            "strategic national stockpile",
        ),
        "exclude_keywords": DEFAULT_EXCLUDE_KEYWORDS,
    },
    "Vaccines": {
        "keywords": (
            "vaccine",
            "vaccination",
            "immunization",
            "vaccine development",
            "vaccine manufacturing",
            "pandemic vaccine",
        ),
        "exclude_keywords": DEFAULT_EXCLUDE_KEYWORDS,
    },
}


class CongressApiError(RuntimeError):
    """Raised when Congress.gov returns an error or invalid response."""


@dataclass(frozen=True)
class CongressBillSearch:
    """Parameters for a first-pass Congress.gov bill ingestion."""

    congress: int = DEFAULT_CONGRESS
    limit: int = 100
    max_pages: int = 5
    sort: str = "updateDate+desc"
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    exclude_keywords: tuple[str, ...] = DEFAULT_EXCLUDE_KEYWORDS
    start_date: date | None = None
    end_date: date | None = None


def get_api_key(env_var: str = "CONGRESS_API_KEY") -> str:
    """Read the Congress.gov API key from the environment."""
    api_key = os.environ.get(env_var, "").strip() or _get_windows_user_env(env_var)
    if not api_key:
        raise CongressApiError(
            f"{env_var} is not set. Open a new terminal after running setx, "
            "or set it for the current session before running ingestion."
        )
    return api_key


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


def fetch_recent_bills(
    api_key: str,
    search: CongressBillSearch | None = None,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Fetch recent bills and return both raw pages and locally filtered matches."""
    search = search or CongressBillSearch()
    pages: list[dict[str, Any]] = []
    bills: list[dict[str, Any]] = []

    for page_number in range(search.max_pages):
        offset = page_number * search.limit
        page = _get_json(
            f"{base_url}/bill/{search.congress}",
            {
                "api_key": api_key,
                "format": "json",
                "limit": search.limit,
                "offset": offset,
                "sort": search.sort,
            },
        )
        pages.append(page)
        page_bills = page.get("bills", [])
        if not isinstance(page_bills, list):
            raise CongressApiError("Unexpected Congress.gov response: 'bills' was not a list.")
        bills.extend(page_bills)
        if len(page_bills) < search.limit:
            break

    matches = [bill for bill in bills if bill_matches_search(bill, search)]
    return {
        "metadata": {
            "source": "congress.gov",
            "endpoint": f"{base_url}/bill/{search.congress}",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "congress": search.congress,
            "limit": search.limit,
            "max_pages": search.max_pages,
            "sort": search.sort,
            "keywords": list(search.keywords),
            "exclude_keywords": list(search.exclude_keywords),
            "start_date": search.start_date.isoformat() if search.start_date else None,
            "end_date": search.end_date.isoformat() if search.end_date else None,
            "total_bills_seen": len(bills),
            "matched_bills": len(matches),
        },
        "matches": matches,
        "raw_pages": pages,
    }


def bill_matches_keywords(bill: dict[str, Any], keywords: tuple[str, ...]) -> bool:
    """Return true when a bill's list-level text matches any configured keyword."""
    haystack = _bill_search_text(bill)
    return any(keyword.casefold() in haystack for keyword in keywords)


def bill_matches_search(bill: dict[str, Any], search: CongressBillSearch) -> bool:
    """Return true when a bill matches keywords, exclusions, and date bounds."""
    haystack = _bill_search_text(bill)
    if search.keywords and not any(keyword.casefold() in haystack for keyword in search.keywords):
        return False
    if search.exclude_keywords and any(
        keyword.casefold() in haystack for keyword in search.exclude_keywords
    ):
        return False

    bill_date = _bill_relevant_date(bill)
    if search.start_date and (bill_date is None or bill_date < search.start_date):
        return False
    if search.end_date and (bill_date is None or bill_date > search.end_date):
        return False
    return True


def _bill_search_text(bill: dict[str, Any]) -> str:
    haystack_parts = [
        bill.get("title", ""),
        bill.get("type", ""),
        bill.get("number", ""),
    ]
    latest_action = bill.get("latestAction")
    if isinstance(latest_action, dict):
        haystack_parts.append(latest_action.get("text", ""))
    return " ".join(str(part) for part in haystack_parts).casefold()


def _bill_relevant_date(bill: dict[str, Any]) -> date | None:
    for field_name in ("introducedDate", "updateDate", "updateDateIncludingText"):
        value = bill.get(field_name)
        parsed = _parse_date(value)
        if parsed:
            return parsed
    latest_action = bill.get("latestAction")
    if isinstance(latest_action, dict):
        return _parse_date(latest_action.get("actionDate"))
    return None


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def save_raw_ingest(payload: dict[str, Any], output_dir: Path) -> Path:
    """Save a raw Congress.gov ingestion payload with a timestamped filename."""
    if not payload.get("matches"):
        raise CongressApiError("No matching bills to save.")
    output_dir.mkdir(parents=True, exist_ok=True)
    retrieved_at = payload["metadata"]["retrieved_at"]
    timestamp = retrieved_at.replace(":", "").replace("-", "").split(".")[0]
    congress = payload["metadata"]["congress"]
    output_path = output_dir / f"congress_bills_{congress}_{timestamp}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    request_url = f"{url}?{urlencode(params)}"
    request = Request(request_url, headers={"User-Agent": "biosecurity-dashboard/0.1"})
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise CongressApiError(f"Congress.gov request failed: {exc.code} {message}") from exc
    except URLError as exc:
        raise CongressApiError(f"Congress.gov request failed: {exc.reason}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CongressApiError("Congress.gov returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise CongressApiError("Congress.gov returned an unexpected JSON shape.")
    return parsed
