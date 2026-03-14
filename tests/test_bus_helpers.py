"""Tests for assistant.bus_helpers — shared event production helpers."""
import json
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from assistant.bus_helpers import (
    _ensure_json_safe,
    produce_event,
    produce_session_event,
    message_sent_payload,
    sanitize_msg_for_bus,
    reconstruct_msg_from_bus,
    reaction_received_payload,
    health_check_payload,
    service_restarted_payload,
    consolidation_payload,
    reminder_payload,
    session_injected_payload,
    sanitize_reaction_for_bus,
    reconstruct_reaction_from_bus,
    healme_payload,
    vision_payload,
    compaction_triggered_payload,
    service_spawned_payload,
)


class TestEnsureJsonSafe:
    def test_safe_values_pass_through(self):
        payload = {"text": "hello", "count": 42, "flag": True, "nested": {"a": 1}}
        result = _ensure_json_safe(payload)
        assert result == payload

    def test_non_serializable_values_replaced_with_repr(self):
        obj = object()
        payload = {"text": "hello", "bad": obj}
        result = _ensure_json_safe(payload)
        assert result["text"] == "hello"
        assert result["bad"] == repr(obj)

    def test_datetime_replaced_with_repr(self):
        dt = datetime(2026, 3, 13)
        payload = {"ts": dt, "text": "hi"}
        result = _ensure_json_safe(payload)
        assert result["text"] == "hi"
        assert result["ts"] == repr(dt)

    def test_path_replaced_with_repr(self):
        p = Path("/tmp/test")
        payload = {"path": p}
        result = _ensure_json_safe(payload)
        assert result["path"] == repr(p)

    def test_nested_non_serializable_handled(self):
        dt = datetime(2026, 3, 13)
        payload = {"meta": {"ts": dt, "ok": True}, "text": "hi"}
        result = _ensure_json_safe(payload)
        assert result["text"] == "hi"
        assert result["meta"]["ok"] is True
        assert result["meta"]["ts"] == repr(dt)

    def test_list_with_non_serializable_handled(self):
        p = Path("/tmp")
        payload = {"items": [1, p, "hello"]}
        result = _ensure_json_safe(payload)
        assert result["items"] == [1, repr(p), "hello"]


class TestProduceEvent:
    def test_sends_to_producer(self):
        producer = MagicMock()
        produce_event(producer, "messages", "message.received", {"text": "hi"}, key="+1", source="imessage")
        producer.send.assert_called_once_with(
            "messages",
            payload={"text": "hi"},
            key="+1",
            type="message.received",
            source="imessage",
        )

    def test_noop_when_producer_is_none(self):
        # Should not raise
        produce_event(None, "messages", "message.received", {"text": "hi"})

    def test_sanitizes_non_json_safe_payload(self):
        producer = MagicMock()
        obj = object()
        produce_event(producer, "messages", "message.received", {"text": "hi", "bad": obj})
        call_payload = producer.send.call_args.kwargs["payload"]
        assert call_payload["text"] == "hi"
        assert call_payload["bad"] == repr(obj)

    def test_swallows_exceptions(self):
        producer = MagicMock()
        producer.send.side_effect = RuntimeError("db locked")
        # Should not raise
        produce_event(producer, "messages", "message.received", {"text": "hi"})


class TestProduceSessionEvent:
    def test_delegates_to_produce_event(self):
        producer = MagicMock()
        produce_session_event(producer, "+123", "session.created", {"tier": "admin"}, source="daemon")
        producer.send.assert_called_once_with(
            "sessions",
            payload={"tier": "admin"},
            key="+123",
            type="session.created",
            source="daemon",
        )

    def test_default_source_is_daemon(self):
        producer = MagicMock()
        produce_session_event(producer, "+123", "session.killed", {})
        assert producer.send.call_args.kwargs["source"] == "daemon"


class TestMessageSentPayload:
    def test_required_fields_always_present(self):
        payload = message_sent_payload("+123", "hello", False, True)
        assert payload == {
            "chat_id": "+123",
            "text": "hello",
            "is_group": False,
            "success": True,
        }

    def test_extra_fields_included(self):
        payload = message_sent_payload("+123", "hi", False, True, elapsed_ms=42.5, has_image=True)
        assert payload["elapsed_ms"] == 42.5
        assert payload["has_image"] is True
        # Required fields still present
        assert payload["chat_id"] == "+123"
        assert payload["success"] is True

    def test_consistent_across_transports(self):
        """All transports produce the same base fields."""
        imessage = message_sent_payload("+1", "hi", False, True, elapsed_ms=10)
        signal = message_sent_payload("+1", "hi", False, True)
        # Both have the same required keys
        required = {"chat_id", "text", "is_group", "success"}
        assert required.issubset(imessage.keys())
        assert required.issubset(signal.keys())


class TestSanitizeMsgForBus:
    def test_whitelisted_fields_pass_through(self):
        msg = {
            "rowid": 12345,
            "phone": "+16175969496",
            "text": "hello",
            "is_group": False,
            "group_name": None,
            "chat_identifier": "+16175969496",
            "is_audio_message": False,
            "audio_transcription": None,
            "thread_originator_guid": None,
            "source": "imessage",
        }
        payload = sanitize_msg_for_bus(msg)
        assert payload["rowid"] == 12345
        assert payload["phone"] == "+16175969496"
        assert payload["text"] == "hello"
        assert payload["chat_id"] == "+16175969496"

    def test_datetime_converted_to_ms(self):
        dt = datetime(2026, 3, 13, 19, 0, 0)
        msg = {"timestamp": dt, "phone": "+1", "text": "hi"}
        payload = sanitize_msg_for_bus(msg)
        assert "timestamp_ms" in payload
        assert isinstance(payload["timestamp_ms"], int)
        assert "timestamp" not in payload  # datetime not passed through

    def test_attachments_preserved(self):
        msg = {"phone": "+1", "text": "hi", "attachments": [
            {"path": "/tmp/img.png", "mime_type": "image/png", "name": "img.png", "size": 1024}
        ]}
        payload = sanitize_msg_for_bus(msg)
        assert payload["has_attachments"] is True
        assert payload["attachment_count"] == 1
        assert payload["attachments"] == [
            {"path": "/tmp/img.png", "mime_type": "image/png", "name": "img.png", "size": 1024}
        ]

    def test_attachments_with_path_objects(self):
        """Path objects in attachments are converted to strings."""
        msg = {"phone": "+1", "text": "hi", "attachments": [
            {"path": Path("/tmp/img.png"), "mime_type": "image/png", "name": "img.png", "size": 0}
        ]}
        payload = sanitize_msg_for_bus(msg)
        assert payload["attachments"][0]["path"] == "/tmp/img.png"
        assert isinstance(payload["attachments"][0]["path"], str)

    def test_non_serializable_unknown_fields_dropped(self):
        msg = {"phone": "+1", "text": "hi", "weird_obj": object()}
        payload = sanitize_msg_for_bus(msg)
        assert "weird_obj" not in payload
        assert payload["text"] == "hi"

    def test_serializable_unknown_fields_kept(self):
        msg = {"phone": "+1", "text": "hi", "custom_flag": True}
        payload = sanitize_msg_for_bus(msg)
        assert payload["custom_flag"] is True

    def test_chat_id_from_phone_for_individual(self):
        msg = {"phone": "+16175969496", "text": "hi", "is_group": False}
        payload = sanitize_msg_for_bus(msg)
        assert payload["chat_id"] == "+16175969496"

    def test_chat_id_from_chat_identifier_for_group(self):
        msg = {"phone": "+1", "text": "hi", "is_group": True, "chat_identifier": "abc123"}
        payload = sanitize_msg_for_bus(msg)
        assert payload["chat_id"] == "abc123"

    def test_empty_attachments(self):
        msg = {"phone": "+1", "text": "hi", "attachments": []}
        payload = sanitize_msg_for_bus(msg)
        assert payload["has_attachments"] is False
        assert payload["attachment_count"] == 0


class TestReconstructMsgFromBus:
    def test_timestamp_ms_restored_to_datetime(self):
        payload = {"phone": "+1", "text": "hi", "timestamp_ms": 1773448800000}
        msg = reconstruct_msg_from_bus(payload)
        assert isinstance(msg["timestamp"], datetime)
        assert "timestamp_ms" not in msg

    def test_convenience_fields_removed(self):
        payload = {
            "phone": "+1", "text": "hi",
            "has_attachments": True, "attachment_count": 1,
            "chat_id": "+1",
            "attachments": [{"path": "/tmp/img.png"}],
        }
        msg = reconstruct_msg_from_bus(payload)
        assert "has_attachments" not in msg
        assert "attachment_count" not in msg
        assert "chat_id" not in msg
        assert msg["attachments"] == [{"path": "/tmp/img.png"}]

    def test_does_not_mutate_input(self):
        payload = {"phone": "+1", "text": "hi", "timestamp_ms": 1773448800000}
        reconstruct_msg_from_bus(payload)
        assert "timestamp_ms" in payload  # original unchanged


class TestSanitizeReconstructRoundTrip:
    """Test that sanitize → reconstruct preserves all fields needed by process_message."""

    def _make_full_msg(self):
        """Build a realistic message dict as produced by MessagesReader."""
        return {
            "rowid": 30001,
            "phone": "+16175969496",
            "text": "hello world",
            "is_group": False,
            "group_name": None,
            "chat_identifier": "+16175969496",
            "is_audio_message": False,
            "audio_transcription": None,
            "thread_originator_guid": None,
            "source": "imessage",
            "timestamp": datetime(2026, 3, 13, 19, 30, 0),
            "attachments": [
                {"path": "/tmp/att/IMG_001.jpg", "mime_type": "image/jpeg", "name": "IMG_001.jpg", "size": 204800},
            ],
        }

    def test_round_trip_preserves_required_fields(self):
        original = self._make_full_msg()
        payload = sanitize_msg_for_bus(original)
        reconstructed = reconstruct_msg_from_bus(payload)

        # All fields process_message reads must survive
        assert reconstructed["phone"] == original["phone"]
        assert reconstructed["text"] == original["text"]
        assert reconstructed["rowid"] == original["rowid"]
        assert reconstructed["is_group"] == original["is_group"]
        assert reconstructed["group_name"] == original["group_name"]
        assert reconstructed["chat_identifier"] == original["chat_identifier"]
        assert reconstructed["is_audio_message"] == original["is_audio_message"]
        assert reconstructed["audio_transcription"] == original["audio_transcription"]
        assert reconstructed["thread_originator_guid"] == original["thread_originator_guid"]
        assert reconstructed["source"] == original["source"]

    def test_round_trip_preserves_timestamp(self):
        original = self._make_full_msg()
        payload = sanitize_msg_for_bus(original)
        reconstructed = reconstruct_msg_from_bus(payload)

        # Timestamp should be restored as datetime (may lose sub-second precision)
        assert isinstance(reconstructed["timestamp"], datetime)
        assert abs(reconstructed["timestamp"].timestamp() - original["timestamp"].timestamp()) < 1

    def test_round_trip_preserves_attachments(self):
        original = self._make_full_msg()
        payload = sanitize_msg_for_bus(original)
        reconstructed = reconstruct_msg_from_bus(payload)

        assert len(reconstructed["attachments"]) == 1
        att = reconstructed["attachments"][0]
        assert att["path"] == "/tmp/att/IMG_001.jpg"
        assert att["mime_type"] == "image/jpeg"
        assert att["name"] == "IMG_001.jpg"
        assert att["size"] == 204800

    def test_round_trip_no_attachments(self):
        msg = {
            "rowid": 1, "phone": "+1", "text": "hi",
            "is_group": False, "source": "imessage",
        }
        payload = sanitize_msg_for_bus(msg)
        reconstructed = reconstruct_msg_from_bus(payload)
        assert reconstructed.get("attachments") is None
        assert reconstructed["text"] == "hi"

    def test_round_trip_group_message(self):
        msg = {
            "rowid": 2, "phone": "user@email.com", "text": "group msg",
            "is_group": True, "group_name": "test-group",
            "chat_identifier": "abc123hex",
            "source": "imessage",
        }
        payload = sanitize_msg_for_bus(msg)
        reconstructed = reconstruct_msg_from_bus(payload)
        assert reconstructed["is_group"] is True
        assert reconstructed["group_name"] == "test-group"
        assert reconstructed["chat_identifier"] == "abc123hex"
        assert reconstructed["phone"] == "user@email.com"


# ─── Phase 1: Audit event payload builders ───────────────────────────

class TestReactionReceivedPayload:
    def test_required_fields(self):
        payload = reaction_received_payload("+123", "+456", "👍")
        assert payload == {
            "chat_id": "+123",
            "phone": "+456",
            "emoji": "👍",
            "is_removal": False,
        }

    def test_with_target_text(self):
        payload = reaction_received_payload("+123", "+456", "❤️", target_text="hello world")
        assert payload["target_text"] == "hello world"

    def test_with_removal(self):
        payload = reaction_received_payload("+123", "+456", "👍", is_removal=True)
        assert payload["is_removal"] is True

    def test_extra_fields(self):
        payload = reaction_received_payload("+123", "+456", "👍",
                                            target_guid="abc", rowid=42)
        assert payload["target_guid"] == "abc"
        assert payload["rowid"] == 42


class TestHealthCheckPayload:
    def test_default_empty_services(self):
        payload = health_check_payload()
        assert payload == {"services_restarted": []}

    def test_with_services(self):
        payload = health_check_payload(services_restarted=["signal", "search"])
        assert payload["services_restarted"] == ["signal", "search"]

    def test_extra_fields(self):
        payload = health_check_payload(sessions_checked=5)
        assert payload["sessions_checked"] == 5


class TestServiceRestartedPayload:
    def test_required_fields(self):
        payload = service_restarted_payload("signal", "died")
        assert payload == {"service": "signal", "reason": "died"}

    def test_extra_fields(self):
        payload = service_restarted_payload("search", "unresponsive", attempts=3)
        assert payload["attempts"] == 3


class TestConsolidationPayload:
    def test_default_success(self):
        payload = consolidation_payload("person_facts")
        assert payload == {"stage": "person_facts", "success": True}

    def test_failure(self):
        payload = consolidation_payload("chat_context", success=False, error="timeout")
        assert payload["success"] is False
        assert payload["error"] == "timeout"


class TestReminderPayload:
    def test_required_fields(self):
        payload = reminder_payload("rem-1", "Nikhil", "+123", "Do laundry", "once")
        assert payload == {
            "reminder_id": "rem-1",
            "contact": "Nikhil",
            "chat_id": "+123",
            "title": "Do laundry",
            "schedule_type": "once",
            "success": True,
        }

    def test_failure_with_error(self):
        payload = reminder_payload("rem-2", "Admin", "+1", "task", "cron",
                                   success=False, error="session not found")
        assert payload["success"] is False
        assert payload["error"] == "session not found"


class TestSessionInjectedPayload:
    def test_required_fields(self):
        payload = session_injected_payload("+123", "message")
        assert payload == {"chat_id": "+123", "injection_type": "message"}

    def test_with_contact_and_tier(self):
        payload = session_injected_payload("+123", "reaction",
                                           contact_name="Nikhil", tier="admin")
        assert payload["contact_name"] == "Nikhil"
        assert payload["tier"] == "admin"

    def test_all_injection_types(self):
        for t in ("message", "reaction", "group", "consolidation", "reminder"):
            payload = session_injected_payload("+1", t)
            assert payload["injection_type"] == t

    def test_extra_fields(self):
        payload = session_injected_payload("+1", "message", inject_ms=42.5)
        assert payload["inject_ms"] == 42.5


# ─── Phase 2: Reaction serialization ─────────────────────────────────

class TestSanitizeReactionForBus:
    def _make_reaction(self):
        return {
            "rowid": 50001,
            "phone": "+16175969496",
            "emoji": "👍",
            "is_removal": False,
            "target_guid": "p:0/abc-def-123",
            "target_text": "hello world",
            "target_is_from_me": True,
            "is_group": False,
            "chat_identifier": "+16175969496",
            "source": "imessage",
            "timestamp": datetime(2026, 3, 13, 21, 30, 0),
        }

    def test_whitelisted_fields_pass_through(self):
        reaction = self._make_reaction()
        payload = sanitize_reaction_for_bus(reaction)
        assert payload["rowid"] == 50001
        assert payload["phone"] == "+16175969496"
        assert payload["emoji"] == "👍"
        assert payload["is_removal"] is False
        assert payload["target_guid"] == "p:0/abc-def-123"
        assert payload["target_text"] == "hello world"
        assert payload["target_is_from_me"] is True
        assert payload["is_group"] is False
        assert payload["chat_identifier"] == "+16175969496"
        assert payload["source"] == "imessage"

    def test_datetime_converted_to_ms(self):
        reaction = self._make_reaction()
        payload = sanitize_reaction_for_bus(reaction)
        assert "timestamp_ms" in payload
        assert isinstance(payload["timestamp_ms"], int)
        assert "timestamp" not in payload

    def test_chat_id_set_from_phone_for_individual(self):
        reaction = self._make_reaction()
        payload = sanitize_reaction_for_bus(reaction)
        assert payload["chat_id"] == "+16175969496"

    def test_chat_id_set_from_chat_identifier_for_group(self):
        reaction = self._make_reaction()
        reaction["is_group"] = True
        reaction["chat_identifier"] = "abc123hexgroup"
        payload = sanitize_reaction_for_bus(reaction)
        assert payload["chat_id"] == "abc123hexgroup"

    def test_non_serializable_fields_dropped(self):
        reaction = self._make_reaction()
        reaction["weird_obj"] = object()
        payload = sanitize_reaction_for_bus(reaction)
        assert "weird_obj" not in payload

    def test_serializable_unknown_fields_kept(self):
        reaction = self._make_reaction()
        reaction["custom_flag"] = True
        payload = sanitize_reaction_for_bus(reaction)
        assert payload["custom_flag"] is True


class TestReconstructReactionFromBus:
    def test_timestamp_ms_restored_to_datetime(self):
        payload = {
            "phone": "+1", "emoji": "👍",
            "timestamp_ms": 1773448800000,
        }
        reaction = reconstruct_reaction_from_bus(payload)
        assert isinstance(reaction["timestamp"], datetime)
        assert "timestamp_ms" not in reaction

    def test_chat_id_removed(self):
        payload = {
            "phone": "+1", "emoji": "👍",
            "chat_id": "+1",
        }
        reaction = reconstruct_reaction_from_bus(payload)
        assert "chat_id" not in reaction

    def test_does_not_mutate_input(self):
        payload = {"phone": "+1", "emoji": "👍", "timestamp_ms": 1773448800000}
        reconstruct_reaction_from_bus(payload)
        assert "timestamp_ms" in payload


class TestSanitizeReconstructReactionRoundTrip:
    def _make_full_reaction(self):
        return {
            "rowid": 50001,
            "phone": "+16175969496",
            "emoji": "❤️",
            "is_removal": False,
            "target_guid": "p:0/abc-def-123",
            "target_text": "test message with emoji 🎉",
            "target_is_from_me": True,
            "is_group": False,
            "chat_identifier": "+16175969496",
            "source": "imessage",
            "timestamp": datetime(2026, 3, 13, 21, 30, 0),
        }

    def test_round_trip_preserves_all_fields(self):
        original = self._make_full_reaction()
        payload = sanitize_reaction_for_bus(original)
        reconstructed = reconstruct_reaction_from_bus(payload)

        assert reconstructed["phone"] == original["phone"]
        assert reconstructed["emoji"] == original["emoji"]
        assert reconstructed["rowid"] == original["rowid"]
        assert reconstructed["is_removal"] == original["is_removal"]
        assert reconstructed["target_guid"] == original["target_guid"]
        assert reconstructed["target_text"] == original["target_text"]
        assert reconstructed["target_is_from_me"] == original["target_is_from_me"]
        assert reconstructed["is_group"] == original["is_group"]
        assert reconstructed["chat_identifier"] == original["chat_identifier"]
        assert reconstructed["source"] == original["source"]

    def test_round_trip_preserves_timestamp(self):
        original = self._make_full_reaction()
        payload = sanitize_reaction_for_bus(original)
        reconstructed = reconstruct_reaction_from_bus(payload)

        assert isinstance(reconstructed["timestamp"], datetime)
        assert abs(reconstructed["timestamp"].timestamp() - original["timestamp"].timestamp()) < 1

    def test_round_trip_group_reaction(self):
        reaction = {
            "rowid": 99, "phone": "+1",
            "emoji": "👎", "is_removal": False,
            "target_is_from_me": True,
            "is_group": True, "chat_identifier": "abc123hex",
            "source": "imessage",
        }
        payload = sanitize_reaction_for_bus(reaction)
        assert payload["chat_id"] == "abc123hex"
        reconstructed = reconstruct_reaction_from_bus(payload)
        assert reconstructed["is_group"] is True
        assert reconstructed["chat_identifier"] == "abc123hex"

    def test_round_trip_removal_reaction(self):
        reaction = {
            "rowid": 100, "phone": "+1",
            "emoji": "👍", "is_removal": True,
            "target_is_from_me": True, "is_group": False,
            "source": "imessage",
        }
        payload = sanitize_reaction_for_bus(reaction)
        reconstructed = reconstruct_reaction_from_bus(payload)
        assert reconstructed["is_removal"] is True


# ─── ReminderPoller bus integration ──────────────────────────────────

class TestReminderPollerProduceEvent:
    """Verify ReminderPoller._produce_event delegates to bus_helpers correctly."""

    def test_produce_event_delegates_to_bus_helpers(self):
        from assistant.manager import ReminderPoller

        # Mock backend with a bus producer
        mock_backend = MagicMock()
        mock_producer = MagicMock()
        mock_backend._producer = mock_producer

        mock_contacts = MagicMock()
        poller = ReminderPoller(mock_backend, mock_contacts)

        # This should NOT throw AttributeError
        poller._produce_event("system", "reminder.fired", {
            "reminder_id": "test-1",
            "title": "test",
        }, key="reminder", source="reminder")

        # Verify it delegated to the producer
        mock_producer.send.assert_called_once()
        call_kwargs = mock_producer.send.call_args
        assert call_kwargs.args[0] == "system"
        assert call_kwargs.kwargs["type"] == "reminder.fired"
        assert call_kwargs.kwargs["source"] == "reminder"

    def test_produce_event_survives_none_producer(self):
        from assistant.manager import ReminderPoller

        mock_backend = MagicMock()
        mock_backend._producer = None

        mock_contacts = MagicMock()
        poller = ReminderPoller(mock_backend, mock_contacts)

        # Should not raise (produce_event no-ops on None producer)
        poller._produce_event("system", "reminder.fired", {}, key="reminder")

    def test_produce_event_swallows_exceptions(self):
        from assistant.manager import ReminderPoller

        mock_backend = MagicMock()
        mock_producer = MagicMock()
        mock_producer.send.side_effect = RuntimeError("db locked")
        mock_backend._producer = mock_producer

        mock_contacts = MagicMock()
        poller = ReminderPoller(mock_backend, mock_contacts)

        # Should not raise (produce_event catches exceptions)
        poller._produce_event("system", "reminder.fired", {}, key="reminder")


# ─── v5 payload builders ─────────────────────────────────────────────

class TestHealmePayload:
    def test_required_fields(self):
        payload = healme_payload("+123", "Admin", "triggered")
        assert payload == {
            "admin_phone": "+123",
            "admin_name": "Admin",
            "stage": "triggered",
        }

    def test_with_custom_prompt(self):
        payload = healme_payload("+123", "Admin", "triggered",
                                  custom_prompt="check logs")
        assert payload["custom_prompt"] == "check logs"

    def test_completed_stage(self):
        payload = healme_payload("+123", "Admin", "completed",
                                  pid=12345, returncode=0)
        assert payload["stage"] == "completed"
        assert payload["pid"] == 12345
        assert payload["returncode"] == 0

    def test_without_custom_prompt_omits_key(self):
        payload = healme_payload("+123", "Admin", "triggered")
        assert "custom_prompt" not in payload

    def test_extra_fields(self):
        payload = healme_payload("+123", "Admin", "triggered", foo="bar")
        assert payload["foo"] == "bar"


class TestVisionPayload:
    def test_required_fields(self):
        payload = vision_payload("+123", "/tmp/img.jpg", True, 500)
        assert payload == {
            "chat_id": "+123",
            "image_path": "/tmp/img.jpg",
            "success": True,
            "description_length": 500,
        }

    def test_failure_with_error(self):
        payload = vision_payload("+123", "/tmp/img.jpg", False,
                                  error="gemini timeout")
        assert payload["success"] is False
        assert payload["error"] == "gemini timeout"
        assert payload["description_length"] == 0

    def test_extra_fields(self):
        payload = vision_payload("+123", "/tmp/img.jpg", True, 100,
                                  model="gemini-3")
        assert payload["model"] == "gemini-3"


class TestCompactionTriggeredPayload:
    def test_required_fields(self):
        payload = compaction_triggered_payload(
            "imessage/_123", "+123", "Nikhil", 42
        )
        assert payload == {
            "session_name": "imessage/_123",
            "chat_id": "+123",
            "contact_name": "Nikhil",
            "turn_count": 42,
        }

    def test_extra_fields(self):
        payload = compaction_triggered_payload(
            "imessage/_123", "+123", "Nikhil", 42,
            reason="context_full"
        )
        assert payload["reason"] == "context_full"


class TestServiceSpawnedPayload:
    def test_required_fields(self):
        payload = service_spawned_payload("search", 12345)
        assert payload == {
            "service": "search",
            "pid": 12345,
        }

    def test_with_extra_fields(self):
        payload = service_spawned_payload("signal", 99999, socket="/tmp/signal.sock")
        assert payload["service"] == "signal"
        assert payload["pid"] == 99999
        assert payload["socket"] == "/tmp/signal.sock"

    def test_all_service_types(self):
        for svc in ("search", "signal", "sven-api"):
            payload = service_spawned_payload(svc, 1)
            assert payload["service"] == svc


# ─── Integration: session creation events ─────────────────────────────

class TestGroupSessionCreatedEvent:
    """Verify group/bg/master session creation emits session.created events."""

    def test_create_group_session_emits_event(self):
        """create_group_session() should emit session.created."""
        # This is a structural test: verify the code path exists
        import ast
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend.create_group_session)
        assert "session.created" in source
        assert "produce_session_event" in source

    def test_create_group_session_unlocked_emits_event(self):
        """_create_group_session_unlocked() should emit session.created."""
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend._create_group_session_unlocked)
        assert "session.created" in source
        assert "produce_session_event" in source

    def test_create_background_session_emits_event(self):
        """create_background_session() should emit session.created."""
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend.create_background_session)
        assert "session.created" in source
        assert "produce_session_event" in source

    def test_create_master_session_emits_event(self):
        """create_master_session() should emit session.created."""
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend.create_master_session)
        assert "session.created" in source
        assert "produce_session_event" in source


class TestMasterInjectionEvent:
    """Verify MASTER command injection emits session.injected."""

    def test_inject_master_prompt_emits_event(self):
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend.inject_master_prompt)
        assert "session.injected" in source
        assert "produce_session_event" in source
        assert "injection_type" in source
        assert "master" in source


class TestAuthErrorNotificationEvent:
    """Verify auth error notification emits message.sent."""

    def test_send_auth_error_notification_emits_event(self):
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend._send_auth_error_notification)
        assert "message.sent" in source or "message_sent_payload" in source
        assert "produce_event" in source


class TestGeminiVisionEvents:
    """Verify Gemini vision analysis emits vision.analyzed/failed."""

    def test_inject_gemini_vision_emits_analyzed(self):
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend._inject_gemini_vision)
        assert "vision.analyzed" in source
        assert "vision_payload" in source

    def test_inject_gemini_vision_emits_failed(self):
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend._inject_gemini_vision)
        assert "vision.failed" in source


class TestHealthCheckEvents:
    """Verify fast/deep health checks emit completion events."""

    def test_fast_health_check_emits_event(self):
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend.fast_health_check)
        assert "health.fast_check_completed" in source
        assert "produce_event" in source

    def test_deep_health_check_emits_event(self):
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend.deep_health_check)
        assert "health.deep_check_completed" in source
        assert "produce_event" in source


class TestHealmeEvents:
    """Verify HEALME spawning emits healme.triggered/completed."""

    def test_process_message_emits_healme_triggered(self):
        import inspect
        from assistant.manager import Manager

        source = inspect.getsource(Manager.process_message)
        assert "healme.triggered" in source
        assert "healme_payload" in source

    def test_spawn_healing_session_emits_healme_completed(self):
        import inspect
        from assistant.manager import Manager

        source = inspect.getsource(Manager._spawn_healing_session)
        assert "healme.completed" in source
        assert "healme_payload" in source


class TestServiceSpawnedEvents:
    """Verify daemon spawns emit health.service_spawned."""

    def test_spawn_search_daemon_emits_event(self):
        import inspect
        from assistant.manager import Manager

        source = inspect.getsource(Manager._spawn_search_daemon)
        assert "health.service_spawned" in source
        assert "service_spawned_payload" in source

    def test_spawn_sven_api_daemon_emits_event(self):
        import inspect
        from assistant.manager import Manager

        source = inspect.getsource(Manager._spawn_sven_api_daemon)
        assert "health.service_spawned" in source
        assert "service_spawned_payload" in source

    def test_spawn_signal_daemon_emits_event(self):
        import inspect
        from assistant.manager import Manager

        source = inspect.getsource(Manager._spawn_signal_daemon)
        assert "health.service_spawned" in source
        assert "service_spawned_payload" in source


class TestCompactionEvent:
    """Verify PreCompact hook emits compaction.triggered."""

    def test_pre_compact_hook_emits_event(self):
        import inspect
        from assistant.sdk_session import SDKSession

        source = inspect.getsource(SDKSession._pre_compact_hook)
        assert "compaction.triggered" in source
        assert "compaction_triggered_payload" in source

    def test_pre_compact_hook_emits_compaction_event(self):
        """PreCompact hook emits compaction.triggered (not message.sent - no SMS is sent from here)."""
        import inspect
        from assistant.sdk_session import SDKSession

        source = inspect.getsource(SDKSession._pre_compact_hook)
        assert "compaction.triggered" in source


class TestSessionBusProducerPropagation:
    """Verify bus producer is propagated to SDKSession for event emission."""

    def test_sdk_session_has_bus_producer_attribute(self):
        from assistant.sdk_session import SDKSession

        session = SDKSession(
            chat_id="+123",
            contact_name="Test",
            tier="admin",
            cwd="/tmp",
        )
        assert hasattr(session, "_producer")
        assert session._producer is None

    def test_bus_producer_set_in_create_session(self):
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend.create_session)
        assert "_producer" in source

    def test_bus_producer_set_in_create_session_unlocked(self):
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend._create_session_unlocked)
        assert "_producer" in source

    def test_bus_producer_set_in_create_group_session(self):
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend.create_group_session)
        assert "_producer" in source

    def test_bus_producer_set_in_create_group_session_unlocked(self):
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend._create_group_session_unlocked)
        assert "_producer" in source

    def test_bus_producer_set_in_create_background_session(self):
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend.create_background_session)
        assert "_producer" in source

    def test_bus_producer_set_in_create_master_session(self):
        import inspect
        from assistant.sdk_backend import SDKBackend

        source = inspect.getsource(SDKBackend.create_master_session)
        assert "_producer" in source
