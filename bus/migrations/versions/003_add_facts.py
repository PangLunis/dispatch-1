"""003_add_facts — Add structured facts table.

Stores extracted facts (travel, events, preferences) per contact.
Facts are extracted nightly, published to the bus, and injected into CLAUDE.md.

Revision ID: 003
Create Date: 2026-03-18
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind().connection.dbapi_connection
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY,
            contact TEXT NOT NULL,
            fact_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            details TEXT,
            confidence TEXT DEFAULT 'high',
            starts_at TEXT,
            ends_at TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            last_confirmed TEXT,
            source TEXT NOT NULL,
            source_ref TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_facts_contact ON facts(contact, fact_type) WHERE active = 1;
        CREATE INDEX IF NOT EXISTS idx_facts_temporal ON facts(starts_at, ends_at) WHERE active = 1;
        CREATE INDEX IF NOT EXISTS idx_facts_type ON facts(fact_type) WHERE active = 1;
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_facts_contact")
    op.execute("DROP INDEX IF EXISTS idx_facts_temporal")
    op.execute("DROP INDEX IF EXISTS idx_facts_type")
    op.execute("DROP TABLE IF EXISTS facts")
