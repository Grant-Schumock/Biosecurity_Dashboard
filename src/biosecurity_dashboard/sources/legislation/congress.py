"""Congress.gov API client for legislation ingestion."""

from __future__ import annotations

import html
import json
import os
import re
import socket
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://api.congress.gov/v3"
REQUEST_TIMEOUT_SECONDS = 20
REQUEST_RETRIES = 2
DEFAULT_START_DATE = date(2015, 1, 1)
DEFAULT_CONGRESS_RANGE = tuple(range(114, 120))
DEFAULT_KEYWORDS = (
    "nucleic acid synthesis",
    "nucleic acid procurement",
    "synthetic nucleic acids",
    "sequence screening",
    "sequence-of-concern",
    "customer screening",
    "benchtop nucleic acid synthesis",
    "benchtop synthesizer",
    "dual use research of concern",
    "DURC",
    "PEPP",
    "pathogens with enhanced pandemic potential",
    "pathogenicity",
    "gain-of-function",
    "biosecurity",
    "biosafety",
    "biodefense",
    "biological incident",
    "bioterrorism",
    "pandemic",
    "public health emergency",
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
    max_bills: int = 1000
    sort: str = "updateDate+desc"
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    start_date: date = DEFAULT_START_DATE
    end_date: date | None = None
    include_full_text: bool = True


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
    """Fetch recent bills, enrich them, and return local keyword matches."""
    search = search or CongressBillSearch()
    end_date = search.end_date or date.today()
    pages: list[dict[str, Any]] = []
    candidate_bills: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    offset = 0

    while len(candidate_bills) < search.max_bills:
        page = _get_json(
            f"{base_url}/bill",
            {
                "api_key": api_key,
                "format": "json",
                "limit": min(search.limit, search.max_bills - len(candidate_bills)),
                "offset": offset,
                "sort": search.sort,
            },
        )
        pages.append(page)
        page_bills = page.get("bills", [])
        if not isinstance(page_bills, list):
            raise CongressApiError("Unexpected Congress.gov response: 'bills' was not a list.")
        candidate_bills.extend(page_bills)
        if len(page_bills) < search.limit:
            break
        offset += search.limit

    for bill in candidate_bills[: search.max_bills]:
        bill_date = _bill_relevant_date(bill)
        if bill_date and (bill_date < search.start_date or bill_date > end_date):
            continue
        try:
            enriched_bill = fetch_bill(
                api_key,
                congress=int(bill["congress"]),
                bill_type=str(bill["type"]),
                bill_number=str(bill["number"]),
                include_full_text=search.include_full_text,
                base_url=base_url,
            )
        except CongressApiError as exc:
            enriched_bill = {**bill, "summaries": [], "fullText": "", "enrichmentError": str(exc)}
        matched_terms = matching_keywords(enriched_bill, search.keywords)
        if matched_terms:
            enriched_bill["matchedKeywords"] = matched_terms
            matches.append(enriched_bill)

    return {
        "metadata": {
            "source": "congress.gov",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "congresses": list(search.congresses),
            "limit": search.limit,
            "max_pages_per_congress": search.max_pages_per_congress,
            "max_bills": search.max_bills,
            "include_full_text": search.include_full_text,
            "sort": search.sort,
            "keywords": list(search.keywords),
            "start_date": search.start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_bills_seen": len(candidate_bills[: search.max_bills]),
            "matched_bills": len(matches),
        },
        "matches": matches,
        "raw_pages": pages,
    }


def fetch_recent_bill(
    api_key: str,
    congress: int = 119,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Fetch one recently updated bill and enrich it with summaries."""
    page = _get_json(
        f"{base_url}/bill/{congress}",
        {
            "api_key": api_key,
            "format": "json",
            "limit": 1,
            "offset": 0,
            "sort": "updateDate+desc",
        },
    )
    bills = page.get("bills", [])
    if not isinstance(bills, list) or not bills:
        raise CongressApiError(f"No recent bills returned for Congress {congress}.")
    return fetch_bill(
        api_key,
        congress=int(bills[0]["congress"]),
        bill_type=str(bills[0]["type"]),
        bill_number=str(bills[0]["number"]),
        include_full_text=True,
        base_url=base_url,
    )


def fetch_bill(
    api_key: str,
    congress: int,
    bill_type: str,
    bill_number: str,
    include_full_text: bool = True,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Fetch one bill by citation and enrich it with summaries and optional full text."""
    normalized_bill_type = bill_type.lower()
    bill_payload = _get_json(
        f"{base_url}/bill/{congress}/{normalized_bill_type}/{bill_number}",
        {"api_key": api_key, "format": "json"},
    )
    bill = bill_payload.get("bill")
    if not isinstance(bill, dict):
        raise CongressApiError(
            f"No bill returned for {congress} {bill_type.upper()} {bill_number}."
        )
    enriched_bill = enrich_bill_with_summaries(api_key, bill, base_url=base_url)
    if include_full_text:
        enriched_bill = enrich_bill_with_full_text(api_key, enriched_bill, base_url=base_url)
    return enriched_bill


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

    try:
        summary_payload = _get_json(
            f"{base_url}/bill/{congress}/{bill_type}/{bill_number}/summaries",
            {"api_key": api_key, "format": "json", "limit": 250},
        )
    except CongressApiError as exc:
        return {**bill, "summaries": [], "summaryError": str(exc)}
    summaries = summary_payload.get("summaries", [])
    if not isinstance(summaries, list):
        summaries = []
    return {**bill, "summaries": summaries}


def enrich_bill_with_full_text(
    api_key: str,
    bill: dict[str, Any],
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Return a bill with best-effort full text metadata and downloaded text attached."""
    bill_type = str(bill.get("type", "")).lower()
    bill_number = str(bill.get("number", ""))
    congress = bill.get("congress")
    if not bill_type or not bill_number or not congress:
        return {**bill, "textVersions": [], "fullText": ""}

    try:
        text_payload = _get_json(
            f"{base_url}/bill/{congress}/{bill_type}/{bill_number}/text",
            {"api_key": api_key, "format": "json"},
        )
    except CongressApiError as exc:
        return {**bill, "textVersions": [], "selectedTextUrl": "", "fullText": "", "fullTextError": str(exc)}
    text_versions = text_payload.get("textVersions", [])
    if not isinstance(text_versions, list):
        text_versions = []
    text_url = _select_text_url(text_versions)
    try:
        full_text = _get_text(text_url) if text_url else ""
    except CongressApiError as exc:
        return {
            **bill,
            "textVersions": text_versions,
            "selectedTextUrl": text_url,
            "fullText": "",
            "fullTextError": str(exc),
        }
    return {
        **bill,
        "textVersions": text_versions,
        "selectedTextUrl": text_url,
        "fullText": full_text,
    }


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
    parts.append(bill.get("fullText", ""))
    return _clean_text(" ".join(str(part) for part in parts))


def _select_text_url(text_versions: list[dict[str, Any]]) -> str:
    if not text_versions:
        return ""
    latest_version = text_versions[0]
    formats = latest_version.get("formats", [])
    if not isinstance(formats, list):
        return ""

    preferred_labels = ("formatted text", "xml", "html", "pdf")
    for preferred_label in preferred_labels:
        for text_format in formats:
            if not isinstance(text_format, dict):
                continue
            label = " ".join(
                str(text_format.get(field_name, ""))
                for field_name in ("type", "name", "format")
            ).casefold()
            if preferred_label in label:
                url = text_format.get("url")
                if isinstance(url, str) and url:
                    return url

    for text_format in formats:
        if isinstance(text_format, dict) and isinstance(text_format.get("url"), str):
            return text_format["url"]
    return ""


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
    body = _read_request(request, "Congress.gov request")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CongressApiError("Congress.gov returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise CongressApiError("Congress.gov returned an unexpected JSON shape.")
    return parsed


def _get_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "biosecurity-dashboard/0.1"})
    body, charset = _read_binary_request(request, "Congress.gov text download")
    return body.decode(charset or "utf-8", errors="replace")


def _read_request(request: Request, label: str) -> str:
    body, charset = _read_binary_request(request, label)
    return body.decode(charset or "utf-8", errors="replace")


def _read_binary_request(request: Request, label: str) -> tuple[bytes, str | None]:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return response.read(), response.headers.get_content_charset()
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise CongressApiError(f"{label} failed: {exc.code} {message}") from exc
        except (TimeoutError, socket.timeout, URLError) as exc:
            last_error = exc
            if attempt < REQUEST_RETRIES:
                time.sleep(attempt)
                continue
    raise CongressApiError(f"{label} failed after {REQUEST_RETRIES} attempts: {last_error}")
