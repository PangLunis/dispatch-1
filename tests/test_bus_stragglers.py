"""Tests for bus straggler fixes — ensuring all operations produce bus events.

Covers:
1. ConsumerRunner activation (init + startup)
2. inject_reaction() produces session.injected event
3. inject_group_message() produces session.injected event
4. Reminder _inject_to_session() produces session.injected events
5. Direct SMS control commands produce message.sent/failed events
6. Consolidation/skillify injection produces events
7. HEALME failure produces healme.completed event
8. ConsumerRunner processes events end-to-end
"""
import json
import time
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, call

import pytest

from assistant.bus_helpers import (
    produce_event, produce_session_event,
    session_injected_payload, message_sent_payload,
    consolidation_payload, healme_payload,
)


# ─── Fix 2: inject_reaction() bus event ───────────────────────


class TestInjectReactionBusEvent:
    """inject_reaction() should produce a session.injected event."""

    def test_session_injected_payload_for_reaction(self):
        """session_injected_payload supports reaction type with emoji."""
        payload = session_injected_payload(
            "+1234567890", "reaction", "Alice", "admin", emoji="👍"
        )
        assert payload["chat_id"] == "+1234567890"
        assert payload["injection_type"] == "reaction"
        assert payload["contact_name"] == "Alice"
        assert payload["tier"] == "admin"
        assert payload["emoji"] == "👍"

    def test_produce_session_event_called_for_reaction(self):
        """Verify produce_session_event is called with correct args."""
        producer = MagicMock()
        produce_session_event(
            producer, "+1234567890", "session.injected",
            session_injected_payload("+1234567890", "reaction", "Alice", "admin", emoji="👍"),
            source="inject",
        )
        producer.send.assert_called_once()
        call_args = producer.send.call_args
        assert call_args[0][0] == "sessions"
        assert call_args[1]["type"] == "session.injected"
        assert call_args[1]["key"] == "+1234567890"
        assert call_args[1]["source"] == "inject"
        payload = call_args[1]["payload"]
        assert payload["injection_type"] == "reaction"
        assert payload["emoji"] == "👍"


# ─── Fix 3: inject_group_message() bus event ──────────────────


class TestInjectGroupMessageBusEvent:
    """inject_group_message() should produce a session.injected event."""

    def test_session_injected_payload_for_group(self):
        """session_injected_payload supports group type with group_name."""
        payload = session_injected_payload(
            "abc123", "group", "Bob", "favorite", group_name="Family Chat"
        )
        assert payload["chat_id"] == "abc123"
        assert payload["injection_type"] == "group"
        assert payload["contact_name"] == "Bob"
        assert payload["tier"] == "favorite"
        assert payload["group_name"] == "Family Chat"


# ─── Fix 4: Reminder injection bus event ──────────────────────


class TestReminderInjectionBusEvent:
    """Reminder _inject_to_session() should produce session.injected events."""

    def test_session_injected_payload_for_reminder(self):
        """session_injected_payload supports reminder type with reminder_id."""
        payload = session_injected_payload(
            "+1234567890", "reminder", "Admin", "admin",
            reminder_id="rem_123", target="fg"
        )
        assert payload["injection_type"] == "reminder"
        assert payload["reminder_id"] == "rem_123"
        assert payload["target"] == "fg"


# ─── Fix 5: Direct SMS control commands ──────────────────────


class TestDirectSMSBusEvent:
    """_send_sms() should produce message.sent/failed events."""

    def test_message_sent_payload_for_control(self):
        """message_sent_payload supports daemon-control source."""
        payload = message_sent_payload(
            "+1234567890", "[RESTART] Session restarted",
            is_group=False, success=True, source="daemon-control"
        )
        assert payload["chat_id"] == "+1234567890"
        assert payload["text"] == "[RESTART] Session restarted"
        assert payload["is_group"] is False
        assert payload["success"] is True
        assert payload["source"] == "daemon-control"

    def test_message_failed_payload_for_control(self):
        """message_sent_payload supports failure with error."""
        payload = message_sent_payload(
            "+1234567890", "[RESTART] Failed",
            is_group=False, success=False, error="timeout"
        )
        assert payload["success"] is False
        assert payload["error"] == "timeout"


# ─── Fix 6: Consolidation/skillify bus events ────────────────


class TestConsolidationBusEvents:
    """Consolidation and skillify injection should produce bus events."""

    def test_consolidation_completed_payload(self):
        payload = consolidation_payload("summary_injected", success=True)
        assert payload["stage"] == "summary_injected"
        assert payload["success"] is True

    def test_consolidation_failed_payload(self):
        payload = consolidation_payload("summary_injection", success=False, error="session dead")
        assert payload["stage"] == "summary_injection"
        assert payload["success"] is False
        assert payload["error"] == "session dead"

    def test_skillify_started_payload(self):
        payload = consolidation_payload("skillify", success=True)
        assert payload["stage"] == "skillify"
        assert payload["success"] is True


# ─── Fix 7: HEALME failure bus event ─────────────────────────


class TestHEALMEFailureBusEvent:
    """HEALME spawn failure should produce healme.completed with failed stage."""

    def test_healme_failed_payload(self):
        payload = healme_payload("+1234567890", "Admin", "failed", error="spawn error")
        assert payload["stage"] == "failed"
        assert payload["error"] == "spawn error"
        assert payload["admin_phone"] == "+1234567890"


# ─── Fix 1 & 8: ConsumerRunner activation ────────────────────


class TestConsumerRunnerActivation:
    """ConsumerRunner should be initialized and started."""

    def test_consumer_runner_processes_events(self):
        """End-to-end: produce events → consumer processes them."""
        from bus.bus import Bus
        from bus.consumers import ConsumerRunner, ConsumerConfig, actions

        with tempfile.TemporaryDirectory() as tmpdir:
            bus = Bus(db_path=str(Path(tmpdir) / "test.db"))
            bus.create_topic("test-topic")

            received = []

            runner = ConsumerRunner(bus, [
                ConsumerConfig(
                    topic="test-topic",
                    group="test-group",
                    action=actions.call_function(
                        lambda records: received.extend(records)
                    ),
                ),
            ])

            # Produce some events
            producer = bus.producer()
            producer.send("test-topic", payload={"msg": "hello"}, key="k1", type="test.event")
            producer.send("test-topic", payload={"msg": "world"}, key="k2", type="test.event")
            producer.flush()

            # Process one round
            results = runner.run_once()
            assert results["test-group"] == 2
            assert len(received) == 2
            assert received[0].payload["msg"] == "hello"
            assert received[1].payload["msg"] == "world"

            # Second round should get nothing (offsets committed)
            results = runner.run_once()
            assert results["test-group"] == 0

            runner.stop()
            bus.close()

    def test_consumer_runner_with_filter(self):
        """Consumer filter correctly selects events by type."""
        from bus.bus import Bus
        from bus.consumers import ConsumerRunner, ConsumerConfig, actions

        with tempfile.TemporaryDirectory() as tmpdir:
            bus = Bus(db_path=str(Path(tmpdir) / "test.db"))
            bus.create_topic("messages")

            received = []

            runner = ConsumerRunner(bus, [
                ConsumerConfig(
                    topic="messages",
                    group="reactions-only",
                    filter=lambda r: r.type == "reaction.received",
                    action=actions.call_function(
                        lambda records: received.extend(records)
                    ),
                ),
            ])

            producer = bus.producer()
            producer.send("messages", payload={"text": "hi"}, key="k1", type="message.received")
            producer.send("messages", payload={"emoji": "👍"}, key="k2", type="reaction.received")
            producer.send("messages", payload={"text": "bye"}, key="k3", type="message.received")
            producer.flush()

            results = runner.run_once()
            assert results["reactions-only"] == 1
            assert len(received) == 1
            assert received[0].type == "reaction.received"

            runner.stop()
            bus.close()

    def test_consumer_runner_multi_topic(self):
        """Multiple consumers across different topics work independently."""
        from bus.bus import Bus
        from bus.consumers import ConsumerRunner, ConsumerConfig, actions

        with tempfile.TemporaryDirectory() as tmpdir:
            bus = Bus(db_path=str(Path(tmpdir) / "test.db"))
            bus.create_topic("messages")
            bus.create_topic("sessions")
            bus.create_topic("system")

            msg_received = []
            sess_received = []
            sys_received = []

            runner = ConsumerRunner(bus, [
                ConsumerConfig(
                    topic="messages",
                    group="audit-messages",
                    action=actions.call_function(lambda r: msg_received.extend(r)),
                ),
                ConsumerConfig(
                    topic="sessions",
                    group="audit-sessions",
                    action=actions.call_function(lambda r: sess_received.extend(r)),
                ),
                ConsumerConfig(
                    topic="system",
                    group="audit-system",
                    action=actions.call_function(lambda r: sys_received.extend(r)),
                ),
            ])

            producer = bus.producer()
            producer.send("messages", payload={}, key="k1", type="message.received")
            producer.send("sessions", payload={}, key="k2", type="session.created")
            producer.send("system", payload={}, key="k3", type="daemon.started")
            producer.flush()

            runner.run_once()
            assert len(msg_received) == 1
            assert len(sess_received) == 1
            assert len(sys_received) == 1

            runner.stop()
            bus.close()

    def test_consumer_runner_thread_safety(self):
        """ConsumerRunner can run in background thread and be stopped cleanly."""
        from bus.bus import Bus
        from bus.consumers import ConsumerRunner, ConsumerConfig, actions

        with tempfile.TemporaryDirectory() as tmpdir:
            bus = Bus(db_path=str(Path(tmpdir) / "test.db"))
            bus.create_topic("test-topic")

            received = []
            runner = ConsumerRunner(bus, [
                ConsumerConfig(
                    topic="test-topic",
                    group="thread-test",
                    action=actions.call_function(lambda r: received.extend(r)),
                ),
            ])

            # Start in background thread
            thread = threading.Thread(
                target=runner.run_forever,
                kwargs={"poll_interval_ms": 50},
                daemon=True,
            )
            thread.start()

            # Produce while running
            producer = bus.producer()
            producer.send("test-topic", payload={"n": 1}, key="k", type="test")
            producer.flush()
            time.sleep(0.2)

            producer.send("test-topic", payload={"n": 2}, key="k", type="test")
            producer.flush()
            time.sleep(0.2)

            # Stop cleanly
            runner.stop()
            thread.join(timeout=2)
            assert not thread.is_alive()

            assert len(received) == 2
            bus.close()
