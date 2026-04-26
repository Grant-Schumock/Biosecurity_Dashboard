"""Congress.gov API client for legislation ingestion."""

from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://api.congress.gov/v3"
DEFAULT_START_DATE = date(2015, 1, 1)
DEFAULT_CONGRESS_RANGE = tuple(range(114, 120))
DEFAULT_KEYWORDS = (
    "nucleic acid synthesis",
    "synthetic nucleic acids",
    "sequence screening",
    "customer screening",
    "benchtop nucleic acid synthesis",
    "dual use research of concern",
    "DURC",
    "PEPP",
    "pathogens with enhanced pandemic potential",
    "gain-of-function",
    "biosecurity",
    "biosafety",
    "artificial intelligence AND biosecurity",
    "CBRN AND artificial intelligence",
)


class CongressApiError(RuntimeError):
    """Raised when Congress.gov returns an error or invalid response."""


@dataclass(frozen=True)
class CongressBillSearch:
    """Parameters for Congress.gov bill ingestion into the local database."""

    congresses: tuple[int, ...] = DEFAULT_CONGRESS_RANGE
    limit: int = 250
    max_pages_per_congress: int = 200
    sort: str = "updateDate+desc"
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    start_date: date = DEFAULT_START_DATE
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


def fetch_matching_bills(
    api_key: str,
    search: CongressBillSearch | None = None,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Fetch bills, enrich with summaries, and return title/summary keyword matches."""
    search = search or CongressBillSearch()
    end_date = search.end_date or date.today()
    pages: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    total_bills_seen = 0

    for congress in search.congresses:
        for page_number in range(search.max_pages_per_congress):
            offset = page_number * search.limit
            page = _get_json(
                f"{base_url}/bill/{congress}",
                {
                    "api_key": api_key,
                    "format": "json",
                    "limit": search.limit,
                    "offset": offset,
                    "sort": search.sort,
                    "fromDateTime": f"{search.start_date.isoformat()}T00:00:00Z",
                    "toDateTime": f"{end_date.isoformat()}T23:59:59Z",
                },
            )
            pages.append(page)
            page_bills = page.get("bills", [])
            if not isinstance(page_bills, list):
                raise CongressApiError("Unexpected Congress.gov response: 'bills' was not a list.")
            total_bills_seen += len(page_bills)

            for bill in page_bills:
                bill_date = _bill_relevant_date(bill)
                if bill_date is None or bill_date < search.start_date or bill_date > end_date:
                    continue
                enriched_bill = enrich_bill_with_summaries(api_key, bill, base_url=base_url)
                matched_terms = matching_keywords(enriched_bill, search.keywords)
                if matched_terms:
                    enriched_bill["matchedKeywords"] = matched_terms
                    matches.append(enriched_bill)

            if len(page_bills) < search.limit:
                break

    return {
        "metadata": {
            "source": "congress.gov",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "congresses": list(search.congresses),
            "limit": search.limit,
            "max_pages_per_congress": search.max_pages_per_congress,
            "sort": search.sort,
            "keywords": list(search.keywords),
            "start_date": search.start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_bills_seen": total_bills_seen,
            "matched_bills": len(matches),
        },
        "matches": matches,
        "raw_pages": pages,
    }


def enrich_bill_with_summaries(
    api_key: str,
    bill: dict[str, Any],
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Return a bill with Congress.gov summaries attached."""
    bill_type = str(bill.get("type", "")).lower()
    bill_number = str(bill.get("number", ""))
    congress = bill.get("congress")
    if not bill_type or not bill_number or not congress:
        return {**bill, "summaries": []}

    summary_payload = _get_json(
        f"{base_url}/bill/{congress}/{bill_type}/{bill_number}/summaries",
        {"api_key": api_key, "format": "json", "limit": 250},
    )
    summaries = summary_payload.get("summaries", [])
    if not isinstance(summaries, list):
        summaries = []
    return {**bill, "summaries": summaries}


def matching_keywords(bill: dict[str, Any], keywords: tuple[str, ...]) -> list[str]:
    """Return keyword expressions that match the bill title or summary text."""
    haystack = _bill_match_text(bill)
    return [keyword for keyword in keywords if _keyword_expression_matches(keyword, haystack)]


def bill_matches_keywords(bill: dict[str, Any], keywords: tuple[str, ...]) -> bool:
    """Return true when any keyword expression matches the bill title or summary text."""
    return bool(matching_keywords(bill, keywords))


def save_raw_ingest(payload: dict[str, Any], output_dir: Path) -> Path:
    """Save a raw Congress.gov ingestion payload with a timestamped filename."""
    if not payload.get("matches"):
        raise CongressApiError("No matching bills to save.")
    output_dir.mkdir(parents=True, exist_ok=True)
    retrieved_at = payload["metadata"]["retrieved_at"]
    timestamp = retrieved_at.replace(":", "").replace("-", "").split(".")[0]
    output_path = output_dir / f"congress_bills_{timestamp}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def _bill_match_text(bill: dict[str, Any]) -> str:
    parts = [bill.get("title", "")]
    summaries = bill.get("summaries", [])
    if isinstance(summaries, list):
        for summary in summaries:
            if isinstance(summary, dict):
                parts.append(summary.get("text", ""))
    return _clean_text(" ".join(str(part) for part in parts))


def _keyword_expression_matches(keyword: str, haystack: str) -> bool:
    terms = _keyword_terms(keyword)
    return bool(terms) and all(term.casefold() in haystack for term in terms)


def _keyword_terms(keyword: str) -> list[str]:
    return [
        term.strip().strip('"')
        for term in re.split(r"\s+AND\s+", keyword, flags=re.I)
        if term.strip().strip('"')
    ]


def _clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return re.sub(r"\s+", " ", without_tags).strip().casefold()


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
