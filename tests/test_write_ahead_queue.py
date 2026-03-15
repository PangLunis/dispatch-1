"""
Tests for the write-ahead queue (WAL) system.

Covers:
- inject() write-ahead pattern: bus event before memory queue
- inject() graceful degradation when bus unavailable
- Tuple-based queue format (message_id, text)
- Delivery confirmation after query()
- Sentinel bypass (no WAL for __SHUTDOWN__)
- query_undelivered_messages SQL query
- _is_send_command pattern matching
- Replay logic (dedup, at-most-once, error handling)
"""
import asyncio
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# ── _is_send_command tests ───────────────────────────────────────────

from assistant.sdk_session import _is_send_command


class TestIsSendCommand:
    """Test send command detection."""

    def test_send_sms(self):
        assert _is_send_command('~/.claude/skills/sms-assistant/scripts/send-sms "+1234" "hello"')

    def test_send_signal(self):
        assert _is_send_command('~/.claude/skills/signal/scripts/send-signal "+1234" "hello"')

    def test_send_signal_group(self):
        assert _is_send_command('~/.claude/skills/signal/scripts/send-signal-group "id" "hello"')

    def test_reply(self):
        assert _is_send_command('~/.claude/skills/sms-assistant/scripts/reply "hello"')

    def test_non_send_command(self):
        assert not _is_send_command("ls -la")

    def test_grep_command(self):
        assert not _is_send_command("grep 'hello' file.txt")

    def test_echo_command(self):
        assert not _is_send_command('echo "hello world"')

    def test_empty_command(self):
        assert not _is_send_command("")

    def test_partial_match_not_at_path(self):
        """send-sms in a non-path context should still match (substring)."""
        # This is acceptable — the pattern is in a path-like location
        assert _is_send_command("/scripts/send-sms foo")

    def test_bash_with_pipe(self):
        assert not _is_send_command("cat file.txt | grep pattern")


# ── query_undelivered_messages tests ─────────────────────────────────

from assistant.bus_helpers import query_undelivered_messages


class TestQueryUndeliveredMessages:
    """Test bus query for undelivered messages."""

    @pytest.fixture
    def bus_db(self, tmp_path):
        """Create an in-memory bus DB with the records table."""
        db_path = str(tmp_path / "test_bus.db")
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE records (
                id INTEGER PRIMARY KEY,
                topic TEXT NOT NULL,
                type TEXT NOT NULL,
                key TEXT,
                payload TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                source TEXT
            )
        """)
        conn.execute("CREATE INDEX idx_records_topic_type ON records(topic, type)")
        conn.execute("CREATE INDEX idx_records_topic_key ON records(topic, key)")
        conn.commit()
        conn.close()
        return db_path

    def _insert_record(self, db_path, topic, type_, key, payload, timestamp_ms):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO records (topic, type, key, payload, timestamp, source) VALUES (?, ?, ?, ?, ?, ?)",
            (topic, type_, key, json.dumps(payload), timestamp_ms, "test"),
        )
        conn.commit()
        conn.close()

    def test_no_records_returns_empty(self, bus_db):
        result = query_undelivered_messages(bus_db, "chat123")
        assert result == []

    def test_queued_without_delivered_returned(self, bus_db):
        now_ms = int(time.time() * 1000)
        self._insert_record(bus_db, "messages", "message.queued", "chat123", {
            "message_id": "msg-001",
            "chat_id": "chat123",
            "text": "hello",
            "source": "imessage",
        }, now_ms)

        result = query_undelivered_messages(bus_db, "chat123")
        assert len(result) == 1
        assert result[0]["message_id"] == "msg-001"
        assert result[0]["text"] == "hello"

    def test_delivered_message_excluded(self, bus_db):
        now_ms = int(time.time() * 1000)
        self._insert_record(bus_db, "messages", "message.queued", "chat123", {
            "message_id": "msg-001",
            "chat_id": "chat123",
            "text": "hello",
            "source": "imessage",
        }, now_ms)
        self._insert_record(bus_db, "messages", "message.delivered", "chat123", {
            "message_id": "msg-001",
        }, now_ms + 100)

        result = query_undelivered_messages(bus_db, "chat123")
        assert result == []

    def test_different_chat_id_excluded(self, bus_db):
        now_ms = int(time.time() * 1000)
        self._insert_record(bus_db, "messages", "message.queued", "other_chat", {
            "message_id": "msg-001",
            "text": "hello",
            "source": "imessage",
        }, now_ms)

        result = query_undelivered_messages(bus_db, "chat123")
        assert result == []

    def test_old_messages_excluded(self, bus_db):
        old_ms = int((time.time() - 25 * 3600) * 1000)  # 25 hours ago
        self._insert_record(bus_db, "messages", "message.queued", "chat123", {
            "message_id": "msg-001",
            "text": "hello",
            "source": "imessage",
        }, old_ms)

        result = query_undelivered_messages(bus_db, "chat123")
        assert result == []

    def test_sentinel_messages_filtered(self, bus_db):
        now_ms = int(time.time() * 1000)
        self._insert_record(bus_db, "messages", "message.queued", "chat123", {
            "message_id": "msg-001",
            "text": "__SHUTDOWN__",
            "source": "imessage",
        }, now_ms)

        result = query_undelivered_messages(bus_db, "chat123")
        assert result == []

    def test_multiple_undelivered_ordered_by_time(self, bus_db):
        now_ms = int(time.time() * 1000)
        self._insert_record(bus_db, "messages", "message.queued", "chat123", {
            "message_id": "msg-002",
            "text": "second",
            "source": "imessage",
        }, now_ms + 100)
        self._insert_record(bus_db, "messages", "message.queued", "chat123", {
            "message_id": "msg-001",
            "text": "first",
            "source": "imessage",
        }, now_ms)

        result = query_undelivered_messages(bus_db, "chat123")
        assert len(result) == 2
        assert result[0]["text"] == "first"
        assert result[1]["text"] == "second"

    def test_partial_delivery_returns_only_undelivered(self, bus_db):
        now_ms = int(time.time() * 1000)
        self._insert_record(bus_db, "messages", "message.queued", "chat123", {
            "message_id": "msg-001",
            "text": "delivered",
            "source": "imessage",
        }, now_ms)
        self._insert_record(bus_db, "messages", "message.queued", "chat123", {
            "message_id": "msg-002",
            "text": "undelivered",
            "source": "imessage",
        }, now_ms + 100)
        self._insert_record(bus_db, "messages", "message.delivered", "chat123", {
            "message_id": "msg-001",
        }, now_ms + 200)

        result = query_undelivered_messages(bus_db, "chat123")
        assert len(result) == 1
        assert result[0]["message_id"] == "msg-002"

    def test_custom_max_age(self, bus_db):
        """Messages within custom max_age should be returned."""
        two_hours_ago_ms = int((time.time() - 2 * 3600) * 1000)
        self._insert_record(bus_db, "messages", "message.queued", "chat123", {
            "message_id": "msg-001",
            "text": "hello",
            "source": "imessage",
        }, two_hours_ago_ms)

        # 1 hour max_age should exclude it
        result = query_undelivered_messages(bus_db, "chat123", max_age_hours=1)
        assert result == []

        # 3 hour max_age should include it
        result = query_undelivered_messages(bus_db, "chat123", max_age_hours=3)
        assert len(result) == 1


# ── inject() WAL tests ──────────────────────────────────────────────

@pytest.mark.asyncio
class TestInjectWriteAhead:
    """Test inject() write-ahead pattern."""

    async def test_inject_puts_tuple_in_queue(self, sdk_session):
        """inject() should put (message_id, text) tuple in queue."""
        await sdk_session.start()
        await sdk_session.inject("test message")
        # Give run_loop time to dequeue
        await asyncio.sleep(0.2)
        # The mock client should have received the message
        assert sdk_session._client._queries == ["test message"]

    async def test_inject_sentinel_has_none_id(self, sdk_session):
        """Sentinel messages should have None message_id."""
        # Don't start — just test the queue directly
        await sdk_session.inject("__SHUTDOWN__")
        msg_id, text = sdk_session._message_queue.get_nowait()
        assert msg_id is None
        assert text == "__SHUTDOWN__"

    async def test_inject_normal_has_uuid_id(self, sdk_session):
        """Normal messages should have a UUID message_id."""
        # Put directly without starting (avoid run_loop consuming it)
        await sdk_session.inject("hello")
        msg_id, text = sdk_session._message_queue.get_nowait()
        assert msg_id is not None
        assert len(msg_id) == 36  # UUID format
        assert text == "hello"

    async def test_inject_with_producer_emits_queued_event(self, sdk_session):
        """inject() should emit message.queued when producer is available."""
        mock_producer = MagicMock()
        sdk_session._producer = mock_producer

        with patch("assistant.sdk_session.produce_event") as mock_produce:
            await sdk_session.inject("hello")

            mock_produce.assert_called_once()
            args = mock_produce.call_args
            assert args[0][1] == "messages"  # topic
            assert args[0][2] == "message.queued"  # type
            payload = args[0][3]
            assert payload["text"] == "hello"
            assert "message_id" in payload
            assert payload["chat_id"] == sdk_session.chat_id

    async def test_inject_without_producer_still_queues(self, sdk_session):
        """inject() should work without a producer (graceful degradation)."""
        sdk_session._producer = None
        await sdk_session.inject("hello")
        msg_id, text = sdk_session._message_queue.get_nowait()
        assert text == "hello"

    async def test_inject_bus_failure_non_fatal(self, sdk_session):
        """Bus write failure should not prevent message from being queued."""
        mock_producer = MagicMock()
        sdk_session._producer = mock_producer

        with patch("assistant.sdk_session.produce_event", side_effect=Exception("bus down")):
            await sdk_session.inject("hello")

        # Message should still be in queue
        msg_id, text = sdk_session._message_queue.get_nowait()
        assert text == "hello"

    async def test_sentinel_skips_wal(self, sdk_session):
        """Sentinel messages should NOT emit bus events."""
        mock_producer = MagicMock()
        sdk_session._producer = mock_producer

        with patch("assistant.sdk_session.produce_event") as mock_produce:
            await sdk_session.inject("__SHUTDOWN__")
            mock_produce.assert_not_called()


# ── Delivery confirmation tests ──────────────────────────────────────

@pytest.mark.asyncio
class TestDeliveryConfirmation:
    """Test that _run_loop emits message.delivered after successful query."""

    async def test_delivery_event_after_query(self, sdk_session):
        """After successful query(), message.delivered should be emitted."""
        mock_producer = MagicMock()
        sdk_session._producer = mock_producer

        await sdk_session.start()

        produced_events = []

        def capture_event(*args, **kwargs):
            produced_events.append(args)

        with patch("assistant.sdk_session.produce_event", side_effect=capture_event):
            await sdk_session.inject("hello")
            await asyncio.sleep(0.5)

        # Should have both queued and delivered events
        queued = [e for e in produced_events if e[2] == "message.queued"]
        delivered = [e for e in produced_events if e[2] == "message.delivered"]
        assert len(queued) == 1
        assert len(delivered) == 1
        assert delivered[0][3]["message_id"] == queued[0][3]["message_id"]


# ── Replay tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestReplayUndelivered:
    """Test _replay_undelivered method on SDKBackend."""

    async def test_replay_injects_undelivered_messages(self, sdk_backend):
        """Replay should inject undelivered messages into session."""
        session = await sdk_backend.create_session(
            "Test User", "test:+15555551234", "admin", source="test"
        )

        undelivered = [
            {"message_id": "msg-001", "text": "missed message", "source": "imessage", "timestamp": 123},
        ]

        with patch("assistant.bus_helpers.query_undelivered_messages", return_value=undelivered):
            count = await sdk_backend._replay_undelivered("test:+15555551234", "existing-session-id")

        assert count == 1
        await asyncio.sleep(0.3)
        assert "missed message" in session._client._queries

    async def test_replay_dedup_skips_duplicate_texts(self, sdk_backend):
        """Replay should skip duplicate message texts within the batch."""
        session = await sdk_backend.create_session(
            "Test User", "test:+15555551234", "admin", source="test"
        )

        undelivered = [
            {"message_id": "msg-001", "text": "hello", "source": "imessage", "timestamp": 100},
            {"message_id": "msg-002", "text": "hello", "source": "imessage", "timestamp": 200},
        ]

        with patch("assistant.bus_helpers.query_undelivered_messages", return_value=undelivered):
            count = await sdk_backend._replay_undelivered("test:+15555551234", "existing-session-id")

        assert count == 1  # Only first "hello" replayed

    async def test_replay_returns_zero_when_no_undelivered(self, sdk_backend):
        """Replay should return 0 when nothing to replay."""
        await sdk_backend.create_session(
            "Test User", "test:+15555551234", "admin", source="test"
        )

        with patch("assistant.bus_helpers.query_undelivered_messages", return_value=[]):
            count = await sdk_backend._replay_undelivered("test:+15555551234", None)

        assert count == 0

    async def test_replay_handles_query_failure(self, sdk_backend):
        """Replay should return 0 on query failure."""
        await sdk_backend.create_session(
            "Test User", "test:+15555551234", "admin", source="test"
        )

        with patch("assistant.bus_helpers.query_undelivered_messages", side_effect=Exception("db locked")):
            count = await sdk_backend._replay_undelivered("test:+15555551234", None)

        assert count == 0

    async def test_replay_handles_inject_failure(self, sdk_backend):
        """Replay should continue after individual inject failures."""
        session = await sdk_backend.create_session(
            "Test User", "test:+15555551234", "admin", source="test"
        )

        undelivered = [
            {"message_id": "msg-001", "text": "will fail", "source": "imessage", "timestamp": 100},
            {"message_id": "msg-002", "text": "will succeed", "source": "imessage", "timestamp": 200},
        ]

        call_count = 0
        original_inject = session.inject

        async def failing_inject(text):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("inject failed")
            return await original_inject(text)

        session.inject = failing_inject

        with patch("assistant.bus_helpers.query_undelivered_messages", return_value=undelivered):
            count = await sdk_backend._replay_undelivered("test:+15555551234", "existing-session-id")

        assert count == 1  # Only second message succeeded

    async def test_replay_returns_zero_for_missing_session(self, sdk_backend):
        """Replay should return 0 if session doesn't exist."""
        with patch("assistant.bus_helpers.query_undelivered_messages", return_value=[
            {"message_id": "msg-001", "text": "hello", "source": "imessage", "timestamp": 100},
        ]):
            count = await sdk_backend._replay_undelivered("nonexistent", None)

        assert count == 0

    async def test_replay_emits_delivered_before_inject(self, sdk_backend):
        """At-most-once: delivered event should be emitted BEFORE inject."""
        session = await sdk_backend.create_session(
            "Test User", "test:+15555551234", "admin", source="test"
        )

        mock_producer = MagicMock()
        sdk_backend._producer = mock_producer

        undelivered = [
            {"message_id": "msg-001", "text": "hello", "source": "imessage", "timestamp": 100},
        ]

        event_order = []
        original_inject = session.inject

        async def tracking_inject(text):
            event_order.append(("inject", text))
            return await original_inject(text)

        session.inject = tracking_inject

        def tracking_produce(*args, **kwargs):
            if len(args) >= 3 and args[2] == "message.delivered":
                event_order.append(("delivered", args[3].get("message_id")))

        with patch("assistant.bus_helpers.query_undelivered_messages", return_value=undelivered), \
             patch("assistant.sdk_backend.produce_event", side_effect=tracking_produce):
            await sdk_backend._replay_undelivered("test:+15555551234", "existing-session-id")

        # Delivered should come before inject (at-most-once)
        assert len(event_order) == 2
        assert event_order[0][0] == "delivered"
        assert event_order[1][0] == "inject"
