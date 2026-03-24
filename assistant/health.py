"""
Two-tier session healing: fast regex + deep Haiku analysis.

Tier 1 (every 60s): Regex scan of recent transcript entries for known fatal errors.
Tier 2 (every 5 min): Haiku LLM classification of recent assistant messages.

Fatal errors are unrecoverable — the bad data is baked into conversation context
and will cause the same API error on every retry. Only a session restart fixes them.
"""
from __future__ import annotations

import json
import logging
import os
import plistlib
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)
lifecycle_log = logging.getLogger("lifecycle")

# ──────────────────────────────────────────────────────────────
# Tier 1: Regex-based fatal error detection
# ──────────────────────────────────────────────────────────────

# Pattern: (regex, label) — matched against assistant message text
FATAL_PATTERNS: list[tuple[str, str]] = [
    # Context-size patterns MUST come before generic invalid_request_400 catch-all
    # so check_fatal_regex (first-match) returns the specific label, enabling clean restart.
    (r"prompt is too long", "prompt_too_long"),
    (r"context_length_exceeded", "context_too_long"),
    (r"content size exceeds", "content_too_large"),
    (r"JSON message exceeded maximum buffer size", "buffer_overflow"),
    (r"API Error: 400.*invalid_request_error", "invalid_request_400"),
    (r"image dimensions exceed max allowed size", "image_too_large"),
    (r"Could not process image", "image_processing_failed"),
    (r"\"authentication_\w+\"", "auth_error"),
    (r"\"billing_error\"", "billing_error"),
]

# Compiled for performance (called every 60s across all sessions)
_COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), label) for p, label in FATAL_PATTERNS]


def get_transcript_entries_since(
    session_cwd: str,
    session_id: Optional[str],
    since: datetime,
) -> list[dict[str, Any]]:
    """Read recent assistant message entries from the session's transcript JSONL.

    Reads from end of file for efficiency (sessions can have thousands of lines).
    Only returns type=assistant entries newer than `since`.
    """
    transcript_path = _find_transcript(session_cwd, session_id)
    if not transcript_path or not transcript_path.exists():
        return []

    try:
        # Read last 128KB — enough for ~5-10 min of activity
        with open(transcript_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            chunk = min(size, 131072)
            f.seek(size - chunk)
            tail = f.read().decode('utf-8', errors='replace')
    except OSError as e:
        log.warning(f"Failed to read transcript {transcript_path}: {e}")
        return []

    # Ensure since is timezone-aware for comparison
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    entries = []
    for line in tail.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if obj.get('type') != 'assistant':
            continue

        ts_str = obj.get('timestamp', '')
        if not ts_str:
            continue

        try:
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            if ts > since:
                entries.append(obj)
        except ValueError:
            continue

    return entries


def check_fatal_regex(entries: list[dict[str, Any]]) -> Optional[str]:
    """Check assistant message entries for known fatal error patterns.

    Returns the pattern label if a fatal error is found, None otherwise.
    """
    for entry in entries:
        content = entry.get('message', {}).get('content', [])
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get('text', '')
            if not text:
                continue

            for pattern, label in _COMPILED_PATTERNS:
                if pattern.search(text):
                    return label

    return None


def extract_assistant_text(entries: list[dict[str, Any]], max_chars: int = 4000) -> str:
    """Extract text from assistant message entries for Haiku analysis.

    Concatenates TextBlock content, truncated to max_chars.
    """
    texts = []
    total = 0

    for entry in entries:
        content = entry.get('message', {}).get('content', [])
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get('text', '')
            if not text:
                continue

            remaining = max_chars - total
            if remaining <= 0:
                break
            chunk = text[:remaining]
            texts.append(chunk)
            total += len(chunk)

        if total >= max_chars:
            break

    return "\n---\n".join(texts)


# ──────────────────────────────────────────────────────────────
# Tier 2: Haiku-based deep analysis
# ──────────────────────────────────────────────────────────────

HAIKU_PROMPT = """You are a session health monitor for an AI assistant that communicates with users via SMS. Analyze these recent assistant messages and determine if the session needs intervention.

FATAL means the session is broken and needs a restart:
- API errors baked into conversation context (image dimensions, context length, invalid content) that will repeat on every retry
- Authentication or billing errors
- Repeated identical errors with no progress between them (same error 2+ times)
- Session crashed mid-task and never sent the user a response — the user is left hanging with no reply
- Session is stuck in a loop doing the same thing repeatedly without making progress

HEALTHY means the session is operating normally:
- Rate limits (429) or server overload (529) — these are transient
- Tool execution failures where Claude tries alternatives
- Normal error handling and recovery
- A single error followed by successful work
- Session is actively working on a task and making progress

Recent assistant messages (last 5 minutes):
{messages}

Respond with ONLY one of:
FATAL: <one-line reason>
HEALTHY"""


async def check_deep_haiku(entries: list[dict[str, Any]], session_name: str) -> Optional[str]:
    """Send recent assistant messages to Haiku for fatal error classification.

    Uses claude_agent_sdk.query() with model=haiku for a one-shot classification.
    Returns the diagnosis string if fatal, None if healthy.
    """
    text = extract_assistant_text(entries)
    if not text or len(text.strip()) < 20:
        return None

    try:
        from claude_agent_sdk import (
            query as sdk_query,
            ClaudeAgentOptions,
            AssistantMessage,
            TextBlock,
        )

        from pathlib import Path
        options = ClaudeAgentOptions(
            cli_path=Path.home() / ".local" / "bin" / "claude",  # Use system CLI for OAuth compat
            model="haiku",
            max_turns=1,
            permission_mode="bypassPermissions",
        )

        prompt = HAIKU_PROMPT.format(messages=text)
        result_text = ""
        async for message in sdk_query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text

        result = result_text.strip()
        log.info(f"DEEP_HEAL | {session_name} | Haiku response: {result}")

        if result.startswith("FATAL:"):
            return result[6:].strip()
        return None

    except Exception as e:
        log.warning(f"DEEP_HEAL | {session_name} | Haiku call failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Tier 3: Haiku-based stuck session investigation
# ──────────────────────────────────────────────────────────────

STUCK_INVESTIGATION_PROMPT = """You are investigating whether an AI assistant session is genuinely stuck or just working on a long task.

Context: A message was injected {stuck_minutes:.0f} minutes ago with no ResultMessage returned yet. The session process is alive.

Analyze the recent transcript entries below. These are the most recent tool calls, thinking, and messages from the session.

STUCK means the session is genuinely unresponsive or broken:
- No tool calls or thinking activity in the last 5+ minutes
- Session is in an error loop (same error repeating)
- Process is alive but producing no output at all
- Last activity was a tool call that seems to have hung (no result)

WORKING means the session is actively processing and should NOT be interrupted:
- Recent tool calls (Read, Grep, Bash, Agent, Write, Edit) — even if slow
- Thinking blocks indicate active reasoning
- Subagent operations in progress (Agent tool calls without results yet are normal — subagents can run 15+ min)
- Code exploration or research happening (multiple Read/Grep calls)
- The session is making forward progress, just slowly

Recent transcript entries (most recent last):
{entries}

Respond with ONLY one of:
STUCK: <one-line reason>
WORKING: <what it appears to be doing>"""


async def check_stuck_haiku(session_cwd: str, session_id: str | None,
                            session_name: str, stuck_minutes: float) -> bool:
    """Investigate if a session is genuinely stuck using Haiku.

    Reads recent transcript JSONL entries and asks Haiku to classify
    whether the session is stuck or just working on something long.

    Returns True if stuck (should restart), False if working (leave alone).
    """
    try:
        transcript_path = _find_transcript(session_cwd, session_id)
        if not transcript_path or not transcript_path.exists():
            log.warning(f"STUCK_CHECK | {session_name} | No transcript found, assuming stuck")
            return True

        # Read last 64KB of transcript for recent activity
        entries_text = ""
        with open(transcript_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            chunk = min(size, 65536)  # 64KB
            f.seek(size - chunk)
            raw = f.read().decode("utf-8", errors="replace")
            # Get last 30 valid JSON lines
            lines = [line for line in raw.strip().split("\n") if line.strip()]
            recent = lines[-30:]
            entries_text = "\n".join(recent)

        if not entries_text or len(entries_text.strip()) < 20:
            log.warning(f"STUCK_CHECK | {session_name} | Empty transcript, assuming stuck")
            return True

        from claude_agent_sdk import (
            query as sdk_query,
            ClaudeAgentOptions,
            AssistantMessage,
            TextBlock,
        )

        options = ClaudeAgentOptions(
            cli_path=Path.home() / ".local" / "bin" / "claude",
            model="haiku",
            max_turns=1,
            permission_mode="bypassPermissions",
        )

        prompt = STUCK_INVESTIGATION_PROMPT.format(
            stuck_minutes=stuck_minutes,
            entries=entries_text,
        )
        result_text = ""
        async for message in sdk_query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text

        result = result_text.strip()
        log.info(f"STUCK_CHECK | {session_name} | Haiku verdict: {result}")

        if result.startswith("STUCK:"):
            return True
        return False

    except Exception as e:
        log.warning(f"STUCK_CHECK | {session_name} | Haiku investigation failed: {e}")
        # On failure, don't restart — avoid false positives
        return False


# ──────────────────────────────────────────────────────────────
# Transcript file location
# ──────────────────────────────────────────────────────────────

def _find_transcript(session_cwd: str, session_id: Optional[str]) -> Optional[Path]:
    """Locate the active transcript JSONL for a session.

    Uses the SDK's project directory structure:
    ~/.claude/projects/{sanitized_cwd}/{session_id}.jsonl
    """
    if not session_cwd:
        return None

    # SDK sanitizes cwd: /Users/sven/transcripts/foo -> -Users-sven-transcripts-foo
    sanitized = session_cwd.replace("/", "-")
    if not sanitized.startswith("-"):
        sanitized = "-" + sanitized

    projects_dir = Path.home() / ".claude" / "projects" / sanitized

    if not projects_dir.exists():
        return None

    # If we have a session_id, use it directly
    if session_id:
        direct = projects_dir / f"{session_id}.jsonl"
        if direct.exists():
            return direct

    # Fallback: check sessions-index.json for most recent
    index_path = projects_dir / "sessions-index.json"
    if index_path.exists():
        try:
            with open(index_path) as f:
                index = json.load(f)
            entries = index.get("entries", [])
            if entries:
                entries.sort(key=lambda e: e.get("modified", ""), reverse=True)
                transcript_path = Path(entries[0]["fullPath"])
                if transcript_path.exists():
                    return transcript_path
        except (json.JSONDecodeError, KeyError):
            pass

    # Last resort: most recent .jsonl by mtime
    jsonl_files = list(projects_dir.glob("*.jsonl"))
    if jsonl_files:
        jsonl_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return jsonl_files[0]

    return None


# ──────────────────────────────────────────────────────────────
# Disk space monitoring
# ──────────────────────────────────────────────────────────────

# Track last alert time to avoid spamming (alert at most once per 30 min)
_last_disk_alert_time: float = 0.0


def _get_apfs_container_space() -> tuple[int, int] | None:
    """Get APFS container total and free bytes via diskutil.

    On macOS with APFS, the container free space includes purgeable space
    (caches, snapshots, etc. that macOS can reclaim on demand). This matches
    what macOS Settings shows as "Available" and avoids false disk warnings.

    Returns (total_bytes, free_bytes) or None if not available.
    """
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["diskutil", "info", "-plist", "/"],
            capture_output=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        plist = plistlib.loads(result.stdout)
        container_size = plist.get("APFSContainerSize")
        container_free = plist.get("APFSContainerFree")
        if container_size and container_free:
            return (container_size, container_free)
    except Exception as e:
        log.debug(f"APFS container query failed: {e}")
    return None


def check_disk_space(warn_pct: float = 90.0, critical_pct: float = 95.0) -> dict[str, Any]:
    """Check disk space on the root volume.

    On macOS with APFS, uses container-level free space which includes
    purgeable space (what macOS Settings shows as "Available"). Falls back
    to shutil.disk_usage on non-APFS or non-macOS systems.

    Returns dict with:
        total_gb, used_gb, free_gb, used_pct,
        warning (bool), critical (bool), message (str or None)
    """
    # Try APFS container space first (includes purgeable)
    apfs = _get_apfs_container_space()
    if apfs:
        total_bytes, free_bytes = apfs
        used_bytes = total_bytes - free_bytes
    else:
        usage = shutil.disk_usage("/")
        total_bytes = usage.total
        used_bytes = usage.used
        free_bytes = usage.free

    total_gb = total_bytes / (1024 ** 3)
    used_gb = used_bytes / (1024 ** 3)
    free_gb = free_bytes / (1024 ** 3)
    used_pct = (used_bytes / total_bytes) * 100

    result: dict[str, Any] = {
        "total_gb": round(total_gb, 1),
        "used_gb": round(used_gb, 1),
        "free_gb": round(free_gb, 1),
        "used_pct": round(used_pct, 1),
        "warning": used_pct >= warn_pct,
        "critical": used_pct >= critical_pct,
        "message": None,
    }

    if used_pct >= critical_pct:
        result["message"] = (
            f"DISK CRITICAL: {used_pct:.1f}% used "
            f"({free_gb:.1f}GB free of {total_gb:.0f}GB)"
        )
    elif used_pct >= warn_pct:
        result["message"] = (
            f"DISK WARNING: {used_pct:.1f}% used "
            f"({free_gb:.1f}GB free of {total_gb:.0f}GB)"
        )

    return result


def should_send_disk_alert() -> bool:
    """Rate-limit disk alerts to at most once per 30 minutes."""
    global _last_disk_alert_time
    import time
    now = time.time()
    if now - _last_disk_alert_time >= 1800:  # 30 minutes
        _last_disk_alert_time = now
        return True
    return False


# ──────────────────────────────────────────────────────────────
# Quota monitoring — alert admin when approaching usage limits
# ──────────────────────────────────────────────────────────────

# Thresholds to alert at (ascending order)
QUOTA_THRESHOLDS = [80, 90, 95]

# Track which thresholds have been alerted per quota type per reset cycle.
# Key: (quota_type, resets_at_iso) → set of thresholds already alerted
_quota_alerts_sent: dict[tuple[str, str], set[int]] = {}


def _get_oauth_token() -> str | None:
    """Get OAuth access token from macOS keychain."""
    try:
        raw = subprocess.check_output(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        import json as _json
        data = _json.loads(raw)
        return data.get("claudeAiOauth", {}).get("accessToken")
    except Exception:
        return None


def fetch_quota_oauth() -> dict | None:
    """Fetch usage quota via OAuth API. Returns raw usage dict or None."""
    token = _get_oauth_token()
    if not token:
        log.warning("QUOTA_CHECK | No OAuth token available")
        return None

    import ssl
    import urllib.request
    ctx = ssl.create_default_context()
    req = urllib.request.Request("https://api.anthropic.com/api/oauth/usage")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("anthropic-beta", "oauth-2025-04-20")
    req.add_header("Accept", "application/json")

    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=15)
        return json.loads(resp.read().decode())
    except Exception as e:
        log.warning(f"QUOTA_CHECK | OAuth fetch failed: {e}")
        return None


def check_quota_thresholds(usage: dict) -> list[dict[str, Any]]:
    """Check all quota blocks against thresholds.

    Returns list of alerts to send, each with:
        quota_type, utilization, threshold, resets_at
    Only returns alerts that haven't been sent yet for this reset cycle.
    """
    global _quota_alerts_sent

    alerts: list[dict[str, Any]] = []

    # Define which blocks to check
    blocks = [
        ("5-hour", usage.get("five_hour", {})),
        ("7-day all", usage.get("seven_day", {})),
        ("7-day sonnet", usage.get("seven_day_sonnet", {})),
        ("7-day opus", usage.get("seven_day_opus", {})),
    ]

    for quota_type, block in blocks:
        if not block:
            continue
        util = block.get("utilization")
        if util is None:
            continue
        resets_at = block.get("resets_at", "unknown")

        cache_key = (quota_type, resets_at)

        # Clean up old entries: if resets_at has passed, remove from cache
        if resets_at != "unknown":
            try:
                reset_dt = datetime.fromisoformat(resets_at)
                if reset_dt.tzinfo is None:
                    reset_dt = reset_dt.replace(tzinfo=timezone.utc)
                if reset_dt < datetime.now(timezone.utc):
                    _quota_alerts_sent.pop(cache_key, None)
                    continue  # Block has reset, skip
            except (ValueError, TypeError):
                pass

        sent = _quota_alerts_sent.get(cache_key, set())

        # Find all newly crossed thresholds
        newly_crossed = [t for t in QUOTA_THRESHOLDS if util >= t and t not in sent]

        if newly_crossed:
            # Only alert for the highest newly crossed threshold
            # (e.g. if first seen at 92%, alert 90% not both 80% and 90%)
            highest = max(newly_crossed)
            alerts.append({
                "quota_type": quota_type,
                "utilization": util,
                "threshold": highest,
                "resets_at": resets_at,
            })
            # Mark ALL crossed thresholds as sent (including lower ones)
            sent.update(newly_crossed)

        if sent:
            _quota_alerts_sent[cache_key] = sent

    # Prune stale entries (keep only entries with future reset times)
    stale_keys = []
    for key in _quota_alerts_sent:
        qt, ra = key
        if ra == "unknown":
            continue
        try:
            reset_dt = datetime.fromisoformat(ra)
            if reset_dt.tzinfo is None:
                reset_dt = reset_dt.replace(tzinfo=timezone.utc)
            if reset_dt < datetime.now(timezone.utc):
                stale_keys.append(key)
        except (ValueError, TypeError):
            stale_keys.append(key)
    for k in stale_keys:
        _quota_alerts_sent.pop(k, None)

    return alerts


def format_quota_alert(alert: dict[str, Any]) -> str:
    """Format a single quota alert into an SMS message."""
    util = alert["utilization"]
    threshold = alert["threshold"]
    quota_type = alert["quota_type"]
    resets_at = alert["resets_at"]

    # Format reset time
    reset_str = "unknown"
    if resets_at and resets_at != "unknown":
        try:
            dt = datetime.fromisoformat(resets_at)
            local = dt.astimezone()
            reset_str = local.strftime("%I:%M %p %Z").lstrip("0")
        except (ValueError, TypeError):
            reset_str = resets_at

    emoji = "🔴" if threshold >= 95 else "🟠" if threshold >= 90 else "🟡"
    return f"{emoji} {quota_type}: {util:.0f}% used (resets {reset_str})"
