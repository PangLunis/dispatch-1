"""
SDKSession: Wraps ClaudeSDKClient with async message queue for injection.

Each SDKSession manages a single Claude agent session for one contact.
Messages are sent via query() immediately and received by a background
receiver task using receive_messages(). This allows mid-turn steering:
new messages are injected while Claude is processing, and Claude sees
them as UserMessages between tool calls.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import time
import uuid
from datetime import datetime
from uuid import uuid4
from pathlib import Path
from typing import Any, NamedTuple, Optional

from typing import TYPE_CHECKING


class QueueItem(NamedTuple):
    """Item in the session message queue. message_id is None for sentinels."""
    message_id: str | None
    text: str

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    UserMessage,
    PermissionResultAllow,
    PermissionResultDeny,
    HookMatcher,
)

# Patch SDK message parser to handle unknown message types gracefully.
# The bundled parser raises MessageParseError for new types like rate_limit_event,
# which kills the receive iterator and crashes the session.
try:
    import claude_agent_sdk._internal.message_parser as _mp
    import claude_agent_sdk._internal.client as _client

    _original_parse = _mp.parse_message

    def _tolerant_parse(data):
        try:
            return _original_parse(data)
        except Exception:
            return SystemMessage(subtype=data.get("type", "unknown"), data=data)

    _client.parse_message = _tolerant_parse  # type: ignore[assignment]
except (ImportError, AttributeError):
    pass  # SDK mocked in tests

if TYPE_CHECKING:
    from claude_agent_sdk.types import (
        SyncHookJSONOutput,
        HookContext,
        PreToolUseHookInput,
        PostToolUseHookInput,
        PostToolUseFailureHookInput,
        UserPromptSubmitHookInput,
        StopHookInput,
        SubagentStopHookInput,
        PreCompactHookInput,
        NotificationHookInput,
    )
    # Union of all hook input types
    HookInputType = (
        PreToolUseHookInput | PostToolUseHookInput | PostToolUseFailureHookInput |
        UserPromptSubmitHookInput | StopHookInput | SubagentStopHookInput |
        PreCompactHookInput | NotificationHookInput
    )

from assistant.common import SKILLS_DIR, UV
from assistant import perf
from assistant.bus_helpers import produce_event, produce_session_event, compaction_triggered_payload

# Script path fragments that indicate a message send
_SEND_SCRIPT_PATTERNS = (
    "/scripts/send-sms",
    "/scripts/send-signal",
    "/scripts/send-signal-group",
    "/scripts/reply",
    "/scripts/reply-sven",
)

def _is_send_command(cmd: str) -> bool:
    """Check if a Bash command is a message send.

    Matches the executable (first token) against known send script paths.
    Strips outer quotes to extract the command path.
    """
    # Extract first token (the executable), stripping quotes
    stripped = cmd.strip().strip('"').strip("'")
    first_token = stripped.split()[0] if stripped else ""
    return any(first_token.endswith(pattern) for pattern in _SEND_SCRIPT_PATTERNS)

log = logging.getLogger(__name__)

# Per-session log directory
SESSION_LOG_DIR = Path.home() / "dispatch/logs/sessions"
SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _get_session_logger(session_name: str) -> logging.Logger:
    """Create a per-session logger with rotating file handler."""
    from logging.handlers import RotatingFileHandler

    logger = logging.getLogger(f"session.{session_name}")
    # Close existing handlers to prevent FD leaks on session restarts
    for h in logger.handlers[:]:
        try:
            h.close()
        except Exception:
            pass
        logger.removeHandler(h)
    if True:
        handler = RotatingFileHandler(
            SESSION_LOG_DIR / f"{session_name}.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


class SDKSession:
    """Manages a single Claude Agent SDK session using ClaudeSDKClient.

    Uses concurrent send/receive architecture: a background receiver task
    runs receive_messages() continuously while the sender dispatches
    query() calls immediately from the queue. This enables mid-turn
    steering — new messages reach Claude between tool calls without
    waiting for the current turn to finish.
    """

    def __init__(
        self,
        chat_id: str,
        contact_name: str,
        tier: str,
        cwd: str,
        session_type: str = "individual",
        source: str = "imessage",
        model: str = "opus",
        producer=None,
        resume_id: Optional[str] = None,
    ):
        self.chat_id = chat_id
        self.contact_name = contact_name
        self.tier = tier
        self.cwd = cwd
        self.session_type = session_type
        self.source = source
        self.model = model
        self._producer = producer
        self.resume_id = resume_id

        self._client: Optional[ClaudeSDKClient] = None
        self._message_queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._pending_queries = 0  # Tracks in-flight queries; reset to 0 on ResultMessage
        self.running = False

        # Metrics
        self.session_id: Optional[str] = None
        self.turn_count = 0
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.last_inject_at: Optional[datetime] = None  # When last message was injected
        self.last_response_at: datetime = datetime.now()  # When last ResultMessage received
        self._error_count = 0
        self._consecutive_error_turns = 0

        # Heartbeat tracking
        self._last_heartbeat_at: float = time.time()

        # Deferred system prompt injection (set by sdk_backend, consumed by _inject_system_prompt_if_needed)
        self._needs_system_prompt: bool = False
        self._system_prompt_args: tuple | None = None
        self._system_prompt_type: str | None = None  # "individual" or "group"
        self._restart_role: str | None = None  # "initiator", "passive", or None (fresh)

        # Tool execution timing: maps tool_use_id -> (start_time, tool_input, tool_name)
        self._pending_tools: dict[str, tuple[float, dict, str]] = {}

        # Per-session logger
        from assistant.common import get_session_name
        session_name = get_session_name(chat_id, source)
        log_name = session_name.replace("/", "-")
        self._log = _get_session_logger(log_name)

    def get_transcript_file(self) -> Optional[Path]:
        """Return path to this session's active transcript JSONL."""
        from assistant.health import _find_transcript
        return _find_transcript(self.cwd, self.session_id)

    async def start(self, resume_session_id: Optional[str] = None):
        """Connect ClaudeSDKClient and start the message processing loop."""
        options = self._build_options(resume_session_id)
        self._client = ClaudeSDKClient(options=options)
        await self._client.connect()
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        self._log.info(f"SESSION_START | resume={resume_session_id} | tier={self.tier}")
        log.info(f"[{self.contact_name}] SDK session started (resume={resume_session_id})")

    async def _kill_subprocess(self):
        """Kill the Claude CLI subprocess to prevent zombies.

        Called from both stop() and _run_loop's finally block to ensure
        the subprocess is terminated when the session ends or crashes.
        """
        if not self._client:
            return

        try:
            transport = getattr(self._client, '_transport', None)
            if transport:
                process = getattr(transport, '_process', None)
                if process and process.returncode is None:
                    self._log.info("SUBPROCESS_KILL | Terminating Claude CLI subprocess")
                    process.terminate()
                    # Give it a moment to terminate gracefully
                    try:
                        await asyncio.wait_for(process.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        process.kill()  # Force kill if terminate didn't work
                        self._log.warning("SUBPROCESS_KILL | Had to force kill")
        except Exception as e:
            self._log.warning(f"SUBPROCESS_KILL_ERROR | {e}")
        finally:
            self._client = None

    async def stop(self):
        """Stop the session by cancelling its task and killing the subprocess.

        We explicitly kill the subprocess to prevent zombie sessions from
        continuing to run after restart. The SDK's disconnect() method can
        cause anyio cancel scope issues, so we terminate the subprocess directly.
        """
        self.running = False

        # First cancel the task to stop the receive loop
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        await self._kill_subprocess()

        self._log.info(f"SESSION_STOP | turns={self.turn_count}")
        log.info(f"[{self.contact_name}] SDK session stopped (turns={self.turn_count})")

    async def inject(self, text: str, *, replay_source_message_id: str | None = None):
        """Queue a message for delivery to the Claude session.

        Args:
            replay_source_message_id: If this inject is a replay of a previously
                lost message, the original message_id for lineage tracing.
        """
        # Sentinel passes through without WAL
        if text == "__SHUTDOWN__":
            await self._message_queue.put(QueueItem(None, "__SHUTDOWN__"))
            return

        # Write-ahead: persist to bus BEFORE memory queue
        # Bus failure is non-fatal — degrade to memory-only (pre-fix behavior)
        message_id = str(uuid4())
        if self._producer:
            try:
                payload = {
                    "message_id": message_id,
                    "chat_id": self.chat_id,
                    "text": text,
                    "source": self.source,
                }
                if replay_source_message_id:
                    payload["replay_source_message_id"] = replay_source_message_id
                produce_event(self._producer, "messages", "message.queued",
                    payload, key=self.chat_id, source="sdk_session")
            except Exception as e:
                self._log.warning(f"WAL_WRITE_FAILED | msg_id={message_id[:8]} | {e}")

        queue_depth = self._message_queue.qsize()
        await self._message_queue.put(QueueItem(message_id, text))

        self.last_inject_at = datetime.now()
        perf.gauge("sdk_queue_depth", queue_depth + 1, component="session", contact=self.contact_name)
        self._log.info(f"QUEUED | msg_id={message_id[:8]} | len={len(text)} | queue_depth={queue_depth + 1}")

    @property
    def is_busy(self) -> bool:
        return self._pending_queries > 0

    def is_alive(self) -> bool:
        return self.running and self._task is not None and not self._task.done()

    def is_healthy(self) -> tuple[bool, str]:
        """Check session health. Returns (healthy, reason) tuple.

        The reason string describes why the session is unhealthy, or "ok" if healthy.
        """
        if not self.is_alive():
            return False, "dead"
        if self._error_count >= 3:
            return False, f"error_count={self._error_count}"
        # API errors (e.g. context too large, image size limits)
        if self._consecutive_error_turns >= 3:
            return False, f"consecutive_error_turns={self._consecutive_error_turns}"
        # Stale: messages pending but no activity for 10+ min
        if self._message_queue.qsize() > 0:
            idle = (datetime.now() - self.last_activity).total_seconds()
            if idle > 600:
                return False, f"stale_queue(qsize={self._message_queue.qsize()}, idle={idle:.0f}s)"
        # Stuck: message was injected but no ResultMessage received for 10+ min.
        # Catches silent SDK connection hangs where process is alive but not responding.
        # When this triggers, check_session_health() launches a Haiku investigation
        # to determine if the session is genuinely stuck or just running a long operation.
        if self.last_inject_at and self.last_inject_at > self.last_response_at:
            stuck_seconds = (datetime.now() - self.last_inject_at).total_seconds()
            if stuck_seconds > 600:
                return False, f"stuck(inject={stuck_seconds:.0f}s_ago)"
        return True, "ok"

    async def interrupt(self):
        """Interrupt a stuck session."""
        if self._client:
            await self._client.interrupt()
            self._log.info("INTERRUPTED")
            log.info(f"[{self.contact_name}] Session interrupted")

    async def _run_loop(self):
        """Main loop: start background receiver, then send queries from queue.

        The receiver runs receive_messages() continuously in the background.
        The sender dispatches query() calls immediately — Claude sees new
        messages as UserMessages between tool calls (mid-turn steering).
        Multiple queries during a single turn merge into one ResultMessage.
        """
        receiver = asyncio.create_task(self._receive_loop())
        try:
            while self.running:
                # Check if receiver crashed
                if receiver.done():
                    self._log.warning("RECEIVER_CRASHED | Exiting main loop")
                    break

                try:
                    message_id, msg = await asyncio.wait_for(
                        self._message_queue.get(), timeout=30
                    )
                except asyncio.TimeoutError:
                    # Emit heartbeat every 2 min to prove session loop is responsive
                    now = time.time()
                    if now - self._last_heartbeat_at >= 120:
                        produce_event(self._producer, "system", "session.heartbeat", {
                            "session_name": f"{self.source}/{self.chat_id}",
                            "chat_id": self.chat_id,
                            "contact_name": self.contact_name,
                            "queue_depth": self._message_queue.qsize(),
                            "pending_queries": self._pending_queries,
                            "turn_count": self.turn_count,
                            "is_busy": self.is_busy,
                            "idle_seconds": round((datetime.now() - self.last_activity).total_seconds()),
                        }, key=f"{self.source}/{self.chat_id}", source="sdk")
                        self._last_heartbeat_at = now
                    continue  # Check receiver health every 30s

                # Sentinel from _receive_loop signals shutdown
                if msg == "__SHUTDOWN__":
                    self._log.info("SHUTDOWN_SENTINEL | Receiver requested shutdown")
                    break

                wake_start = time.time()
                self.last_activity = datetime.now()
                self._log.info(f"IN | {msg}")
                self._pending_queries += 1

                try:
                    assert self._client is not None
                    await self._client.query(msg)
                    # Log wake latency - time from queue get to query completion
                    wake_ms = (time.time() - wake_start) * 1000
                    perf.timing("session_wake_latency_ms", wake_ms, component="session", contact=self.contact_name)
                    # Mark as delivered — message_id came WITH the message from queue
                    if message_id and self._producer:
                        try:
                            produce_event(self._producer, "messages", "message.delivered", {
                                "message_id": message_id,
                                "chat_id": self.chat_id,
                            }, key=self.chat_id, source="sdk_session")
                        except Exception:
                            pass  # Non-fatal: message was delivered to Claude regardless
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self._pending_queries = max(0, self._pending_queries - 1)
                    self._error_count += 1
                    self._log.error(f"ERROR #{self._error_count} | {e}")
                    log.error(f"[{self.contact_name}] Query error #{self._error_count}: {e}")
                    if self._error_count >= 3:
                        self._log.error("MAX_ERRORS | Session dead")
                        self.running = False
                        break
                    await asyncio.sleep(2 * self._error_count)

        except asyncio.CancelledError:
            self._log.info("LOOP_CANCELLED")
            raise
        finally:
            receiver.cancel()
            try:
                await receiver
            except asyncio.CancelledError:
                pass
            # Kill subprocess to prevent zombies when receiver crashes
            await self._kill_subprocess()

    async def _receive_loop(self):
        """Background receiver: continuously handle all messages from the SDK.

        Uses receive_messages() (infinite async iterator) instead of
        receive_response() (stops at ResultMessage). This allows the
        receiver to span multiple merged turns.
        """
        try:
            assert self._client is not None
            async for message in self._client.receive_messages():
                await self._handle_message(message)
                if isinstance(message, ResultMessage):
                    self._pending_queries = 0  # Reset: merged queries produce 1 ResultMessage
                    self._error_count = 0
                    # Note: _consecutive_error_turns is tracked in _handle_message
                    # Cleanup stale pending tools (edge case: tool call never got result)
                    self._cleanup_stale_pending_tools()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._error_count += 1
            self._log.error(f"RECEIVER_ERROR #{self._error_count} | {e}")
            log.error(f"[{self.contact_name}] Receiver error: {e}")
            # Populate sdk_events for error tracing
            if self._producer and hasattr(self._producer, 'send_sdk_event'):
                self._producer.send_sdk_event(
                    session_name=f"{self.source}/{self.chat_id}",
                    chat_id=self.chat_id,
                    event_type="error",
                    is_error=True,
                    payload=str(e)[:2048],
                )
            # Buffer overflow is fatal - the SDK connection is broken
            error_str = str(e).lower()
            is_fatal = "buffer" in error_str or "1048576" in error_str
            produce_session_event(self._producer, self.chat_id, "session.receive_error", {
                "error": str(e), "error_count": self._error_count,
                "is_fatal": is_fatal,
                "contact_name": self.contact_name,
            }, source="sdk")
            if is_fatal:
                self._log.error("RECEIVER_FATAL | Buffer overflow - marking session dead")
                self.running = False
                # Wake _run_loop immediately instead of waiting for 30s timeout
                try:
                    self._message_queue.put_nowait(QueueItem(None, "__SHUTDOWN__"))
                except Exception:
                    pass
            elif self._error_count >= 3:
                self._log.error("RECEIVER_DEAD | Stopping session")
                self.running = False
                try:
                    self._message_queue.put_nowait(QueueItem(None, "__SHUTDOWN__"))
                except Exception:
                    pass

    def _cleanup_stale_pending_tools(self) -> None:
        """Remove pending tools older than 30 minutes.

        Edge case handling: if a tool call never receives a result (e.g. session
        killed mid-call), the entry would stay forever. This cleans them up.
        """
        now = time.perf_counter()
        stale_ids = [
            tid for tid, (start_time, _, _) in self._pending_tools.items()
            if now - start_time > 1800  # 30 minutes
        ]
        for tid in stale_ids:
            self._log.warning(f"PENDING_TOOL_STALE | tool_use_id={tid}")
            self._pending_tools.pop(tid, None)

    def _build_options(self, resume_id: Optional[str] = None) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions based on contact tier."""
        if self.tier in ("admin", "partner"):
            tools = [
                "Read", "Write", "Edit", "Bash", "Glob", "Grep",
                "WebSearch", "WebFetch", "Task", "NotebookEdit",
                "Skill", "AskUserQuestion",
            ]
            perm_mode = "bypassPermissions"
        elif self.tier == "family":
            tools = [
                "Read", "Write", "Edit", "Bash", "Glob", "Grep",
                "WebSearch", "WebFetch", "Task",
            ]
            perm_mode = "default"
        elif self.tier == "favorite":
            tools = ["Read", "WebSearch", "WebFetch", "Grep", "Glob", "Bash"]
            perm_mode = "default"
        else:
            # Group sessions, master, etc - full access
            tools = [
                "Read", "Write", "Edit", "Bash", "Glob", "Grep",
                "WebSearch", "WebFetch", "Task", "NotebookEdit",
                "Skill", "AskUserQuestion",
            ]
            perm_mode = "bypassPermissions"

        # Per-turn limit prevents unbounded costs (bug #15 fix)
        # Each inject gets up to max_turns before stopping.
        # Admin/partner get generous limits; restricted tiers get tighter limits.
        if self.tier in ("admin", "partner"):
            turn_limit = 200
        elif self.tier == "family":
            turn_limit = 50
        elif self.tier == "favorite":
            turn_limit = 30
        else:
            turn_limit = 30

        opts = ClaudeAgentOptions(
            cli_path=Path.home() / ".local" / "bin" / "claude",  # Use system CLI (not bundled) for OAuth compat
            cwd=self.cwd,
            allowed_tools=tools,
            permission_mode=perm_mode,
            setting_sources=["project"],  # Load CLAUDE.md + skills from cwd
            model=self.model,
            fallback_model="sonnet",  # Only triggers on 529 (server overloaded), not normal usage
            max_turns=turn_limit,
            max_buffer_size=10 * 1024 * 1024,  # 10MB - prevents crash on large Task outputs
            hooks={
                "PreToolUse": [HookMatcher(matcher="Read", hooks=[self._resize_image_hook])],  # type: ignore[list-item]
                "Stop": [HookMatcher(hooks=[self._stop_hook])],  # type: ignore[list-item]
                "PreCompact": [HookMatcher(hooks=[self._pre_compact_hook])],  # type: ignore[list-item]
                # PostCompact is handled by settings.json command hook (bin/post-compact-hook)
                # because the Python SDK doesn't have a PostCompact hook type yet.
            }
        )

        # Permission callback for tier-based security enforcement.
        # NOTE: family tier is intentionally excluded from SDK-level blocking.
        # Family restrictions are enforced via system prompt only (family-rules.md),
        # which allows the admin to override via inject-prompt when needed.
        # Do NOT add SDK-level can_use_tool blocks for family — admin explicitly
        # rejected this ("revert", "do not do sdk level blocks"). Only favorites
        # use hard SDK-level blocks here.
        if self.tier == "favorite":
            opts.can_use_tool = self._permission_check

        # Session resume: use --resume <session_id> to continue a previous session.
        # CLI 2.1+ error: "--session-id can only be used with --continue or --resume
        # if --fork-session is also specified" — means --session-id + --resume needs
        # --fork-session. Fix: use --resume <id> alone (no --session-id).
        # For fresh sessions: --session-id <uuid> alone works fine (sets ID for new session).
        if resume_id or self.resume_id:
            session_id = resume_id or self.resume_id
            opts.extra_args = {"resume": session_id}
        else:
            fresh_session_id = str(uuid.uuid4())
            opts.extra_args = {"session-id": fresh_session_id}

        return opts

    async def _permission_check(self, tool_name: str, tool_input: dict[str, Any], context: Any) -> PermissionResultAllow | PermissionResultDeny:
        """Security callback: enforce tier-based tool restrictions.

        Runs before every tool call. Better than system prompt alone -
        survives compaction.
        """
        self._log.info(f"PERM_CHECK | tool={tool_name} tier={self.tier}")

        if self.tier == "favorite":
            # Block file modifications
            if tool_name in ("Write", "Edit", "NotebookEdit"):
                produce_session_event(self._producer, self.chat_id, "permission.denied", {
                    "tool_name": tool_name, "tier": self.tier,
                    "reason": f"{tool_name} blocked for favorites tier",
                    "contact_name": self.contact_name,
                }, source="sdk")
                return PermissionResultDeny(message=f"{tool_name} blocked for favorites tier")
            # Block dangerous bash
            if tool_name == "Bash":
                cmd = tool_input.get("command", "")
                if not cmd.startswith("osascript"):
                    produce_session_event(self._producer, self.chat_id, "permission.denied", {
                        "tool_name": tool_name, "tier": self.tier,
                        "reason": "Only osascript allowed for favorites tier",
                        "contact_name": self.contact_name,
                    }, source="sdk")
                    return PermissionResultDeny(message="Only osascript allowed for favorites tier")
                # Block osascript commands that attempt shell escape via "do shell script"
                if re.search(r'do\s+shell\s+script', cmd, re.IGNORECASE):
                    produce_session_event(self._producer, self.chat_id, "permission.denied", {
                        "tool_name": tool_name, "tier": self.tier,
                        "reason": "osascript 'do shell script' blocked for favorites tier",
                        "contact_name": self.contact_name,
                    }, source="sdk")
                    return PermissionResultDeny(message="osascript 'do shell script' blocked for favorites tier")
                # Block JXA (JavaScript for Automation) which can bypass AppleScript restrictions
                if re.search(r'-l\s+(JavaScript|js)\b', cmd, re.IGNORECASE):
                    produce_session_event(self._producer, self.chat_id, "permission.denied", {
                        "tool_name": tool_name, "tier": self.tier,
                        "reason": "osascript JXA (-l JavaScript) blocked for favorites tier",
                        "contact_name": self.contact_name,
                    }, source="sdk")
                    return PermissionResultDeny(message="osascript JXA (-l JavaScript) blocked for favorites tier")
            # Block sensitive file reads
            if tool_name == "Read":
                path = tool_input.get("file_path", "")
                if any(s in path for s in [".ssh", ".env", "credentials", "secrets"]):
                    produce_session_event(self._producer, self.chat_id, "permission.denied", {
                        "tool_name": tool_name, "tier": self.tier,
                        "reason": "Sensitive file blocked for favorites tier",
                        "contact_name": self.contact_name,
                    }, source="sdk")
                    return PermissionResultDeny(message="Sensitive file blocked for favorites tier")

        return PermissionResultAllow()

    async def _resize_image_hook(self, input_data: "HookInputType", tool_use_id: str | None, context: "HookContext") -> "SyncHookJSONOutput":
        """PreToolUse hook for Read: block oversized images to prevent API errors.

        The API rejects images >2000px in multi-image conversations.
        If an image is too large, deny the read and tell Claude to resize first.
        """
        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
        MAX_DIM = 2000  # API limit for multi-image (>20 images) requests

        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if not file_path:
            return {}

        ext = Path(file_path).suffix.lower()
        if ext not in IMAGE_EXTS:
            return {}

        if not Path(file_path).exists():
            return {}

        try:
            result = subprocess.run(
                ["sips", "-g", "pixelWidth", "-g", "pixelHeight", file_path],
                capture_output=True, text=True, timeout=5,
            )
            width = height = 0
            for line in result.stdout.splitlines():
                if "pixelWidth" in line:
                    width = int(line.split(":")[-1].strip())
                elif "pixelHeight" in line:
                    height = int(line.split(":")[-1].strip())

            if width <= MAX_DIM and height <= MAX_DIM:
                return {}

            self._log.info(f"IMAGE_TOO_LARGE | {file_path} | {width}x{height}")
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Image is {width}x{height}px. The API rejects images >2000px when there are many images in the conversation. "
                        f"Resize first: sips --resampleHeightWidthMax {MAX_DIM} \"{file_path}\" then read again."
                    ),
                },
            }
        except Exception as e:
            self._log.warning(f"IMAGE_CHECK_ERROR | {file_path} | {e}")
            return {}

    async def _pre_compact_hook(self, input_data: "HookInputType", tool_use_id: str | None, context: "HookContext") -> "SyncHookJSONOutput":
        """PreCompact hook: notify and let Claude Code compact natively.

        Fires when the CLI's context window is about to be compacted.
        We send an SMS notification and log the event, then return empty
        to let the native compaction proceed. The Notification hook will
        handle post-compaction logging.
        """
        from assistant.common import get_session_name
        session_name = get_session_name(self.chat_id, self.source)
        self._log.info(f"PRECOMPACT | triggered | session={session_name} turns={self.turn_count}")
        log.info(f"[{self.contact_name}] PreCompact hook fired (turns={self.turn_count})")
        produce_event(self._producer, "system", "compaction.triggered",
            compaction_triggered_payload(session_name, self.chat_id, self.contact_name, self.turn_count),
            source="compaction")

        # Log to compactions.log for visibility
        compaction_log = Path.home() / "dispatch/logs/compactions.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(compaction_log, "a") as f:
            f.write(f"{timestamp} | HOOK | PreCompact fired for {session_name}\n")

        # Send compaction notice to the chat (fire-and-forget but reap the process)
        try:
            from assistant import config
            from assistant.backends import get_backend
            assistant_name = config.get("assistant.name", "Assistant")
            backend = get_backend(self.source)
            if self.session_type == "group":
                send_tpl = backend.send_group_cmd
            else:
                send_tpl = backend.send_cmd
            # Template is like '~/.claude/skills/.../send-sms "{chat_id}"'
            # Extract the script path (before the first space) and expand ~
            script_path = str(Path(send_tpl.split()[0]).expanduser())
            proc = subprocess.Popen(
                [script_path, self.chat_id, f"[{assistant_name.upper()}] Compacting conversation\u2026"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Reap in a background thread to prevent zombie processes
            import threading
            threading.Thread(target=proc.wait, daemon=True, name="reap-compact-sms").start()
        except Exception as e:
            self._log.error(f"PRECOMPACT | send notice failed: {e}")

        # Let native compaction proceed (no more summarize-and-restart)
        return {}

    # PostCompact is handled by settings.json command hook (bin/post-compact-hook).
    # The old _notification_hook workaround has been removed since the CLI now
    # supports PostCompact as a native hook event in settings.json.

    async def _stop_hook(self, input_data: "HookInputType", tool_use_id: str | None, context: "HookContext") -> "SyncHookJSONOutput":
        """Stop hook: remind Claude to send updates via send-sms if needed.

        Only fires if the session is processing an incoming message (not idle turns).
        Checks if send-sms was already called to avoid duplicate sends.
        """
        # Check if we recently sent a message by looking at recent tool use
        from assistant.backends import get_backend
        backend = get_backend(self.source)
        # Extract CLI name from send_cmd template (e.g. "send-sms" from '~/.claude/skills/sms-assistant/scripts/send-sms "{chat_id}"')
        send_marker = backend.send_cmd.split("/")[-1].split('"')[0].strip()
        response = getattr(context, 'response', None) or {}
        messages = response.get('messages', []) if isinstance(response, dict) else []
        already_sent = any(
            send_marker in str(msg.get('content', ''))
            for msg in messages
            if msg.get('type') == 'tool_use'
        )
        if already_sent:
            return {}
        return {
            "systemMessage": (
                f"Reminder: If you haven't sent the user an update via {send_marker} yet, "
                "do so now to keep them informed of your progress or completion."
            )
        }

    async def _handle_message(self, message):
        """Handle messages from client.receive_response().

        NOTE: We do NOT auto-send text output as SMS. Claude calls send-sms
        explicitly via Bash tool when it wants to message the user.
        Auto-sending caused massive SMS spam (every intermediate TextBlock
        became a separate message).
        """
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    self._log.info(f"OUT | {block.text}")
                elif isinstance(block, ToolUseBlock):
                    self._log.info(f"TOOL_USE | {block.name}")
                    # Track tool start time for performance logging
                    self._pending_tools[block.id] = (
                        time.perf_counter(),
                        block.input if isinstance(block.input, dict) else {},
                        block.name,
                    )
                    # Populate sdk_events for tool-level tracing
                    if self._producer and hasattr(self._producer, 'send_sdk_event'):
                        self._producer.send_sdk_event(
                            session_name=f"{self.source}/{self.chat_id}",
                            chat_id=self.chat_id,
                            event_type="tool_use",
                            tool_name=block.name,
                            tool_use_id=block.id,
                        )

        elif isinstance(message, UserMessage):
            # UserMessage contains tool results - track completion timing
            for block in (message.content if isinstance(message.content, list) else []):
                if isinstance(block, ToolResultBlock):
                    tool_use_id = block.tool_use_id
                    if tool_use_id in self._pending_tools:
                        start_time, tool_input, tool_name = self._pending_tools.pop(tool_use_id)
                        duration_ms = (time.perf_counter() - start_time) * 1000
                        session_name = f"{self.source}/{self.chat_id}"
                        perf.log_tool_execution(
                            session=session_name,
                            tool=tool_name,
                            tool_input=tool_input,
                            duration_ms=duration_ms,
                            is_error=block.is_error or False,
                            session_type=self.session_type,
                        )
                        # Populate sdk_events for tool-level tracing
                        if self._producer and hasattr(self._producer, 'send_sdk_event'):
                            self._producer.send_sdk_event(
                                session_name=session_name,
                                chat_id=self.chat_id,
                                event_type="tool_result",
                                tool_name=tool_name,
                                tool_use_id=tool_use_id,
                                duration_ms=duration_ms,
                                is_error=block.is_error or False,
                            )
                        # Detect outbound message sends for e2e latency measurement
                        if tool_name == "Bash" and tool_input and not (block.is_error or False):
                            cmd = tool_input.get("command", "")
                            if _is_send_command(cmd):
                                if self._producer:
                                    produce_event(self._producer, "messages", "message.sent", {
                                        "chat_id": self.chat_id,
                                        "command": cmd,
                                        "tool_use_id": tool_use_id,
                                        "duration_ms": duration_ms,
                                    }, key=f"{self.source}:{self.chat_id}", source="sdk_session")
                    else:
                        self._log.warning(f"TOOL_RESULT_ORPHAN | tool_use_id={tool_use_id}")

        elif isinstance(message, ResultMessage):
            self.turn_count += message.num_turns or 0
            if message.session_id:
                self.session_id = message.session_id
            self.last_activity = datetime.now()
            self.last_response_at = datetime.now()  # Track for stuck detection
            if message.is_error:
                self._consecutive_error_turns += 1
            else:
                self._consecutive_error_turns = 0
            self._log.info(
                f"TURN | #{self.turn_count} | "
                f"duration={message.duration_ms}ms | error={message.is_error} | "
                f"sid={message.session_id}"
            )
            session_name = f"{self.source}/{self.chat_id}"
            produce_event(self._producer, "system", "sdk.turn_complete", {
                "session_name": session_name,
                "chat_id": self.chat_id,
                "contact_name": self.contact_name,
                "tier": self.tier,
                "duration_ms": message.duration_ms,
                "num_turns": message.num_turns,
                "is_error": message.is_error,
                "total_turns": self.turn_count,
            }, key=session_name, source="sdk")
            # Populate sdk_events table for tool-level observability
            if self._producer and hasattr(self._producer, 'send_sdk_event'):
                self._producer.send_sdk_event(
                    session_name=session_name,
                    chat_id=self.chat_id,
                    event_type="result",
                    duration_ms=message.duration_ms,
                    is_error=message.is_error or False,
                    num_turns=message.num_turns,
                )

        elif isinstance(message, SystemMessage):
            # Capture session_id from init message
            if hasattr(message, 'data') and isinstance(message.data, dict):
                sid = message.data.get('session_id')
                if sid and not self.session_id:
                    self.session_id = sid
            self._log.info(f"SYSTEM | {getattr(message, 'subtype', 'unknown')}")
