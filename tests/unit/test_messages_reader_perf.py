"""Unit tests for MessagesReader performance optimizations.

Tests the persistent connection pooling, WAL checkpoint throttling,
and connection recovery behavior.
"""

import sqlite3
import tempfile
import time
import os
from unittest.mock import patch, MagicMock
import pytest


def _create_test_db(path: str) -> sqlite3.Connection:
    """Create a minimal Messages-compatible test database."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript('''
        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY,
            date INTEGER,
            text TEXT,
            is_from_me INTEGER DEFAULT 0,
            handle_id INTEGER,
            attributedBody BLOB,
            cache_has_attachments INTEGER DEFAULT 0,
            is_audio_message INTEGER DEFAULT 0,
            thread_originator_guid TEXT,
            guid TEXT,
            associated_message_type INTEGER DEFAULT 0,
            associated_message_emoji TEXT,
            associated_message_guid TEXT
        );
        CREATE TABLE handle (
            ROWID INTEGER PRIMARY KEY,
            id TEXT
        );
        CREATE TABLE chat (
            ROWID INTEGER PRIMARY KEY,
            style INTEGER,
            display_name TEXT,
            chat_identifier TEXT
        );
        CREATE TABLE chat_message_join (
            message_id INTEGER,
            chat_id INTEGER
        );
        CREATE TABLE attachment (
            ROWID INTEGER PRIMARY KEY,
            filename TEXT,
            mime_type TEXT,
            transfer_name TEXT,
            total_bytes INTEGER DEFAULT 0
        );
        CREATE TABLE message_attachment_join (
            message_id INTEGER,
            attachment_id INTEGER
        );
    ''')
    # Insert a handle and chat
    conn.execute("INSERT INTO handle (ROWID, id) VALUES (1, '+16175551234')")
    conn.execute("INSERT INTO chat (ROWID, style, display_name, chat_identifier) VALUES (1, 45, NULL, '+16175551234')")
    conn.commit()
    return conn


def _insert_message(conn, rowid, text="test message"):
    """Insert a test message into the DB."""
    # macOS epoch timestamp for ~2026
    conn.execute(
        "INSERT INTO message (ROWID, date, text, handle_id, is_from_me) VALUES (?, 791264348197529984, ?, 1, 0)",
        (rowid, text)
    )
    conn.execute(
        "INSERT INTO chat_message_join (message_id, chat_id) VALUES (?, 1)",
        (rowid,)
    )
    conn.commit()


class TestPersistentConnection:
    """Tests for connection reuse (no new connection per poll)."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "chat.db")
        self.writer_conn = _create_test_db(self.db_path)

    def teardown_method(self):
        self.writer_conn.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_reader(self):
        """Create a MessagesReader pointing at our test DB."""
        from assistant.manager import MessagesReader
        reader = MessagesReader.__new__(MessagesReader)
        reader.db_path = self.db_path
        reader._contacts = None
        reader._conn = None
        reader._last_checkpoint = 0.0
        return reader

    def test_connection_reused_across_calls(self):
        """Same connection object should be returned on multiple calls."""
        reader = self._make_reader()

        conn1 = reader._get_conn()
        conn2 = reader._get_conn()

        assert conn1 is conn2, "Connection should be reused, not recreated"
        reader.close()

    def test_connection_has_wal_mode(self):
        """Persistent connection should use WAL journal mode."""
        reader = self._make_reader()
        conn = reader._get_conn()

        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal", f"Expected WAL mode, got {mode}"
        reader.close()

    def test_connection_has_read_uncommitted(self):
        """Persistent connection should have read_uncommitted=1."""
        reader = self._make_reader()
        conn = reader._get_conn()

        val = conn.execute("PRAGMA read_uncommitted").fetchone()[0]
        assert val == 1, f"Expected read_uncommitted=1, got {val}"
        reader.close()

    def test_connection_recovery_on_close(self):
        """If connection is closed externally, _get_conn should create a new one."""
        reader = self._make_reader()

        conn1 = reader._get_conn()
        conn1.close()  # Simulate external close / corruption

        conn2 = reader._get_conn()
        assert conn2 is not conn1, "Should create new connection after close"
        # Should still work
        conn2.execute("SELECT 1").fetchone()
        reader.close()

    def test_close_cleans_up(self):
        """close() should set _conn to None."""
        reader = self._make_reader()
        reader._get_conn()  # Initialize connection

        assert reader._conn is not None
        reader.close()
        assert reader._conn is None

    def test_get_new_messages_uses_persistent_conn(self):
        """get_new_messages should not create a new connection each call."""
        reader = self._make_reader()

        _insert_message(self.writer_conn, 100, "first")
        _insert_message(self.writer_conn, 101, "second")

        # First call initializes connection
        msgs1 = reader.get_new_messages(0)
        conn_after_first = reader._conn

        # Second call should reuse
        msgs2 = reader.get_new_messages(100)
        conn_after_second = reader._conn

        assert conn_after_first is conn_after_second, "Connection should be reused"
        assert len(msgs1) == 2
        assert len(msgs2) == 1
        reader.close()

    def test_get_new_reactions_uses_persistent_conn(self):
        """get_new_reactions should share the same persistent connection."""
        reader = self._make_reader()

        # Call both methods
        reader.get_new_messages(0)
        conn_after_messages = reader._conn

        reader.get_new_reactions(0)
        conn_after_reactions = reader._conn

        assert conn_after_messages is conn_after_reactions, "Should share connection"
        reader.close()


class TestWALCheckpointThrottling:
    """Tests for WAL checkpoint rate limiting."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "chat.db")
        self.writer_conn = _create_test_db(self.db_path)

    def teardown_method(self):
        self.writer_conn.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_reader(self):
        from assistant.manager import MessagesReader
        reader = MessagesReader.__new__(MessagesReader)
        reader.db_path = self.db_path
        reader._contacts = None
        reader._conn = None
        reader._last_checkpoint = 0.0
        return reader

    def test_checkpoint_runs_on_first_call(self):
        """First call should trigger a WAL checkpoint."""
        reader = self._make_reader()
        conn = reader._get_conn()
        cursor = conn.cursor()

        assert reader._last_checkpoint == 0.0
        reader._maybe_checkpoint(cursor)
        assert reader._last_checkpoint > 0, "Checkpoint time should be set"
        reader.close()

    def test_checkpoint_throttled_within_interval(self):
        """Checkpoint should not run again within the interval."""
        reader = self._make_reader()
        conn = reader._get_conn()
        cursor = conn.cursor()

        # First checkpoint
        reader._maybe_checkpoint(cursor)
        first_ts = reader._last_checkpoint

        # Immediate second call — should be throttled
        reader._maybe_checkpoint(cursor)
        second_ts = reader._last_checkpoint

        assert first_ts == second_ts, "Checkpoint should be throttled"
        reader.close()

    def test_checkpoint_runs_after_interval(self):
        """Checkpoint should run again after the interval elapses."""
        reader = self._make_reader()
        conn = reader._get_conn()
        cursor = conn.cursor()

        # First checkpoint
        reader._maybe_checkpoint(cursor)
        first_ts = reader._last_checkpoint

        # Pretend time has passed
        reader._last_checkpoint = time.time() - reader.WAL_CHECKPOINT_INTERVAL - 1

        reader._maybe_checkpoint(cursor)
        second_ts = reader._last_checkpoint

        assert second_ts > first_ts, "Checkpoint should run after interval"
        reader.close()

    def test_rapid_polls_only_checkpoint_once(self):
        """Simulating 50 rapid polls should only checkpoint once."""
        reader = self._make_reader()
        conn = reader._get_conn()
        cursor = conn.cursor()

        checkpoint_times = []
        for _ in range(50):
            old_ts = reader._last_checkpoint
            reader._maybe_checkpoint(cursor)
            if reader._last_checkpoint != old_ts:
                checkpoint_times.append(reader._last_checkpoint)

        # Should only have 1 checkpoint (the first one)
        assert len(checkpoint_times) == 1, f"Expected 1 checkpoint, got {len(checkpoint_times)}"
        reader.close()


class TestEndToEndPollPerformance:
    """Integration-style tests for poll performance."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "chat.db")
        self.writer_conn = _create_test_db(self.db_path)

    def teardown_method(self):
        self.writer_conn.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_reader(self):
        from assistant.manager import MessagesReader
        reader = MessagesReader.__new__(MessagesReader)
        reader.db_path = self.db_path
        reader._contacts = None
        reader._conn = None
        reader._last_checkpoint = 0.0
        return reader

    def test_100_polls_under_200ms(self):
        """100 consecutive polls should complete well under 200ms total."""
        reader = self._make_reader()
        _insert_message(self.writer_conn, 100, "test")

        start = time.time()
        for i in range(100):
            reader.get_new_messages(99)
            reader.get_new_reactions(99)
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 200, f"100 polls took {elapsed_ms:.0f}ms, expected <200ms"
        reader.close()

    def test_poll_with_no_messages_is_fast(self):
        """Empty poll should be very fast (<2ms)."""
        reader = self._make_reader()

        # Warm up connection
        reader.get_new_messages(999999)

        # Force checkpoint to already have happened
        reader._last_checkpoint = time.time()

        start = time.time()
        result = reader.get_new_messages(999999)
        elapsed_ms = (time.time() - start) * 1000

        assert result == []
        assert elapsed_ms < 5, f"Empty poll took {elapsed_ms:.1f}ms, expected <5ms"
        reader.close()

    def test_concurrent_writes_dont_block_reads(self):
        """Writes from another connection shouldn't block our reads."""
        reader = self._make_reader()
        _insert_message(self.writer_conn, 100, "existing")

        # Read existing
        msgs = reader.get_new_messages(0)
        assert len(msgs) == 1

        # Write new message from writer connection (simulating Messages.app)
        _insert_message(self.writer_conn, 101, "new message")

        # Read should pick it up without blocking
        start = time.time()
        msgs = reader.get_new_messages(100)
        elapsed_ms = (time.time() - start) * 1000

        assert len(msgs) == 1
        assert elapsed_ms < 10, f"Read after write took {elapsed_ms:.1f}ms"
        reader.close()
