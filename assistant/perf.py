"""
Performance metrics collection via structured JSONL logging.

Usage:
    from assistant.perf import timing, incr, gauge, timed

    # Record a timing
    timing("poll_cycle_ms", 45.2, component="daemon")

    # Increment a counter
    incr("messages_read", count=3, component="daemon")

    # Record a gauge
    gauge("active_sessions", 5, component="daemon")

    # Context manager for timing a block
    with timed("inject_ms", component="daemon", session="imessage/+1234"):
        do_something()

    # Decorator for timing a function (sync or async)
    @timed_fn("contact_lookup_ms", component="daemon")
    def lookup_contact(phone):
        ...

    @timed_fn("claude_response_ms", component="session")
    async def get_response():
        ...

Logs are written to ~/dispatch/logs/perf-YYYY-MM-DD.jsonl
"""

import inspect
import json
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

PERF_DIR = Path.home() / "dispatch" / "logs"
SCHEMA_VERSION = 1
MAX_FILE_SIZE_MB = 100

# Sampling state for high-frequency metrics
_sample_counters: dict[str, int] = {}

# Buffered writer: accumulate metrics in memory and flush periodically
# to avoid opening a file for every single metric.
import threading

_buffer: list[str] = []
_buffer_lock = threading.Lock()
_flush_timer: threading.Timer | None = None
_FLUSH_INTERVAL = 2.0  # seconds
_current_fh: Any = None
_current_date: str = ""
_size_exceeded: bool = False


def _get_file_handle():
    """Get or create the file handle for today's perf log."""
    global _current_fh, _current_date, _size_exceeded
    today = f"{datetime.now():%Y-%m-%d}"
    if _current_date != today:
        # Day rolled over, close old handle
        if _current_fh is not None:
            try:
                _current_fh.close()
            except Exception:
                pass
        _current_fh = None
        _current_date = today
        _size_exceeded = False

    if _size_exceeded:
        return None

    if _current_fh is None:
        PERF_DIR.mkdir(parents=True, exist_ok=True)
        path = PERF_DIR / f"perf-{today}.jsonl"
        if path.exists() and path.stat().st_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            _size_exceeded = True
            print(f"[perf] WARNING: {path} exceeds {MAX_FILE_SIZE_MB}MB, skipping", file=sys.stderr)
            return None
        _current_fh = open(path, "a")

    return _current_fh


def _flush_buffer():
    """Flush buffered metrics to disk.

    Both buffer drain and file handle access are protected by _buffer_lock
    to prevent race conditions on day rollover (Timer thread vs main thread).
    """
    global _flush_timer
    with _buffer_lock:
        if not _buffer:
            _flush_timer = None
            return
        lines = _buffer[:]
        _buffer.clear()
        _flush_timer = None

        # File handle access inside the lock to prevent concurrent
        # day-rollover from Timer thread and flush_metrics() caller
        try:
            fh = _get_file_handle()
            if fh:
                fh.write("".join(lines))
                fh.flush()
        except Exception as e:
            print(f"[perf] WARNING: failed to flush metrics: {e}", file=sys.stderr)


def _log_metric(metric: str, value: float, **labels: Any) -> None:
    """Buffer metric for periodic flush. Never raises."""
    global _flush_timer
    try:
        entry = {
            "v": SCHEMA_VERSION,
            "ts": datetime.now().isoformat(),
            "metric": metric,
            "value": value,
            **labels,
        }
        line = json.dumps(entry) + "\n"
        with _buffer_lock:
            _buffer.append(line)
            # Schedule a flush if none pending
            if _flush_timer is None:
                _flush_timer = threading.Timer(_FLUSH_INTERVAL, _flush_buffer)
                _flush_timer.daemon = True
                _flush_timer.start()
    except Exception as e:
        print(f"[perf] WARNING: failed to log metric: {e}", file=sys.stderr)


def flush_metrics():
    """Force-flush all buffered metrics to disk immediately.

    Call this before reading perf logs in tests, or during shutdown.
    """
    global _flush_timer
    with _buffer_lock:
        if _flush_timer is not None:
            _flush_timer.cancel()
            _flush_timer = None
    _flush_buffer()


def reset_state():
    """Reset all internal state. For testing only."""
    global _current_fh, _current_date, _size_exceeded, _flush_timer
    flush_metrics()
    with _buffer_lock:
        _buffer.clear()
    if _current_fh is not None:
        try:
            _current_fh.close()
        except Exception:
            pass
        _current_fh = None
    _current_date = ""
    _size_exceeded = False
    _sample_counters.clear()


def timing(metric: str, ms: float, *, sample_rate: int = 1, **labels: Any) -> None:
    """
    Record a timing metric in milliseconds.

    Args:
        metric: Metric name (e.g., "poll_cycle_ms")
        ms: Duration in milliseconds
        sample_rate: Only log every Nth call (default 1 = log all)
        **labels: Additional labels (component, session, etc.)
    """
    if sample_rate > 1:
        _sample_counters[metric] = _sample_counters.get(metric, 0) + 1
        if _sample_counters[metric] % sample_rate != 0:
            return
    _log_metric(metric, ms, **labels)


def incr(metric: str, count: int = 1, **labels: Any) -> None:
    """Record a counter increment."""
    _log_metric(metric, count, **labels)


def gauge(metric: str, value: float, **labels: Any) -> None:
    """Record a gauge metric (current value)."""
    _log_metric(metric, value, **labels)


@contextmanager
def timed(metric: str, *, sample_rate: int = 1, **labels: Any):
    """
    Context manager to time a block of code.

    Usage:
        with timed("inject_ms", component="daemon"):
            do_something()
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        timing(metric, elapsed_ms, sample_rate=sample_rate, **labels)


def timed_fn(metric: str, *, sample_rate: int = 1, **labels: Any):
    """
    Decorator to time a function (handles both sync and async).

    Usage:
        @timed_fn("contact_lookup_ms", component="daemon")
        def lookup_contact(phone):
            ...

        @timed_fn("claude_response_ms", component="session")
        async def get_response():
            ...
    """

    def decorator(fn):
        if inspect.iscoroutinefunction(fn):

            @wraps(fn)
            async def async_wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return await fn(*args, **kwargs)
                finally:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    timing(metric, elapsed_ms, sample_rate=sample_rate, **labels)

            return async_wrapper
        else:

            @wraps(fn)
            def sync_wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return fn(*args, **kwargs)
                finally:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    timing(metric, elapsed_ms, sample_rate=sample_rate, **labels)

            return sync_wrapper

    return decorator


def error(error_type: str, **labels: Any) -> None:
    """Record an error occurrence."""
    incr("error_count", error_type=error_type, **labels)


# ── Tool Execution Logging ──────────────────────────────────────────────

import re
import shlex
from urllib.parse import urlparse

SKILL_PATTERN = re.compile(r'\.claude/skills/([^/]+)/scripts/([^/\s]+)')


def parse_bash(tool_input: dict[str, Any]) -> dict[str, Any]:
    """Parse Bash command into structured fields."""
    command = tool_input.get("command", "")
    result: dict[str, Any] = {"command": command}

    try:
        result["cmd_argv"] = shlex.split(command)
    except ValueError:
        result["cmd_argv"] = command.split()

    # Detect skill from path
    match = SKILL_PATTERN.search(command)
    if match:
        result["skill"] = match.group(1)
        result["cmd_name"] = match.group(2)
    elif result["cmd_argv"]:
        result["cmd_name"] = Path(result["cmd_argv"][0]).name

    return result


def parse_file_tool(tool_input: dict[str, Any]) -> dict[str, Any]:
    """Parse Read/Write/Edit file path."""
    file_path = tool_input.get("file_path", "")
    result = dict(tool_input)
    if file_path:
        p = Path(file_path)
        result["extension"] = p.suffix or None
        result["directory"] = str(p.parent)
    return result


def parse_web_fetch(tool_input: dict[str, Any]) -> dict[str, Any]:
    """Parse WebFetch URL."""
    url = tool_input.get("url", "")
    result = dict(tool_input)
    if url:
        parsed = urlparse(url)
        result["domain"] = parsed.netloc or None
    return result


TOOL_PARSERS: dict[str, Any] = {
    "Bash": parse_bash,
    "Read": parse_file_tool,
    "Write": parse_file_tool,
    "Edit": parse_file_tool,
    "WebFetch": parse_web_fetch,
    # Grep, Glob, Task, WebSearch: raw input is already good
}


def log_tool_execution(
    session: str,
    tool: str,
    tool_input: dict[str, Any],
    duration_ms: float,
    is_error: bool = False,
    session_type: str | None = None,
) -> None:
    """Log tool execution timing to perf JSONL.

    Each tool gets smart parsing to extract queryable fields:
    - Bash: skill, cmd_name, cmd_argv
    - Read/Write/Edit: extension, directory
    - WebFetch: domain
    - Others: raw input passthrough
    """
    # Smart parse based on tool type
    parser = TOOL_PARSERS.get(tool)
    parsed_input = parser(tool_input) if parser else dict(tool_input)

    extra: dict[str, Any] = {}
    if session_type:
        extra["session_type"] = session_type

    _log_metric(
        "tool_execution",
        duration_ms,
        event="tool_execution",
        session=session,
        tool=tool,
        is_error=is_error,
        input=parsed_input,
        **extra,
    )
