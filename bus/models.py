"""SQLAlchemy Core table definitions for bus.db.

These serve as typed Python documentation of the schema AND as
Alembic's target metadata for autogenerate (where supported).

NOTE: WITHOUT ROWID tables are defined here for documentation but
excluded from autogenerate via include_object in env.py.
FTS5 virtual tables are NOT defined here (use raw DDL in migrations).
"""
from sqlalchemy import MetaData, Table, Column, Integer, Text, Float

metadata = MetaData()

# ── Tables that support autogenerate ──

topics = Table("topics", metadata,
    Column("name", Text, primary_key=True),
    Column("partitions", Integer, nullable=False, server_default="1"),
    Column("retention_ms", Integer, nullable=False, server_default="604800000"),
    Column("created_at", Integer, nullable=False),
    Column("archive", Integer, nullable=False, server_default="1"),
)

sdk_events = Table("sdk_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", Integer, nullable=False),
    Column("session_name", Text, nullable=False),
    Column("chat_id", Text),
    Column("event_type", Text, nullable=False),
    Column("tool_name", Text),
    Column("tool_use_id", Text),
    Column("duration_ms", Float),
    Column("is_error", Integer, server_default="0"),
    Column("payload", Text),
    Column("num_turns", Integer),
)

sdk_events_archive = Table("sdk_events_archive", metadata,
    Column("id", Integer, nullable=False),
    Column("timestamp", Integer, nullable=False),
    Column("session_name", Text, nullable=False),
    Column("chat_id", Text),
    Column("event_type", Text, nullable=False),
    Column("tool_name", Text),
    Column("tool_use_id", Text),
    Column("duration_ms", Float),
    Column("is_error", Integer, server_default="0"),
    Column("payload", Text),
    Column("num_turns", Integer),
    Column("archived_at", Integer, nullable=False),
)

consumer_groups = Table("consumer_groups", metadata,
    Column("group_id", Text, primary_key=True),
    Column("generation", Integer, nullable=False, server_default="0"),
)

facts = Table("facts", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("contact", Text, nullable=False),
    Column("fact_type", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("details", Text),
    Column("confidence", Text, server_default="high"),
    Column("starts_at", Text),
    Column("ends_at", Text),
    Column("active", Integer, server_default="1"),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text),
    Column("last_confirmed", Text),
    Column("source", Text, nullable=False),
    Column("source_ref", Text),
)

# ── WITHOUT ROWID tables (excluded from autogenerate, hand-written migrations) ──
# Defined here for documentation only. Actual DDL uses WITHOUT ROWID clause.

# records: PRIMARY KEY (topic, partition, offset) WITHOUT ROWID
# records_archive: PRIMARY KEY (topic, partition, offset) WITHOUT ROWID
# consumer_offsets: PRIMARY KEY (group_id, topic, partition) WITHOUT ROWID
# consumer_members: PRIMARY KEY (group_id, consumer_id) WITHOUT ROWID

# ── FTS5 virtual tables (not representable in SQLAlchemy) ──
# records_fts: USING fts5(topic, key, type, source, payload_text, ...)
# sdk_events_fts: USING fts5(session_name, event_type, tool_name, payload_text, ...)

# Tables excluded from autogenerate:
WITHOUT_ROWID_TABLES = {"records", "records_archive", "consumer_offsets", "consumer_members"}
FTS_TABLES = {"records_fts", "sdk_events_fts"}
EXCLUDE_FROM_AUTOGENERATE = WITHOUT_ROWID_TABLES | FTS_TABLES
