"""Tests for the performance metrics module."""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from assistant import perf


@pytest.fixture
def temp_perf_dir(tmp_path):
    """Use a temporary directory for perf logs."""
    perf.reset_state()  # Clean up any prior buffered state
    with patch.object(perf, "PERF_DIR", tmp_path):
        yield tmp_path
        perf.reset_state()  # Flush and clean up after test


def read_perf_log(perf_dir: Path) -> list[dict]:
    """Read all entries from today's perf log."""
    perf.flush_metrics()  # Ensure buffered metrics are written to disk
    log_file = perf_dir / f"perf-{datetime.now():%Y-%m-%d}.jsonl"
    if not log_file.exists():
        return []
    entries = []
    with open(log_file) as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries


class TestTiming:
    def test_timing_logs_metric(self, temp_perf_dir):
        perf.timing("test_metric", 42.5, component="test")

        entries = read_perf_log(temp_perf_dir)
        assert len(entries) == 1
        assert entries[0]["metric"] == "test_metric"
        assert entries[0]["value"] == 42.5
        assert entries[0]["component"] == "test"
        assert entries[0]["v"] == 1
        assert "ts" in entries[0]

    def test_timing_with_sampling(self, temp_perf_dir):
        # Log 10 calls with sample_rate=5
        for i in range(10):
            perf.timing("sampled_metric", float(i), sample_rate=5, component="test")

        entries = read_perf_log(temp_perf_dir)
        # Should only log every 5th call (indices 4 and 9 since we start at 1)
        assert len(entries) == 2

    def test_timing_sample_rate_1_logs_all(self, temp_perf_dir):
        for i in range(5):
            perf.timing("all_metric", float(i), sample_rate=1, component="test")

        entries = read_perf_log(temp_perf_dir)
        assert len(entries) == 5


class TestIncr:
    def test_incr_logs_count(self, temp_perf_dir):
        perf.incr("messages_read", count=3, component="daemon")

        entries = read_perf_log(temp_perf_dir)
        assert len(entries) == 1
        assert entries[0]["metric"] == "messages_read"
        assert entries[0]["value"] == 3
        assert entries[0]["component"] == "daemon"

    def test_incr_default_count(self, temp_perf_dir):
        perf.incr("events")

        entries = read_perf_log(temp_perf_dir)
        assert entries[0]["value"] == 1


class TestGauge:
    def test_gauge_logs_value(self, temp_perf_dir):
        perf.gauge("active_sessions", 7, component="daemon")

        entries = read_perf_log(temp_perf_dir)
        assert len(entries) == 1
        assert entries[0]["metric"] == "active_sessions"
        assert entries[0]["value"] == 7


class TestTimedContextManager:
    def test_timed_context_logs_duration(self, temp_perf_dir):
        with perf.timed("test_duration_ms", component="test"):
            # Simulate some work
            pass

        entries = read_perf_log(temp_perf_dir)
        assert len(entries) == 1
        assert entries[0]["metric"] == "test_duration_ms"
        assert entries[0]["value"] >= 0  # Should be a non-negative duration
        assert entries[0]["component"] == "test"

    def test_timed_context_logs_on_exception(self, temp_perf_dir):
        with pytest.raises(ValueError):
            with perf.timed("error_duration_ms", component="test"):
                raise ValueError("test error")

        # Should still log even if exception was raised
        entries = read_perf_log(temp_perf_dir)
        assert len(entries) == 1
        assert entries[0]["metric"] == "error_duration_ms"


class TestTimedDecorator:
    def test_timed_fn_sync(self, temp_perf_dir):
        @perf.timed_fn("sync_fn_ms", component="test")
        def my_sync_fn(x, y):
            return x + y

        result = my_sync_fn(2, 3)

        assert result == 5
        entries = read_perf_log(temp_perf_dir)
        assert len(entries) == 1
        assert entries[0]["metric"] == "sync_fn_ms"

    def test_timed_fn_async(self, temp_perf_dir):
        @perf.timed_fn("async_fn_ms", component="test")
        async def my_async_fn(x, y):
            await asyncio.sleep(0.001)
            return x * y

        result = asyncio.run(my_async_fn(3, 4))

        assert result == 12
        entries = read_perf_log(temp_perf_dir)
        assert len(entries) == 1
        assert entries[0]["metric"] == "async_fn_ms"
        assert entries[0]["value"] >= 1  # At least 1ms from sleep

    def test_timed_fn_logs_on_exception(self, temp_perf_dir):
        @perf.timed_fn("error_fn_ms", component="test")
        def my_error_fn():
            raise RuntimeError("oops")

        with pytest.raises(RuntimeError):
            my_error_fn()

        entries = read_perf_log(temp_perf_dir)
        assert len(entries) == 1


class TestError:
    def test_error_logs_with_type(self, temp_perf_dir):
        perf.error("contact_lookup_failed", component="daemon")

        entries = read_perf_log(temp_perf_dir)
        assert len(entries) == 1
        assert entries[0]["metric"] == "error_count"
        assert entries[0]["error_type"] == "contact_lookup_failed"
        assert entries[0]["value"] == 1


class TestGracefulDegradation:
    def test_write_failure_does_not_raise(self, temp_perf_dir):
        # Make the directory read-only to simulate write failure
        with patch.object(perf, "PERF_DIR", Path("/nonexistent/path")):
            # Should not raise, just log to stderr
            perf.timing("test", 1.0)

    def test_file_size_limit(self, temp_perf_dir):
        # Create a file that's already at the limit
        log_file = temp_perf_dir / f"perf-{datetime.now():%Y-%m-%d}.jsonl"
        with open(log_file, "w") as f:
            # Write more than MAX_FILE_SIZE_MB worth of data
            f.write("x" * (perf.MAX_FILE_SIZE_MB * 1024 * 1024 + 1))

        # This should skip logging
        perf.timing("test", 1.0)

        # File should still be at original size (no append)
        content = log_file.read_text()
        assert content.startswith("x" * 100)  # Still contains our dummy data
        assert '"metric"' not in content  # No new entry added


class TestIntegration:
    """End-to-end test of the perf logging system."""

    def test_full_workflow(self, temp_perf_dir):
        """Test the full workflow of logging and reading metrics."""
        # Simulate daemon metrics
        perf.timing("poll_cycle_ms", 45.2, component="daemon")
        perf.incr("messages_read", count=2, component="daemon")
        perf.gauge("active_sessions", 3, component="daemon")

        # Simulate session metrics
        with perf.timed("inject_ms", component="daemon", session="test"):
            pass

        @perf.timed_fn("response_ms", component="session")
        def process():
            return "done"

        process()

        perf.error("network_timeout", component="daemon")

        # Verify all logged
        entries = read_perf_log(temp_perf_dir)
        assert len(entries) == 6

        metrics = {e["metric"] for e in entries}
        assert metrics == {
            "poll_cycle_ms",
            "messages_read",
            "active_sessions",
            "inject_ms",
            "response_ms",
            "error_count",
        }


class TestToolExecutionLogging:
    """Tests for tool execution performance logging."""

    def test_parse_bash_skill_detection(self):
        result = perf.parse_bash({"command": "~/.claude/skills/contacts/scripts/contact-lookup +1617"})
        assert result["skill"] == "contacts"
        assert result["cmd_name"] == "contact-lookup"
        assert result["cmd_argv"] == ["~/.claude/skills/contacts/scripts/contact-lookup", "+1617"]

    def test_parse_bash_no_skill(self):
        result = perf.parse_bash({"command": "ls -la /tmp"})
        assert "skill" not in result
        assert result["cmd_name"] == "ls"

    def test_parse_bash_quoted_args(self):
        result = perf.parse_bash({"command": 'send-sms "+1234" "hello world"'})
        assert result["cmd_argv"] == ["send-sms", "+1234", "hello world"]

    def test_parse_bash_invalid_quotes_fallback(self):
        # shlex.split fails on unclosed quotes, should fallback to simple split
        result = perf.parse_bash({"command": 'echo "unclosed'})
        assert result["cmd_argv"] == ['echo', '"unclosed']

    def test_parse_file_tool(self):
        result = perf.parse_file_tool({"file_path": "/Users/sven/code/example.py"})
        assert result["extension"] == ".py"
        assert result["directory"] == "/Users/sven/code"

    def test_parse_file_tool_no_extension(self):
        result = perf.parse_file_tool({"file_path": "/Users/sven/code/Makefile"})
        assert result["extension"] is None
        assert result["directory"] == "/Users/sven/code"

    def test_parse_web_fetch(self):
        result = perf.parse_web_fetch({"url": "https://api.example.com/v1/data"})
        assert result["domain"] == "api.example.com"

    def test_parse_web_fetch_no_url(self):
        result = perf.parse_web_fetch({"prompt": "get data"})
        assert result.get("domain") is None

    def test_log_tool_execution_bash(self, temp_perf_dir):
        perf.log_tool_execution(
            session="imessage/+1617",
            tool="Bash",
            tool_input={"command": "~/.claude/skills/contacts/scripts/contact-lookup +1617"},
            duration_ms=72.5,
            is_error=False,
        )

        entries = read_perf_log(temp_perf_dir)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["metric"] == "tool_execution"
        assert entry["tool"] == "Bash"
        assert entry["session"] == "imessage/+1617"
        assert entry["value"] == 72.5
        assert entry["is_error"] is False
        assert entry["input"]["skill"] == "contacts"
        assert entry["input"]["cmd_name"] == "contact-lookup"

    def test_log_tool_execution_read(self, temp_perf_dir):
        perf.log_tool_execution(
            session="imessage/+1617",
            tool="Read",
            tool_input={"file_path": "/Users/sven/code/example.py", "offset": 0, "limit": 100},
            duration_ms=5.0,
        )

        entries = read_perf_log(temp_perf_dir)
        entry = entries[0]
        assert entry["tool"] == "Read"
        assert entry["input"]["extension"] == ".py"
        assert entry["input"]["directory"] == "/Users/sven/code"

    def test_log_tool_execution_unknown_tool(self, temp_perf_dir):
        """Unknown tools should pass through with raw input."""
        perf.log_tool_execution(
            session="imessage/+1617",
            tool="SomeNewTool",
            tool_input={"foo": "bar", "baz": 123},
            duration_ms=100.0,
        )

        entries = read_perf_log(temp_perf_dir)
        entry = entries[0]
        assert entry["tool"] == "SomeNewTool"
        assert entry["input"] == {"foo": "bar", "baz": 123}

    def test_log_tool_execution_with_error(self, temp_perf_dir):
        perf.log_tool_execution(
            session="imessage/+1617",
            tool="Bash",
            tool_input={"command": "false"},
            duration_ms=10.0,
            is_error=True,
        )

        entries = read_perf_log(temp_perf_dir)
        assert entries[0]["is_error"] is True
