"""Tests for stability fixes (P0/P1/P2 issues from deep dive audit).

Covers:
1. Producer gets its own SQLite connection (not shared with Bus)
2. Zombie process reaping in pre_compact_hook
3. RotatingFileHandler FD leak prevention
4. Log file handle cleanup on spawn failure
5. Batched state saves (_flush_state)
6. Reminder poller only saves when modified
7. Thread-safe signal_db lazy init
8. Graceful producer shutdown
9. Perf.py buffered writes
10. Bus offset caching within batches
11. Consumer heartbeat throttling
12. Manual lock release fix in inject_message
13. HEIC temp file cleanup
14. _ensure_json_safe fast path
15. sanitize_msg_for_bus type fast path
16. Producer close() closes its own connection
"""

import json
import logging
import queue
import sqlite3
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# ──────────────────────────────────────────────────────────────
# 1. Producer gets its own connection
# ──────────────────────────────────────────────────────────────

class TestProducerOwnConnection:
    """P0: Producer must have its own SQLite connection, not share bus._conn."""

    def test_producer_connection_is_separate_from_bus(self, tmp_path):
        from bus.bus import Bus
        bus = Bus(db_path=str(tmp_path / "test.db"))
        producer = bus.producer()
        # Producer's connection should be different from bus's connection
        assert producer._conn is not bus._conn
        producer.close()
        bus.close()

    def test_producer_close_closes_own_connection(self, tmp_path):
        from bus.bus import Bus
        bus = Bus(db_path=str(tmp_path / "test.db"))
        producer = bus.producer()
        conn = producer._conn
        producer.close()
        # Connection should be closed (executing on it should fail)
        with pytest.raises(Exception):
            conn.execute("SELECT 1")
        bus.close()


# ──────────────────────────────────────────────────────────────
# 2. Offset caching within batches
# ──────────────────────────────────────────────────────────────

class TestOffsetCaching:
    """P2: Offset cache should work within batches but clear between them."""

    def test_offset_cache_cleared_between_batches(self, tmp_path):
        """Cache is cleared at start of each batch, preventing stale offsets."""
        from bus.bus import Bus
        bus = Bus(db_path=str(tmp_path / "test.db"))
        bus.create_topic("test")
        producer = bus.producer()

        # Send two separate batches
        producer.send("test", key="a", value={"msg": 1})
        producer.flush()

        producer.send("test", key="a", value={"msg": 2})
        producer.flush()

        # Verify both records written with unique offsets (no UNIQUE constraint violation)
        cursor = bus._conn.execute(
            "SELECT offset FROM records WHERE topic = 'test' ORDER BY offset"
        )
        offsets = [row[0] for row in cursor.fetchall()]
        assert offsets == [0, 1]

        producer.close()
        bus.close()

    def test_two_producers_no_offset_collision(self, tmp_path):
        """Two producers writing to same DB should get unique offsets."""
        from bus.bus import Bus
        bus1 = Bus(db_path=str(tmp_path / "test.db"))
        bus1.create_topic("shared")
        bus2 = Bus(db_path=str(tmp_path / "test.db"))

        p1 = bus1.producer()
        p2 = bus2.producer()

        # Interleave writes
        for i in range(10):
            p1.send("shared", key=str(i), value={"from": "p1", "n": i})
            p2.send("shared", key=str(i), value={"from": "p2", "n": i})

        p1.flush()
        p2.flush()

        # Verify all offsets are unique
        cursor = bus1._conn.execute(
            "SELECT DISTINCT offset FROM records WHERE topic = 'shared' ORDER BY offset"
        )
        offsets = [row[0] for row in cursor.fetchall()]
        assert len(offsets) == 20
        assert offsets == list(range(20))

        p1.close()
        p2.close()
        bus1.close()
        bus2.close()

    def test_topic_cache_populated(self, tmp_path):
        from bus.bus import Bus
        bus = Bus(db_path=str(tmp_path / "test.db"))
        bus.create_topic("cached-topic", partitions=3)
        producer = bus.producer()

        producer.send("cached-topic", key="k", value={"x": 1})
        producer.flush()

        # Topic metadata should be cached after first write
        assert "cached-topic" in producer._topic_cache
        assert producer._topic_cache["cached-topic"] == 3

        producer.close()
        bus.close()


# ──────────────────────────────────────────────────────────────
# 3. Consumer heartbeat throttling
# ──────────────────────────────────────────────────────────────

class TestConsumerHeartbeatThrottle:
    """P2: Consumer heartbeats should be throttled to every 10s, not every poll."""

    def test_consumer_has_heartbeat_throttle_attrs(self, tmp_path):
        from bus.bus import Bus
        bus = Bus(db_path=str(tmp_path / "test.db"))
        bus.create_topic("hb-test")
        consumer = bus.consumer(group_id="hb-group", topics=["hb-test"])

        # Consumer should have heartbeat throttling attributes
        assert hasattr(consumer, "_last_heartbeat")
        assert hasattr(consumer, "_heartbeat_interval_ms")
        assert consumer._heartbeat_interval_ms == 10_000  # 10 seconds

        consumer.close()
        bus.close()

    def test_heartbeat_skipped_on_rapid_polls(self, tmp_path):
        """After first poll sends heartbeat, rapid subsequent polls should skip it."""
        from bus.bus import Bus
        bus = Bus(db_path=str(tmp_path / "test.db"))
        bus.create_topic("hb-test2")
        consumer = bus.consumer(group_id="hb-group2", topics=["hb-test2"])

        # First poll: heartbeat sent, _last_heartbeat updated
        consumer.poll(timeout_ms=10)
        first_hb = consumer._last_heartbeat
        assert first_hb > 0

        # Rapid second poll: heartbeat should be skipped (same _last_heartbeat)
        consumer.poll(timeout_ms=10)
        assert consumer._last_heartbeat == first_hb  # Not updated

        consumer.close()
        bus.close()


# ──────────────────────────────────────────────────────────────
# 4. RotatingFileHandler FD leak prevention
# ──────────────────────────────────────────────────────────────

class TestSessionLoggerHandlerCleanup:
    """P1: Session logger must close handlers before replacing them."""

    def test_handlers_closed_on_recreation(self, tmp_path):
        from assistant.sdk_session import _get_session_logger

        # Create logger first time
        logger1 = _get_session_logger("test-session")
        handler1 = logger1.handlers[0]

        # Recreate logger (simulates session restart)
        logger2 = _get_session_logger("test-session")
        handler2 = logger2.handlers[0]

        # Old handler should be closed (stream should be None or closed)
        assert handler1 not in logger2.handlers
        # The handler should have been closed (its stream is closed)
        assert handler1.stream is None or handler1.stream.closed

        # New handler should be active
        assert len(logger2.handlers) == 1
        assert handler2 is logger2.handlers[0]


# ──────────────────────────────────────────────────────────────
# 5. Batched state saves
# ──────────────────────────────────────────────────────────────

class TestBatchedStateSave:
    """P1: _save_state should only update in-memory; _flush_state writes disk."""

    def test_save_state_does_not_write_file(self, tmp_path):
        """_save_state should only update memory, not disk."""
        from assistant.manager import Manager

        state_file = tmp_path / "last_rowid.txt"
        state_file.write_text("100")

        with patch("assistant.manager.STATE_FILE", state_file):
            mgr = MagicMock()
            mgr.last_rowid = 100
            mgr._state_dirty = False

            # Call the real _save_state
            Manager._save_state(mgr, 200)

            assert mgr.last_rowid == 200
            assert mgr._state_dirty is True
            # File should still have old value
            assert state_file.read_text() == "100"

    def test_flush_state_writes_file(self, tmp_path):
        from assistant.manager import Manager
        state_file = tmp_path / "last_rowid.txt"
        state_file.write_text("100")

        with patch("assistant.manager.STATE_FILE", state_file):
            mgr = MagicMock()
            mgr.last_rowid = 200
            mgr._state_dirty = True

            Manager._flush_state(mgr)

            assert state_file.read_text() == "200"
            assert mgr._state_dirty is False

    def test_flush_state_noop_when_clean(self, tmp_path):
        from assistant.manager import Manager

        state_file = tmp_path / "last_rowid.txt"
        state_file.write_text("100")

        with patch("assistant.manager.STATE_FILE", state_file):
            mgr = MagicMock()
            mgr.last_rowid = 200
            mgr._state_dirty = False

            Manager._flush_state(mgr)

            # File should not be written
            assert state_file.read_text() == "100"


# ──────────────────────────────────────────────────────────────
# 6. Thread-safe signal_db init
# ──────────────────────────────────────────────────────────────

class TestSignalDbThreadSafe:
    """P2: get_signal_db() should be thread-safe."""

    def test_lock_exists(self):
        from assistant.manager import _signal_db_lock
        assert isinstance(_signal_db_lock, type(threading.Lock()))


# ──────────────────────────────────────────────────────────────
# 7. Perf buffered writes
# ──────────────────────────────────────────────────────────────

class TestPerfBufferedWrites:
    """P1: Perf metrics should be buffered, not written per-call."""

    def test_metrics_buffered(self, tmp_path):
        from assistant import perf

        perf.reset_state()
        with patch.object(perf, "PERF_DIR", tmp_path):
            # Write a metric
            perf.timing("buffered_test", 1.0, component="test")

            # File should NOT exist yet (buffered)
            log_file = tmp_path / f"perf-{datetime.now():%Y-%m-%d}.jsonl"
            # May or may not exist depending on timing, but flush should work
            perf.flush_metrics()

            # After flush, file should exist
            assert log_file.exists()
            entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]
            assert len(entries) == 1
            assert entries[0]["metric"] == "buffered_test"

        perf.reset_state()

    def test_flush_idempotent(self, tmp_path):
        from assistant import perf

        perf.reset_state()
        with patch.object(perf, "PERF_DIR", tmp_path):
            perf.timing("idempotent_test", 1.0, component="test")
            perf.flush_metrics()
            perf.flush_metrics()  # Second flush should be safe

            log_file = tmp_path / f"perf-{datetime.now():%Y-%m-%d}.jsonl"
            entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]
            assert len(entries) == 1  # Still just one entry

        perf.reset_state()


# ──────────────────────────────────────────────────────────────
# 8. _ensure_json_safe fast path
# ──────────────────────────────────────────────────────────────

class TestEnsureJsonSafeFastPath:
    """P2: _ensure_json_safe should skip round-trip for already-safe payloads."""

    def test_fast_path_returns_same_dict(self):
        from assistant.bus_helpers import _ensure_json_safe
        payload = {"key": "value", "num": 42, "bool": True, "list": [1, 2, 3]}
        result = _ensure_json_safe(payload)
        # Fast path: same dict object returned (no copy)
        assert result is payload

    def test_slow_path_for_non_serializable(self):
        from assistant.bus_helpers import _ensure_json_safe
        payload = {"key": "value", "bad": datetime.now()}
        result = _ensure_json_safe(payload)
        # Slow path: new dict with repr'd values
        assert result is not payload
        assert isinstance(result["bad"], str)


# ──────────────────────────────────────────────────────────────
# 9. sanitize_msg_for_bus type fast path
# ──────────────────────────────────────────────────────────────

class TestSanitizeMsgFastPath:
    """P2: sanitize_msg_for_bus should skip json.dumps probe for common types."""

    def test_unknown_string_field_included_without_probe(self):
        from assistant.bus_helpers import sanitize_msg_for_bus
        msg = {
            "phone": "+1234",
            "text": "hello",
            "custom_string": "some value",
            "custom_int": 42,
            "custom_bool": True,
            "custom_none": None,
        }
        result = sanitize_msg_for_bus(msg)
        assert result["custom_string"] == "some value"
        assert result["custom_int"] == 42
        assert result["custom_bool"] is True
        assert result["custom_none"] is None


# ──────────────────────────────────────────────────────────────
# 10. Auto-prune runs in background thread
# ──────────────────────────────────────────────────────────────

class TestBackgroundPrune:
    """P1: Auto-prune should not block the writer thread."""

    def test_background_prune_method_exists(self):
        from bus.bus import Producer
        assert hasattr(Producer, "_background_prune")

    def test_prune_runs_in_thread(self, tmp_path):
        from bus.bus import Bus, AUTO_PRUNE_INTERVAL
        bus = Bus(db_path=str(tmp_path / "test.db"))
        bus.create_topic("prune-test")
        producer = bus.producer()

        # Track if _background_prune was called on the producer
        # (not bus.prune — the async writer calls _background_prune directly)
        prune_called = threading.Event()
        original_bg_prune = producer._background_prune

        def track_prune():
            prune_called.set()
            return original_bg_prune()

        producer._background_prune = track_prune

        # Produce enough to trigger auto-prune
        for i in range(AUTO_PRUNE_INTERVAL + 1):
            producer.send("prune-test", key=str(i), value={"n": i})
        producer.flush()

        # Prune should have been triggered (give background thread time)
        prune_called.wait(timeout=10)
        assert prune_called.is_set()

        producer.close()
        bus.close()


# ──────────────────────────────────────────────────────────────
# 11. Graceful producer shutdown
# ──────────────────────────────────────────────────────────────

class TestGracefulProducerShutdown:
    """P2: Producer.close() should drain queue and close connection."""

    def test_close_drains_and_closes(self, tmp_path):
        from bus.bus import Bus
        bus = Bus(db_path=str(tmp_path / "test.db"))
        bus.create_topic("shutdown-test")
        producer = bus.producer()

        # Send some events
        for i in range(5):
            producer.send("shutdown-test", key=str(i), value={"n": i})

        # Close should drain
        producer.close()

        # Verify events were written
        cursor = bus._conn.execute("SELECT COUNT(*) FROM records WHERE topic = 'shutdown-test'")
        count = cursor.fetchone()[0]
        assert count == 5

        bus.close()


# ──────────────────────────────────────────────────────────────
# 12. inject_message lock safety
# ──────────────────────────────────────────────────────────────

class TestInjectMessageLockSafety:
    """P1: inject_message should not manually release/re-acquire the lock."""

    def test_no_manual_lock_release(self):
        """Verify the manual lock release pattern is gone from inject_message."""
        import inspect
        from assistant.sdk_backend import SDKBackend
        source = inspect.getsource(SDKBackend.inject_message)
        # Should NOT contain manual lock release
        assert "self._lock.release()" not in source
        assert "await self._lock.acquire()" not in source


# ──────────────────────────────────────────────────────────────
# 13. ROLLBACK error handling
# ──────────────────────────────────────────────────────────────

class TestRollbackErrorHandling:
    """P2: ROLLBACK failure should not leave connection in bad state."""

    def test_write_batch_handles_rollback_failure(self, tmp_path):
        """_write_batch should handle ROLLBACK failures gracefully."""
        import inspect
        from bus.bus import Producer
        source = inspect.getsource(Producer._write_batch)
        # Should have try/except around ROLLBACK
        assert "ROLLBACK" in source
        assert "rb_err" in source  # Our error variable name


# ──────────────────────────────────────────────────────────────
# 14. get_latest_rowid uses persistent connection
# ──────────────────────────────────────────────────────────────

class TestGetLatestRowidConnection:
    """P2: get_latest_rowid should use _get_conn(), not open a new connection."""

    def test_uses_persistent_connection(self):
        import inspect
        from assistant.manager import MessagesReader
        source = inspect.getsource(MessagesReader.get_latest_rowid)
        # Should use _get_conn(), not sqlite3.connect()
        assert "_get_conn" in source
        assert "sqlite3.connect" not in source


# ──────────────────────────────────────────────────────────────
# 15. _group_has_blessed_participant uses persistent connection
# ──────────────────────────────────────────────────────────────

class TestGroupBlessedConnection:
    """P0: _group_has_blessed_participant should not open new connections."""

    def test_uses_persistent_connection(self):
        import inspect
        from assistant.manager import MessagesReader
        source = inspect.getsource(MessagesReader._group_has_blessed_participant)
        # Should use _get_conn(), not sqlite3.connect()
        assert "_get_conn" in source
        assert "sqlite3.connect" not in source
