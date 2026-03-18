"""
Tests for health check and auto-restart logic.

Covers:
- health_check_all identifies unhealthy sessions
- Auto-restart of unhealthy sessions
- Idle session detection thresholds
- Master/BG session exemption from idle killing
- Multiple unhealthy sessions handled correctly
- Health check doesn't restart healthy sessions
- Tier 1: Fast regex-based fatal error detection from transcripts
- Tier 2: Deep Haiku-based session analysis
- Deduplication between tiers
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio


@pytest.mark.asyncio
class TestHealthCheckAll:
    """Test health_check_all behavior."""

    async def test_all_healthy(self, sdk_backend):
        await sdk_backend.create_session("U1", "test:+15555550006", "admin", source="test")
        await sdk_backend.create_session("U2", "test:+15555550008", "admin", source="test")
        results = await sdk_backend.health_check_all()
        assert all(results.values())

    async def test_detects_unhealthy(self, sdk_backend):
        await sdk_backend.create_session("U1", "test:+15555550006", "admin", source="test")
        # Make it unhealthy
        session = sdk_backend.sessions["test:+15555550006"]
        session._error_count = 3
        results = await sdk_backend.health_check_all()
        # Should detect unhealthy and attempt restart
        assert "test:+15555550006" in results

    async def test_empty_sessions(self, sdk_backend):
        results = await sdk_backend.health_check_all()
        assert len(results) == 0


@pytest.mark.asyncio
class TestIdleSessionThresholds:
    """Test idle session detection at various thresholds."""

    async def test_exactly_at_threshold(self, sdk_backend):
        """Session idle for exactly the threshold should be killed."""
        await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        session = sdk_backend.sessions["test:+15555550006"]
        session.last_activity = datetime.now() - timedelta(hours=2, seconds=1)
        killed = await sdk_backend.check_idle_sessions(2.0)
        assert "test:+15555550006" in killed

    async def test_just_under_threshold(self, sdk_backend):
        """Session idle for just under threshold should survive."""
        await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        session = sdk_backend.sessions["test:+15555550006"]
        session.last_activity = datetime.now() - timedelta(hours=1, minutes=59)
        killed = await sdk_backend.check_idle_sessions(2.0)
        assert len(killed) == 0

    async def test_mixed_idle_and_active(self, sdk_backend):
        """Only idle sessions should be killed, active ones preserved."""
        await sdk_backend.create_session("Idle", "test:+15555550006", "admin", source="test")
        await sdk_backend.create_session("Active", "test:+15555550008", "admin", source="test")

        sdk_backend.sessions["test:+15555550006"].last_activity = datetime.now() - timedelta(hours=5)
        sdk_backend.sessions["test:+15555550008"].last_activity = datetime.now()

        killed = await sdk_backend.check_idle_sessions(2.0)
        assert "test:+15555550006" in killed
        assert "test:+15555550008" not in killed
        # Active session should still exist
        assert "test:+15555550008" in sdk_backend.sessions


@pytest.mark.asyncio
class TestSpecialSessionExemptions:
    """Test that BG and master sessions are exempt from idle killing."""

    async def test_bg_session_exempt(self, sdk_backend):
        await sdk_backend.create_session("User", "test:+15555550006-bg", "admin", source="test")
        sdk_backend.sessions["test:+15555550006-bg"].last_activity = datetime.now() - timedelta(hours=10)
        killed = await sdk_backend.check_idle_sessions(2.0)
        assert len(killed) == 0

    async def test_master_session_exempt(self, sdk_backend):
        """Master session should never be idle-killed."""
        from assistant.common import MASTER_SESSION
        # Create a session with the master key
        await sdk_backend.create_session("Master", MASTER_SESSION, "admin", source="imessage")
        sdk_backend.sessions[MASTER_SESSION].last_activity = datetime.now() - timedelta(hours=24)
        killed = await sdk_backend.check_idle_sessions(2.0)
        assert MASTER_SESSION not in killed


@pytest.mark.asyncio
class TestHealthCheckDoesNotOverRestart:
    """Ensure healthy sessions are not restarted."""

    async def test_healthy_session_not_restarted(self, sdk_backend):
        s1 = await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        s1_id = id(s1)
        await sdk_backend.health_check_all()
        # Session object should be the same (not restarted)
        s2 = sdk_backend.sessions.get("test:+15555550006")
        assert s2 is not None
        assert id(s2) == s1_id


# ──────────────────────────────────────────────────────────────
# Tier 1: Fast regex-based fatal error detection (health.py)
# ──────────────────────────────────────────────────────────────

def _make_assistant_entry(text: str, ts: datetime | None = None) -> dict:
    """Create a fake transcript assistant entry for testing."""
    if ts is None:
        ts = datetime.now(timezone.utc)
    return {
        "type": "assistant",
        "timestamp": ts.isoformat(),
        "message": {
            "content": [{"type": "text", "text": text}],
            "model": "claude-opus-4-5-20251101",
        },
    }


class TestCheckFatalRegex:
    """Test regex-based fatal error detection."""

    def test_detects_image_dimension_error(self):
        from assistant.health import check_fatal_regex
        entries = [_make_assistant_entry(
            'API Error: 400 {"type":"error","error":{"type":"invalid_request_error",'
            '"message":"messages.21.content.94.image.source.base64.data: At least one '
            'of the image dimensions exceed max allowed size for many-image requests: 2000 pixels"}}'
        )]
        result = check_fatal_regex(entries)
        assert result is not None
        assert "invalid_request" in result or "image" in result

    def test_detects_context_length_exceeded(self):
        from assistant.health import check_fatal_regex
        entries = [_make_assistant_entry(
            'API Error: 400 {"type":"error","error":{"type":"invalid_request_error",'
            '"message":"context_length_exceeded: the prompt is too long"}}'
        )]
        result = check_fatal_regex(entries)
        assert result is not None

    def test_detects_prompt_too_long(self):
        from assistant.health import check_fatal_regex
        entries = [_make_assistant_entry(
            'API Error: 400 prompt is too long: 250000 tokens'
        )]
        result = check_fatal_regex(entries)
        assert result is not None

    def test_detects_image_processing_failed(self):
        from assistant.health import check_fatal_regex
        entries = [_make_assistant_entry(
            'Could not process image at /path/to/image.png'
        )]
        result = check_fatal_regex(entries)
        assert result == "image_processing_failed"

    def test_detects_auth_failed(self):
        from assistant.health import check_fatal_regex
        entries = [_make_assistant_entry(
            'Error: "authentication_failed" - your API key is invalid'
        )]
        result = check_fatal_regex(entries)
        assert result == "auth_error"

    def test_detects_auth_error(self):
        """Test that authentication_error is also detected (the actual API error type)."""
        from assistant.health import check_fatal_regex
        entries = [_make_assistant_entry(
            'Error: "authentication_error" - invalid API key'
        )]
        result = check_fatal_regex(entries)
        assert result == "auth_error"

    def test_detects_billing_error(self):
        from assistant.health import check_fatal_regex
        entries = [_make_assistant_entry(
            'Error: "billing_error" - account has insufficient credits'
        )]
        result = check_fatal_regex(entries)
        assert result == "billing_error"

    def test_ignores_transient_rate_limit(self):
        from assistant.health import check_fatal_regex
        entries = [_make_assistant_entry(
            'Rate limit exceeded. Retrying in 5 seconds...'
        )]
        result = check_fatal_regex(entries)
        assert result is None

    def test_ignores_server_overload(self):
        from assistant.health import check_fatal_regex
        entries = [_make_assistant_entry(
            'Server overloaded (529). Retrying...'
        )]
        result = check_fatal_regex(entries)
        assert result is None

    def test_ignores_normal_text(self):
        from assistant.health import check_fatal_regex
        entries = [_make_assistant_entry(
            "I'll help you with that task. Let me check the files."
        )]
        result = check_fatal_regex(entries)
        assert result is None

    def test_empty_entries(self):
        from assistant.health import check_fatal_regex
        assert check_fatal_regex([]) is None

    def test_multiple_entries_catches_fatal_in_any(self):
        from assistant.health import check_fatal_regex
        entries = [
            _make_assistant_entry("I'll look into that."),
            _make_assistant_entry("Let me check the code."),
            _make_assistant_entry(
                'API Error: 400 {"type":"error","error":{"type":"invalid_request_error",'
                '"message":"image dimensions exceed max allowed size"}}'
            ),
        ]
        result = check_fatal_regex(entries)
        assert result is not None

    def test_detects_content_size_exceeds(self):
        from assistant.health import check_fatal_regex
        entries = [_make_assistant_entry(
            'API Error: 400 content size exceeds maximum allowed size'
        )]
        result = check_fatal_regex(entries)
        assert result == "content_too_large"


class TestExtractAssistantText:
    """Test text extraction from transcript entries."""

    def test_extracts_text_blocks(self):
        from assistant.health import extract_assistant_text
        entries = [
            _make_assistant_entry("Hello world"),
            _make_assistant_entry("Second message"),
        ]
        result = extract_assistant_text(entries)
        assert "Hello world" in result
        assert "Second message" in result

    def test_respects_max_chars(self):
        from assistant.health import extract_assistant_text
        entries = [_make_assistant_entry("x" * 5000)]
        result = extract_assistant_text(entries, max_chars=100)
        assert len(result) <= 100

    def test_empty_entries(self):
        from assistant.health import extract_assistant_text
        assert extract_assistant_text([]) == ""

    def test_skips_non_text_content(self):
        from assistant.health import extract_assistant_text
        entries = [{
            "type": "assistant",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": {
                "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}],
            },
        }]
        result = extract_assistant_text(entries)
        assert result == ""


class TestGetTranscriptEntriesSince:
    """Test transcript JSONL reading."""

    def test_reads_entries_after_timestamp(self, tmp_path):
        from assistant.health import get_transcript_entries_since

        # Create a fake transcript
        now = datetime.now(timezone.utc)
        old = now - timedelta(minutes=10)
        recent = now - timedelta(seconds=30)

        lines = [
            json.dumps({
                "type": "assistant",
                "timestamp": old.isoformat(),
                "message": {"content": [{"type": "text", "text": "old message"}]},
            }),
            json.dumps({
                "type": "assistant",
                "timestamp": recent.isoformat(),
                "message": {"content": [{"type": "text", "text": "recent message"}]},
            }),
        ]

        # Write to a fake transcript location
        session_id = "test-session-abc"
        sanitized_cwd = str(tmp_path / "cwd").replace("/", "-")
        if not sanitized_cwd.startswith("-"):
            sanitized_cwd = "-" + sanitized_cwd
        project_dir = Path.home() / ".claude" / "projects" / sanitized_cwd
        project_dir.mkdir(parents=True, exist_ok=True)
        transcript = project_dir / f"{session_id}.jsonl"
        transcript.write_text("\n".join(lines))

        try:
            since = now - timedelta(minutes=5)
            entries = get_transcript_entries_since(str(tmp_path / "cwd"), session_id, since)
            assert len(entries) == 1
            assert "recent message" in json.dumps(entries[0])
        finally:
            # Cleanup
            transcript.unlink(missing_ok=True)
            try:
                project_dir.rmdir()
            except OSError:
                pass

    def test_returns_empty_for_missing_transcript(self):
        from assistant.health import get_transcript_entries_since
        entries = get_transcript_entries_since("/nonexistent/path", "no-session", datetime.now(timezone.utc))
        assert entries == []

    def test_filters_non_assistant_types(self, tmp_path):
        from assistant.health import get_transcript_entries_since

        now = datetime.now(timezone.utc)
        lines = [
            json.dumps({"type": "user", "timestamp": now.isoformat(), "message": {"content": "hello"}}),
            json.dumps({"type": "system", "timestamp": now.isoformat(), "subtype": "init"}),
            json.dumps({"type": "assistant", "timestamp": now.isoformat(), "message": {"content": [{"type": "text", "text": "response"}]}}),
        ]

        session_id = "test-filter"
        sanitized_cwd = str(tmp_path / "filter-cwd").replace("/", "-")
        if not sanitized_cwd.startswith("-"):
            sanitized_cwd = "-" + sanitized_cwd
        project_dir = Path.home() / ".claude" / "projects" / sanitized_cwd
        project_dir.mkdir(parents=True, exist_ok=True)
        transcript = project_dir / f"{session_id}.jsonl"
        transcript.write_text("\n".join(lines))

        try:
            since = now - timedelta(minutes=1)
            entries = get_transcript_entries_since(str(tmp_path / "filter-cwd"), session_id, since)
            assert len(entries) == 1
            assert entries[0]["type"] == "assistant"
        finally:
            transcript.unlink(missing_ok=True)
            try:
                project_dir.rmdir()
            except OSError:
                pass


# ──────────────────────────────────────────────────────────────
# Tier 2: Deep Haiku analysis (health.py)
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestCheckDeepHaiku:
    """Test Haiku-based session analysis."""

    async def test_returns_none_for_empty_entries(self):
        from assistant.health import check_deep_haiku
        result = await check_deep_haiku([], "test-session")
        assert result is None

    async def test_returns_none_for_short_text(self):
        from assistant.health import check_deep_haiku
        entries = [_make_assistant_entry("ok")]
        result = await check_deep_haiku(entries, "test-session")
        assert result is None

    async def test_fatal_response_returns_reason(self):
        from assistant.health import check_deep_haiku
        from claude_agent_sdk import AssistantMessage, TextBlock, ResultMessage

        async def _fake_query(**kwargs):
            yield AssistantMessage([TextBlock("FATAL: Repeated image dimension errors with no recovery")])
            yield ResultMessage()

        entries = [_make_assistant_entry("API Error: 400 image dimensions exceed max")]

        with patch("claude_agent_sdk.query", _fake_query):
            result = await check_deep_haiku(entries, "test-session")

        assert result is not None
        assert "image" in result.lower()

    async def test_healthy_response_returns_none(self):
        from assistant.health import check_deep_haiku
        from claude_agent_sdk import AssistantMessage, TextBlock, ResultMessage

        async def _fake_query(**kwargs):
            yield AssistantMessage([TextBlock("HEALTHY")])
            yield ResultMessage()

        entries = [_make_assistant_entry("I'll help with that task.")]

        with patch("claude_agent_sdk.query", _fake_query):
            result = await check_deep_haiku(entries, "test-session")

        assert result is None

    async def test_api_failure_returns_none(self):
        from assistant.health import check_deep_haiku

        entries = [_make_assistant_entry("Some error message that is long enough")]

        async def _failing_query(**kwargs):
            raise Exception("SDK query failed")
            yield  # noqa: unreachable — makes this an async generator

        with patch("claude_agent_sdk.query", _failing_query):
            result = await check_deep_haiku(entries, "test-session")

        assert result is None  # Graceful fallback, don't crash


# ──────────────────────────────────────────────────────────────
# Integration: SDKBackend fast_health_check / deep_health_check
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestFastHealthCheck:
    """Test Tier 1 fast regex health check on SDKBackend."""

    async def test_no_sessions_returns_empty(self, sdk_backend):
        result = await sdk_backend.fast_health_check()
        assert result == []

    async def test_healthy_sessions_not_restarted(self, sdk_backend):
        await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        # No transcript = no entries = no fatal errors
        result = await sdk_backend.fast_health_check()
        assert result == []

    async def test_detects_fatal_from_transcript(self, sdk_backend):
        await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        session = sdk_backend.sessions["test:+15555550006"]

        # Mock get_transcript_entries_since to return a fatal entry
        fatal_entry = _make_assistant_entry(
            'API Error: 400 {"type":"error","error":{"type":"invalid_request_error",'
            '"message":"image dimensions exceed max allowed size for many-image requests: 2000 pixels"}}'
        )

        with patch("assistant.sdk_backend.get_transcript_entries_since", return_value=[fatal_entry]):
            with patch("assistant.sdk_backend.check_fatal_regex", return_value="image_too_large"):
                result = await sdk_backend.fast_health_check()

        assert "test:+15555550006" in result
        assert "test:+15555550006" in sdk_backend._recently_healed

    async def test_skips_bg_sessions(self, sdk_backend):
        await sdk_backend.create_session("User", "test:+15555550006-bg", "admin", source="test")

        with patch("assistant.sdk_backend.get_transcript_entries_since") as mock:
            await sdk_backend.fast_health_check()
            mock.assert_not_called()

    async def test_skips_recently_healed(self, sdk_backend):
        await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        sdk_backend._recently_healed["test:+15555550006"] = datetime.now()

        with patch("assistant.sdk_backend.get_transcript_entries_since") as mock:
            await sdk_backend.fast_health_check()
            mock.assert_not_called()

    async def test_updates_last_fast_check(self, sdk_backend):
        await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")

        with patch("assistant.sdk_backend.get_transcript_entries_since", return_value=[]):
            await sdk_backend.fast_health_check()

        assert "test:+15555550006" in sdk_backend._last_fast_check


@pytest.mark.asyncio
class TestDeepHealthCheck:
    """Test Tier 2 deep Haiku health check on SDKBackend."""

    async def test_no_sessions_returns_empty(self, sdk_backend):
        result = await sdk_backend.deep_health_check()
        assert result == []

    async def test_skips_sessions_in_skip_set(self, sdk_backend):
        await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")

        with patch("assistant.sdk_backend.get_transcript_entries_since") as mock:
            await sdk_backend.deep_health_check(skip_chat_ids={"test:+15555550006"})
            mock.assert_not_called()

    async def test_skips_recently_healed(self, sdk_backend):
        await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        sdk_backend._recently_healed["test:+15555550006"] = datetime.now()

        with patch("assistant.sdk_backend.get_transcript_entries_since") as mock:
            await sdk_backend.deep_health_check()
            mock.assert_not_called()

    async def test_calls_haiku_with_entries(self, sdk_backend):
        await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")

        entries = [_make_assistant_entry("Something suspicious")]

        with patch("assistant.sdk_backend.get_transcript_entries_since", return_value=entries):
            with patch("assistant.sdk_backend.check_deep_haiku", new_callable=AsyncMock, return_value=None) as mock_haiku:
                await sdk_backend.deep_health_check()
                mock_haiku.assert_called_once()

    async def test_restarts_on_fatal_haiku_diagnosis(self, sdk_backend):
        await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")

        entries = [_make_assistant_entry("Repeated errors")]

        with patch("assistant.sdk_backend.get_transcript_entries_since", return_value=entries):
            with patch("assistant.sdk_backend.check_deep_haiku", new_callable=AsyncMock, return_value="Session stuck in error loop"):
                result = await sdk_backend.deep_health_check()

        assert "test:+15555550006" in result
        assert "test:+15555550006" in sdk_backend._recently_healed


@pytest.mark.asyncio
class TestHealingDeduplication:
    """Test that Tier 1 and Tier 2 don't double-heal the same session."""

    async def test_recently_healed_expires(self, sdk_backend):
        """Recently healed entries should expire after 5 minutes."""
        sdk_backend._recently_healed["old"] = datetime.now() - timedelta(minutes=6)
        sdk_backend._recently_healed["recent"] = datetime.now()

        # fast_health_check cleans stale entries
        with patch("assistant.sdk_backend.get_transcript_entries_since", return_value=[]):
            await sdk_backend.fast_health_check()

        assert "old" not in sdk_backend._recently_healed
        assert "recent" in sdk_backend._recently_healed

    async def test_recently_healed_prevents_check_session_health(self, sdk_backend):
        """check_session_health should skip sessions in _recently_healed (prevents double-restart)."""
        session = await sdk_backend.create_session("User", "test:+15555550099", "admin", source="test")
        # Make session unhealthy
        session._error_count = 100

        # Mark as recently healed
        sdk_backend._recently_healed["test:+15555550099"] = datetime.now()

        # check_session_health should return True (skip) and NOT fire a restart
        result = await sdk_backend.check_session_health("test:+15555550099")
        assert result is True

    async def test_check_session_health_marks_recently_healed(self, sdk_backend):
        """check_session_health should mark chat_id in _recently_healed before restarting."""
        session = await sdk_backend.create_session("User", "test:+15555550098", "admin", source="test")
        # Make session unhealthy
        session._error_count = 100

        assert "test:+15555550098" not in sdk_backend._recently_healed

        with patch.object(sdk_backend, "restart_session", new_callable=AsyncMock):
            await sdk_backend.check_session_health("test:+15555550098")

        assert "test:+15555550098" in sdk_backend._recently_healed

    async def test_tier1_heal_prevents_tier2(self, sdk_backend):
        """Session healed by fast check should be skipped by deep check."""
        await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")

        fatal_entry = _make_assistant_entry('API Error: 400 invalid_request_error image dimensions')

        # Tier 1 catches it
        with patch("assistant.sdk_backend.get_transcript_entries_since", return_value=[fatal_entry]):
            with patch("assistant.sdk_backend.check_fatal_regex", return_value="image_too_large"):
                healed = await sdk_backend.fast_health_check()

        assert "test:+15555550006" in healed

        # Tier 2 should skip it
        with patch("assistant.sdk_backend.get_transcript_entries_since") as mock_entries:
            with patch("assistant.sdk_backend.check_deep_haiku") as mock_haiku:
                await sdk_backend.deep_health_check(skip_chat_ids=set(healed))
                mock_entries.assert_not_called()
                mock_haiku.assert_not_called()


# ──────────────────────────────────────────────────────────────
# Stuck session detection (is_healthy with last_inject_at / last_response_at)
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestStuckSessionDetection:
    """Test that is_healthy() detects stuck sessions where a message was
    injected but no ResultMessage received for 10+ minutes."""

    async def test_healthy_fresh_session(self, sdk_backend):
        """Fresh session (system prompt injected, no response yet) should be healthy
        because it hasn't been stuck for 10+ minutes."""
        session = await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        healthy, reason = session.is_healthy()
        assert healthy
        assert reason == "ok"
        # last_inject_at is set by the system prompt injection during create_session
        assert session.last_inject_at is not None

    async def test_healthy_when_response_after_inject(self, sdk_backend):
        """Session with response after inject should be healthy."""
        session = await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        session.last_inject_at = datetime.now() - timedelta(minutes=15)
        session.last_response_at = datetime.now() - timedelta(minutes=5)
        healthy, reason = session.is_healthy()
        assert healthy

    async def test_unhealthy_when_stuck_over_10_min(self, sdk_backend):
        """Session stuck for >10 min after inject should be flagged as stuck.
        Note: check_session_health() will then use Haiku to confirm before restarting."""
        session = await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        session.last_inject_at = datetime.now() - timedelta(minutes=15)
        session.last_response_at = datetime.now() - timedelta(minutes=20)
        healthy, reason = session.is_healthy()
        assert not healthy
        assert "stuck" in reason

    async def test_healthy_when_stuck_under_10_min(self, sdk_backend):
        """Session stuck for <10 min should still be healthy (processing)."""
        session = await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        session.last_inject_at = datetime.now() - timedelta(minutes=5)
        session.last_response_at = datetime.now() - timedelta(minutes=10)
        healthy, reason = session.is_healthy()
        assert healthy

    async def test_inject_updates_last_inject_at(self, sdk_backend):
        """inject() should update last_inject_at to current time."""
        session = await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        # last_inject_at already set by system prompt injection
        old_inject_at = session.last_inject_at
        before = datetime.now()
        await session.inject("test message")
        assert session.last_inject_at is not None
        assert session.last_inject_at >= before
        assert session.last_inject_at > old_inject_at

    async def test_stuck_detection_triggers_health_check(self, sdk_backend):
        """health_check_all should detect stuck sessions (Haiku investigation handles restart)."""
        session = await sdk_backend.create_session("User", "test:+15555550006", "admin", source="test")
        session.last_inject_at = datetime.now() - timedelta(minutes=15)
        session.last_response_at = datetime.now() - timedelta(minutes=20)
        healthy, reason = session.is_healthy()
        assert not healthy
        results = await sdk_backend.health_check_all()
        assert "test:+15555550006" in results
