"""001_baseline — Create all tables with IF NOT EXISTS.
Safe for both fresh databases and existing ones with data.

Revision ID: 001
Create Date: 2026-03-18
"""
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Use raw DBAPI connection for multi-statement executescript
    # (SQLAlchemy's execute() only supports single statements)
    conn = op.get_bind().connection.dbapi_connection
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS topics (
            name TEXT PRIMARY KEY,
            partitions INTEGER NOT NULL DEFAULT 1,
            retention_ms INTEGER NOT NULL DEFAULT 604800000,
            created_at INTEGER NOT NULL,
            archive INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS records (
            topic TEXT NOT NULL,
            partition INTEGER NOT NULL,
            offset INTEGER NOT NULL,
            timestamp INTEGER NOT NULL,
            key TEXT,
            type TEXT,
            source TEXT,
            payload TEXT NOT NULL,
            headers TEXT,
            PRIMARY KEY (topic, partition, offset)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS records_archive (
            topic TEXT NOT NULL,
            partition INTEGER NOT NULL,
            offset INTEGER NOT NULL,
            timestamp INTEGER NOT NULL,
            key TEXT,
            type TEXT,
            source TEXT,
            payload TEXT NOT NULL,
            headers TEXT,
            archived_at INTEGER NOT NULL,
            PRIMARY KEY (topic, partition, offset)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS sdk_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            session_name TEXT NOT NULL,
            chat_id TEXT,
            event_type TEXT NOT NULL,
            tool_name TEXT,
            tool_use_id TEXT,
            duration_ms REAL,
            is_error INTEGER DEFAULT 0,
            payload TEXT,
            num_turns INTEGER
        );

        CREATE TABLE IF NOT EXISTS sdk_events_archive (
            id INTEGER NOT NULL,
            timestamp INTEGER NOT NULL,
            session_name TEXT NOT NULL,
            chat_id TEXT,
            event_type TEXT NOT NULL,
            tool_name TEXT,
            tool_use_id TEXT,
            duration_ms REAL,
            is_error INTEGER DEFAULT 0,
            payload TEXT,
            num_turns INTEGER,
            archived_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS consumer_offsets (
            group_id TEXT NOT NULL,
            topic TEXT NOT NULL,
            partition INTEGER NOT NULL,
            committed_offset INTEGER NOT NULL,
            generation INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (group_id, topic, partition)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS consumer_members (
            group_id TEXT NOT NULL,
            consumer_id TEXT NOT NULL,
            generation INTEGER NOT NULL DEFAULT 0,
            assigned_partitions TEXT,
            last_heartbeat INTEGER NOT NULL,
            PRIMARY KEY (group_id, consumer_id)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS consumer_groups (
            group_id TEXT PRIMARY KEY,
            generation INTEGER NOT NULL DEFAULT 0
        );

        -- All indexes
        CREATE INDEX IF NOT EXISTS idx_records_topic_ts ON records(topic, timestamp);
        CREATE INDEX IF NOT EXISTS idx_records_key ON records(topic, key) WHERE key IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_records_type ON records(topic, type) WHERE type IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_records_source ON records(topic, source) WHERE source IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_archive_topic_ts ON records_archive(topic, timestamp);
        CREATE INDEX IF NOT EXISTS idx_archive_type ON records_archive(topic, type) WHERE type IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_archive_key ON records_archive(topic, key) WHERE key IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_archive_archived_at ON records_archive(archived_at);

        CREATE INDEX IF NOT EXISTS idx_sdk_session ON sdk_events(session_name, timestamp);
        CREATE INDEX IF NOT EXISTS idx_sdk_type ON sdk_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_sdk_tool ON sdk_events(tool_name) WHERE tool_name IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_sdk_archive_session ON sdk_events_archive(session_name, timestamp);
        CREATE INDEX IF NOT EXISTS idx_sdk_archive_tool ON sdk_events_archive(tool_name) WHERE tool_name IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_sdk_archive_archived_at ON sdk_events_archive(archived_at);
    """)


def downgrade():
    raise NotImplementedError("Cannot downgrade past baseline — would destroy all data")
