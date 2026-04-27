"""SQLite storage for legislation data."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path("Data/processed/legislation.sqlite")


def initialize_database(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create legislation database tables if they do not exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS bills (
                bill_id TEXT PRIMARY KEY,
                congress INTEGER NOT NULL,
                bill_type TEXT NOT NULL,
                bill_number TEXT NOT NULL,
                title TEXT NOT NULL,
                introduced_date TEXT,
                update_date TEXT,
                latest_action_date TEXT,
                latest_action_text TEXT,
                summary_text TEXT,
                full_text TEXT,
                matched_keywords TEXT NOT NULL,
                api_url TEXT,
                raw_json TEXT NOT NULL,
                refreshed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS refresh_metadata (
                source TEXT PRIMARY KEY,
                refreshed_at TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                total_bills_seen INTEGER NOT NULL,
                matched_bills INTEGER NOT NULL,
                keywords TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS regulatory_documents (
                document_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                document_type TEXT,
                agency_id TEXT,
                docket_id TEXT,
                normalized_docket_id TEXT,
                posted_date TEXT,
                comment_start_date TEXT,
                comment_end_date TEXT,
                abstract TEXT,
                matched_keywords TEXT NOT NULL,
                api_url TEXT,
                raw_json TEXT NOT NULL,
                refreshed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS federal_register_documents (
                document_number TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                document_type TEXT,
                agency_names TEXT,
                docket_id TEXT,
                normalized_docket_id TEXT,
                publication_date TEXT,
                abstract TEXT,
                action TEXT,
                full_text TEXT,
                matched_keywords TEXT NOT NULL,
                html_url TEXT,
                pdf_url TEXT,
                raw_text_url TEXT,
                raw_json TEXT NOT NULL,
                refreshed_at TEXT NOT NULL
            );
            """
        )
        _ensure_column(connection, "regulatory_documents", "normalized_docket_id", "TEXT")
        _ensure_column(connection, "federal_register_documents", "normalized_docket_id", "TEXT")
        _ensure_column(connection, "federal_register_documents", "full_text", "TEXT")
        _ensure_column(connection, "bills", "full_text", "TEXT")


def upsert_congress_payload(payload: dict[str, Any], db_path: Path = DEFAULT_DB_PATH) -> int:
    """Store matched Congress.gov bills and refresh metadata."""
    initialize_database(db_path)
    metadata = payload["metadata"]
    refreshed_at = datetime.now(UTC).isoformat()
    matches = payload.get("matches", [])

    with sqlite3.connect(db_path) as connection:
        for bill in matches:
            connection.execute(
                """
                INSERT INTO bills (
                    bill_id,
                    congress,
                    bill_type,
                    bill_number,
                    title,
                    introduced_date,
                    update_date,
                    latest_action_date,
                    latest_action_text,
                    summary_text,
                    full_text,
                    matched_keywords,
                    api_url,
                    raw_json,
                    refreshed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bill_id) DO UPDATE SET
                    title = excluded.title,
                    introduced_date = excluded.introduced_date,
                    update_date = excluded.update_date,
                    latest_action_date = excluded.latest_action_date,
                    latest_action_text = excluded.latest_action_text,
                    summary_text = excluded.summary_text,
                    full_text = excluded.full_text,
                    matched_keywords = excluded.matched_keywords,
                    api_url = excluded.api_url,
                    raw_json = excluded.raw_json,
                    refreshed_at = excluded.refreshed_at
                """,
                _bill_record(bill, refreshed_at),
            )

        connection.execute(
            """
            INSERT INTO refresh_metadata (
                source,
                refreshed_at,
                start_date,
                end_date,
                total_bills_seen,
                matched_bills,
                keywords
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                refreshed_at = excluded.refreshed_at,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                total_bills_seen = excluded.total_bills_seen,
                matched_bills = excluded.matched_bills,
                keywords = excluded.keywords
            """,
            (
                "congress.gov",
                refreshed_at,
                metadata["start_date"],
                metadata["end_date"],
                metadata["total_bills_seen"],
                metadata["matched_bills"],
                json.dumps(metadata["keywords"]),
            ),
        )
    return len(matches)


def upsert_regulations_payload(payload: dict[str, Any], db_path: Path = DEFAULT_DB_PATH) -> int:
    """Store matched Regulations.gov documents and refresh metadata."""
    initialize_database(db_path)
    metadata = payload["metadata"]
    refreshed_at = datetime.now(UTC).isoformat()
    matches = payload.get("matches", [])

    with sqlite3.connect(db_path) as connection:
        for document in matches:
            connection.execute(
                """
                INSERT INTO regulatory_documents (
                    document_id,
                    title,
                    document_type,
                    agency_id,
                    docket_id,
                    normalized_docket_id,
                    posted_date,
                    comment_start_date,
                    comment_end_date,
                    abstract,
                    matched_keywords,
                    api_url,
                    raw_json,
                    refreshed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    title = excluded.title,
                    document_type = excluded.document_type,
                    agency_id = excluded.agency_id,
                    docket_id = excluded.docket_id,
                    normalized_docket_id = excluded.normalized_docket_id,
                    posted_date = excluded.posted_date,
                    comment_start_date = excluded.comment_start_date,
                    comment_end_date = excluded.comment_end_date,
                    abstract = excluded.abstract,
                    matched_keywords = excluded.matched_keywords,
                    api_url = excluded.api_url,
                    raw_json = excluded.raw_json,
                    refreshed_at = excluded.refreshed_at
                """,
                _regulatory_document_record(document, refreshed_at),
            )

        connection.execute(
            """
            INSERT INTO refresh_metadata (
                source,
                refreshed_at,
                start_date,
                end_date,
                total_bills_seen,
                matched_bills,
                keywords
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                refreshed_at = excluded.refreshed_at,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                total_bills_seen = excluded.total_bills_seen,
                matched_bills = excluded.matched_bills,
                keywords = excluded.keywords
            """,
            (
                "regulations.gov",
                refreshed_at,
                metadata["start_date"],
                metadata["end_date"],
                metadata["total_documents_seen"],
                metadata["matched_documents"],
                json.dumps(metadata["keywords"]),
            ),
        )
    return len(matches)


def upsert_federal_register_payload(payload: dict[str, Any], db_path: Path = DEFAULT_DB_PATH) -> int:
    """Store matched FederalRegister.gov documents and refresh metadata."""
    initialize_database(db_path)
    metadata = payload["metadata"]
    refreshed_at = datetime.now(UTC).isoformat()
    matches = payload.get("matches", [])

    with sqlite3.connect(db_path) as connection:
        for document in matches:
            connection.execute(
                """
                INSERT INTO federal_register_documents (
                    document_number,
                    title,
                    document_type,
                    agency_names,
                    docket_id,
                    normalized_docket_id,
                    publication_date,
                    abstract,
                    action,
                    full_text,
                    matched_keywords,
                    html_url,
                    pdf_url,
                    raw_text_url,
                    raw_json,
                    refreshed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_number) DO UPDATE SET
                    title = excluded.title,
                    document_type = excluded.document_type,
                    agency_names = excluded.agency_names,
                    docket_id = excluded.docket_id,
                    normalized_docket_id = excluded.normalized_docket_id,
                    publication_date = excluded.publication_date,
                    abstract = excluded.abstract,
                    action = excluded.action,
                    full_text = excluded.full_text,
                    matched_keywords = excluded.matched_keywords,
                    html_url = excluded.html_url,
                    pdf_url = excluded.pdf_url,
                    raw_text_url = excluded.raw_text_url,
                    raw_json = excluded.raw_json,
                    refreshed_at = excluded.refreshed_at
                """,
                _federal_register_document_record(document, refreshed_at),
            )

        connection.execute(
            """
            INSERT INTO refresh_metadata (
                source,
                refreshed_at,
                start_date,
                end_date,
                total_bills_seen,
                matched_bills,
                keywords
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                refreshed_at = excluded.refreshed_at,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                total_bills_seen = excluded.total_bills_seen,
                matched_bills = excluded.matched_bills,
                keywords = excluded.keywords
            """,
            (
                "federalregister.gov",
                refreshed_at,
                metadata["start_date"],
                metadata["end_date"],
                metadata["total_documents_seen"],
                metadata["matched_documents"],
                json.dumps(metadata["keywords"]),
            ),
        )
    return len(matches)


def load_bills(
    start_date: str | None = None,
    end_date: str | None = None,
    keyword_query: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Load dashboard-ready bills from SQLite."""
    if not db_path.exists():
        return []
    clauses: list[str] = []
    params: list[str] = []
    if start_date:
        clauses.append("COALESCE(update_date, introduced_date, latest_action_date) >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("COALESCE(update_date, introduced_date, latest_action_date) <= ?")
        params.append(end_date)
    for keyword in _split_keyword_query(keyword_query):
        clauses.append(
            """
            (
                LOWER(title) LIKE ?
                OR LOWER(COALESCE(summary_text, '')) LIKE ?
                OR LOWER(COALESCE(full_text, '')) LIKE ?
                OR LOWER(COALESCE(latest_action_text, '')) LIKE ?
                OR LOWER(matched_keywords) LIKE ?
            )
            """
        )
        like_keyword = f"%{keyword}%"
        params.extend([like_keyword, like_keyword, like_keyword, like_keyword, like_keyword])

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT
                bill_id,
                congress,
                bill_type,
                bill_number,
                title,
                introduced_date,
                update_date,
                latest_action_date,
                latest_action_text,
                summary_text,
                full_text,
                matched_keywords,
                api_url,
                refreshed_at
            FROM bills
            {where_sql}
            ORDER BY COALESCE(update_date, introduced_date, latest_action_date) DESC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def load_grouped_records(
    sources: tuple[str, ...],
    start_date: str | None = None,
    end_date: str | None = None,
    keyword_query: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Load records grouped by normalized docket when possible."""
    records: list[dict[str, Any]] = []
    if "Congress.gov" in sources:
        records.extend(_bill_group_record(bill) for bill in load_bills(start_date, end_date, keyword_query, db_path))
    if "Regulations.gov" in sources:
        records.extend(
            _regulatory_group_record(document)
            for document in load_regulatory_documents(start_date, end_date, keyword_query, db_path)
        )
    if "Federal Register" in sources:
        records.extend(
            _federal_register_group_record(document)
            for document in load_federal_register_documents(start_date, end_date, keyword_query, db_path)
        )

    groups: dict[str, dict[str, Any]] = {}
    for record in records:
        group_key = record["normalized_docket_id"] or f"{record['source']}:{record['record_id']}"
        group = groups.setdefault(
            group_key,
            {
                "group_key": group_key,
                "docket": record["docket_id"],
                "normalized_docket_id": record["normalized_docket_id"],
                "title": record["title"],
                "sources": set(),
                "record_count": 0,
                "latest_date": record["date"],
                "matched_keywords": set(),
                "records": [],
            },
        )
        group["sources"].add(record["source"])
        group["record_count"] += 1
        group["records"].append(record)
        group["matched_keywords"].update(record["matched_keywords"])
        if record["date"] and (not group["latest_date"] or record["date"] > group["latest_date"]):
            group["latest_date"] = record["date"]
            group["title"] = record["title"] or group["title"]
            group["docket"] = record["docket_id"] or group["docket"]

    grouped_records = []
    for group in groups.values():
        group["sources"] = sorted(group["sources"])
        group["matched_keywords"] = sorted(group["matched_keywords"])
        group["records"].sort(key=lambda record: record["date"] or "", reverse=True)
        grouped_records.append(group)
    return sorted(grouped_records, key=lambda group: group["latest_date"] or "", reverse=True)


def _split_keyword_query(keyword_query: str | None) -> list[str]:
    if not keyword_query:
        return []
    return [part.strip().casefold() for part in keyword_query.split() if part.strip()]


def get_last_refresh(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    """Return the most recent Congress.gov refresh metadata."""
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM refresh_metadata WHERE source = ?",
            ("congress.gov",),
        ).fetchone()
    return dict(row) if row else None


def get_refresh_metadata(source: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    """Return refresh metadata for a source."""
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM refresh_metadata WHERE source = ?",
            (source,),
        ).fetchone()
    return dict(row) if row else None


def load_regulatory_documents(
    start_date: str | None = None,
    end_date: str | None = None,
    keyword_query: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Load dashboard-ready Regulations.gov documents from SQLite."""
    if not db_path.exists():
        return []
    clauses: list[str] = []
    params: list[str] = []
    if start_date:
        clauses.append("posted_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("posted_date <= ?")
        params.append(end_date)
    for keyword in _split_keyword_query(keyword_query):
        clauses.append(
            """
            (
                LOWER(title) LIKE ?
                OR LOWER(COALESCE(abstract, '')) LIKE ?
                OR LOWER(COALESCE(document_type, '')) LIKE ?
                OR LOWER(COALESCE(agency_id, '')) LIKE ?
                OR LOWER(matched_keywords) LIKE ?
            )
            """
        )
        like_keyword = f"%{keyword}%"
        params.extend([like_keyword, like_keyword, like_keyword, like_keyword, like_keyword])

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT
                document_id,
                title,
                document_type,
                agency_id,
                docket_id,
                normalized_docket_id,
                posted_date,
                comment_start_date,
                comment_end_date,
                abstract,
                matched_keywords,
                api_url,
                refreshed_at
            FROM regulatory_documents
            {where_sql}
            ORDER BY posted_date DESC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def load_federal_register_documents(
    start_date: str | None = None,
    end_date: str | None = None,
    keyword_query: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Load dashboard-ready Federal Register documents from SQLite."""
    if not db_path.exists():
        return []
    clauses: list[str] = []
    params: list[str] = []
    if start_date:
        clauses.append("publication_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("publication_date <= ?")
        params.append(end_date)
    for keyword in _split_keyword_query(keyword_query):
        clauses.append(
            """
            (
                LOWER(title) LIKE ?
                OR LOWER(COALESCE(abstract, '')) LIKE ?
                OR LOWER(COALESCE(action, '')) LIKE ?
                OR LOWER(COALESCE(full_text, '')) LIKE ?
                OR LOWER(COALESCE(document_type, '')) LIKE ?
                OR LOWER(COALESCE(agency_names, '')) LIKE ?
                OR LOWER(matched_keywords) LIKE ?
            )
            """
        )
        like_keyword = f"%{keyword}%"
        params.extend([like_keyword] * 7)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT
                document_number,
                title,
                document_type,
                agency_names,
                docket_id,
                normalized_docket_id,
                publication_date,
                abstract,
                action,
                full_text,
                matched_keywords,
                html_url,
                pdf_url,
                raw_text_url,
                refreshed_at
            FROM federal_register_documents
            {where_sql}
            ORDER BY publication_date DESC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def normalize_docket_id(value: str | None) -> str:
    """Normalize agency docket numbers across source-specific formatting."""
    if not value:
        return ""
    text = str(value).upper()
    text = re.sub(r"\bDOCKET\s+(?:NO|NUMBER|ID)\.?\b", " ", text)
    text = re.sub(r"\bDOCKET\b", " ", text)
    text = re.sub(r"\bNO\.\b", " ", text)
    docket_like = re.search(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)*-\d{4}-\d{3,}\b", text)
    if docket_like:
        return docket_like.group(0)
    text = re.sub(r"[^A-Z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def _bill_record(bill: dict[str, Any], refreshed_at: str) -> tuple[Any, ...]:
    latest_action = bill.get("latestAction") if isinstance(bill.get("latestAction"), dict) else {}
    congress = int(bill["congress"])
    bill_type = str(bill["type"])
    bill_number = str(bill["number"])
    bill_id = f"{congress}-{bill_type.lower()}-{bill_number}"
    return (
        bill_id,
        congress,
        bill_type,
        bill_number,
        bill.get("title", ""),
        bill.get("introducedDate"),
        bill.get("updateDate") or bill.get("updateDateIncludingText"),
        latest_action.get("actionDate"),
        latest_action.get("text", ""),
        _summary_text(bill),
        bill.get("fullText", ""),
        json.dumps(bill.get("matchedKeywords", [])),
        bill.get("url", ""),
        json.dumps(bill, sort_keys=True),
        refreshed_at,
    )


def _summary_text(bill: dict[str, Any]) -> str:
    summaries = bill.get("summaries", [])
    if not isinstance(summaries, list):
        return ""
    return "\n\n".join(
        str(summary.get("text", ""))
        for summary in summaries
        if isinstance(summary, dict) and summary.get("text")
    )


def _regulatory_document_record(document: dict[str, Any], refreshed_at: str) -> tuple[Any, ...]:
    attributes = document.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}
    links = document.get("links")
    if not isinstance(links, dict):
        links = {}
    docket_id = attributes.get("docketId", "")
    return (
        str(document["id"]),
        attributes.get("title", ""),
        attributes.get("documentType", ""),
        attributes.get("agencyId", ""),
        docket_id,
        normalize_docket_id(docket_id),
        attributes.get("postedDate"),
        attributes.get("commentStartDate"),
        attributes.get("commentEndDate"),
        attributes.get("docAbstract", ""),
        json.dumps(document.get("matchedKeywords", [])),
        links.get("self", ""),
        json.dumps(document, sort_keys=True),
        refreshed_at,
    )


def _federal_register_document_record(
    document: dict[str, Any],
    refreshed_at: str,
) -> tuple[Any, ...]:
    docket_id = _federal_register_docket_id(document)
    return (
        str(document["document_number"]),
        document.get("title", ""),
        document.get("type", ""),
        json.dumps(document.get("agency_names", [])),
        docket_id,
        normalize_docket_id(docket_id),
        document.get("publication_date"),
        document.get("abstract", ""),
        document.get("action", ""),
        document.get("fullText", ""),
        json.dumps(document.get("matchedKeywords", [])),
        document.get("html_url", ""),
        document.get("pdf_url", ""),
        document.get("raw_text_url", ""),
        json.dumps(document, sort_keys=True),
        refreshed_at,
    )


def _federal_register_docket_id(document: dict[str, Any]) -> str:
    docket_id = document.get("docket_id", "")
    if docket_id:
        return str(docket_id)
    docket_ids = document.get("docket_ids", [])
    if isinstance(docket_ids, list) and docket_ids:
        return str(docket_ids[0])
    return ""


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, sql_type: str) -> None:
    columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}")


def _safe_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if item]


def _bill_group_record(bill: dict[str, Any]) -> dict[str, Any]:
    date_value = bill["update_date"] or bill["introduced_date"] or bill["latest_action_date"] or ""
    return {
        "source": "Congress.gov",
        "record_id": bill["bill_id"],
        "title": bill["title"],
        "date": date_value,
        "docket_id": "",
        "normalized_docket_id": "",
        "document_type": "Bill",
        "agency": "",
        "matched_keywords": _safe_json_list(bill["matched_keywords"]),
        "url": bill["api_url"],
        "detail": f"{bill['bill_type']} {bill['bill_number']}",
        "abstract": bill.get("summary_text", ""),
    }


def _regulatory_group_record(document: dict[str, Any]) -> dict[str, Any]:
    docket_id = document["docket_id"] or ""
    normalized_docket_id = document["normalized_docket_id"] or normalize_docket_id(docket_id)
    return {
        "source": "Regulations.gov",
        "record_id": document["document_id"],
        "title": document["title"],
        "date": document["posted_date"] or "",
        "docket_id": docket_id,
        "normalized_docket_id": normalized_docket_id,
        "document_type": document["document_type"],
        "agency": document["agency_id"],
        "matched_keywords": _safe_json_list(document["matched_keywords"]),
        "url": document["api_url"],
        "detail": document["document_id"],
        "abstract": document["abstract"] or "",
    }


def _federal_register_group_record(document: dict[str, Any]) -> dict[str, Any]:
    agency_names = _safe_json_list(document["agency_names"])
    docket_id = document["docket_id"] or ""
    normalized_docket_id = document["normalized_docket_id"] or normalize_docket_id(docket_id)
    return {
        "source": "Federal Register",
        "record_id": document["document_number"],
        "title": document["title"],
        "date": document["publication_date"] or "",
        "docket_id": docket_id,
        "normalized_docket_id": normalized_docket_id,
        "document_type": document["document_type"],
        "agency": ", ".join(agency_names),
        "matched_keywords": _safe_json_list(document["matched_keywords"]),
        "url": document["html_url"],
        "detail": document["document_number"],
        "abstract": document["abstract"] or "",
    }
