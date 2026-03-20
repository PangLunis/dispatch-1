# Plan: SQLAlchemy + Alembic + FTS5 for Bus & Archive (v4.1)

## Goal
Add versioned schema migrations and FTS5 full-text search across all bus and archive tables. Eventually retire the memory-search daemon.

## Current State
- **bus.db** (~19MB): 8 tables, all hand-written SQL via `sqlite3` module
- **Hot tables**: `records` (23.7K rows), `sdk_events` (17.2K rows)
- **Archive tables**: `records_archive` (0 rows, recently pruned), `sdk_events_archive` (9.2K rows)
- **Schema migrations**: Ad-hoc `_migrate_schema()` with column existence checks
- **No FTS** — only B-tree indexes
- **memory-search daemon**: Separate Bun/TypeScript process with its own SQLite FTS5 DB, HTTP API on port 7890
- **Dependencies**: No SQLAlchemy or Alembic currently. Uses `sqlite3` stdlib only.

## Review History
- v1 (SQLAlchemy + Alembic): Claude 6.0, Gemini 4.4 → combined 5.2/10
- v2 (lightweight runner + FTS): Claude 6.4/10 — flagged DELETE collision during prune, CASE/WHEN duplication
- v3 (MIN(rowid) fix): Claude 8.2/10 — flagged fts_rebuild concurrency, sdk text extraction not centralized
- v3.1: Claude 9.0/10 — fixed all remaining issues
- v4: Switched back to SQLAlchemy + Alembic per Nikhil's preference. Claude 8.6/10 — flagged connection API mismatch, missing env.py CLI fallback
- v4.1 (this version): Fixed connection API (raw DBAPI for executescript), dual-path env.py, default sqlalchemy.url. Claude 9.1/10 ✓

## Architecture Decisions

### 1. SQLAlchemy Core + Alembic

Use SQLAlchemy Core (NOT ORM) for declarative schema definitions + Alembic for versioned migrations.

**SQLAlchemy Core gives us:**
- Typed Python schema definitions as single source of truth
- Industry-standard migration framework (Alembic) that contributors already know
- `autogenerate` works for normal tables (sdk_events, topics, consumer_groups)
- Optional query builder for new search code
- Zero runtime overhead on existing hot paths (raw `sqlite3` continues for writes)

**Autogenerate limitations (documented, not blocking):**
- `WITHOUT ROWID` tables (5 of 8): SQLAlchemy can't express this. Configure Alembic `include_object` to exclude these from autogenerate comparison. Migrations for these are always hand-written with `op.execute()`.
- FTS5 virtual tables: Not detected by autogenerate. Always hand-written with `op.execute()`.
- Result: ~40% of tables get autogenerate support; rest are hand-written. This is standard for SQLite projects with advanced features.

**New dependencies:**
```toml
# In dispatch/pyproject.toml
dependencies = [
    ...existing...,
    "sqlalchemy>=2.0.0",   # Schema definitions (~7MB)
    "alembic>=1.13.0",     # Migration framework (~3MB)
]
```

### `dispatch/bus/models.py` — SQLAlchemy Core Schema

```python
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
```

### Alembic Configuration

**`dispatch/bus/alembic.ini`:**
```ini
[alembic]
script_location = %(here)s/migrations
sqlalchemy.url = sqlite:///%(here)s/../state/bus.db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

**`dispatch/bus/migrations/env.py`:**
```python
from alembic import context
from sqlalchemy import create_engine
from bus.models import metadata, EXCLUDE_FROM_AUTOGENERATE

config = context.config

def include_object(object, name, type_, reflected, compare_to):
    """Exclude WITHOUT ROWID and FTS5 tables from autogenerate."""
    if type_ == "table" and name in EXCLUDE_FROM_AUTOGENERATE:
        return False
    return True

def run_migrations():
    # If connection passed via config.attributes (daemon startup path), use it.
    # Otherwise fall back to sqlalchemy.url from alembic.ini (CLI usage).
    connection = config.attributes.get("connection", None)

    if connection is not None:
        # Daemon startup path: reuse existing connection
        context.configure(
            connection=connection,
            target_metadata=metadata,
            render_as_batch=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        # CLI path: create engine from alembic.ini URL
        url = config.get_main_option("sqlalchemy.url")
        engine = create_engine(url)
        with engine.connect() as conn:
            context.configure(
                connection=conn,
                target_metadata=metadata,
                render_as_batch=True,
                include_object=include_object,
            )
            with context.begin_transaction():
                context.run_migrations()

run_migrations()
```

### 2. Incremental Migration (NOT Big-Bang)

- **Migration 001**: Baseline stamp — creates all tables with `IF NOT EXISTS`. Safe for both fresh and existing databases.
- **Migration 002**: FTS5 tables + INSERT/DELETE triggers + backfill from existing data.

### 3. FTS5 Strategy: Standalone Tables (Internal Content)

**Problem**: `records` and `records_archive` are `WITHOUT ROWID` tables. FTS5 `content=` tables require a rowid-based source table.

**Solution**: Standalone FTS5 tables (no `content=` option). These store their own copy of the indexed text and fully support standard INSERT/UPDATE/DELETE operations.

**Confirmed**: SQLite FTS5 docs explicitly state standalone tables support standard DML: "an FTS5 table may be populated using INSERT, UPDATE or DELETE statements like any other table." The existing `store.ts` memory-search daemon uses this same approach with rowid-based DELETE triggers.

### 4. Unified FTS Across Hot + Archive

One FTS table per data type, spanning both hot and archive:
- `records_fts` covers both `records` and `records_archive`
- `sdk_events_fts` covers both `sdk_events` and `sdk_events_archive`

**Prune collision handling**: When records move from hot → archive, both INSERT (archive) and DELETE (hot) triggers fire within the same transaction. This creates a brief moment where two FTS entries exist for the same source record. The DELETE trigger uses `MIN(rowid)` to always remove the older (hot-created) entry, preserving the newer (archive-created) entry.

### 5. Text Extraction: Single Source of Truth

The JSON payload text extraction logic (CASE/WHEN per event type) is defined ONCE as a Python function that generates the SQL fragment. This prevents the 4+ copies that v2 had:

```python
# In dispatch/bus/search.py
def payload_text_sql(payload_ref: str = "NEW.payload", type_ref: str = "NEW.type") -> str:
    """Generate SQL CASE expression for extracting searchable text from JSON payload.

    Single source of truth — used by triggers and backfill queries.
    Changing this requires rebuilding FTS (bus fts-rebuild).

    Example expanded output (for triggers):
        CASE
            WHEN NEW.type LIKE 'message.%' THEN json_extract(NEW.payload, '$.text')
            WHEN NEW.type LIKE 'scan.%' THEN json_extract(NEW.payload, '$.summary')
            ...
            ELSE substr(NEW.payload, 1, 4000)
        END
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
```

**Assumption**: Records are never UPDATEd in-place. The bus is append-only (INSERT, then eventual DELETE/archive). If this changes, UPDATE triggers would need to be added.

## Detailed Schema

### FTS5 Virtual Tables

```sql
-- Unified FTS for records + records_archive
-- Join-back via (topic, partition, offset_val) composite key
CREATE VIRTUAL TABLE records_fts USING fts5(
    topic,                      -- filterable (also part of join key)
    key,                        -- filterable (chat_id)
    type,                       -- filterable (event type)
    source,                     -- filterable (imessage/signal/system)
    payload_text,               -- the actual searchable content
    timestamp UNINDEXED,        -- for display/sort, not tokenized
    partition UNINDEXED,        -- for join-back
    offset_val UNINDEXED,       -- for join-back (offset is FTS5 reserved word)
    tokenize='porter unicode61'
);

-- Unified FTS for sdk_events + sdk_events_archive
-- Join-back via source_id (original sdk_events.id)
CREATE VIRTUAL TABLE sdk_events_fts USING fts5(
    session_name,               -- filterable
    event_type,                 -- filterable
    tool_name,                  -- filterable
    payload_text,               -- searchable content
    chat_id UNINDEXED,          -- for filtering
    timestamp UNINDEXED,        -- for display/sort
    source_id UNINDEXED,        -- original id for join-back
    tokenize='porter unicode61'
);
```

### Triggers: records

```sql
-- INSERT trigger on records (hot table)
CREATE TRIGGER records_fts_ai AFTER INSERT ON records
BEGIN
    INSERT INTO records_fts(topic, key, type, source, payload_text, timestamp, partition, offset_val)
    VALUES (
        NEW.topic, NEW.key, NEW.type, NEW.source,
        <payload_text_sql(NEW.payload, NEW.type)>,
        NEW.timestamp, NEW.partition, NEW.offset
    );
END;

-- DELETE trigger on records (prune/delete_topic cleanup)
-- Uses MIN(rowid) to remove the OLDEST matching FTS entry.
-- During prune, the archive INSERT trigger fires BEFORE this DELETE trigger
-- (within the same transaction: INSERT archive → DELETE hot). MIN(rowid)
-- ensures we delete the hot-created entry (older), not the archive-created one (newer).
CREATE TRIGGER records_fts_ad AFTER DELETE ON records
BEGIN
    DELETE FROM records_fts WHERE rowid = (
        SELECT MIN(rowid) FROM records_fts
        WHERE topic = OLD.topic AND partition = OLD.partition AND offset_val = OLD.offset
    );
END;

-- INSERT trigger on records_archive
CREATE TRIGGER records_archive_fts_ai AFTER INSERT ON records_archive
BEGIN
    INSERT INTO records_fts(topic, key, type, source, payload_text, timestamp, partition, offset_val)
    VALUES (
        NEW.topic, NEW.key, NEW.type, NEW.source,
        <payload_text_sql(NEW.payload, NEW.type)>,
        NEW.timestamp, NEW.partition, NEW.offset
    );
END;

-- DELETE trigger on records_archive (defense in depth — manual cleanup, GDPR, etc.)
CREATE TRIGGER records_archive_fts_ad AFTER DELETE ON records_archive
BEGIN
    DELETE FROM records_fts WHERE rowid = (
        SELECT MIN(rowid) FROM records_fts
        WHERE topic = OLD.topic AND partition = OLD.partition AND offset_val = OLD.offset
    );
END;
```

### Triggers: sdk_events

```sql
-- INSERT trigger on sdk_events (hot table)
CREATE TRIGGER sdk_events_fts_ai AFTER INSERT ON sdk_events
BEGIN
    INSERT INTO sdk_events_fts(session_name, event_type, tool_name, payload_text, chat_id, timestamp, source_id)
    VALUES (
        NEW.session_name, NEW.event_type, NEW.tool_name,
        {sdk_text_expr},
        NEW.chat_id, NEW.timestamp, NEW.id
    );
END;

-- DELETE trigger on sdk_events (prune cleanup)
-- MIN(rowid) to remove older (hot-created) entry, preserving newer (archive-created) entry.
CREATE TRIGGER sdk_events_fts_ad AFTER DELETE ON sdk_events
BEGIN
    DELETE FROM sdk_events_fts WHERE rowid = (
        SELECT MIN(rowid) FROM sdk_events_fts WHERE source_id = OLD.id
    );
END;

-- INSERT trigger on sdk_events_archive
CREATE TRIGGER sdk_events_archive_fts_ai AFTER INSERT ON sdk_events_archive
BEGIN
    INSERT INTO sdk_events_fts(session_name, event_type, tool_name, payload_text, chat_id, timestamp, source_id)
    VALUES (
        NEW.session_name, NEW.event_type, NEW.tool_name,
        {sdk_text_expr},
        NEW.chat_id, NEW.timestamp, NEW.id
    );
END;

-- DELETE trigger on sdk_events_archive (defense in depth)
CREATE TRIGGER sdk_events_archive_fts_ad AFTER DELETE ON sdk_events_archive
BEGIN
    DELETE FROM sdk_events_fts WHERE rowid = (
        SELECT MIN(rowid) FROM sdk_events_fts WHERE source_id = OLD.id
    );
END;
```

### Prune Flow (Detailed)

Current prune in `Bus.prune()`:
```python
# For topics with archive=1:
INSERT INTO records_archive SELECT ..., ? FROM records WHERE topic=? AND timestamp < ?
DELETE FROM records WHERE topic=? AND timestamp < ?

# For topics with archive=0:
DELETE FROM records WHERE topic=? AND timestamp < ?
```

With FTS triggers (all within same transaction):

**archive=1 (normal prune)**:
1. `INSERT INTO records_archive ...` → fires `records_archive_fts_ai` → adds NEW FTS entry (gets higher rowid)
2. `DELETE FROM records ...` → fires `records_fts_ad` → `MIN(rowid)` removes OLD FTS entry (the hot one)
3. **Net result**: FTS entry replaced (hot → archive), exactly one entry per record.

**archive=0 (no archive, just delete)**:
1. `DELETE FROM records ...` → fires `records_fts_ad` → removes the only matching FTS entry
2. **Net result**: FTS entry removed. No ghost.

**delete_topic (all records removed)**:
1. `DELETE FROM records ...` → fires `records_fts_ad` for each row → removes FTS entries
2. **Net result**: All FTS entries for that topic removed. Clean.

**Manual archive deletion (GDPR, cleanup)**:
1. `DELETE FROM records_archive ...` → fires `records_archive_fts_ad` → removes FTS entry
2. **Net result**: FTS entry removed. No ghost.

### FTS Maintenance

Periodic FTS optimize piggybacked on the existing prune cycle:

```python
def prune(self):
    # ... existing prune logic ...

    # Optimize FTS indexes (merge b-tree segments for query performance)
    # Runs every prune cycle (~every 1000 produces). Fast: <100ms for our data volume.
    try:
        self._conn.execute("INSERT INTO records_fts(records_fts) VALUES('optimize')")
        self._conn.execute("INSERT INTO sdk_events_fts(sdk_events_fts) VALUES('optimize')")
    except Exception:
        pass  # FTS not available yet (pre-migration)
```

### FTS Health Check

```python
def fts_status(self) -> dict:
    """Compare FTS row counts against source tables to detect drift."""
    records_hot = self._conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    records_archive = self._conn.execute("SELECT COUNT(*) FROM records_archive").fetchone()[0]
    records_fts = self._conn.execute("SELECT COUNT(*) FROM records_fts").fetchone()[0]

    sdk_hot = self._conn.execute("SELECT COUNT(*) FROM sdk_events").fetchone()[0]
    sdk_archive = self._conn.execute("SELECT COUNT(*) FROM sdk_events_archive").fetchone()[0]
    sdk_fts = self._conn.execute("SELECT COUNT(*) FROM sdk_events_fts").fetchone()[0]

    return {
        "records": {
            "hot": records_hot, "archive": records_archive, "fts": records_fts,
            "expected": records_hot + records_archive,
            "drift": records_fts - (records_hot + records_archive),
            "healthy": records_fts == records_hot + records_archive,
        },
        "sdk_events": {
            "hot": sdk_hot, "archive": sdk_archive, "fts": sdk_fts,
            "expected": sdk_hot + sdk_archive,
            "drift": sdk_fts - (sdk_hot + sdk_archive),
            "healthy": sdk_fts == sdk_hot + sdk_archive,
        },
    }
```

FTS rebuild drops and recreates from scratch:

```python
def fts_rebuild(self):
    """Drop and recreate FTS indexes from scratch.
    Uses the same logic as migration 002 for table creation + backfill.

    IMPORTANT: Must be run with daemon stopped, or acquires exclusive lock
    to prevent concurrent writes from creating duplicates during backfill.
    """
    from bus.search import payload_text_sql, sdk_payload_text_sql

    # Acquire exclusive lock to prevent concurrent writes during rebuild.
    # This blocks the daemon's writer thread if running, ensuring no new
    # records are inserted between DROP and trigger recreation.
    self._conn.execute("BEGIN EXCLUSIVE")

    try:
        # Drop existing triggers and tables
        for trigger in ["records_fts_ai", "records_fts_ad", "records_archive_fts_ai",
                        "records_archive_fts_ad", "sdk_events_fts_ai", "sdk_events_fts_ad",
                        "sdk_events_archive_fts_ai", "sdk_events_archive_fts_ad"]:
            self._conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        self._conn.execute("DROP TABLE IF EXISTS records_fts")
        self._conn.execute("DROP TABLE IF EXISTS sdk_events_fts")

        # Recreate using shared helper (same code as migration 002)
        _create_fts_tables_and_triggers(self._conn)
        _backfill_fts(self._conn)
        self._conn.commit()  # Releases exclusive lock
    except Exception:
        self._conn.rollback()
        raise
```

Both migration 002 and `fts_rebuild` call the same shared helpers (`_create_fts_tables_and_triggers` and `_backfill_fts`) to avoid code duplication.

## Directory Structure

```
dispatch/bus/
    bus.py              # Unchanged hot paths + add search()/fts_status()/fts_rebuild() methods
    cli.py              # Add search/search-sdk/fts-status/fts-rebuild commands
    models.py           # NEW: SQLAlchemy Core table definitions
    search.py           # NEW: FTS5 search functions + payload_text_sql() helper
    alembic.ini         # NEW: Alembic configuration
    migrations/
        env.py          # NEW: Alembic environment (with include_object for WITHOUT ROWID exclusion)
        script.py.mako  # NEW: Alembic template
        versions/
            001_baseline.py
            002_add_fts5.py
```

## Auto-Migrate on Daemon Start

In `Bus.__init__()`, before `_init_schema()`:

```python
def _run_migrations(self):
    """Run pending Alembic migrations. Called on every daemon start."""
    try:
        from alembic.config import Config
        from alembic import command
        from sqlalchemy import create_engine

        alembic_cfg = Config(str(Path(__file__).parent / "alembic.ini"))
        engine = create_engine(f"sqlite:///{self.db_path}")

        # Pass the engine connection to env.py (avoids creating a second connection)
        with engine.connect() as conn:
            alembic_cfg.attributes["connection"] = conn
            command.upgrade(alembic_cfg, "head")

    except Exception as e:
        logger.error(f"Migration failed (non-fatal, continuing without FTS): {e}")

def __init__(self, db_path: str):
    self.db_path = db_path
    self._conn = self._connect()

    # Run Alembic migrations first
    self._run_migrations()

    # Existing init (becomes no-op once migrations handle everything)
    self._init_schema()
    self._migrate_schema()
```

**Transition plan**: `_init_schema()` and `_migrate_schema()` stay temporarily. Migration 001 uses `IF NOT EXISTS` so it's idempotent alongside old code. Remove old code after 1-2 weeks of stable operation.

## Migration 001: Baseline

```python
"""001_baseline — Create all tables with IF NOT EXISTS.
Safe for both fresh databases and existing ones with data.

Revision ID: 001
Create Date: 2026-03-18
"""
from alembic import op

revision = "001"
down_revision = None

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
```

## Migration 002: Add FTS5

```python
"""002_add_fts5 — Add FTS5 full-text search indexes.
Creates virtual tables, INSERT/DELETE triggers on all 4 source tables,
and backfills existing data.

Revision ID: 002
Create Date: 2026-03-18
"""
from alembic import op
from bus.search import payload_text_sql, sdk_payload_text_sql

revision = "002"
down_revision = "001"


def _create_fts_tables_and_triggers(connection):
    """Create FTS5 virtual tables and all triggers. Shared by migration and fts-rebuild.

    Args:
        connection: A raw sqlite3.Connection (NOT SQLAlchemy Connection).
                    Callers in Alembic context use op.get_bind().connection.dbapi_connection.
                    Callers in Bus context use self._conn directly.
    """

    # Check FTS5 is available
    opts = [r[0] for r in connection.execute("PRAGMA compile_options").fetchall()]
    if "ENABLE_FTS5" not in opts:
        raise RuntimeError("SQLite compiled without FTS5 support")

    text_expr = payload_text_sql("NEW.payload", "NEW.type")
    sdk_text_expr = sdk_payload_text_sql("NEW.payload")

    connection.executescript(f"""
        -- FTS5 virtual tables
        CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
            topic, key, type, source, payload_text,
            timestamp UNINDEXED, partition UNINDEXED, offset_val UNINDEXED,
            tokenize='porter unicode61'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS sdk_events_fts USING fts5(
            session_name, event_type, tool_name, payload_text,
            chat_id UNINDEXED, timestamp UNINDEXED, source_id UNINDEXED,
            tokenize='porter unicode61'
        );

        -- records: INSERT trigger (hot)
        CREATE TRIGGER IF NOT EXISTS records_fts_ai AFTER INSERT ON records
        BEGIN
            INSERT INTO records_fts(topic, key, type, source, payload_text, timestamp, partition, offset_val)
            VALUES (NEW.topic, NEW.key, NEW.type, NEW.source,
                    {text_expr}, NEW.timestamp, NEW.partition, NEW.offset);
        END;

        -- records: DELETE trigger (hot) — MIN(rowid) removes older entry during prune
        CREATE TRIGGER IF NOT EXISTS records_fts_ad AFTER DELETE ON records
        BEGIN
            DELETE FROM records_fts WHERE rowid = (
                SELECT MIN(rowid) FROM records_fts
                WHERE topic = OLD.topic AND partition = OLD.partition AND offset_val = OLD.offset
            );
        END;

        -- records_archive: INSERT trigger
        CREATE TRIGGER IF NOT EXISTS records_archive_fts_ai AFTER INSERT ON records_archive
        BEGIN
            INSERT INTO records_fts(topic, key, type, source, payload_text, timestamp, partition, offset_val)
            VALUES (NEW.topic, NEW.key, NEW.type, NEW.source,
                    {text_expr}, NEW.timestamp, NEW.partition, NEW.offset);
        END;

        -- records_archive: DELETE trigger (defense in depth)
        CREATE TRIGGER IF NOT EXISTS records_archive_fts_ad AFTER DELETE ON records_archive
        BEGIN
            DELETE FROM records_fts WHERE rowid = (
                SELECT MIN(rowid) FROM records_fts
                WHERE topic = OLD.topic AND partition = OLD.partition AND offset_val = OLD.offset
            );
        END;

        -- sdk_events: INSERT trigger (hot)
        CREATE TRIGGER IF NOT EXISTS sdk_events_fts_ai AFTER INSERT ON sdk_events
        BEGIN
            INSERT INTO sdk_events_fts(session_name, event_type, tool_name, payload_text, chat_id, timestamp, source_id)
            VALUES (NEW.session_name, NEW.event_type, NEW.tool_name,
                    {sdk_text_expr},
                    NEW.chat_id, NEW.timestamp, NEW.id);
        END;

        -- sdk_events: DELETE trigger (hot) — MIN(rowid) removes older entry during prune
        CREATE TRIGGER IF NOT EXISTS sdk_events_fts_ad AFTER DELETE ON sdk_events
        BEGIN
            DELETE FROM sdk_events_fts WHERE rowid = (
                SELECT MIN(rowid) FROM sdk_events_fts WHERE source_id = OLD.id
            );
        END;

        -- sdk_events_archive: INSERT trigger
        CREATE TRIGGER IF NOT EXISTS sdk_events_archive_fts_ai AFTER INSERT ON sdk_events_archive
        BEGIN
            INSERT INTO sdk_events_fts(session_name, event_type, tool_name, payload_text, chat_id, timestamp, source_id)
            VALUES (NEW.session_name, NEW.event_type, NEW.tool_name,
                    {sdk_text_expr},
                    NEW.chat_id, NEW.timestamp, NEW.id);
        END;

        -- sdk_events_archive: DELETE trigger (defense in depth)
        CREATE TRIGGER IF NOT EXISTS sdk_events_archive_fts_ad AFTER DELETE ON sdk_events_archive
        BEGIN
            DELETE FROM sdk_events_fts WHERE rowid = (
                SELECT MIN(rowid) FROM sdk_events_fts WHERE source_id = OLD.id
            );
        END;
    """)


def _backfill_fts(connection):
    """Backfill FTS tables from existing data. Shared by migration and fts-rebuild.
    IMPORTANT: Hot tables are backfilled BEFORE archive tables to ensure hot entries
    get lower rowids. This guarantees MIN(rowid) DELETE triggers work correctly."""
    text_expr = payload_text_sql("payload", "type")
    sdk_text = sdk_payload_text_sql("payload")

    # Backfill records (hot)
    connection.execute(f"""
        INSERT INTO records_fts(topic, key, type, source, payload_text, timestamp, partition, offset_val)
        SELECT topic, key, type, source, {text_expr}, timestamp, partition, offset
        FROM records
    """)

    # Backfill records_archive
    connection.execute(f"""
        INSERT INTO records_fts(topic, key, type, source, payload_text, timestamp, partition, offset_val)
        SELECT topic, key, type, source, {text_expr}, timestamp, partition, offset
        FROM records_archive
    """)

    # Backfill sdk_events (hot)
    connection.execute(f"""
        INSERT INTO sdk_events_fts(session_name, event_type, tool_name, payload_text, chat_id, timestamp, source_id)
        SELECT session_name, event_type, tool_name, {sdk_text},
            chat_id, timestamp, id
        FROM sdk_events
    """)

    # Backfill sdk_events_archive
    connection.execute(f"""
        INSERT INTO sdk_events_fts(session_name, event_type, tool_name, payload_text, chat_id, timestamp, source_id)
        SELECT session_name, event_type, tool_name, {sdk_text},
            chat_id, timestamp, id
        FROM sdk_events_archive
    """)

    # Optimize after bulk insert
    connection.execute("INSERT INTO records_fts(records_fts) VALUES('optimize')")
    connection.execute("INSERT INTO sdk_events_fts(sdk_events_fts) VALUES('optimize')")


def upgrade():
    """Run via Alembic. Gets raw DBAPI connection for executescript() support."""
    conn = op.get_bind().connection.dbapi_connection
    _create_fts_tables_and_triggers(conn)
    _backfill_fts(conn)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS records_fts_ai")
    op.execute("DROP TRIGGER IF EXISTS records_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS records_archive_fts_ai")
    op.execute("DROP TRIGGER IF EXISTS records_archive_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS sdk_events_fts_ai")
    op.execute("DROP TRIGGER IF EXISTS sdk_events_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS sdk_events_archive_fts_ai")
    op.execute("DROP TRIGGER IF EXISTS sdk_events_archive_fts_ad")
    op.execute("DROP TABLE IF EXISTS records_fts")
    op.execute("DROP TABLE IF EXISTS sdk_events_fts")
```

## Search API

### `dispatch/bus/search.py`

```python
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
        match_parts.append(f'payload_text:({query})')

    if not match_parts:
        return []

    match_expr = " ".join(match_parts)

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
        match_parts.append(f'payload_text:({query})')

    if not match_parts:
        return []

    match_expr = " ".join(match_parts)

    sql = """
        SELECT session_name, event_type, tool_name, payload_text,
               chat_id, timestamp, source_id, rank
        FROM sdk_events_fts
        WHERE sdk_events_fts MATCH ?
    """
    params: list = [match_expr]

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
```

### CLI Commands (additions to cli.py)

```python
# bus search <query> [--topic TOPIC] [--type TYPE] [--key KEY] [--source SOURCE] [--since DAYS] [--limit N]
search_parser = subparsers.add_parser("search", help="Full-text search across bus records")
search_parser.add_argument("query", help="Search query (FTS5 syntax: AND, OR, NOT, \"phrases\")")
search_parser.add_argument("--topic", help="Filter by topic")
search_parser.add_argument("--type", help="Filter by event type")
search_parser.add_argument("--key", help="Filter by key (chat_id)")
search_parser.add_argument("--source", help="Filter by source")
search_parser.add_argument("--since", type=int, help="Only results from last N days")
search_parser.add_argument("--limit", type=int, default=20, help="Max results")

# bus search-sdk <query> [--session SESSION] [--event-type TYPE] [--tool TOOL] [--chat-id ID] [--since DAYS] [--limit N]
search_sdk_parser = subparsers.add_parser("search-sdk", help="Full-text search across SDK events")
search_sdk_parser.add_argument("query", help="Search query")
search_sdk_parser.add_argument("--session", help="Filter by session name")
search_sdk_parser.add_argument("--event-type", help="Filter by event type")
search_sdk_parser.add_argument("--tool", help="Filter by tool name")
search_sdk_parser.add_argument("--chat-id", help="Filter by chat ID")
search_sdk_parser.add_argument("--since", type=int, help="Only results from last N days")
search_sdk_parser.add_argument("--limit", type=int, default=20, help="Max results")

# bus fts-status — check FTS health
fts_status_parser = subparsers.add_parser("fts-status", help="Check FTS index health and row count drift")

# bus fts-rebuild — rebuild FTS from scratch
fts_rebuild_parser = subparsers.add_parser("fts-rebuild", help="Drop and rebuild FTS indexes from all data")
```

**Error handling in CLI layer:**
```python
def handle_search(args):
    try:
        results = search_records(conn, args.query, topic=args.topic, ...)
    except sqlite3.OperationalError as e:
        if "fts5" in str(e).lower() or "syntax" in str(e).lower():
            print(f"Invalid search query: {e}", file=sys.stderr)
            print("Tip: Use quotes for phrases (\"exact match\"), OR for alternatives", file=sys.stderr)
            sys.exit(1)
        raise
```

### Example Usage

```bash
# Search messages about WebGPU
bus search "WebGPU matmul" --topic messages

# Search what Nikhil said
bus search "deploy" --key "+16175969496" --since 7

# Phrase search
bus search '"buffer pooling"' --topic messages

# Search SDK events for errors
bus search-sdk "error" --event-type error

# Search specific session's tool usage
bus search-sdk "send-sms" --session "imessage/_16175969496" --since 3

# Check FTS health
bus fts-status
# → records: hot=23711 archive=0 fts=23711 drift=0 ✓
# → sdk_events: hot=17246 archive=9168 fts=26414 drift=0 ✓

# Rebuild if drift detected
bus fts-rebuild
```

## Assumptions & Invariants

1. **Records are never UPDATEd in-place.** The bus is append-only (INSERT, then eventual DELETE/archive). If this changes, UPDATE triggers must be added.
2. **Backfill order matters.** Hot records are backfilled before archive records, ensuring hot entries have lower rowids. This guarantees MIN(rowid) DELETE triggers work correctly.
3. **FTS5 is available.** macOS system SQLite ships with FTS5 enabled. Migration 002 checks `PRAGMA compile_options` and fails explicitly if missing.
4. **Triggers fire within the same transaction as the DML.** SQLite guarantees this, which is what makes the INSERT-archive-then-DELETE-hot prune flow atomic for FTS.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| FTS5 on JSON payloads creates noise | Low search quality | Per-type CASE/WHEN extraction via `payload_text_sql()` |
| DB size growth from FTS | ~5MB increase (~25%) | Acceptable; periodic optimize in prune cycle |
| Migration failure on daemon start | Daemon won't start | try/except with logging; fall back to no-FTS mode |
| FTS drift (count mismatch) | Search returns ghosts/misses | `bus fts-status` health check + `bus fts-rebuild` to fix |
| Malformed FTS5 query from user | OperationalError | CLI catches and shows friendly error message |
| MIN(rowid) DELETE during prune | Wrong entry removed | Backfill order guarantees hot entries have lower rowids |
| Concurrent writes during backfill | Lock contention | Runs at daemon start before consumers; no contention |
| New event types not in CASE/WHEN | Falls through to ELSE (raw JSON) | Acceptable degradation; update payload_text_sql + rebuild |

## Implementation Order

1. **Add dependencies** — `sqlalchemy>=2.0.0`, `alembic>=1.13.0` to pyproject.toml, `uv sync`
2. **Create `models.py`** — SQLAlchemy Core table definitions
3. **Create `search.py`** — `payload_text_sql()`, `sdk_payload_text_sql()` + search functions + typed results
4. **Initialize Alembic** — `alembic.ini`, `migrations/env.py` with `include_object` filter
5. **Create `migrations/versions/001_baseline.py`** — idempotent table creation via `op.execute()`
6. **Create `migrations/versions/002_add_fts5.py`** — FTS tables + triggers + backfill
7. **Add `_run_migrations()`** to `Bus.__init__()` — `command.upgrade(cfg, "head")`
8. **Add `search()`/`search_sdk()`/`fts_status()`/`fts_rebuild()`** to `Bus` class
9. **Add CLI commands** — `search`, `search-sdk`, `fts-status`, `fts-rebuild`
10. **Add FTS optimize** to prune cycle
11. **Test**: Fresh DB, existing DB migration, search quality, prune safety, FTS health
12. **Remove `_init_schema()` and `_migrate_schema()`** once Alembic is proven stable
13. **Later**: Retire memory-search daemon once bus FTS proves sufficient

## What This Replaces

- **memory-search daemon** (localhost:7890): Bus FTS replaces its keyword search over message content
- **`memory.py search`**: `bus search` replaces event-based queries
- **Ad-hoc `_migrate_schema()`**: Migration runner replaces all column-existence-check hacks

## What This Does NOT Replace (Yet)

- **File-based indexing** (skills, documents, transcripts) — still in memory-search daemon
- **Vector/semantic search** — FTS5 is keyword-only, no embeddings
- **Memory save/load** — contact-specific memory CRUD stays in memory.py for now

## New Dependencies

```toml
dependencies = [
    ...existing...,
    "sqlalchemy>=2.0.0",   # Schema definitions for Alembic (~7MB)
    "alembic>=1.13.0",     # Migration framework (~3MB)
]
```
