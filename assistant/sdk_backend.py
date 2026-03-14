"""
SDKBackend: Manages all Claude Agent SDK sessions.

Replaces the tmux-based SessionManager with ClaudeSDKClient-based sessions.
All session operations go through this backend.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from assistant.common import (
    HOME,
    SKILLS_DIR,
    TRANSCRIPTS_DIR,
    UV,
    MASTER_SESSION,
    MASTER_TRANSCRIPT_DIR,
    ensure_transcript_dir,
    get_session_name,
    get_group_session_name_from_participants,
    normalize_chat_id,
    wrap_sms,
    wrap_admin,
    wrap_group_message,
    format_message_body,
    get_reply_chain,
)
from assistant.health import get_transcript_entries_since, check_fatal_regex, check_deep_haiku
from assistant.sdk_session import SDKSession
from assistant import perf
from assistant.bus_helpers import (
    produce_event, produce_session_event,
    session_injected_payload, health_check_payload,
    vision_payload,
)

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Fire-and-forget task tracking
# ──────────────────────────────────────────────────────────────

_background_tasks: set[asyncio.Task] = set()


def _fire_and_forget(coro, *, name: str | None = None) -> asyncio.Task:
    """Create a task with automatic cleanup and exception logging.

    Prevents exceptions from being silently lost in fire-and-forget patterns.
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)

    def _task_done(t: asyncio.Task):
        _background_tasks.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            log.error(f"Background task {t.get_name()!r} failed: {exc}")

    task.add_done_callback(_task_done)
    return task


# ──────────────────────────────────────────────────────────────
# Gemini Vision Analysis (async image understanding)
# ──────────────────────────────────────────────────────────────

# Image extensions that Gemini can analyze
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}

GEMINI_CLI = Path.home() / ".claude" / "skills" / "gemini" / "scripts" / "gemini"


async def analyze_image_with_gemini(image_path: str, message_context: str | None = None) -> Optional[str]:
    """Analyze an image using Gemini Vision.

    Runs in background, returns description or None on failure.
    Uses gemini-3-pro-image-preview for best visual understanding.

    Args:
        image_path: Path to the image file
        message_context: Optional text that was sent with the image (provides context)
    """
    path = Path(image_path)
    if not path.exists():
        log.warning(f"Gemini vision: image not found: {image_path}")
        return None

    # Check if it's an image
    suffix = path.suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        log.debug(f"Gemini vision: not an image: {image_path}")
        return None

    # Convert HEIC to JPEG if needed (Gemini doesn't support HEIC directly)
    actual_path = image_path
    heic_temp_path: Path | None = None
    if suffix in {".heic", ".heif"}:
        try:
            import tempfile
            jpeg_path = Path(tempfile.gettempdir()) / f"{path.stem}_converted.jpg"
            proc = await asyncio.create_subprocess_exec(
                "sips", "-s", "format", "jpeg", str(path), "--out", str(jpeg_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            if jpeg_path.exists():
                actual_path = str(jpeg_path)
                heic_temp_path = jpeg_path
                log.debug(f"Gemini vision: converted HEIC to JPEG: {jpeg_path}")
            else:
                log.warning(f"Gemini vision: HEIC conversion failed for {image_path}")
                return None
        except Exception as e:
            log.warning(f"Gemini vision: HEIC conversion error: {e}")
            return None

    # Build context-aware prompt
    if message_context and message_context.strip() and message_context != "(no text)":
        # Check if it looks like multi-line conversation context vs single message
        if "\n" in message_context:
            prompt = f"""Recent conversation context:
{message_context}

Now an image was shared. Briefly describe what you see in this image, considering the conversation context above. Be concise but capture key details. 2-3 sentences max."""
        else:
            prompt = f"""The sender shared this image with the message: "{message_context}"

Briefly describe what you see in this image, keeping the sender's context in mind. Be concise but capture key details. 2-3 sentences max."""
    else:
        prompt = "Briefly describe what you see in this image. Be concise but capture key details - who/what is shown, the setting, and any notable elements. 2-3 sentences max."

    # Call Gemini CLI
    try:
        import time
        gemini_start = time.perf_counter()
        proc = await asyncio.create_subprocess_exec(
            str(GEMINI_CLI),
            "-m", "gemini-3-pro-image-preview",
            "-i", actual_path,
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
        gemini_ms = (time.perf_counter() - gemini_start) * 1000
        perf.timing("gemini_vision_ms", gemini_ms, component="daemon")

        if proc.returncode == 0 and stdout:
            description = stdout.decode().strip()
            log.info(f"Gemini vision: analyzed {path.name} ({len(description)} chars)")
            return description
        else:
            log.warning(f"Gemini vision failed: {stderr.decode()[:200]}")
            perf.error("gemini_vision_failed", component="daemon")
            return None
    except asyncio.TimeoutError:
        log.warning(f"Gemini vision: timeout for {image_path}")
        return None
    except Exception as e:
        log.warning(f"Gemini vision error: {e}")
        return None
    finally:
        # Clean up HEIC temp file to prevent /tmp accumulation
        if heic_temp_path and heic_temp_path.exists():
            try:
                heic_temp_path.unlink()
            except Exception:
                pass

# Lifecycle logger (matches current format)
lifecycle_log = logging.getLogger("lifecycle")


class SessionRegistry:
    """Persistent registry mapping chat_id to session metadata.

    Unified registry - replaces both the old SessionRegistry in manager.py
    and the _load_registry/_save_registry in cli.py.
    """

    def __init__(self, registry_file: Path):
        self._file = registry_file
        self._registry: Dict[str, Dict[str, Any]] = {}
        self._dirty = False
        self._last_save_time = 0.0
        self._save_interval = 1.0  # Debounce: at most one save per second for frequent updates
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                self._registry = json.loads(self._file.read_text())
                log.info(f"Loaded {len(self._registry)} sessions from registry")
            except Exception as e:
                log.error(f"Failed to load session registry: {e}")
                self._registry = {}

    def _save(self):
        import fcntl
        self._file.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write with file locking (bug #12 fix: CLI and daemon race)
        tmp_path = self._file.with_suffix('.tmp')
        with open(tmp_path, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(json.dumps(self._registry, indent=2, default=str))
        tmp_path.rename(self._file)  # Atomic rename

    def register(self, chat_id: str, session_name: str, **metadata) -> Dict[str, Any]:
        if not chat_id:
            raise ValueError("chat_id cannot be empty")
        existing = self._registry.get(chat_id, {})
        session_data = {
            "chat_id": chat_id,
            "session_name": session_name,
            "created_at": existing.get("created_at", datetime.now().isoformat()),
            "updated_at": datetime.now().isoformat(),
            **metadata,
        }
        self._registry[chat_id] = session_data
        self._save_debounced()
        return session_data

    def get(self, chat_id: str) -> Optional[Dict[str, Any]]:
        return self._registry.get(chat_id)

    def get_by_session_name(self, session_name: str) -> Optional[Dict[str, Any]]:
        for data in self._registry.values():
            if data.get("session_name") == session_name:
                return data
        return None

    def all(self) -> Dict[str, Dict[str, Any]]:
        return self._registry.copy()

    def remove(self, chat_id: str):
        if chat_id in self._registry:
            del self._registry[chat_id]
            self._save()

    def update_session_id(self, chat_id: str, session_id: str):
        """Update the SDK session_id for resume support."""
        if chat_id in self._registry:
            self._registry[chat_id]["session_id"] = session_id
            self._registry[chat_id]["updated_at"] = datetime.now().isoformat()
            self._save()

    def _save_debounced(self):
        """Save only if enough time has elapsed since last save. Otherwise mark dirty."""
        import time as _time
        now = _time.monotonic()
        if now - self._last_save_time >= self._save_interval:
            self._save()
            self._last_save_time = now
            self._dirty = False
        else:
            self._dirty = True

    def flush(self):
        """Force save if there are pending dirty writes."""
        if self._dirty:
            self._save()
            self._dirty = False

    def update_last_message_time(self, chat_id: str):
        """Update last_message_time for idle tracking. Uses debounced save."""
        if chat_id in self._registry:
            self._registry[chat_id]["last_message_time"] = datetime.now().isoformat()
            self._registry[chat_id]["updated_at"] = datetime.now().isoformat()
            self._save_debounced()

    def mark_was_active(self, chat_id: str):
        """Mark a session as active before shutdown, so it gets recreated on startup."""
        if chat_id in self._registry:
            self._registry[chat_id]["was_active"] = True
            self._registry[chat_id]["updated_at"] = datetime.now().isoformat()
            self._save()

    def clear_was_active(self, chat_id: str):
        """Clear the was_active flag after successful recreation."""
        if chat_id in self._registry:
            self._registry[chat_id].pop("was_active", None)
            self._save()


class SDKBackend:
    """Agent SDK-based session management using ClaudeSDKClient.

    Replaces the tmux-based SessionManager entirely.
    """

    def __init__(
        self,
        registry: SessionRegistry,
        contacts_manager=None,
        producer=None,
    ):
        self.registry = registry
        self.contacts = contacts_manager
        self._producer = producer
        self.sessions: Dict[str, SDKSession] = {}  # chat_id -> SDKSession
        self._lock = asyncio.Lock()

        # Two-tier healing state
        self._last_fast_check: Dict[str, datetime] = {}  # chat_id -> last scan timestamp
        self._recently_healed: Dict[str, datetime] = {}  # chat_id -> heal timestamp
        self._last_auth_error_notification: Optional[datetime] = None  # debounce auth error SMS

    def _read_restart_initiator(self) -> str | None:
        """Read the restart initiator chat_id from the graceful restart marker.

        Returns the chat_id of the session that triggered the restart, or None
        if this was a crash/external restart or the marker doesn't exist.
        """
        import json
        marker = Path("/tmp/dispatch-graceful-restart")
        if not marker.exists():
            return None
        try:
            data = json.loads(marker.read_text())
            return data.get("initiator_chat_id")
        except (json.JSONDecodeError, ValueError):
            return None

    async def recreate_sessions_with_pending_summaries(self) -> int:
        """Recreate sessions that were active during previous daemon shutdown.

        Called at startup to preserve context across daemon restarts.
        Recreates sessions that either:
        1. Have a .pending-summary.md file (summary was generated before shutdown)
        2. Were marked as was_active in registry (catches cases where shutdown
           was too fast for summary generation, e.g. SIGTERM during self-restart)

        Returns the number of sessions recreated.
        """
        recreated = 0

        # Determine which session (if any) initiated this restart
        restart_initiator = self._read_restart_initiator()

        # Iterate through registry to find sessions to recreate
        for chat_id, entry in self.registry.all().items():
            session_name = entry.get("session_name")
            if not session_name:
                continue

            # Check if there's a pending summary OR the session was marked active
            transcript_dir = TRANSCRIPTS_DIR / session_name
            pending_file = transcript_dir / ".pending-summary.md"
            has_pending = pending_file.exists()
            was_active = entry.get("was_active", False)

            if not has_pending and not was_active:
                continue

            # Get session metadata from registry
            contact_name = entry.get("contact_name", "Unknown")
            tier = entry.get("tier", "favorite")
            session_type = entry.get("type", "individual")

            # Parse source from session_name (format: imessage/chat_id or signal/chat_id)
            source = "imessage"
            if "/" in session_name:
                source = session_name.split("/")[0]

            # Determine restart role: "initiator" if this session triggered the restart,
            # "passive" if restarted by something else
            if restart_initiator is not None and chat_id == restart_initiator:
                restart_role = "initiator"
            else:
                restart_role = "passive"

            reason = "pending_summary" if has_pending else "was_active"
            log.info(f"STARTUP | Recreating session ({reason}): {session_name}"
                     f" [restart_role={restart_role}]")
            lifecycle_log.info(f"STARTUP | RECREATE_{reason.upper()} | {session_name}")

            try:
                if session_type == "group":
                    display_name = entry.get("display_name", chat_id)
                    await self.create_group_session(
                        chat_id=chat_id,
                        display_name=display_name,
                        source=source,
                        restart_role=restart_role,
                    )
                else:
                    await self.create_session(
                        contact_name=contact_name,
                        chat_id=chat_id,
                        tier=tier,
                        source=source,
                        session_type=session_type,
                        restart_role=restart_role,
                    )
                recreated += 1
            except Exception as e:
                log.error(f"STARTUP | Failed to recreate {session_name}: {e}")

            # Clear the was_active flag after successful recreation
            self.registry.clear_was_active(chat_id)

        if recreated:
            log.info(f"STARTUP | Recreated {recreated} sessions")
            lifecycle_log.info(f"STARTUP | RECREATE_COMPLETE | count={recreated}")
            # Flush any debounced registry writes from batch session creation
            self.registry.flush()

        return recreated

    # ──────────────────────────────────────────────────────────────
    # Individual sessions
    # ──────────────────────────────────────────────────────────────

    async def create_session(
        self,
        contact_name: str,
        chat_id: str,
        tier: str,
        source: str = "imessage",
        session_type: str = "individual",
        restart_role: str | None = None,
    ) -> SDKSession:
        """Create a new SDK session for an individual contact."""
        async with self._lock:
            if chat_id in self.sessions and self.sessions[chat_id].is_alive():
                return self.sessions[chat_id]

            # Kill zombie session: if session exists but is not alive, its subprocess
            # may still be running (buffer overflow crash leaves orphan PIDs).
            # Must kill it before creating a new session to prevent duplicates.
            if chat_id in self.sessions:
                old_session = self.sessions.pop(chat_id)
                lifecycle_log.info(
                    f"ZOMBIE_CLEANUP | {chat_id} | Killing orphan subprocess before recreate"
                )
                await old_session._kill_subprocess()

            session_name = get_session_name(chat_id, source=source)
            transcript_dir = ensure_transcript_dir(session_name)

            # For non-default backends, create session-specific CLAUDE.md override
            self._create_backend_claude_md(transcript_dir, source)

            lifecycle_log.info(
                f"CREATE | {session_name} | START | contact={contact_name} "
                f"tier={tier} chat_id={chat_id} source={source}"
            )

            # Resolve model: check registry for explicit override, else default to opus
            existing_entry = self.registry.get(chat_id)
            model = existing_entry.get("model", "opus") if existing_entry else "opus"

            session = SDKSession(
                chat_id=chat_id,
                contact_name=contact_name,
                tier=tier,
                cwd=str(transcript_dir),
                session_type=session_type,
                source=source,
                model=model,
                producer=self._producer,
            )
            await session.start(resume_session_id=None)
            self.sessions[chat_id] = session

            # Defer system prompt to outside the lock
            session._needs_system_prompt = True
            session._system_prompt_args = (session_name, contact_name, tier, chat_id, source)
            session._restart_role = restart_role

            # Register in persistent registry (preserve model if already set)
            self.registry.register(
                chat_id=chat_id,
                session_name=session_name,
                transcript_dir=str(transcript_dir),
                type=session_type,
                contact_name=contact_name,
                tier=tier,
                source=source,
                model=model,
            )

            lifecycle_log.info(
                f"CREATE | {session_name} | SUCCESS | contact={contact_name} "
                f"tier={tier}"
            )
            produce_session_event(self._producer, chat_id, "session.created", {
                "contact_name": contact_name, "tier": tier,
                "session_type": session_type, "source": source,
            }, source="daemon")

        # Inject system prompt outside lock (includes slow subprocess for memory)
        await self._inject_system_prompt_if_needed(session)
        return session

    async def _create_session_unlocked(
        self,
        contact_name: str,
        chat_id: str,
        tier: str,
        source: str = "imessage",
        session_type: str = "individual",
    ) -> SDKSession:
        """Create a session without acquiring the lock (caller must hold it).

        This avoids deadlock when inject_message needs to create + inject atomically.
        """
        if chat_id in self.sessions and self.sessions[chat_id].is_alive():
            return self.sessions[chat_id]

        # Kill zombie session: if session exists but is not alive, its subprocess
        # may still be running (buffer overflow crash leaves orphan PIDs).
        # Must kill it before creating a new session to prevent duplicates.
        if chat_id in self.sessions:
            old_session = self.sessions.pop(chat_id)
            lifecycle_log.info(
                f"ZOMBIE_CLEANUP | {chat_id} | Killing orphan subprocess before recreate"
            )
            await old_session._kill_subprocess()

        session_name = get_session_name(chat_id, source=source)
        transcript_dir = ensure_transcript_dir(session_name)

        self._create_backend_claude_md(transcript_dir, source)

        lifecycle_log.info(
            f"CREATE | {session_name} | START | contact={contact_name} "
            f"tier={tier} chat_id={chat_id} source={source}"
        )

        # Resolve model: check registry for explicit override, else default to opus
        existing_entry = self.registry.get(chat_id)
        model = existing_entry.get("model", "opus") if existing_entry else "opus"

        session = SDKSession(
            chat_id=chat_id,
            contact_name=contact_name,
            tier=tier,
            cwd=str(transcript_dir),
            session_type=session_type,
            source=source,
            model=model,
            producer=self._producer,
        )
        import time
        spawn_start = time.perf_counter()
        await session.start(resume_session_id=None)
        spawn_ms = (time.perf_counter() - spawn_start) * 1000
        perf.timing("session_spawn_ms", spawn_ms, component="daemon", tier=tier, source=source)
        self.sessions[chat_id] = session

        # System prompt injection deferred to _inject_system_prompt_if_needed()
        # so it can run outside the lock (includes slow subprocess calls)
        session._needs_system_prompt = True
        session._system_prompt_args = (session_name, contact_name, tier, chat_id, source)

        self.registry.register(
            chat_id=chat_id,
            session_name=session_name,
            transcript_dir=str(transcript_dir),
            type=session_type,
            contact_name=contact_name,
            tier=tier,
            source=source,
            model=model,
        )

        lifecycle_log.info(
            f"CREATE | {session_name} | SUCCESS | contact={contact_name} tier={tier}"
        )
        produce_session_event(self._producer, chat_id, "session.created", {
            "contact_name": contact_name, "tier": tier,
            "session_type": session_type, "source": source,
            "spawn_ms": round(spawn_ms, 1),
        }, source="daemon")
        # Yield control to event loop so other tasks can run during concurrent creations
        await asyncio.sleep(0)
        return session

    async def _inject_system_prompt_if_needed(self, session: SDKSession):
        """Inject the system prompt if the session was just created.

        Called OUTSIDE the lock so the slow subprocess call (_get_memory_summary)
        doesn't block other session operations.
        """
        if not getattr(session, '_needs_system_prompt', False):
            return
        session._needs_system_prompt = False
        args = getattr(session, '_system_prompt_args', None)
        if not args:
            return
        restart_role = getattr(session, '_restart_role', None)
        prompt_type = getattr(session, '_system_prompt_type', 'individual')
        if prompt_type == 'group':
            system_prompt = await self._build_group_system_prompt(*args, restart_role=restart_role)
        else:
            system_prompt = await self._build_individual_system_prompt(*args, restart_role=restart_role)
        await session.inject(system_prompt)

    async def inject_message(
        self,
        contact_name: str,
        chat_id: str,
        text: str,
        tier: str,
        attachments: list | None = None,
        audio_transcription: str | None = None,
        thread_originator_guid: str | None = None,
        source: str = "imessage",
        message_timestamp: datetime | None = None,
    ) -> bool:
        """Inject a message into an existing session.
        Creates session on-demand if missing (lazy creation).
        """
        import time
        inject_start = time.perf_counter()
        if not chat_id:
            raise ValueError(f"chat_id cannot be empty for contact {contact_name}")

        # Format message body
        msg_body = format_message_body(text, attachments, audio_transcription)

        # Prefix chat_id for registry storage (e.g. signal:+1234567890)
        # But don't add prefix if chat_id already has it
        from assistant.backends import get_backend
        backend = get_backend(source)
        if backend.registry_prefix and not chat_id.startswith(backend.registry_prefix):
            registry_chat_id = f"{backend.registry_prefix}{chat_id}"
        else:
            registry_chat_id = chat_id
        normalized = normalize_chat_id(registry_chat_id)

        # Only hold the lock for session creation check + creation.
        # Once we have the session, inject outside the lock (session has its own queue).
        needs_restart = False
        async with self._lock:
            existing = self.sessions.get(normalized)
            if not existing or not existing.is_alive():
                await self._create_session_unlocked(contact_name, normalized, tier, source)
            elif existing.tier != tier:
                # Tier mismatch! Session was created with different tier.
                # Must restart to apply correct permissions (e.g., favorite -> admin).
                log.info(f"Tier mismatch for {chat_id}: session has {existing.tier}, inject wants {tier}. Restarting...")
                needs_restart = True

        # Do restart outside the lock to avoid manual release/re-acquire
        if needs_restart:
            await self.restart_session(normalized, tier_override=tier)

        async with self._lock:
            session = self.sessions.get(normalized)

        if not session:
            log.error(f"Failed to create session for {chat_id}")
            return False

        # Inject system prompt outside lock (includes slow subprocess for memory)
        await self._inject_system_prompt_if_needed(session)

        wrapped = wrap_sms(
            msg_body, contact_name, tier, chat_id,
            reply_to_guid=thread_originator_guid, source=source,
        )
        await session.inject(wrapped)
        self.registry.update_last_message_time(normalized)
        inject_ms = (time.perf_counter() - inject_start) * 1000
        perf.timing("inject_ms", inject_ms, component="daemon", source=source, tier=tier)
        log.info(f"Injected message for {chat_id} via {source}")
        produce_session_event(self._producer, normalized, "session.injected",
            session_injected_payload(normalized, "message", contact_name, tier),
            source="inject")

        # Spawn async Gemini vision analysis for image attachments
        if attachments:
            for att in attachments:
                image_path = att.get("path")
                if image_path and Path(image_path).suffix.lower() in IMAGE_EXTENSIONS:
                    _fire_and_forget(
                        self._inject_gemini_vision(
                            session, normalized, image_path,
                            source=source,
                            chat_id=chat_id,
                            message_timestamp=message_timestamp,
                        ),
                        name=f"gemini-vision-{normalized}",
                    )

        return True

    async def inject_reaction(
        self,
        chat_id: str,
        reaction_text: str,
        emoji: str,
        sender_name: str,
        sender_tier: str,
        source: str = "imessage",
    ) -> bool:
        """Inject a reaction notification into an existing session.

        Unlike inject_message, this does NOT create a session on-demand.
        Reactions only matter if there's an active conversation.
        """
        from assistant.backends import get_backend
        backend = get_backend(source)
        if backend.registry_prefix and not chat_id.startswith(backend.registry_prefix):
            registry_chat_id = f"{backend.registry_prefix}{chat_id}"
        else:
            registry_chat_id = chat_id
        normalized = normalize_chat_id(registry_chat_id)

        # Only inject if session exists and is alive
        async with self._lock:
            session = self.sessions.get(normalized)
            if not session or not session.is_alive():
                log.debug(f"No active session for {chat_id}, skipping reaction")
                return False

        # Inject the reaction notification (no wrapping needed, it's already formatted)
        await session.inject(reaction_text)
        log.info(f"Injected reaction {emoji} from {sender_name} for {chat_id}")
        produce_session_event(self._producer, normalized, "session.injected",
            session_injected_payload(normalized, "reaction", sender_name, sender_tier,
                                     emoji=emoji),
            source="inject")
        return True

    async def _inject_gemini_vision(
        self,
        session: SDKSession,
        normalized_chat_id: str,
        image_path: str,
        source: str = "imessage",
        chat_id: str | None = None,
        message_timestamp: datetime | None = None,
    ) -> None:
        """Background task: analyze image with Gemini and inject result into session.

        Silently skips if Gemini fails (no error injection).

        Args:
            session: The SDK session to inject into
            normalized_chat_id: Internal chat ID (normalized, for logging)
            image_path: Path to the image file
            source: Backend source ("imessage", "signal", "sven-app")
            chat_id: Original chat identifier for context lookup
            message_timestamp: Timestamp of the image message for context anchoring
        """
        try:
            # Get conversation context using the appropriate reader
            conversation_context = ""

            from assistant.backends import get_backend
            backend_config = get_backend(source)

            if backend_config.supports_image_context and chat_id and message_timestamp:
                from assistant.readers import get_reader, format_context_for_gemini
                reader = get_reader(source)

                if reader:
                    # Run blocking DB query in executor to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    messages = await loop.run_in_executor(
                        None,
                        reader.get_context_around,
                        chat_id,
                        message_timestamp,
                        10,  # before
                        1,   # after
                    )
                    conversation_context = format_context_for_gemini(messages)

            description = await analyze_image_with_gemini(image_path, conversation_context)
            if description:
                # Check session is still alive before injecting
                if session.is_alive():
                    vision_msg = f"""
---VISION ANALYSIS---
Gemini analyzed the attached image:
{description}
---END VISION---
"""
                    await session.inject(vision_msg)
                    log.info(f"Injected Gemini vision for {normalized_chat_id}")
                    produce_event(self._producer, "system", "vision.analyzed",
                        vision_payload(normalized_chat_id, image_path, True,
                                       description_length=len(description)),
                        source="vision")
                else:
                    log.debug(f"Session {normalized_chat_id} died before vision inject")
            else:
                produce_event(self._producer, "system", "vision.failed",
                    vision_payload(normalized_chat_id, image_path, False),
                    source="vision")
        except Exception as e:
            log.warning(f"Gemini vision task failed for {normalized_chat_id}: {e}")
            produce_event(self._producer, "system", "vision.failed",
                vision_payload(normalized_chat_id, image_path, False, error=str(e)),
                source="vision")

    # ──────────────────────────────────────────────────────────────
    # Group sessions
    # ──────────────────────────────────────────────────────────────

    def get_group_session_name(self, chat_id: str, display_name: str | None = None,
                                source: str = "imessage") -> str:
        existing = self.registry.get(chat_id)
        if existing:
            return existing["session_name"]
        return get_session_name(chat_id, source)

    async def create_group_session(
        self,
        chat_id: str,
        display_name: str | None = None,
        participants: list | None = None,
        source: str = "imessage",
        restart_role: str | None = None,
    ) -> SDKSession:
        """Create a group session."""
        async with self._lock:
            if chat_id in self.sessions and self.sessions[chat_id].is_alive():
                return self.sessions[chat_id]

            # Kill zombie session: if session exists but is not alive, its subprocess
            # may still be running (buffer overflow crash leaves orphan PIDs).
            if chat_id in self.sessions:
                old_session = self.sessions.pop(chat_id)
                lifecycle_log.info(
                    f"ZOMBIE_CLEANUP | {chat_id} | Killing orphan subprocess before recreate"
                )
                await old_session._kill_subprocess()

            # Resolve participants from chat.db if not provided (only works for iMessage)
            if not participants:
                from assistant.backends import get_backend
                backend = get_backend(source)
                if not backend.registry_prefix:  # iMessage has no prefix
                    participants = await self._resolve_group_participants(chat_id)

            session_name = self.get_group_session_name(chat_id, display_name, source)
            transcript_dir = ensure_transcript_dir(session_name)

            session = SDKSession(
                chat_id=chat_id,
                contact_name=display_name or chat_id,
                tier="admin",  # Groups get full access
                cwd=str(transcript_dir),
                session_type="group",
                source=source,
                producer=self._producer,
            )
            await session.start(resume_session_id=None)
            self.sessions[chat_id] = session

            # Always inject system prompt - session reads old messages for context
            startup = await self._build_group_system_prompt(
                session_name, chat_id, display_name, participants, source,
                restart_role=restart_role,
            )
            await session.inject(startup)

            self.registry.register(
                chat_id=chat_id,
                session_name=session_name,
                transcript_dir=str(transcript_dir),
                type="group",
                display_name=display_name or chat_id,
                participants=participants or [],
                source=source,
            )

            lifecycle_log.info(f"CREATE | {session_name} | SUCCESS | type=group chat_id={chat_id}")
            produce_session_event(self._producer, chat_id, "session.created", {
                "contact_name": display_name or chat_id, "tier": "admin",
                "session_type": "group", "source": source,
            }, source="daemon")
            return session

    async def _create_group_session_unlocked(
        self,
        chat_id: str,
        display_name: str | None = None,
        participants: list | None = None,
        source: str = "imessage",
    ) -> SDKSession:
        """Create a group session without acquiring the lock (caller must hold it)."""
        if chat_id in self.sessions and self.sessions[chat_id].is_alive():
            return self.sessions[chat_id]

        # Kill zombie session: if session exists but is not alive, its subprocess
        # may still be running (buffer overflow crash leaves orphan PIDs).
        if chat_id in self.sessions:
            old_session = self.sessions.pop(chat_id)
            lifecycle_log.info(
                f"ZOMBIE_CLEANUP | {chat_id} | Killing orphan subprocess before recreate"
            )
            await old_session._kill_subprocess()

        # Resolve participants from chat.db if not provided (only works for iMessage)
        if not participants:
            from assistant.backends import get_backend
            backend = get_backend(source)
            if not backend.registry_prefix:  # iMessage has no prefix
                participants = await self._resolve_group_participants(chat_id)

        session_name = self.get_group_session_name(chat_id, display_name, source)
        transcript_dir = ensure_transcript_dir(session_name)

        session = SDKSession(
            chat_id=chat_id,
            contact_name=display_name or chat_id,
            tier="admin",
            cwd=str(transcript_dir),
            session_type="group",
            source=source,
            producer=self._producer,
        )
        await session.start(resume_session_id=None)
        self.sessions[chat_id] = session

        # Defer system prompt to outside the lock
        session._needs_system_prompt = True
        session._system_prompt_args = (session_name, chat_id, display_name, participants, source)
        session._system_prompt_type = "group"

        self.registry.register(
            chat_id=chat_id,
            session_name=session_name,
            transcript_dir=str(transcript_dir),
            type="group",
            display_name=display_name or chat_id,
            participants=participants or [],
            source=source,
        )

        lifecycle_log.info(f"CREATE | {session_name} | SUCCESS | type=group chat_id={chat_id}")
        produce_session_event(self._producer, chat_id, "session.created", {
            "contact_name": display_name or chat_id, "tier": "admin",
            "session_type": "group", "source": source,
        }, source="daemon")
        return session

    async def inject_group_message(
        self,
        chat_id: str,
        display_name: str | None,
        sender_name: str,
        sender_tier: str,
        text: str,
        attachments: list | None = None,
        audio_transcription: str | None = None,
        thread_originator_guid: str | None = None,
        source: str = "imessage",
        message_timestamp: datetime | None = None,
    ) -> bool:
        """Inject a message into a group session."""
        if not chat_id:
            raise ValueError("chat_id cannot be empty for group message")

        msg_body = format_message_body(text, attachments, audio_transcription)

        # Lock only for session creation check; inject happens outside lock
        async with self._lock:
            if chat_id not in self.sessions or not self.sessions[chat_id].is_alive():
                await self._create_group_session_unlocked(chat_id, display_name, source=source)
            session = self.sessions.get(chat_id)

        if not session:
            log.error(f"Failed to create group session for {chat_id}")
            return False

        # Inject system prompt outside lock if session was just created
        await self._inject_system_prompt_if_needed(session)

        wrapped = wrap_group_message(
            chat_id, display_name, sender_name, sender_tier,
            msg_body, reply_to_guid=thread_originator_guid, source=source,
        )
        await session.inject(wrapped)
        self.registry.update_last_message_time(chat_id)
        produce_session_event(self._producer, chat_id, "session.injected",
            session_injected_payload(chat_id, "group", sender_name, sender_tier,
                                     group_name=display_name),
            source="inject")

        # Spawn async Gemini vision analysis for image attachments
        if attachments:
            for att in attachments:
                image_path = att.get("path")
                if image_path and Path(image_path).suffix.lower() in IMAGE_EXTENSIONS:
                    _fire_and_forget(
                        self._inject_gemini_vision(
                            session, chat_id, image_path,
                            source=source,
                            chat_id=chat_id,
                            message_timestamp=message_timestamp,
                        ),
                        name=f"gemini-vision-{chat_id}",
                    )

        return True

    # ──────────────────────────────────────────────────────────────
    # Background sessions (for nightly consolidation)
    # ──────────────────────────────────────────────────────────────

    async def create_background_session(
        self,
        contact_name: str,
        chat_id: str,
        tier: str,
        source: str = "imessage",
    ) -> SDKSession:
        """Create a background session for nightly consolidation."""
        bg_id = f"{chat_id}-bg"

        async with self._lock:
            if bg_id in self.sessions and self.sessions[bg_id].is_alive():
                return self.sessions[bg_id]

            # Kill zombie session: if session exists but is not alive, its subprocess
            # may still be running (buffer overflow crash leaves orphan PIDs).
            if bg_id in self.sessions:
                old_session = self.sessions.pop(bg_id)
                lifecycle_log.info(
                    f"ZOMBIE_CLEANUP | {bg_id} | Killing orphan subprocess before recreate"
                )
                await old_session._kill_subprocess()

            fg_session_name = get_session_name(chat_id, source=source)
            transcript_dir = ensure_transcript_dir(fg_session_name)

            session = SDKSession(
                chat_id=bg_id,
                contact_name=f"{contact_name} (BG)",
                tier=tier,
                cwd=str(transcript_dir),
                session_type="background",
                source=source,
                producer=self._producer,
            )
            await session.start()
            self.sessions[bg_id] = session

            # Inject BG-specific prompt - general purpose task runner
            bg_prompt = f"""BACKGROUND SESSION - Task runner for {contact_name}.

This is a headless background session for executing scheduled tasks (reminders, cron jobs, etc).
You receive task injections and execute them, then wait for the next task.

When you receive a task:
1. Execute it immediately
2. If it involves sending a message, use the appropriate send command
3. Report completion if requested
4. Wait for next task

Session: {fg_session_name}
Ready for tasks...
"""
            await session.inject(bg_prompt)

            lifecycle_log.info(f"CREATE | {fg_session_name}-bg | SUCCESS | background for {contact_name}")
            produce_session_event(self._producer, bg_id, "session.created", {
                "contact_name": f"{contact_name} (BG)", "tier": tier,
                "session_type": "background", "source": source,
            }, source="daemon")
            return session

    async def inject_consolidation(self, contact_name: str, chat_id: str):
        """Trigger nightly consolidation for a contact."""
        bg_id = f"{chat_id}-bg"
        reg = self.registry.get(chat_id)
        source = reg.get("source", "imessage") if reg else "imessage"
        fg_session_name = get_session_name(chat_id, source=source)

        # Ensure BG session exists
        if bg_id not in self.sessions or not self.sessions[bg_id].is_alive():
            reg = self.registry.get(chat_id)
            tier = reg.get("tier", "admin") if reg else "admin"
            await self.create_background_session(contact_name, chat_id, tier)

        session = self.sessions.get(bg_id)
        if not session:
            log.error(f"Could not create BG session for {contact_name}")
            return

        consolidation_prompt = f"""
--- NIGHTLY MEMORY CONSOLIDATION ---
Time to consolidate memories for {contact_name}.

Run this command to see today's conversations:
uv run ~/.claude/skills/memory/scripts/memory.py consolidate "{fg_session_name}"

Review the output and save any important memories:
- Facts about the person
- Preferences they expressed
- Projects you worked on together
- Lessons learned

For each memory, run:
uv run ~/.claude/skills/memory/scripts/memory.py save "{fg_session_name}" "memory text" --type TYPE

Types: fact, preference, project, lesson, relationship, context

When done, sync the CLAUDE.md:
uv run ~/.claude/skills/memory/scripts/memory.py sync "{fg_session_name}"

Start now!
"""
        await session.inject(consolidation_prompt)
        log.info(f"Injected consolidation prompt for {contact_name}")

    # ──────────────────────────────────────────────────────────────
    # Master session
    # ──────────────────────────────────────────────────────────────

    async def create_master_session(self) -> SDKSession:
        """Create the always-alive master admin session."""
        async with self._lock:
            if MASTER_SESSION in self.sessions and self.sessions[MASTER_SESSION].is_alive():
                return self.sessions[MASTER_SESSION]

            # Kill zombie session: if session exists but is not alive, its subprocess
            # may still be running (buffer overflow crash leaves orphan PIDs).
            if MASTER_SESSION in self.sessions:
                old_session = self.sessions.pop(MASTER_SESSION)
                lifecycle_log.info(
                    f"ZOMBIE_CLEANUP | {MASTER_SESSION} | Killing orphan subprocess before recreate"
                )
                await old_session._kill_subprocess()

            MASTER_TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
            claude_symlink = MASTER_TRANSCRIPT_DIR / ".claude"
            if not claude_symlink.exists():
                claude_symlink.symlink_to(HOME / ".claude")

            session = SDKSession(
                chat_id=MASTER_SESSION,
                contact_name="Master",
                tier="admin",
                cwd=str(MASTER_TRANSCRIPT_DIR),
                session_type="master",
                producer=self._producer,
            )
            await session.start()
            self.sessions[MASTER_SESSION] = session

            lifecycle_log.info("MASTER | CREATED")
            produce_session_event(self._producer, MASTER_SESSION, "session.created", {
                "contact_name": "Master", "tier": "admin",
                "session_type": "master", "source": "imessage",
            }, source="daemon")
            return session

    async def inject_master_prompt(self, admin_phone: str, prompt: str) -> bool:
        """Inject a prompt into the master session."""
        if MASTER_SESSION not in self.sessions or not self.sessions[MASTER_SESSION].is_alive():
            await self.create_master_session()

        session = self.sessions.get(MASTER_SESSION)
        if not session:
            return False

        wrapped = f"""---MASTER COMMAND---
From: Admin ({admin_phone})
{prompt}
---END MASTER COMMAND---

Respond via: ~/.claude/skills/sms-assistant/scripts/send-sms "{admin_phone}" "[MASTER] your response"
"""
        await session.inject(wrapped)
        lifecycle_log.info(f"MASTER | INJECTED | prompt_len={len(prompt)}")
        produce_session_event(self._producer, MASTER_SESSION, "session.injected", {
            "chat_id": MASTER_SESSION, "injection_type": "master",
            "contact_name": "Master", "tier": "admin",
        }, source="inject")
        return True

    # ──────────────────────────────────────────────────────────────
    # Session lifecycle
    # ──────────────────────────────────────────────────────────────

    async def kill_session(self, chat_id: str) -> bool:
        """Kill a session (FG + BG)."""
        async with self._lock:
            session = self.sessions.pop(chat_id, None)
            bg_session = self.sessions.pop(f"{chat_id}-bg", None)

        if session:
            # Save session_id before stopping
            if session.session_id:
                self.registry.update_session_id(chat_id, session.session_id)
            uptime = (datetime.now() - session.created_at).total_seconds()
            produce_session_event(self._producer, chat_id, "session.killed", {
                "contact_name": session.contact_name, "tier": session.tier,
                "turn_count": session.turn_count, "uptime_seconds": round(uptime, 1),
                "error_count": session._error_count,
            }, source="daemon")
            await session.stop()
        if bg_session:
            await bg_session.stop()

        lifecycle_log.info(f"KILL | {chat_id} | fg={'yes' if session else 'no'} bg={'yes' if bg_session else 'no'}")
        return session is not None

    async def kill_all_sessions(self) -> int:
        """Kill all sessions."""
        async with self._lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()

        # Save session_ids before stopping
        for s in sessions:
            if s.session_id and s.chat_id:
                self.registry.update_session_id(s.chat_id, s.session_id)

        for s in sessions:
            try:
                await s.stop()
            except (Exception, asyncio.CancelledError) as e:
                log.error(f"Error stopping session {s.contact_name}: {e}")
            finally:
                task = asyncio.current_task()
                if task is not None:
                    while task.cancelling() > 0:
                        task.uncancel()

        lifecycle_log.info(f"KILL_ALL | count={len(sessions)}")
        return len(sessions)

    def _clear_sdk_session_index(self, session_name: str) -> None:
        """Clear the SDK's sessions-index.json to prevent auto-resume of poisoned sessions.

        The SDK auto-resumes from ~/.claude/projects/<sanitized-cwd>/sessions-index.json.
        When restarting a crashed/poisoned session, we need to clear this index so the SDK
        creates a fresh session instead of resuming the old one.
        """
        transcript_dir = ensure_transcript_dir(session_name)
        # SDK sanitizes cwd path: /Users/sven/transcripts/foo -> -Users-sven-transcripts-foo
        sanitized = str(transcript_dir).replace("/", "-")
        if sanitized.startswith("-"):
            sanitized = sanitized  # Already starts with dash from leading /

        sdk_project_dir = HOME / ".claude" / "projects" / sanitized
        index_file = sdk_project_dir / "sessions-index.json"

        if index_file.exists():
            try:
                index_file.unlink()
                lifecycle_log.info(f"CLEAR_INDEX | {session_name} | Deleted {index_file}")
            except Exception as e:
                log.warning(f"Failed to delete session index {index_file}: {e}")

    async def restart_session(self, chat_id: str, tier_override: str | None = None) -> Optional[SDKSession]:
        """Kill and recreate a session.

        Args:
            chat_id: The chat ID to restart
            tier_override: Optional tier to use instead of registry value
        """
        # Save session info before killing
        reg = self.registry.get(chat_id)

        await self.kill_session(chat_id)

        # Clear the SDK session index to prevent auto-resume of poisoned session
        if reg and reg.get("session_name"):
            self._clear_sdk_session_index(reg["session_name"])

        if reg:
            lifecycle_log.info(f"RESTART | {reg.get('session_name', chat_id)} | START")
            # Group chats use display_name; individuals use contact_name
            contact_name = reg.get("contact_name") or reg.get("display_name", "Unknown")
            # Use tier_override if provided, else fall back to registry or default
            tier = tier_override or reg.get("tier", "admin")
            source = reg.get("source", "imessage")
            produce_session_event(self._producer, chat_id, "session.restarted", {
                "contact_name": contact_name, "tier": tier,
                "reason": "restart_requested",
            }, source="daemon")
            session = await self.create_session(
                contact_name,
                chat_id,
                tier,
                source,
                reg.get("type", "individual"),
            )
            lifecycle_log.info(f"RESTART | {reg.get('session_name', chat_id)} | COMPLETE")
            return session
        return None

    async def check_session_health(self, chat_id: str) -> bool:
        """Check if a session is healthy. Auto-restarts if not."""
        session = self.sessions.get(chat_id)
        if not session:
            return False
        if not session.is_healthy():
            lifecycle_log.info(
                f"HEALTH_CHECK | {session.contact_name} | UNHEALTHY | "
                f"alive={session.is_alive()} errors={session._error_count}"
            )
            produce_session_event(self._producer, chat_id, "session.crashed", {
                "contact_name": session.contact_name,
                "error_count": session._error_count,
                "turn_count": session.turn_count,
            }, source="daemon")
            # Fire-and-forget: do NOT await restart_session at all.
            async def _isolated_restart(cid: str):
                try:
                    await self.restart_session(cid)
                except Exception as e:
                    log.error(f"Health check restart failed for {cid}: {e}")

            _fire_and_forget(_isolated_restart(chat_id), name=f"health-restart-{chat_id}")
            return False
        return True

    def _send_auth_error_notification(self):
        """Send SMS to admin when OAuth token has expired.

        Uses subprocess directly (not a Claude session) since sessions
        can't function without valid auth. Runs in fire-and-forget mode.
        """
        from assistant import config

        try:
            admin_phone = config.require("owner.phone")
            send_sms = HOME / ".claude/skills/sms-assistant/scripts/send-sms"
            message = "[AUTH] OAuth token expired - run /login to refresh"

            result = subprocess.run(
                [str(send_sms), admin_phone, message],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                lifecycle_log.info(f"AUTH_ERROR_NOTIFY | Sent SMS to admin: {message}")
                produce_event(self._producer, "messages", "message.sent", {
                    "chat_id": admin_phone, "text": message,
                    "is_group": False, "success": True, "context": "auth_error",
                }, key=admin_phone, source="daemon")
            else:
                log.warning(f"AUTH_ERROR_NOTIFY | SMS failed: {result.stderr}")
        except Exception as e:
            log.error(f"AUTH_ERROR_NOTIFY | Failed to send SMS: {e}")

    async def health_check_all(self) -> Dict[str, bool]:
        """Check all sessions. Auto-restarts unhealthy ones."""
        results = {}
        for chat_id in list(self.sessions.keys()):
            results[chat_id] = await self.check_session_health(chat_id)

        # Perf: track active session count
        alive_count = sum(1 for s in self.sessions.values() if s.is_alive())
        perf.gauge("active_sessions", alive_count, component="daemon")

        lifecycle_log.info(f"HEALTH_CHECK_ALL | COMPLETE | {sum(results.values())}/{len(results)} healthy")
        produce_event(self._producer, "system", "health.check_completed",
            health_check_payload(active_sessions=alive_count,
                                 healthy=sum(results.values()),
                                 total=len(results)),
            source="health")
        return results

    async def fast_health_check(self) -> List[str]:
        """Tier 1: Regex-based fatal error detection from transcripts.

        Reads recent transcript JSONL entries for each session and checks
        for known unrecoverable error patterns (400 API errors, image limits,
        context overflow, etc.). Returns list of chat_ids that were restarted.

        Also restarts dead sessions (e.g., buffer overflow crashes that set
        running=False but weren't auto-restarted).

        Runs every 60 seconds.
        """
        now = datetime.now()
        restarted = []

        # Clean stale entries from recently_healed (older than 5 min)
        cutoff = now.timestamp() - 300
        self._recently_healed = {
            cid: ts for cid, ts in self._recently_healed.items()
            if ts.timestamp() > cutoff
        }

        for chat_id, session in list(self.sessions.items()):
            if chat_id.endswith("-bg") or chat_id == MASTER_SESSION:
                continue
            if chat_id in self._recently_healed:
                continue

            # Restart dead sessions (buffer overflow, receiver crash, etc.)
            if not session.is_alive():
                session_name = get_session_name(session.chat_id, session.source)
                lifecycle_log.info(
                    f"FAST_HEAL | {session_name} | DEAD_SESSION | Restarting"
                )
                self._recently_healed[chat_id] = now

                async def _isolated_restart(cid: str):
                    try:
                        await self.restart_session(cid)
                    except Exception as e:
                        log.error(f"Fast heal restart failed for {cid}: {e}")

                _fire_and_forget(
                    _isolated_restart(chat_id),
                    name=f"fast-heal-dead-{chat_id}",
                )
                restarted.append(chat_id)
                continue

            # Only scan entries since last check for this session
            since = self._last_fast_check.get(chat_id, session.created_at)
            entries = get_transcript_entries_since(session.cwd, session.session_id, since)
            self._last_fast_check[chat_id] = now

            if not entries:
                continue

            fatal_label = check_fatal_regex(entries)
            if fatal_label:
                session_name = get_session_name(session.chat_id, session.source)
                lifecycle_log.info(
                    f"FAST_HEAL | {session_name} | {fatal_label} | Restarting"
                )

                # Send SMS notification for auth errors (OAuth token expired)
                # Debounce to max once per 5 minutes to avoid spam
                if fatal_label == "auth_error":
                    should_notify = True
                    if self._last_auth_error_notification:
                        elapsed = (now - self._last_auth_error_notification).total_seconds()
                        if elapsed < 300:  # 5 minutes
                            should_notify = False

                    if should_notify:
                        self._last_auth_error_notification = now
                        self._send_auth_error_notification()

                self._recently_healed[chat_id] = now

                async def _isolated_restart(cid: str):
                    try:
                        await self.restart_session(cid)
                    except Exception as e:
                        log.error(f"Fast heal restart failed for {cid}: {e}")

                _fire_and_forget(
                    _isolated_restart(chat_id),
                    name=f"fast-heal-{chat_id}",
                )
                restarted.append(chat_id)

        lifecycle_log.info(
            f"FAST_HEAL | SCAN | {len(self.sessions)} sessions checked | "
            f"{len(restarted)} fatal"
        )
        produce_event(self._producer, "system", "health.fast_check_completed", {
            "sessions_checked": len(self.sessions),
            "restarted": len(restarted),
        }, source="health")
        return restarted

    async def deep_health_check(self, skip_chat_ids: set | None = None) -> List[str]:
        """Tier 2: Haiku-based deep analysis of session health.

        Sends recent assistant messages to Haiku for classification of
        subtle/complex failure modes. Skips sessions already handled by
        fast_health_check or recently healed.

        Runs every 5 minutes alongside the existing health_check_all().
        """
        skip = skip_chat_ids or set()
        now = datetime.now()
        restarted = []

        # Look back 5 minutes for deep analysis
        from datetime import timedelta
        since = now - timedelta(minutes=5)

        for chat_id, session in list(self.sessions.items()):
            if chat_id.endswith("-bg") or chat_id == MASTER_SESSION:
                continue
            if not session.is_alive():
                continue
            if chat_id in skip or chat_id in self._recently_healed:
                continue

            entries = get_transcript_entries_since(session.cwd, session.session_id, since)
            if not entries:
                continue

            session_name = get_session_name(session.chat_id, session.source)
            diagnosis = await check_deep_haiku(entries, session_name)

            if diagnosis:
                lifecycle_log.info(
                    f"DEEP_HEAL | {session_name} | {diagnosis} | Restarting"
                )

                self._recently_healed[chat_id] = now

                async def _isolated_restart(cid: str):
                    try:
                        await self.restart_session(cid)
                    except Exception as e:
                        log.error(f"Deep heal restart failed for {cid}: {e}")

                _fire_and_forget(
                    _isolated_restart(chat_id),
                    name=f"deep-heal-{chat_id}",
                )
                restarted.append(chat_id)

        lifecycle_log.info(
            f"DEEP_HEAL | SCAN | {len(self.sessions) - len(skip)} sessions checked | "
            f"{len(restarted)} fatal"
        )
        produce_event(self._producer, "system", "health.deep_check_completed", {
            "sessions_checked": len(self.sessions) - len(skip),
            "restarted": len(restarted),
        }, source="health")
        return restarted

    async def check_idle_sessions(self, timeout_hours: float) -> List[str]:
        """Kill idle sessions exceeding timeout. Returns chat_ids killed."""
        now = datetime.now()
        killed = []
        # Snapshot under lock to avoid concurrent modification (bug #16 fix)
        async with self._lock:
            sessions_snapshot = list(self.sessions.items())
        for chat_id, session in sessions_snapshot:
            if chat_id.endswith("-bg") or chat_id == MASTER_SESSION:
                continue  # Don't idle-kill BG or master sessions
            idle_seconds = (now - session.last_activity).total_seconds()
            if idle_seconds > timeout_hours * 3600:
                idle_hours = idle_seconds / 3600
                log.info(f"Session {session.contact_name} idle for {idle_hours:.1f}h, killing...")
                lifecycle_log.info(
                    f"IDLE_TIMEOUT | {session.contact_name} | KILLING | "
                    f"idle_hours={idle_hours:.1f} threshold={timeout_hours}"
                )
                produce_session_event(self._producer, chat_id, "session.idle_killed", {
                    "contact_name": session.contact_name, "idle_hours": round(idle_hours, 1),
                }, source="health")
                # Fire-and-forget: do NOT await kill_session at all.
                # Awaiting (even via wait_for on a separate task) allows anyio
                # cancel scopes to leak CancelledError to this task.
                async def _isolated_kill(cid: str):
                    try:
                        await self.kill_session(cid)
                    except Exception as e:
                        log.error(f"Idle kill failed for {cid}: {e}")

                _fire_and_forget(_isolated_kill(chat_id), name=f"idle-kill-{chat_id}")
                killed.append(chat_id)
        return killed

    async def get_session_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Get info about a session."""
        session = self.sessions.get(chat_id)
        if not session:
            return None
        return {
            "chat_id": chat_id,
            "contact_name": session.contact_name,
            "tier": session.tier,
            "session_type": session.session_type,
            "source": session.source,
            "is_alive": session.is_alive(),
            "is_healthy": session.is_healthy(),
            "is_busy": session.is_busy,
            "turn_count": session.turn_count,
            "session_id": session.session_id,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "queue_size": session._message_queue.qsize(),
        }

    async def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get info about all active sessions."""
        infos = []
        for chat_id in self.sessions:
            info = await self.get_session_info(chat_id)
            if info:
                infos.append(info)
        return infos

    async def get_recent_output(self, chat_id: str, lines: int = 30) -> str:
        """Get recent output from per-session log file."""
        session = self.sessions.get(chat_id)
        if not session:
            return ""
        session_name = get_session_name(session.chat_id, session.source)
        log_name = session_name.replace("/", "-")
        from assistant.sdk_session import SESSION_LOG_DIR
        log_path = SESSION_LOG_DIR / f"{log_name}.log"
        if log_path.exists():
            # Read only the tail of the file efficiently
            import os
            with open(log_path, 'rb') as f:
                try:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    # Read last 64KB max (enough for ~30 lines)
                    chunk_size = min(size, 65536)
                    f.seek(size - chunk_size)
                    tail = f.read().decode('utf-8', errors='replace')
                    tail_lines = tail.splitlines()
                    return "\n".join(tail_lines[-lines:])
                except Exception:
                    return ""
        return ""

    async def _generate_shutdown_summaries(self, sessions: list) -> dict[str, bool]:
        """Generate summaries for all active sessions before shutdown.

        Runs summarize-session for each session concurrently with a timeout.
        Returns dict mapping session_name -> success.
        """
        SUMMARIZE_SCRIPT = HOME / "dispatch/bin/summarize-session"
        TIMEOUT_PER_SESSION = 60  # seconds

        if not sessions:
            return {}

        log.info(f"SHUTDOWN | Generating summaries for {len(sessions)} active sessions...")

        async def summarize_one(session: SDKSession) -> tuple[str, bool]:
            """Generate summary for one session."""
            session_name = get_session_name(session.chat_id, session.source)
            try:
                proc = await asyncio.create_subprocess_exec(
                    str(UV), "run", str(SUMMARIZE_SCRIPT), session_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=TIMEOUT_PER_SESSION
                    )
                    if proc.returncode == 0:
                        log.info(f"SHUTDOWN | Summary generated for {session_name}")
                        return (session_name, True)
                    else:
                        log.warning(f"SHUTDOWN | Summary failed for {session_name}: {stderr.decode()[:200]}")
                        return (session_name, False)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    log.warning(f"SHUTDOWN | Summary timeout for {session_name}")
                    return (session_name, False)
            except Exception as e:
                log.error(f"SHUTDOWN | Summary error for {session_name}: {e}")
                return (session_name, False)

        # Run all summaries concurrently
        results = await asyncio.gather(*[summarize_one(s) for s in sessions], return_exceptions=True)

        # Process results
        summary_results = {}
        for result in results:
            if isinstance(result, Exception):
                log.error(f"SHUTDOWN | Summary exception: {result}")
            elif isinstance(result, tuple):
                session_name, success = result
                summary_results[session_name] = success

        success_count = sum(1 for v in summary_results.values() if v)
        log.info(f"SHUTDOWN | Generated {success_count}/{len(sessions)} summaries")
        return summary_results

    async def shutdown(self):
        """Clean shutdown: generate summaries, save session_ids, disconnect all clients."""
        log.info("SHUTDOWN | Saving session_ids and disconnecting all clients...")
        async with self._lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()

        # Mark all active sessions in registry so they get recreated on startup
        # (even if summary generation fails or is killed before completing)
        for s in sessions:
            if s.chat_id:
                self.registry.mark_was_active(s.chat_id)

        # Generate summaries for active sessions before stopping them
        # This preserves context across daemon restarts
        if sessions:
            await self._generate_shutdown_summaries(sessions)

        # Save session_ids for future resume
        for s in sessions:
            if s.session_id and s.chat_id:
                self.registry.update_session_id(s.chat_id, s.session_id)

        # Disconnect all
        for s in sessions:
            try:
                await s.stop()
            except (Exception, asyncio.CancelledError) as e:
                log.error(f"Error stopping session {s.contact_name}: {e}")
            finally:
                # Clear ALL stacked cancellations from SDK anyio internals
                task = asyncio.current_task()
                if task is not None:
                    while task.cancelling() > 0:
                        task.uncancel()

        lifecycle_log.info(f"SHUTDOWN | COMPLETE | {len(sessions)} sessions stopped")

    # ──────────────────────────────────────────────────────────────
    # System prompt builders (identical to current tmux prompts)
    # ──────────────────────────────────────────────────────────────

    def _get_pending_summary(self, session_name: str) -> str | None:
        """Get and consume pending summary from compaction.

        Reads .pending-summary.md if it exists, validates it, deletes it, and returns content.
        Returns None if no pending summary or validation fails.
        """
        transcript_dir = ensure_transcript_dir(session_name)
        pending_file = transcript_dir / ".pending-summary.md"

        if not pending_file.exists():
            return None

        try:
            summary = pending_file.read_text()

            # Validate length
            if len(summary) < 100:
                log.warning(f"Pending summary too short ({len(summary)} chars), ignoring")
                pending_file.unlink()
                return None
            if len(summary) > 10000:
                log.warning(f"Pending summary too long ({len(summary)} chars), truncating")
                summary = summary[:10000] + "\n\n[truncated]"

            # Consume the file (delete after reading)
            pending_file.unlink()
            log.info(f"Injected pending summary for {session_name} ({len(summary)} chars)")
            return summary

        except Exception as e:
            log.error(f"Error reading pending summary: {e}")
            return None

    async def _build_individual_system_prompt(
        self,
        session_name: str,
        contact_name: str,
        tier: str,
        chat_id: str,
        source: str = "imessage",
        restart_role: str | None = None,
    ) -> str:
        """Build the startup prompt for an individual session.

        Auto-injects SOUL.md, contact notes, memory summary, and chat context for faster startup.
        """
        # Fetch all context in parallel (async, non-blocking)
        soul_content, contact_notes, memory_summary, chat_context = await asyncio.gather(
            self._get_soul_content(),
            self._get_contact_notes(contact_name),
            self._get_memory_summary(session_name),
            self._get_chat_context(session_name),
        )

        # Check for pending summary from compaction
        pending_summary = self._get_pending_summary(session_name)

        # Build sections with clear labels
        soul_section = f"\n## My Identity (from SOUL.md)\n\n{soul_content}\n" if soul_content else ""
        notes_section = f"\n## About {contact_name} (from Contacts.app)\n\n{contact_notes}\n" if contact_notes else ""
        memory_section = f"\n## About {contact_name} (from memories)\n\n{memory_summary}\n" if memory_summary else ""
        context_section = f"\n## Current Conversation Context\n\n{chat_context}\n" if chat_context else ""
        summary_section = f"\n## Previous Session Context\n\n{pending_summary}\n" if pending_summary else ""

        # Determine send command and history based on source
        from assistant.backends import get_backend
        backend = get_backend(source)
        bare_chat_id = chat_id.removeprefix(backend.registry_prefix) if backend.registry_prefix else chat_id
        send_cmd = backend.send_cmd.replace("{chat_id}", bare_chat_id)
        if backend.history_cmd:
            history_note = f'**FIRST**: Run this command to see recent conversation history:\n{backend.history_cmd.replace("{chat_id}", bare_chat_id).replace("{limit}", "20")}'
        else:
            history_note = f"({backend.label} session - no message history command available yet)"

        # Restart notification behavior depends on how this session was created
        # Only the session that initiated the restart sends a back-online message.
        # All other sessions stay silent — users shouldn't notice restarts.
        if restart_role == "initiator":
            # This session triggered the restart — let the user know we're back
            restart_instruction = (
                "IMPORTANT: You asked for a daemon restart and it completed successfully. "
                "Send a brief back-online message to let the user know you're back. "
                "Keep it short and casual (e.g. 'back online 👍'). "
                "Do this BEFORE resuming any work."
            )
        elif restart_role == "passive":
            # Restarted by something else — stay silent, user shouldn't notice
            restart_instruction = (
                "CRITICAL: Do NOT send any restart notification, 'back online' message, or any greeting. "
                "Users should NOT notice session restarts. Just silently resume — read history and act on it "
                "without announcing yourself.\n\n"
                "EXCEPTION: If the last IN message from the user explicitly asked for a restart/deploy "
                "(e.g. 'restart', 'deploy', 'yes restart'), send a brief back-online confirmation "
                "(e.g. 'back online 👍'). The user asked for this and is waiting to know it worked."
            )
        else:
            # Fresh session creation (not a restart) — no notification needed
            restart_instruction = (
                "CRITICAL: Do NOT send any restart notification, 'back online' message, or any greeting. "
                "Users should NOT notice session restarts. Just silently resume — read history and act on it "
                "without announcing yourself.\n\n"
                "EXCEPTION: If the last IN message from the user explicitly asked for a restart/deploy "
                "(e.g. 'restart', 'deploy', 'yes restart'), send a brief back-online confirmation "
                "(e.g. 'back online 👍'). The user asked for this and is waiting to know it worked."
            )

        return f"""SESSION START - INDIVIDUAL {backend.label} CHAT: {contact_name} ({tier} tier)
Chat ID: {chat_id}
{soul_section}{notes_section}{memory_section}{context_section}{summary_section}
{history_note}

After reading, act based on what you see:

1. **Task was in progress** (last OUT messages show active work):
   - Pick up EXACTLY where you left off
   - Do NOT announce restart or say "catching up"
   - If user asked "how's it going?" = you went offline during work, so continue silently

2. **Unanswered message** (last IN message has no response):
   - Respond to it naturally

3. **Conversation was idle** (no pending work or questions):
   - Wait silently for new messages

{restart_instruction}

**If you need more context** about what you were doing before restart:
uv run ~/.claude/skills/sms-assistant/scripts/read_transcript.py --session {session_name}

Quick reference:
- Send message using heredoc (no temp files - avoids race conditions between sessions):
  {send_cmd} "$(cat <<'ENDMSG'
  your message here
  ENDMSG
  )"
- NEVER escape exclamation marks. Write "Hello!" NOT "Hello\\!". The CLI handles escaping. \\! sends a literal backslash.
- Full guidelines: ~/.claude/skills/sms-assistant/SKILL.md
"""

    async def _build_group_system_prompt(
        self,
        session_name: str,
        chat_id: str,
        display_name: str | None = None,
        participants: list | None = None,
        source: str = "imessage",
        restart_role: str | None = None,
    ) -> str:
        """Build the startup prompt for a group session.

        Auto-injects SOUL.md, contact notes for all participants, and memory summaries.
        """
        participants_list = participants or []

        # Build participants list with tiers
        participant_lines = []
        for participant in participants_list:
            if self.contacts:
                contact_info = self.contacts.lookup_phone_by_name(participant)
                tier = contact_info.get("tier", "unknown") if contact_info else "unknown"
            else:
                tier = "unknown"
            participant_lines.append(f"- {participant} ({tier})")

        # Fetch ALL context in parallel: SOUL + chat context + notes for each + memory for each
        async_tasks = [self._get_soul_content(), self._get_chat_context(session_name)]
        async_tasks.extend(self._get_contact_notes(p) for p in participants_list)
        async_tasks.extend(self._get_memory_summary(p) for p in participants_list)

        results = await asyncio.gather(*async_tasks) if async_tasks else []

        # Unpack results: soul, chat_context, then N notes, then N memories
        soul_content = results[0] if results else ""
        chat_context = results[1] if len(results) > 1 else ""
        n_participants = len(participants_list)
        notes_results = results[2:2+n_participants] if n_participants else []
        memory_results = results[2+n_participants:] if n_participants else []

        # Build sections with clear labels
        soul_section = f"\n## My Identity (from SOUL.md)\n\n{soul_content}\n" if soul_content else ""

        # Combine notes and memories per participant
        participant_context_parts = []
        for i, participant in enumerate(participants_list):
            notes = notes_results[i] if i < len(notes_results) else ""
            mem = memory_results[i] if i < len(memory_results) else ""
            if notes or mem:
                part = f"## About {participant}\n"
                if notes:
                    part += f"\n**From Contacts.app:**\n{notes}\n"
                if mem:
                    part += f"\n**From memories:**\n{mem}\n"
                participant_context_parts.append(part)

        # Check for pending summary from compaction
        pending_summary = self._get_pending_summary(session_name)

        participants_section = "\n".join(participant_lines) if participant_lines else "- (unknown participants)"
        participant_context_section = "\n".join(participant_context_parts) if participant_context_parts else ""
        chat_context_section = f"\n## Current Conversation Context\n\n{chat_context}\n" if chat_context else ""
        summary_section = f"\n## Previous Session Context\n\n{pending_summary}\n" if pending_summary else ""

        shown_name = display_name or chat_id

        from assistant.backends import get_backend
        backend = get_backend(source)
        send_cmd = backend.send_group_cmd.replace("{chat_id}", chat_id)
        if backend.history_cmd:
            history_cmd = backend.history_cmd.replace("{chat_id}", chat_id).replace("{limit}", "20")
        else:
            history_cmd = f"uv run ~/.claude/skills/sms-assistant/scripts/read_transcript.py --session {session_name}"

        return f"""SESSION START - GROUP CHAT: {shown_name}
Chat ID: {chat_id}

Participants:
{participants_section}
{soul_section}
{participant_context_section}{chat_context_section}{summary_section}
**FIRST**: Check conversation history: {history_cmd}

After reading, act based on what you see - respond to unanswered messages, continue work in progress, or wait silently.

{"CRITICAL: Do NOT send any restart notification, 'back online' message, or any greeting. Users should NOT notice session restarts. Just silently resume — read history and act on it without announcing yourself."}

**To send a message to this group using heredoc (no temp files - avoids race conditions between sessions):**
{send_cmd} "$(cat <<'ENDMSG'
your message here
ENDMSG
)"

You MUST call the send command above via Bash to actually send messages. Text output alone does NOT reach users.

NEVER escape exclamation marks. Write "Hello!" NOT "Hello\\!". The CLI handles escaping. \\! sends a literal backslash.

Full guidelines: ~/.claude/skills/sms-assistant/SKILL.md
"""

    def _create_backend_claude_md(self, transcript_dir: Path, source: str):
        """Create backend-specific CLAUDE.md override for non-default backends.

        Only created for non-imessage backends to emphasize the correct send commands.
        """
        from assistant.backends import get_backend, BACKENDS
        backend = get_backend(source)

        # Default backend (imessage) doesn't need an override
        if source == "imessage":
            return

        claude_md_path = transcript_dir / "CLAUDE.md"

        # Only create if it doesn't exist
        if claude_md_path.exists():
            return

        # Build the default backend name for the "NEVER use" warning
        default_backend = BACKENDS["imessage"]
        default_send = default_backend.send_cmd.split("/")[-1].split('"')[0].strip()

        content = f"""# {backend.label} Session Override

**CRITICAL: This is a {backend.label} session. You MUST use {backend.label}-specific commands.**

## Sending Messages

**For individual {backend.label} messages:**
```bash
{backend.send_cmd}
```

**For {backend.label} group messages:**
```bash
{backend.send_group_cmd}
```

**NEVER use {default_send} in {backend.label} sessions** - it will send via {default_backend.label} instead of {backend.label}, causing duplicate responses and confusion.

All other system documentation applies normally (see ~/.claude/CLAUDE.md via symlink).
"""

        claude_md_path.write_text(content)
        log.info(f"Created {backend.label}-specific CLAUDE.md at {claude_md_path}")

    async def _resolve_group_participants(self, chat_id: str) -> list:
        """Resolve group participants from chat.db and contacts (async, non-blocking)."""
        def _sync_resolve():
            import sqlite3
            from assistant.common import MESSAGES_DB
            try:
                conn = sqlite3.connect(str(MESSAGES_DB), timeout=5)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT h.id
                    FROM handle h
                    JOIN chat_handle_join chj ON h.ROWID = chj.handle_id
                    JOIN chat c ON chj.chat_id = c.ROWID
                    WHERE c.chat_identifier = ?
                """, (chat_id,))
                phones = [row[0] for row in cursor.fetchall()]
                conn.close()
                return phones
            except Exception as e:
                log.warning(f"Failed to resolve group participants for {chat_id}: {e}")
                return []

        phones = await asyncio.get_event_loop().run_in_executor(None, _sync_resolve)

        names = []
        for phone in phones:
            if self.contacts:
                contact = self.contacts.lookup_identifier(phone)
                if contact:
                    names.append(contact["name"])
                else:
                    names.append(phone)
            else:
                names.append(phone)
        return names

    async def _get_memory_summary(self, contact_name: str) -> str:
        """Get memory summary for a contact from DuckDB (async, non-blocking)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                UV, "run", str(SKILLS_DIR / "memory/scripts/memory.py"), "summary", contact_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(SKILLS_DIR / "memory"),
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode().strip()
            if output and not output.startswith("SUMMARY|") and "No memories" not in output:
                return output
        except Exception as e:
            log.warning(f"Could not load memory summary for {contact_name}: {e}")
        return ""

    async def _get_soul_content(self) -> str:
        """Load SOUL.md content for session identity (async, non-blocking).

        Returns the full content of ~/.claude/SOUL.md which defines the assistant's
        identity, personality, and core values. Same for all sessions.
        """
        try:
            soul_path = HOME / ".claude" / "SOUL.md"
            if soul_path.exists():
                return await asyncio.get_event_loop().run_in_executor(
                    None, soul_path.read_text
                )
        except Exception as e:
            log.warning(f"Could not load SOUL.md: {e}")
        return ""

    async def _get_contact_notes(self, contact_name: str) -> str:
        """Get contact notes from Contacts.app via SQLite (async, non-blocking).

        Returns the notes field for a contact, which contains personal info,
        preferences, and context stored in macOS Contacts.app.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                str(SKILLS_DIR / "contacts/scripts/contacts"), "notes", contact_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode().strip()
            if output and "No notes" not in output and "not found" not in output.lower():
                return output
        except Exception as e:
            log.warning(f"Could not load contact notes for {contact_name}: {e}")
        return ""

    async def _get_chat_context(self, session_name: str) -> str:
        """Load CONTEXT.md for a chat session (async, non-blocking).

        Returns conversation context (ongoing projects, pending tasks, recent topics)
        that was extracted by the nightly consolidation job.
        """
        try:
            # session_name format: imessage/_15555550100 or imessage/ab3876ca...
            parts = session_name.split("/", 1)
            if len(parts) == 2:
                backend, chat_id = parts
                context_file = HOME / "transcripts" / backend / chat_id / "CONTEXT.md"
                if context_file.exists():
                    content = await asyncio.get_event_loop().run_in_executor(
                        None, context_file.read_text
                    )
                    # Skip empty or just-header files
                    if content and ("## Ongoing" in content or "## Pending" in content or "## Recent Topics" in content):
                        return content
        except Exception as e:
            log.warning(f"Could not load CONTEXT.md for {session_name}: {e}")
        return ""
