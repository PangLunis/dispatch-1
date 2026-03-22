"""
Message readers for Gemini vision context.

Each backend has a MessageReader that can retrieve conversation context
around a timestamp for image analysis. This enables Gemini to understand
the conversation context when analyzing images sent via any backend.

Architecture:
- MessageReader is a Protocol (structural subtyping)
- Each backend (iMessage, Signal, dispatch-app) has its own reader implementation
- Readers are created lazily via get_reader() to avoid import-time failures
- All readers use datetime as the universal timestamp type

Timestamp handling:
- iMessage: macOS absolute time (seconds since 2001-01-01) → datetime
- Signal: Unix milliseconds → datetime
- dispatch-app: SQLite DATETIME string → datetime
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Database paths
MESSAGES_DB = Path.home() / "Library" / "Messages" / "chat.db"
SIGNAL_DB = Path.home() / "Library/Application Support/signal-cli/messages.db"
DISPATCH_MESSAGES_DB = Path.home() / "dispatch" / "state" / "dispatch-messages.db"

# macOS absolute time epoch (2001-01-01 00:00:00 UTC)
MACOS_EPOCH = datetime(2001, 1, 1)
MACOS_EPOCH_UNIX = MACOS_EPOCH.timestamp()


@dataclass
class ContextMessage:
    """A message for Gemini vision context.

    Normalized representation across all backends.
    """
    text: str | None
    sender: str
    is_from_me: bool
    timestamp: datetime
    attachments: list[str] = field(default_factory=list)


@runtime_checkable
class MessageReader(Protocol):
    """Protocol for reading message context from any backend.

    Implementations must provide get_context_around() which retrieves
    messages around a given timestamp for use as Gemini vision context.
    """

    def get_context_around(
        self,
        chat_id: str,
        anchor_timestamp: datetime,
        before: int = 10,
        after: int = 1,
    ) -> list[ContextMessage]:
        """Get messages around a timestamp for vision context.

        Args:
            chat_id: Chat identifier (phone number, group ID, etc.)
            anchor_timestamp: The timestamp to anchor around
            before: Number of messages before the anchor
            after: Number of messages after the anchor

        Returns:
            List of ContextMessage in chronological order
        """
        ...


class IMessageReader:
    """Reads message context from iMessage chat.db.

    Uses macOS absolute time (seconds since 2001-01-01) for timestamps.
    The date column in chat.db stores nanoseconds since macOS epoch.
    """

    def __init__(self, db_path: Path = MESSAGES_DB):
        self.db_path = db_path

    def _macos_timestamp_to_datetime(self, macos_ns: int) -> datetime:
        """Convert macOS nanosecond timestamp to datetime."""
        # chat.db stores nanoseconds since 2001-01-01
        unix_seconds = MACOS_EPOCH_UNIX + (macos_ns / 1_000_000_000)
        return datetime.fromtimestamp(unix_seconds)

    def _datetime_to_macos_timestamp(self, dt: datetime) -> int:
        """Convert datetime to macOS nanosecond timestamp."""
        unix_seconds = dt.timestamp()
        macos_seconds = unix_seconds - MACOS_EPOCH_UNIX
        return int(macos_seconds * 1_000_000_000)

    def get_context_around(
        self,
        chat_id: str,
        anchor_timestamp: datetime,
        before: int = 10,
        after: int = 1,
    ) -> list[ContextMessage]:
        """Get messages around a timestamp from iMessage chat.db."""
        if not self.db_path.exists():
            return []

        anchor_macos = self._datetime_to_macos_timestamp(anchor_timestamp)

        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Get messages before the anchor
            cursor.execute("""
                SELECT
                    m.date,
                    m.text,
                    m.is_from_me,
                    h.id as sender
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
                LEFT JOIN chat c ON cmj.chat_id = c.ROWID
                WHERE c.chat_identifier = ?
                  AND m.date < ?
                  AND m.text IS NOT NULL
                  AND m.text != ''
                ORDER BY m.date DESC
                LIMIT ?
            """, (chat_id, anchor_macos, before))
            before_rows = list(reversed(cursor.fetchall()))

            # Get messages after the anchor
            cursor.execute("""
                SELECT
                    m.date,
                    m.text,
                    m.is_from_me,
                    h.id as sender
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
                LEFT JOIN chat c ON cmj.chat_id = c.ROWID
                WHERE c.chat_identifier = ?
                  AND m.date > ?
                  AND m.text IS NOT NULL
                  AND m.text != ''
                ORDER BY m.date ASC
                LIMIT ?
            """, (chat_id, anchor_macos, after))
            after_rows = cursor.fetchall()

            # Convert to ContextMessage
            messages = []
            for date_ns, text, is_from_me, sender in before_rows + after_rows:
                if text and text.strip():
                    messages.append(ContextMessage(
                        text=text.strip(),
                        sender="Me" if is_from_me else (sender or "Unknown"),
                        is_from_me=bool(is_from_me),
                        timestamp=self._macos_timestamp_to_datetime(date_ns),
                    ))

            return messages

        except Exception as e:
            logger.warning(f"IMessageReader.get_context_around failed: {e}")
            return []
        finally:
            if conn:
                conn.close()


class SignalReader:
    """Reads message context from Signal message database.

    Uses Unix milliseconds for timestamps.
    The database is stored at ~/Library/Application Support/signal-cli/messages.db
    """

    def __init__(self, db_path: Path = SIGNAL_DB):
        self.db_path = db_path

    def get_context_around(
        self,
        chat_id: str,
        anchor_timestamp: datetime,
        before: int = 10,
        after: int = 1,
    ) -> list[ContextMessage]:
        """Get messages around a timestamp from Signal database."""
        if not self.db_path.exists():
            return []

        # Signal uses Unix milliseconds
        anchor_ms = int(anchor_timestamp.timestamp() * 1000)

        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Get messages before the anchor
            cursor.execute("""
                SELECT timestamp, text, is_from_me, sender, attachments
                FROM messages
                WHERE chat_id = ?
                  AND timestamp < ?
                  AND (text IS NOT NULL AND text != '')
                ORDER BY timestamp DESC
                LIMIT ?
            """, (chat_id, anchor_ms, before))
            before_rows = list(reversed(cursor.fetchall()))

            # Get messages after the anchor
            cursor.execute("""
                SELECT timestamp, text, is_from_me, sender, attachments
                FROM messages
                WHERE chat_id = ?
                  AND timestamp > ?
                  AND (text IS NOT NULL AND text != '')
                ORDER BY timestamp ASC
                LIMIT ?
            """, (chat_id, anchor_ms, after))
            after_rows = cursor.fetchall()

            # Convert to ContextMessage
            messages = []
            for ts_ms, text, is_from_me, sender, attachments_json in before_rows + after_rows:
                if text and text.strip():
                    attachments = json.loads(attachments_json) if attachments_json else []
                    attachment_paths = [a.get("path", "") for a in attachments if a.get("path")]

                    messages.append(ContextMessage(
                        text=text.strip(),
                        sender="Me" if is_from_me else (sender or "Unknown"),
                        is_from_me=bool(is_from_me),
                        timestamp=datetime.fromtimestamp(ts_ms / 1000),
                        attachments=attachment_paths,
                    ))

            return messages

        except Exception as e:
            logger.warning(f"SignalReader.get_context_around failed: {e}")
            return []
        finally:
            if conn:
                conn.close()


class DispatchAppReader:
    """Reads message context from dispatch-app messages database.

    The database is stored at ~/dispatch/state/dispatch-messages.db
    and uses SQLite DATETIME strings for timestamps.

    Note: dispatch-app is a single-user voice assistant, so there's no chat_id
    filtering - all messages belong to the same conversation context.
    """

    def __init__(self, db_path: Path = DISPATCH_MESSAGES_DB):
        self.db_path = db_path

    def get_context_around(
        self,
        chat_id: str,
        anchor_timestamp: datetime,
        before: int = 10,
        after: int = 1,
    ) -> list[ContextMessage]:
        """Get messages around a timestamp from dispatch-app database."""
        if not self.db_path.exists():
            return []

        # dispatch-app uses ISO format datetime strings
        anchor_str = anchor_timestamp.strftime("%Y-%m-%d %H:%M:%S")

        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            cursor = conn.cursor()

            # Get messages before the anchor
            cursor.execute("""
                SELECT created_at, content, role, image_path
                FROM messages
                WHERE created_at < ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (anchor_str, before))
            before_rows = list(reversed(cursor.fetchall()))

            # Get messages after the anchor
            cursor.execute("""
                SELECT created_at, content, role, image_path
                FROM messages
                WHERE created_at > ?
                ORDER BY created_at ASC
                LIMIT ?
            """, (anchor_str, after))
            after_rows = cursor.fetchall()

            # Convert to ContextMessage
            messages = []
            for created_at, content, role, image_path in before_rows + after_rows:
                if content and content.strip():
                    # Parse SQLite datetime string
                    try:
                        ts = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        ts = datetime.now()

                    is_from_me = role == "assistant"
                    attachments = [image_path] if image_path else []

                    # Use assistant name from config for sender
                    from assistant import config
                    assistant_name = config.get("assistant.name", "Assistant")

                    messages.append(ContextMessage(
                        text=content.strip(),
                        sender=assistant_name if is_from_me else "User",
                        is_from_me=is_from_me,
                        timestamp=ts,
                        attachments=attachments,
                    ))

            return messages

        except Exception as e:
            logger.warning(f"DispatchAppReader.get_context_around failed: {e}")
            return []
        finally:
            if conn:
                conn.close()


# Registry mapping backend names to reader classes.
# Using a dict avoids hardcoded if/elif chains for each backend.
_READER_REGISTRY: dict[str, type] = {
    "imessage": IMessageReader,
    "signal": SignalReader,
    "dispatch-app": DispatchAppReader,
    "dispatch-api": DispatchAppReader,  # shares same DB as dispatch-app
    "sven-app": DispatchAppReader,  # DEPRECATED backward compat
}


def get_reader(source: str) -> MessageReader | None:
    """Get a MessageReader for the given backend source.

    Uses lazy initialization to avoid import-time database connection failures.

    Args:
        source: Backend source name ("imessage", "signal", "dispatch-app", etc.)

    Returns:
        MessageReader instance or None if backend doesn't support image context
    """
    reader_cls = _READER_REGISTRY.get(source)
    if reader_cls is not None:
        return reader_cls()
    return None


def format_context_for_gemini(messages: list[ContextMessage]) -> str:
    """Format messages as a string for Gemini vision prompt.

    Args:
        messages: List of ContextMessage in chronological order

    Returns:
        Formatted string with one message per line
    """
    if not messages:
        return ""

    lines = []
    for msg in messages:
        if msg.text:
            lines.append(f"{msg.sender}: {msg.text}")

    return "\n".join(lines)
