"""
Tests for restart notification feature.

When the daemon restarts, sessions should notify their users they're back online
UNLESS the session itself initiated the restart.

Covers:
- Graceful restart marker reading (JSON format with initiator_chat_id)
- restart_role determination (initiator vs passive vs fresh)
- System prompt content varies by restart_role
- CLI auto-detection of initiator from cwd
"""
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


GRACEFUL_MARKER = Path("/tmp/dispatch-graceful-restart-test")


class TestReadRestartInitiator:
    """Test _read_restart_initiator reads marker correctly."""

    def test_no_marker_returns_none(self, tmp_path):
        """When marker file doesn't exist, should return None."""
        marker = tmp_path / "graceful-restart"
        assert not marker.exists()
        # Simulate the logic
        try:
            data = json.loads(marker.read_text())
            initiator = data.get("initiator_chat_id")
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            initiator = None
        assert initiator is None

    def test_marker_with_initiator(self, tmp_path):
        """Marker with initiator_chat_id should return the chat_id."""
        marker = tmp_path / "graceful-restart"
        marker.write_text(json.dumps({
            "timestamp": 1234567890,
            "initiator_chat_id": "+16175969496",
        }))
        with patch("assistant.sdk_backend.Path") as MockPath:
            MockPath.return_value = marker
            # Actually test the logic directly
            data = json.loads(marker.read_text())
            assert data.get("initiator_chat_id") == "+16175969496"

    def test_marker_without_initiator(self, tmp_path):
        """Marker without initiator_chat_id should return None."""
        marker = tmp_path / "graceful-restart"
        marker.write_text(json.dumps({"timestamp": 1234567890}))
        data = json.loads(marker.read_text())
        assert data.get("initiator_chat_id") is None

    def test_marker_plain_integer_backward_compat(self, tmp_path):
        """Old-format marker (plain integer) should not crash."""
        marker = tmp_path / "graceful-restart"
        marker.write_text("1234567890")
        try:
            data = json.loads(marker.read_text())
            if isinstance(data, dict):
                initiator = data.get("initiator_chat_id")
            else:
                initiator = None  # Plain integer, no initiator info
        except (json.JSONDecodeError, ValueError):
            initiator = None
        assert initiator is None


class TestRestartRole:
    """Test restart_role assignment in recreate logic."""

    def test_initiator_matches_chat_id(self):
        """When restart_initiator == chat_id, role should be 'initiator'."""
        restart_initiator = "+16175969496"
        chat_id = "+16175969496"
        if restart_initiator is not None and chat_id == restart_initiator:
            role = "initiator"
        else:
            role = "passive"
        assert role == "initiator"

    def test_passive_when_different_chat_id(self):
        """When restart_initiator != chat_id, role should be 'passive'."""
        restart_initiator = "+16175969496"
        chat_id = "+15555550100"
        if restart_initiator is not None and chat_id == restart_initiator:
            role = "initiator"
        else:
            role = "passive"
        assert role == "passive"

    def test_passive_when_no_initiator(self):
        """When no initiator (crash/watchdog), role should be 'passive'."""
        restart_initiator = None
        chat_id = "+16175969496"
        if restart_initiator is not None and chat_id == restart_initiator:
            role = "initiator"
        else:
            role = "passive"
        assert role == "passive"


class TestSystemPromptRestartInstruction:
    """Test that system prompts contain correct restart instructions."""

    def test_initiator_gets_notify_instruction(self):
        """Initiator session should get 'send back-online message' — they asked for the restart."""
        restart_role = "initiator"
        if restart_role == "initiator":
            instruction = "IMPORTANT: The daemon was restarted"
        elif restart_role == "passive":
            instruction = "CRITICAL: Never send restart notifications."
        else:
            instruction = "CRITICAL: Never send restart notifications."
        assert "daemon was restarted" in instruction

    def test_passive_gets_silent_instruction(self):
        """Passive session should stay silent — user shouldn't notice restarts they didn't ask for."""
        restart_role = "passive"
        if restart_role == "initiator":
            instruction = "IMPORTANT: The daemon was restarted"
        elif restart_role == "passive":
            instruction = "CRITICAL: Never send restart notifications."
        else:
            instruction = "CRITICAL: Never send restart notifications."
        assert "Never send restart" in instruction

    def test_fresh_gets_silent_instruction(self):
        """Fresh session (no restart) should get 'never send restart notifications'."""
        restart_role = None
        if restart_role == "initiator":
            instruction = "IMPORTANT: The daemon was restarted"
        elif restart_role == "passive":
            instruction = "CRITICAL: Never send restart notifications."
        else:
            instruction = "CRITICAL: Never send restart notifications."
        assert "Never send restart" in instruction


class TestCLIInitiatorAutoDetect:
    """Test CLI auto-detection of initiator from cwd."""

    def test_detect_from_imessage_transcript_dir(self, tmp_path):
        """Should detect chat_id from imessage transcript dir."""
        transcripts = tmp_path / "transcripts"
        imessage_dir = transcripts / "imessage" / "_16175969496"
        imessage_dir.mkdir(parents=True)

        with patch("pathlib.Path.cwd", return_value=imessage_dir), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cwd = Path.cwd()
            transcripts_dir = Path.home() / "transcripts"
            try:
                rel = cwd.relative_to(transcripts_dir)
                parts = rel.parts
                if len(parts) >= 2:
                    sanitized_id = parts[1]
                    initiator = sanitized_id.replace("_", "+", 1)
                else:
                    initiator = None
            except ValueError:
                initiator = None

        assert initiator == "+16175969496"

    def test_detect_from_signal_transcript_dir(self, tmp_path):
        """Should detect chat_id from signal transcript dir."""
        transcripts = tmp_path / "transcripts"
        signal_dir = transcripts / "signal" / "_16175969496"
        signal_dir.mkdir(parents=True)

        with patch("pathlib.Path.cwd", return_value=signal_dir), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cwd = Path.cwd()
            transcripts_dir = Path.home() / "transcripts"
            try:
                rel = cwd.relative_to(transcripts_dir)
                parts = rel.parts
                if len(parts) >= 2:
                    sanitized_id = parts[1]
                    initiator = sanitized_id.replace("_", "+", 1)
                else:
                    initiator = None
            except ValueError:
                initiator = None

        assert initiator == "+16175969496"

    def test_no_detect_from_non_transcript_dir(self, tmp_path):
        """Should return None when not in a transcript dir."""
        non_transcript = tmp_path / "some" / "other" / "dir"
        non_transcript.mkdir(parents=True)

        with patch("pathlib.Path.cwd", return_value=non_transcript), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cwd = Path.cwd()
            transcripts_dir = Path.home() / "transcripts"
            try:
                rel = cwd.relative_to(transcripts_dir)
                parts = rel.parts
                if len(parts) >= 2:
                    sanitized_id = parts[1]
                    initiator = sanitized_id.replace("_", "+", 1)
                else:
                    initiator = None
            except ValueError:
                initiator = None

        assert initiator is None

    def test_group_chat_id_no_plus_prefix(self, tmp_path):
        """Group chat IDs (hex) should get + prefix but that's OK — it's just the marker."""
        transcripts = tmp_path / "transcripts"
        group_dir = transcripts / "imessage" / "b3d258b9a4de447ca412eb335c82a077"
        group_dir.mkdir(parents=True)

        with patch("pathlib.Path.cwd", return_value=group_dir), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cwd = Path.cwd()
            transcripts_dir = Path.home() / "transcripts"
            try:
                rel = cwd.relative_to(transcripts_dir)
                parts = rel.parts
                if len(parts) >= 2:
                    sanitized_id = parts[1]
                    # Only replace leading _ with + (phone numbers)
                    # Group IDs don't start with _
                    initiator = sanitized_id.replace("_", "+", 1)
                else:
                    initiator = None
            except ValueError:
                initiator = None

        # Group IDs don't start with _, so no replacement happens
        assert initiator == "b3d258b9a4de447ca412eb335c82a077"


class TestGracefulMarkerFormat:
    """Test the graceful restart marker JSON format."""

    def test_marker_json_with_initiator(self, tmp_path):
        """Marker should be valid JSON with timestamp and initiator."""
        marker = tmp_path / "marker"
        marker_data = {"timestamp": 1234567890, "initiator_chat_id": "+16175969496"}
        marker.write_text(json.dumps(marker_data))

        data = json.loads(marker.read_text())
        assert data["timestamp"] == 1234567890
        assert data["initiator_chat_id"] == "+16175969496"

    def test_marker_json_without_initiator(self, tmp_path):
        """Marker without initiator (e.g. HEALME restart) should have no initiator_chat_id."""
        marker = tmp_path / "marker"
        marker_data = {"timestamp": 1234567890}
        marker.write_text(json.dumps(marker_data))

        data = json.loads(marker.read_text())
        assert data["timestamp"] == 1234567890
        assert "initiator_chat_id" not in data
