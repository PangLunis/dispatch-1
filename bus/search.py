"""FTS5 search functions for bus records and SDK events.

Also contains payload_text_sql() and sdk_payload_text_sql() — the single
sources of truth for text extraction used by triggers, backfill, and rebuild.
"""
import sqlite3
from dataclasses import dataclass
from typing import Optional


def payload_text_sql(payload_ref: str = "NEW.payload", type_ref: str = "NEW.type") -> str:
    """Generate SQL CASE expression for extracting searchable text from JSON payload.

    Single source of truth for text extraction logic.
    Used by: triggers (migration 002), backfill, and fts-rebuild.
    Changing this requires running `bus fts-rebuild` to reindex.
    """
    return f"""CASE
        WHEN {type_ref} LIKE 'message.%' THEN json_extract({payload_ref}, '$.text')
        WHEN {type_ref} LIKE 'scan.%' THEN json_extract({payload_ref}, '$.summary')
        WHEN {type_ref} LIKE 'session.%' THEN
            COALESCE(json_extract({payload_ref}, '$.contact_name'), '') || ' ' ||
            COALESCE(json_extract({payload_ref}, '$.session_name'), '')
        WHEN {type_ref} LIKE 'health.%' THEN
            COALESCE(json_extract({payload_ref}, '$.status'), '') || ' ' ||
            COALESCE(json_extract({payload_ref}, '$.message'), '')
        ELSE substr({payload_ref}, 1, 4000)
    END"""


def sdk_payload_text_sql(payload_ref: str = "NEW.payload") -> str:
    """Generate SQL expression for extracting searchable text from SDK event payload.

    SDK events have simpler payloads (already text, no per-type extraction needed).
    Single source of truth — used by sdk_events triggers and backfill.
    """
    return f"COALESCE(substr({payload_ref}, 1, 4000), '')"


@dataclass
class SearchResult:
    """A single FTS search result with all metadata."""
    topic: str
    key: Optional[str]
    type: Optional[str]
    source: Optional[str]
    payload_text: str
    timestamp: int  # Unix ms
    partition: int
    offset: int
    rank: float  # BM25 score (lower = more relevant)


@dataclass
class SDKSearchResult:
    """A single SDK event search result."""
    session_name: str
    event_type: str
    tool_name: Optional[str]
    payload_text: str
    chat_id: Optional[str]
    timestamp: int  # Unix ms
    source_id: int
    rank: float


def _quote_fts_value(value: str) -> str:
    """Quote a value for safe use in FTS5 column filters.
    Prevents injection of FTS5 operators (*, +, -, ", etc)."""
    return '"' + value.replace('"', '""') + '"'


def _prepare_query(query: str) -> str:
    """Prepare a user query for FTS5 MATCH.

    If the query contains explicit FTS5 operators (AND, OR, NOT, quotes, *),
    pass it through as-is for power users. Otherwise, quote each token to
    prevent hyphens and special chars from being misinterpreted.
    e.g. "send-sms" becomes '"send-sms"' instead of 'send NOT sms'.
    """
    import re
    # Check for explicit FTS5 operator usage
    if re.search(r'\b(AND|OR|NOT)\b|[*"()]', query):
        return query
    # Simple query — quote each whitespace-separated token
    tokens = query.strip().split()
    return " ".join(_quote_fts_value(t) for t in tokens)


def search_records(conn: sqlite3.Connection, query: str, *,
                   topic: str = None, type: str = None,
                   key: str = None, source: str = None,
                   since_ms: int = None,
                   limit: int = 20) -> list[SearchResult]:
    """Full-text search across bus records (hot + archive) using FTS5 BM25 ranking.

    Args:
        query: Free-text search query. Supports FTS5 syntax (AND, OR, NOT, "phrases").
        topic: Filter by topic (exact match via FTS column filter).
        type: Filter by event type (e.g. "message.in").
        key: Filter by key/chat_id.
        source: Filter by source (imessage/signal/system).
        since_ms: Only results newer than this timestamp (Unix ms).
        limit: Max results (default 20).

    Returns:
        List of SearchResult ordered by BM25 relevance (best first).

    Raises:
        sqlite3.OperationalError: If query contains malformed FTS5 syntax.
    """
    match_parts = []
    if topic:
        match_parts.append(f'topic:{_quote_fts_value(topic)}')
    if type:
        match_parts.append(f'type:{_quote_fts_value(type)}')
    if key:
        match_parts.append(f'key:{_quote_fts_value(key)}')
    if source:
        match_parts.append(f'source:{_quote_fts_value(source)}')

    if query and query.strip():
        match_parts.append(f'payload_text:({_prepare_query(query)})')

    if not match_parts:
        return []

    match_expr = " AND ".join(match_parts)

    sql = """
        SELECT topic, key, type, source, payload_text,
               timestamp, partition, offset_val, rank
        FROM records_fts
        WHERE records_fts MATCH ?
    """
    params: list = [match_expr]

    if since_ms is not None:
        sql += " AND CAST(timestamp AS INTEGER) >= ?"
        params.append(since_ms)

    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [
        SearchResult(
            topic=r[0], key=r[1], type=r[2], source=r[3],
            payload_text=r[4], timestamp=int(r[5]), partition=int(r[6]),
            offset=int(r[7]), rank=float(r[8])
        )
        for r in rows
    ]


def search_sdk_events(conn: sqlite3.Connection, query: str, *,
                      session_name: str = None, event_type: str = None,
                      tool_name: str = None, chat_id: str = None,
                      since_ms: int = None,
                      limit: int = 20) -> list[SDKSearchResult]:
    """Full-text search across SDK events (hot + archive) using FTS5 BM25 ranking."""
    match_parts = []
    if session_name:
        match_parts.append(f'session_name:{_quote_fts_value(session_name)}')
    if event_type:
        match_parts.append(f'event_type:{_quote_fts_value(event_type)}')
    if tool_name:
        match_parts.append(f'tool_name:{_quote_fts_value(tool_name)}')

    if query and query.strip():
        match_parts.append(f'payload_text:({_prepare_query(query)})')

    if not match_parts:
        return []

    match_expr = " AND ".join(match_parts)

    sql = """
        SELECT session_name, event_type, tool_name, payload_text,
               chat_id, timestamp, source_id, rank
        FROM sdk_events_fts
        WHERE sdk_events_fts MATCH ?
    """
    params: list = [match_expr]

    # chat_id is UNINDEXED in FTS5 — this means it's stored but not tokenized,
    # so it can't be used in MATCH expressions but works fine in WHERE clauses.
    if chat_id:
        sql += " AND chat_id = ?"
        params.append(chat_id)

    if since_ms is not None:
        sql += " AND CAST(timestamp AS INTEGER) >= ?"
        params.append(since_ms)

    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [
        SDKSearchResult(
            session_name=r[0], event_type=r[1], tool_name=r[2],
            payload_text=r[3], chat_id=r[4], timestamp=int(r[5]),
            source_id=int(r[6]), rank=float(r[7])
        )
        for r in rows
    ]
