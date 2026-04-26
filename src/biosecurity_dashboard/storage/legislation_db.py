"""SQLite storage for legislation data."""

from __future__ import annotations

import json
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
                posted_date TEXT,
                comment_start_date TEXT,
                comment_end_date TEXT,
                abstract TEXT,
                matched_keywords TEXT NOT NULL,
                api_url TEXT,
                raw_json TEXT NOT NULL,
                refreshed_at TEXT NOT NULL
            );
            """
        )


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
                    matched_keywords,
                    api_url,
                    raw_json,
                    refreshed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bill_id) DO UPDATE SET
                    title = excluded.title,
                    introduced_date = excluded.introduced_date,
                    update_date = excluded.update_date,
                    latest_action_date = excluded.latest_action_date,
                    latest_action_text = excluded.latest_action_text,
                    summary_text = excluded.summary_text,
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
                    posted_date,
                    comment_start_date,
                    comment_end_date,
                    abstract,
                    matched_keywords,
                    api_url,
                    raw_json,
                    refreshed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    title = excluded.title,
                    document_type = excluded.document_type,
                    agency_id = excluded.agency_id,
                    docket_id = excluded.docket_id,
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
        clauses.append("COALESCE(introduced_date, update_date, latest_action_date) >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("COALESCE(introduced_date, update_date, latest_action_date) <= ?")
        params.append(end_date)
    for keyword in _split_keyword_query(keyword_query):
        clauses.append(
            """
            (
                LOWER(title) LIKE ?
                OR LOWER(COALESCE(summary_text, '')) LIKE ?
                OR LOWER(COALESCE(latest_action_text, '')) LIKE ?
                OR LOWER(matched_keywords) LIKE ?
            )
            """
        )
        like_keyword = f"%{keyword}%"
        params.extend([like_keyword, like_keyword, like_keyword, like_keyword])

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
    return (
        str(document["id"]),
        attributes.get("title", ""),
        attributes.get("documentType", ""),
        attributes.get("agencyId", ""),
        attributes.get("docketId", ""),
        attributes.get("postedDate"),
        attributes.get("commentStartDate"),
        attributes.get("commentEndDate"),
        attributes.get("docAbstract", ""),
        json.dumps(document.get("matchedKeywords", [])),
        links.get("self", ""),
        json.dumps(document, sort_keys=True),
        refreshed_at,
    )
