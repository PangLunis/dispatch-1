#!/usr/bin/env python3
"""
Claude Assistant Manager (SDK Backend)

Orchestrates the SMS-based personal assistant system:
- Polls Messages.app for new texts
- Routes messages to appropriate SDK sessions based on contact tier
- Manages session lifecycle (spawn, monitor, restart)
- Ignores messages from unknown contacts (not in any tier group)

Tier hierarchy: admin > wife > family > favorite
"""

import os
import sys
import time
import json
import re
import signal
import sqlite3
import subprocess
import logging
import socket
import threading
import queue
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from assistant.common import (
    HOME,
    ASSISTANT_DIR,
    STATE_DIR,
    LOGS_DIR,
    SESSION_REGISTRY_FILE,
    MESSAGES_DB,
    SKILLS_DIR,
    TRANSCRIPTS_DIR,
    CLAUDE,
    CLAUDE_ASSISTANT_CLI,
    UV,
    BUN,
    MASTER_SESSION,
    MASTER_TRANSCRIPT_DIR,
    SIGNAL_CLI,
    SIGNAL_SOCKET,
    signal_account,
    SIGNAL_DIR,
    normalize_chat_id,
    is_group_chat_id,
    get_session_name,
    get_group_session_name_from_participants,
    wrap_sms,
    wrap_admin,
    wrap_group_message,
    format_message_body,
    get_reply_chain,
    ensure_transcript_dir,
)
from assistant.sdk_backend import SDKBackend, SessionRegistry
from assistant import perf

# Import SignalDB for message persistence (lazy import to avoid startup errors)
_signal_db = None
def get_signal_db():
    """Lazy-load SignalDB to avoid import errors if signal skill not set up."""
    global _signal_db
    if _signal_db is None:
        try:
            sys.path.insert(0, str(Path.home() / ".claude/skills/signal/scripts"))
            from signal_db import SignalDB  # type: ignore[import-not-found]
            _signal_db = SignalDB()
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to load SignalDB: {e}")
            return None
    return _signal_db

# Paths
STATE_FILE = STATE_DIR / "last_rowid.txt"
CONSOLIDATION_STATE_FILE = STATE_DIR / "last_consolidation_date.txt"

# Search daemon config - lives in dispatch/services/memory-search
SEARCH_DAEMON_DIR = ASSISTANT_DIR / "services" / "memory-search"
SEARCH_DAEMON_SCRIPT = SEARCH_DAEMON_DIR / "src" / "daemon.ts"
SEARCH_DAEMON_PORT = 7890
SEARCH_DAEMON_ENABLED = os.environ.get("DISABLE_SEARCH_DAEMON", "").lower() not in ("1", "true", "yes")
SIGNAL_ENABLED = os.environ.get("DISABLE_SIGNAL", "").lower() not in ("1", "true", "yes")

# Sven API config - lives in dispatch/services/sven-api
SVEN_API_DIR = ASSISTANT_DIR / "services" / "sven-api"
SVEN_API_SCRIPT = SVEN_API_DIR / "server.py"
SVEN_API_PORT = 9091

# macOS epoch offset (2001-01-01 to 1970-01-01)
MACOS_EPOCH_OFFSET = 978307200

# Polling interval
POLL_INTERVAL = 0.1  # seconds (100ms for near-instant response)

# Setup logging (stdout only - cli.py redirects stdout to manager.log)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# Separate lifecycle logger for session events
lifecycle_log = logging.getLogger("lifecycle")
lifecycle_handler = logging.FileHandler(LOGS_DIR / "session_lifecycle.log")
lifecycle_handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s'))
lifecycle_log.addHandler(lifecycle_handler)
lifecycle_log.setLevel(logging.INFO)


class ContactsManager:
    """Interface to contacts with in-memory caching for fast lookups.

    Uses ContactsCache from contacts_core.py for O(1) phone lookups after initial load.
    Cache is loaded once on first use (~1 second), then lookups are microseconds.
    """

    CONTACTS_CLI = HOME / "code/contacts-cli/contacts"

    def __init__(self):
        import sys
        # contacts_core.py is in the skills folder
        sys.path.insert(0, str(HOME / "dispatch/skills/contacts/scripts"))
        from contacts_core import lookup_phone_sqlite, lookup_email_sqlite, list_contacts_sqlite
        self._lookup_phone = lookup_phone_sqlite
        self._lookup_email = lookup_email_sqlite
        self._list_contacts = list_contacts_sqlite

    def lookup_phone(self, phone: str) -> Optional[Dict[str, str]]:
        """Lookup contact by phone number via SQLite."""
        return self._lookup_phone(phone)

    def lookup_email(self, email: str) -> Optional[Dict[str, str]]:
        """Lookup contact by email address via SQLite."""
        return self._lookup_email(email)

    def lookup_identifier(self, identifier: str) -> Optional[Dict[str, str]]:
        """Lookup contact by phone OR email via SQLite."""
        with perf.timed("contact_lookup_ms", component="daemon"):
            contact = self._lookup_phone(identifier)
            if contact:
                return contact
            if '@' in identifier:
                return self._lookup_email(identifier)
            return None

    def list_blessed_contacts(self) -> list:
        """Get all contacts with blessed tiers (admin, wife, family, favorite)."""
        contacts = self._list_contacts()
        return [c for c in contacts if c.get("tier") in ("admin", "wife", "family", "favorite")]

    def lookup_phone_by_name(self, name: str) -> Optional[Dict[str, str]]:
        """Lookup contact by name via SQLite."""
        contacts = self._list_contacts()
        name_lower = name.lower()
        for c in contacts:
            if c["name"].lower() == name_lower:
                return c
        return None


class MessagesReader:
    """Reads messages from macOS Messages.app chat.db."""

    def __init__(self, contacts_manager=None):
        self.db_path = MESSAGES_DB
        self._contacts = contacts_manager

    def get_new_messages(self, since_rowid: int) -> list:
        """Get messages newer than the given ROWID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Force WAL checkpoint to ensure we see Messages.app's latest writes
        # TRUNCATE mode flushes all WAL data to main db, preventing stale reads
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        cursor.execute("""
            SELECT
                message.ROWID,
                message.date,
                handle.id as phone,
                message.is_from_me,
                message.text,
                message.attributedBody,
                message.cache_has_attachments,
                message.is_audio_message,
                chat.style,
                chat.display_name,
                chat.chat_identifier,
                message.thread_originator_guid
            FROM message
            LEFT JOIN handle ON message.handle_id = handle.ROWID
            LEFT JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
            LEFT JOIN chat ON chat_message_join.chat_id = chat.ROWID
            WHERE message.ROWID > ?
              AND message.is_from_me = 0
            ORDER BY message.date ASC
        """, (since_rowid,))

        rows = cursor.fetchall()

        messages = []
        for row in rows:
            rowid, date, phone, is_from_me, text, attributed_body, has_attachments, is_audio_message, chat_style, chat_display_name, chat_identifier, thread_originator_guid = row

            # Race condition fix: If chat_style is NULL, the chat_message_join row might not
            # have been written yet. Wait 50ms and re-query this specific message.
            if chat_style is None:
                race_start = time.time()
                log.info(f"[RACE_TELEMETRY] rowid={rowid} chat_style=NULL on initial query, waiting 50ms")
                time.sleep(0.05)  # 50ms
                cursor.execute("""
                    SELECT chat.style, chat.display_name, chat.chat_identifier
                    FROM message
                    LEFT JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
                    LEFT JOIN chat ON chat_message_join.chat_id = chat.ROWID
                    WHERE message.ROWID = ?
                """, (rowid,))
                requery_row = cursor.fetchone()
                race_elapsed_ms = (time.time() - race_start) * 1000
                if requery_row:
                    chat_style, chat_display_name, chat_identifier = requery_row
                    if chat_style is not None:
                        log.info(f"[RACE_TELEMETRY] rowid={rowid} SUCCESS after {race_elapsed_ms:.1f}ms - chat_style={chat_style} chat_identifier={chat_identifier}")
                    else:
                        log.warning(f"[RACE_TELEMETRY] rowid={rowid} STILL_NULL after {race_elapsed_ms:.1f}ms - join row may not exist yet")
                else:
                    log.warning(f"[RACE_TELEMETRY] rowid={rowid} NO_ROW after {race_elapsed_ms:.1f}ms - message may have been deleted")

            # Extract text from attributedBody if needed
            msg_text = text
            if not msg_text and attributed_body:
                msg_text = self._parse_attributed_body(attributed_body)

            # Extract audio transcription if this is an audio message
            audio_transcription = None
            if is_audio_message and attributed_body:
                audio_transcription = self._extract_audio_transcription(attributed_body)

            # Clean up attachment placeholder character
            if msg_text == '\ufffc':
                msg_text = None

            # Get attachments if present
            attachments = []
            if has_attachments:
                attachments = self._get_attachments(cursor, rowid)

            # Skip if no text AND no attachments
            if not msg_text and not attachments:
                continue

            # Skip if phone is None (can happen briefly when message is being written to DB)
            if not phone:
                continue

            # Detect group chat (style 43 = group, 45 = 1:1)
            is_group = chat_style == 43

            # Get group name - use display_name or generate from participants
            group_name = None
            if is_group:
                if chat_display_name:
                    group_name = chat_display_name
                else:
                    group_name = self._generate_group_name(cursor, chat_identifier, self._contacts)

            timestamp = self._macos_to_datetime(date)
            messages.append({
                "rowid": rowid,
                "timestamp": timestamp,
                "phone": phone,
                "text": msg_text,
                "attachments": attachments,
                "is_group": is_group,
                "group_name": group_name,
                "chat_identifier": chat_identifier,
                "is_audio_message": bool(is_audio_message),
                "audio_transcription": audio_transcription,
                "thread_originator_guid": thread_originator_guid
            })

        conn.close()
        return messages

    def get_new_reactions(self, since_rowid: int) -> list:
        """Get reactions newer than the given ROWID.

        Reactions are messages with associated_message_type in 2000-2999 (add) or 3000-3999 (remove).
        Standard types: 2000=❤️, 2001=👍, 2002=👎, 2003=😂, 2004=‼️, 2005=❓
        iOS 17+ uses 2006+ for custom emoji reactions (emoji stored in associated_message_emoji).
        Removals mirror: 3000=remove ❤️, etc.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Force WAL checkpoint for visibility
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        # Query reactions and join to get the target message text
        cursor.execute("""
            SELECT
                r.ROWID,
                r.date,
                h.id as phone,
                r.associated_message_type,
                r.associated_message_emoji,
                r.associated_message_guid,
                target.text as target_text,
                target.is_from_me as target_is_from_me,
                chat.style,
                chat.chat_identifier
            FROM message r
            LEFT JOIN handle h ON r.handle_id = h.ROWID
            LEFT JOIN message target ON substr(r.associated_message_guid, 5) = target.guid
            LEFT JOIN chat_message_join ON r.ROWID = chat_message_join.message_id
            LEFT JOIN chat ON chat_message_join.chat_id = chat.ROWID
            WHERE r.ROWID > ?
              AND r.is_from_me = 0
              AND (
                  r.associated_message_type BETWEEN 2000 AND 2999
                  OR r.associated_message_type BETWEEN 3000 AND 3999
              )
            ORDER BY r.date ASC
        """, (since_rowid,))

        rows = cursor.fetchall()
        reactions = []

        # Map reaction types to emoji (fallback if associated_message_emoji is null)
        REACTION_EMOJI = {
            2000: "❤️", 2001: "👍", 2002: "👎", 2003: "😂", 2004: "‼️", 2005: "❓",
            3000: "❤️", 3001: "👍", 3002: "👎", 3003: "😂", 3004: "‼️", 3005: "❓",
        }

        for row in rows:
            (rowid, date, phone, reaction_type, reaction_emoji, target_guid,
             target_text, target_is_from_me, chat_style, chat_identifier) = row

            if not phone:
                continue

            # Use associated_message_emoji if available (iOS 17+ custom emoji),
            # otherwise fall back to the type mapping
            emoji = reaction_emoji or REACTION_EMOJI.get(reaction_type, "💬")

            # Determine if this is a removal (3000+ series)
            is_removal = reaction_type >= 3000

            timestamp = self._macos_to_datetime(date)
            is_group = chat_style == 43

            reactions.append({
                "rowid": rowid,
                "timestamp": timestamp,
                "phone": phone,
                "emoji": emoji,
                "is_removal": is_removal,
                "target_guid": target_guid,
                "target_text": target_text,
                "target_is_from_me": bool(target_is_from_me),
                "is_group": is_group,
                "chat_identifier": chat_identifier,
                "type": "reaction",  # Mark as reaction for process_message routing
            })

        conn.close()
        return reactions

    def _generate_group_name(self, cursor, chat_identifier: str, contacts_manager=None) -> str | None:
        """Generate a group name from participant names.

        Uses ContactsManager for fast in-memory lookups instead of spawning
        a subprocess per participant (bug #10 fix).
        """
        # Get participant phone numbers
        cursor.execute("""
            SELECT h.id
            FROM handle h
            JOIN chat_handle_join chj ON h.ROWID = chj.handle_id
            JOIN chat c ON chj.chat_id = c.ROWID
            WHERE c.chat_identifier = ?
        """, (chat_identifier,))

        phones = [row[0] for row in cursor.fetchall()]

        # Look up contact names using in-memory contacts cache
        names = []
        for phone in phones:
            if contacts_manager:
                contact = contacts_manager.lookup_identifier(phone)
                if contact:
                    first_name = contact["name"].split()[0].lower()
                    names.append(first_name)
                else:
                    names.append(phone[-4:])
            else:
                names.append(phone[-4:])

        # Sort alphabetically and join
        names.sort()
        return "-".join(names) if names else None

    def _group_has_blessed_participant(self, chat_identifier: str, contacts_manager) -> bool:
        """Check if a group chat has any blessed contacts (admin, wife, family, favorite) as participants.

        This is used to allow messages from unknown senders (e.g., alternate email identifiers)
        in groups where a blessed contact participates. Without this, messages from the admin's alternate
        identifiers (email vs phone) would be ignored.

        Args:
            chat_identifier: The unique identifier for the group chat
            contacts_manager: A ContactsManager instance for looking up contacts
        """
        conn = sqlite3.connect(str(MESSAGES_DB))
        cursor = conn.cursor()

        try:
            # Get all participant identifiers for this chat
            cursor.execute("""
                SELECT h.id
                FROM handle h
                JOIN chat_handle_join chj ON h.ROWID = chj.handle_id
                JOIN chat c ON chj.chat_id = c.ROWID
                WHERE c.chat_identifier = ?
            """, (chat_identifier,))

            participants = [row[0] for row in cursor.fetchall()]

            # Check if any participant is a blessed contact (supports both phone and email identifiers)
            for participant_id in participants:
                contact = contacts_manager.lookup_identifier(participant_id)
                if contact and contact.get("tier") in ("admin", "wife", "family", "favorite"):
                    return True

            return False
        finally:
            conn.close()

    def _get_attachments(self, cursor, message_rowid: int) -> list:
        """Get attachments for a message."""
        cursor.execute("""
            SELECT
                attachment.filename,
                attachment.mime_type,
                attachment.transfer_name,
                attachment.total_bytes
            FROM attachment
            JOIN message_attachment_join ON attachment.ROWID = message_attachment_join.attachment_id
            WHERE message_attachment_join.message_id = ?
        """, (message_rowid,))

        attachments = []
        for row in cursor.fetchall():
            filename, mime_type, transfer_name, total_bytes = row
            if filename:
                # Expand ~ to full path
                full_path = filename.replace("~/", str(Path.home()) + "/")
                attachments.append({
                    "path": full_path,
                    "mime_type": mime_type or "unknown",
                    "name": transfer_name or Path(filename).name,
                    "size": total_bytes or 0
                })
        return attachments

    def get_latest_rowid(self) -> int:
        """Get the most recent message ROWID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        cursor.execute("SELECT MAX(ROWID) FROM message")
        result = cursor.fetchone()[0]
        conn.close()
        return result or 0

    def _parse_attributed_body(self, data: bytes) -> Optional[str]:
        """Extract text from NSAttributedString binary data."""
        if not data:
            return None
        try:
            parts = data.split(b"NSString")
            if len(parts) < 2:
                return None
            content = parts[1][5:]
            if content[0] == 0x81:
                length = int.from_bytes(content[1:3], "little")
                text_start = 3
            else:
                length = content[0]
                text_start = 1
            return content[text_start:text_start + length].decode("utf-8", errors="ignore")
        except Exception:
            return None

    def _extract_audio_transcription(self, data: bytes) -> Optional[str]:
        """Extract Apple's audio transcription from attributedBody."""
        if not data:
            return None
        try:
            import re
            text = data.decode('utf-8', errors='ignore')
            # Look for IMAudioTranscription followed by the text
            match = re.search(r'IMAudioTranscription.(.+?)(?:__kIM|$)', text, re.DOTALL)
            if match:
                raw = match.group(1)
                # Clean up: remove non-printable characters except spaces
                cleaned = ''.join(c for c in raw if c.isprintable() or c == ' ')
                cleaned = cleaned.strip()
                if cleaned and cleaned[0].isdigit():
                    # Skip leading digit (length indicator)
                    cleaned = cleaned[1:].strip()
                # Remove trailing artifacts
                cleaned = cleaned.rstrip('&').strip()
                return cleaned if cleaned else None
            return None
        except Exception:
            return None

    def _macos_to_datetime(self, ts: int) -> datetime:
        """Convert macOS nanosecond timestamp to datetime."""
        unix_ts = ts / 1_000_000_000 + MACOS_EPOCH_OFFSET
        return datetime.fromtimestamp(unix_ts)


class SignalListener(threading.Thread):
    """Listens to signal-cli daemon socket and queues incoming messages.

    Runs in a background thread, connects to the signal-cli JSON-RPC socket,
    subscribes to receive notifications, and pushes incoming messages to a
    thread-safe queue for processing by the main loop.
    """

    def __init__(self, message_queue: queue.Queue):
        super().__init__(daemon=True, name="SignalListener")
        self.message_queue = message_queue
        self.socket_path = str(SIGNAL_SOCKET)
        self.running = False
        self.sock = None
        self._seen_timestamps: set[int] = set()  # Track recent timestamps to avoid duplicates
        self._seen_timestamps_max = 1000  # Prune when set gets too large

    def stop(self):
        """Stop the listener thread."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def run(self):
        """Main listener loop - connects and processes messages."""
        self.running = True
        while self.running:
            try:
                self._connect_and_listen()
            except Exception as e:
                log.error(f"SignalListener error: {e}")
                time.sleep(5)  # Backoff on error

    def _connect_and_listen(self):
        """Connect to socket and process incoming messages."""
        if not SIGNAL_SOCKET.exists():
            log.debug("Signal socket not ready, waiting...")
            time.sleep(1)
            return

        log.info(f"SignalListener connecting to {self.socket_path}")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)
        log.info("SignalListener connected")

        # Subscribe to receive messages
        subscribe_req = json.dumps({
            "jsonrpc": "2.0",
            "method": "subscribeReceive",
            "id": 1,
            "params": {}
        }) + "\n"
        self.sock.sendall(subscribe_req.encode())

        buffer = b""
        while self.running:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    log.warning("SignalListener: socket closed")
                    break
                buffer += chunk

                # Process complete JSON lines
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    self._process_message(line.decode())

            except socket.timeout:
                continue
            except Exception as e:
                log.error(f"SignalListener recv error: {e}")
                break

        if self.sock:
            self.sock.close()
            self.sock = None

    def _process_message(self, line: str):
        """Parse a JSON-RPC message and queue it if it's an incoming message."""
        try:
            data = json.loads(line)

            # We only care about receive notifications
            if data.get("method") != "receive":
                return

            params = data.get("params", {})
            # Handle both direct params and nested result
            result = params.get("result", params)
            envelope = result.get("envelope", {})

            # Extract message data
            # Use phone number if available, fall back to UUID for users who haven't shared their number
            source_number = envelope.get("sourceNumber") or envelope.get("sourceUuid")
            source_name = envelope.get("sourceName")
            data_msg = envelope.get("dataMessage", {})
            body = data_msg.get("message")
            timestamp = data_msg.get("timestamp", 0)

            # Skip if no text message
            if not body:
                return

            # Skip duplicates (use set to handle out-of-order messages)
            if timestamp in self._seen_timestamps:
                return
            self._seen_timestamps.add(timestamp)
            # Prune old timestamps to prevent unbounded growth
            if len(self._seen_timestamps) > self._seen_timestamps_max:
                sorted_ts = sorted(self._seen_timestamps)
                self._seen_timestamps = set(sorted_ts[len(sorted_ts) // 2:])

            # Check for group message
            group_info = data_msg.get("groupInfo", {})
            group_id = group_info.get("groupId")

            # Build message dict matching MessagesReader format
            msg = {
                "rowid": timestamp,  # Use timestamp as unique ID
                "timestamp": datetime.fromtimestamp(timestamp / 1000),
                "phone": source_number,
                "text": body,
                "attachments": self._extract_attachments(data_msg),
                "is_group": bool(group_id),
                "group_name": group_info.get("groupName"),
                "chat_identifier": group_id if group_id else source_number,
                "is_audio_message": False,
                "audio_transcription": None,
                "thread_originator_guid": None,
                "source": "signal",  # Mark as Signal message
            }

            log.info(f"SignalListener: queued message from {source_number}: {body[:50]}...")
            self.message_queue.put(msg)

            # Store in database for history
            try:
                db = get_signal_db()
                if db and not db.message_exists(timestamp, msg["chat_identifier"], source_number):
                    db.store_message(
                        timestamp=timestamp,
                        chat_id=msg["chat_identifier"],
                        sender=source_number,
                        text=body,
                        is_from_me=False,
                        attachments=msg["attachments"] if msg["attachments"] else None,
                        group_name=group_info.get("groupName"),
                    )
                    log.debug(f"SignalListener: stored message in DB")
            except Exception as e:
                log.warning(f"SignalListener: failed to store message in DB: {e}")

        except json.JSONDecodeError as e:
            log.debug(f"SignalListener: invalid JSON: {e}")
        except Exception as e:
            log.error(f"SignalListener: error processing message: {e}")

    def _extract_attachments(self, data_msg: dict) -> List[dict]:
        """Extract attachment info from a Signal message."""
        attachments = []
        for att in data_msg.get("attachments", []):
            attachments.append({
                "path": att.get("file", ""),
                "mime_type": att.get("contentType", "unknown"),
                "name": att.get("filename", "attachment"),
                "size": att.get("size", 0),
            })
        return attachments


class TestMessageWatcher(threading.Thread):
    """Watches test message directory and queues test messages for processing.

    Enables testing without iMessage/Signal by dropping JSON files into a directory.
    File format:
    {
        "from": "+15555551234",
        "text": "message text",
        "is_group": false,
        "chat_id": "+15555551234",  // optional, defaults to "from"
        "group_name": "Test Group",  // optional
        "attachments": ["/path/to/file"],  // optional
        "reply_to": "guid"  // optional
    }
    """

    TEST_DIR = Path(HOME) / ".claude/test-messages"

    def __init__(self, message_queue: queue.Queue):
        super().__init__(daemon=True, name="TestMessageWatcher")
        self.message_queue = message_queue
        self.running = False
        self.TEST_DIR.mkdir(parents=True, exist_ok=True)

    def stop(self):
        """Stop the watcher thread."""
        self.running = False

    def run(self):
        """Main watcher loop - polls directory for .json files."""
        self.running = True
        log.info(f"TestMessageWatcher started, watching {self.TEST_DIR}")

        while self.running:
            try:
                # Look for .json files
                for file_path in sorted(self.TEST_DIR.glob("*.json")):
                    try:
                        with open(file_path) as f:
                            raw_msg = json.load(f)

                        # Normalize to message contract
                        normalized = self._normalize_message(raw_msg)

                        # Queue for processing
                        self.message_queue.put(normalized)
                        log.info(f"Queued test message from {file_path.name}: from={normalized['phone']} is_group={normalized['is_group']}")

                        # Delete file after reading
                        file_path.unlink()

                    except Exception as e:
                        log.error(f"Error processing test message {file_path}: {e}")
                        # Move to error directory instead of leaving in place
                        error_dir = self.TEST_DIR / "errors"
                        error_dir.mkdir(exist_ok=True)
                        try:
                            file_path.rename(error_dir / file_path.name)
                        except Exception:
                            file_path.unlink()  # Delete if can't move

                time.sleep(0.1)  # Poll every 100ms

            except Exception as e:
                log.error(f"TestMessageWatcher error: {e}")
                time.sleep(1)

    def _normalize_message(self, raw: dict) -> dict:
        """Convert test message format to internal message contract."""
        from_phone = raw.get("from", "+15555550005")
        is_group = raw.get("is_group", False)
        chat_id = raw.get("chat_id", from_phone)

        # Normalize chat_id
        chat_id = normalize_chat_id(chat_id)

        # Build message matching MessagesReader/SignalListener format
        msg = {
            "rowid": int(time.time() * 1000),  # Fake ROWID for test messages
            "date": int(time.time()),
            "phone": from_phone,
            "is_from_me": 0,
            "text": raw.get("text", ""),
            "attachments": [],
            "is_group": is_group,
            "group_name": raw.get("group_name"),
            "chat_identifier": chat_id,
            "chat_style": 43 if is_group else 45,
            "reply_to_guid": raw.get("reply_to"),
            "source": "test",  # Tag as test message
        }

        # Handle attachments
        if "attachments" in raw:
            for path in raw["attachments"]:
                msg["attachments"].append({
                    "path": path,
                    "mime_type": "unknown",
                    "name": Path(path).name,
                    "size": 0,
                })

        return msg


class ReminderPoller:
    """Polls for due reminders and cron-based reminders, injecting into contact sessions."""

    POLL_SCRIPT = SKILLS_DIR / "reminders/scripts/poll_due.py"

    def __init__(self, backend: SDKBackend, contacts_manager: ContactsManager):
        self.backend = backend
        self.contacts = contacts_manager
        # Track last-fired times for cron reminders to avoid double-firing
        # Key: reminder_id, Value: datetime of last fire
        self.cron_last_fired = {}

    def check_due_reminders(self) -> list:
        """Poll for due reminders."""
        if not self.POLL_SCRIPT.exists():
            return []

        result = subprocess.run(
            [UV, "run", "python", str(self.POLL_SCRIPT), "--json"],
            capture_output=True, text=True
        )

        if result.returncode != 0:
            log.error(f"Reminder poll failed: {result.stderr}")
            return []

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

    def check_cron_reminders(self) -> list:
        """Get reminders with cron patterns."""
        if not self.POLL_SCRIPT.exists():
            return []

        # Use Python to get cron reminders directly
        import sys
        reminders_path = str(SKILLS_DIR / "reminders/scripts")
        if reminders_path not in sys.path:
            sys.path.insert(0, reminders_path)
        try:
            from poll_due import get_cron_reminders, find_reminders_db
            db_path = find_reminders_db()
            if db_path:
                return get_cron_reminders(db_path)
        except Exception as e:
            log.error(f"Failed to get cron reminders: {e}")
        return []

    def _should_fire_cron(self, reminder_id: int, cron_pattern: str) -> bool:
        """Check if a cron pattern matches current time and hasn't fired this minute."""
        try:
            from croniter import croniter
            now = datetime.now()

            # Check if already fired this minute
            last_fired = self.cron_last_fired.get(reminder_id)
            if last_fired and last_fired.replace(second=0, microsecond=0) == now.replace(second=0, microsecond=0):
                return False

            # Check if cron matches current time
            # Get the previous scheduled time - if it's within the last minute, we should fire
            cron = croniter(cron_pattern, now)
            prev_time = cron.get_prev(datetime)

            # If the previous scheduled time is within the last 60 seconds, fire
            if (now - prev_time).total_seconds() < 60:
                self.cron_last_fired[reminder_id] = now
                return True

            return False
        except Exception as e:
            log.error(f"Failed to evaluate cron pattern '{cron_pattern}': {e}")
            return False

    async def process_due_reminders(self):
        """Check for due reminders and cron reminders, inject into contact sessions."""
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

        # Process one-time due reminders
        due_reminders = self.check_due_reminders()
        if due_reminders:
            log.info(f"REMINDER_POLL | found {len(due_reminders)} due reminders")
        for r in due_reminders:
            # Skip cron reminders here (handled separately)
            if r.get("cron"):
                continue
            await self._inject_reminder(r, timestamp, is_cron=False)

        # Process cron-based reminders
        cron_reminders = self.check_cron_reminders()
        for r in cron_reminders:
            # Check if cron has an until_date and it's past
            until_ts = r.get("until_timestamp")
            if until_ts and now.timestamp() > until_ts:
                log.info(f"Cron reminder expired (past until_date): {r['title']}")
                self._complete_reminder(r["title"], r.get("list", "Reminders"))
                continue

            if self._should_fire_cron(r["id"], r["cron"]):
                log.info(f"Cron reminder triggered: {r['title']} (pattern: {r['cron']})")
                await self._inject_reminder(r, timestamp, is_cron=True)

    async def _inject_reminder(self, r: dict, timestamp: str, is_cron: bool):
        """Inject a reminder into the appropriate session(s) via SDK backend."""
        contact = r.get("contact")
        if not contact:
            log.debug(f"Skipping reminder without contact: {r['title']}")
            return

        # Check if contact is already a chat_id (hex string for group chats or phone number)
        if re.match(r'^[0-9a-f]{32}$', contact) or contact.startswith('+'):
            # Already a chat_id (group chat hex or phone number), use directly
            chat_id = contact
            tier = "admin"  # Default to admin for direct chat_id reminders
        else:
            # Look up contact's chat_id (phone number) by name
            contact_info = self.contacts.lookup_phone_by_name(contact)
            if not contact_info:
                log.warning(f"Could not find chat_id for contact {contact}, skipping reminder")
                return
            chat_id = contact_info.get("phone")
            if not chat_id:
                log.warning(f"No phone for contact {contact}, skipping reminder")
                return
            tier = contact_info.get("tier", "admin")

        # Build reminder injection message
        title = r.get("title", "Reminder")
        notes = r.get("notes", "")
        target = r.get("target", "fg")  # fg, bg, or both
        cron_pattern = r.get("cron", "")

        # Different instructions based on target
        fg_instruction = """ACTION REQUIRED:
1. TEXT the user: "Reminder fired: [task name]. Working on it now..."
2. EXECUTE the task
3. TEXT the user the results when done"""
        bg_instruction = "EXECUTE this task now silently. No need to text the user."

        # Build base prompt
        def build_prompt(instruction):
            injection = f"""
---REMINDER FIRED [{timestamp}]---
{title}
"""
            if notes:
                injection += f"Notes: {notes}\n"
            if is_cron:
                injection += f"Schedule: {cron_pattern} (recurring)\n"
            injection += f"""---END REMINDER---

{instruction}
"""
            return injection

        # Inject into target session(s) directly (not via inject_message which adds SMS wrapping)
        normalized = normalize_chat_id(chat_id)
        if target in ("fg", "both"):
            prompt = build_prompt(fg_instruction)
            try:
                session = self.backend.sessions.get(normalized)
                if session and session.is_alive():
                    await session.inject(prompt)
                    log.info(f"Injected reminder to FG: {title}")
                else:
                    # Create session and inject
                    await self.backend.create_session(contact, normalized, tier)
                    session = self.backend.sessions.get(normalized)
                    if session:
                        await session.inject(prompt)
                        log.info(f"Injected reminder to FG (created): {title}")
                    else:
                        log.error(f"Failed to create FG session for reminder {title}")
            except Exception as e:
                log.error(f"Failed to inject reminder {title} to FG: {e}")

        if target in ("bg", "both"):
            prompt = build_prompt(bg_instruction)
            try:
                # Inject into background session
                bg_id = f"{normalize_chat_id(chat_id)}-bg"
                session = self.backend.sessions.get(bg_id)
                if session and session.is_alive():
                    await session.inject(prompt)
                    log.info(f"Injected reminder to BG: {title}")
                else:
                    # Create BG session and inject
                    await self.backend.create_background_session(contact, chat_id, tier)
                    session = self.backend.sessions.get(bg_id)
                    if session:
                        await session.inject(prompt)
                        log.info(f"Injected reminder to BG (created): {title}")
                    else:
                        log.error(f"Failed to create BG session for reminder {title}")
            except Exception as e:
                log.error(f"Failed to inject reminder {title} to BG: {e}")

        # Only mark complete if NOT a cron reminder
        if not is_cron:
            self._complete_reminder(r["title"], r.get("list", "Reminders"))

    def _complete_reminder(self, title: str, list_name: str = "Reminders"):
        """Mark a reminder as complete."""
        result = subprocess.run(
            [UV, "run", "python", str(self.POLL_SCRIPT), "--complete", title, "--list", list_name],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            log.info(f"Marked reminder complete: {title} (list: {list_name})")
        else:
            log.error(f"Failed to complete reminder '{title}' in list '{list_name}': {result.stderr} {result.stdout}")


class IPCServer:
    """Unix socket IPC server for CLI commands."""

    IPC_SOCKET = Path("/tmp/claude-assistant.sock")

    def __init__(self, backend: SDKBackend, registry: SessionRegistry, contacts: ContactsManager):
        self.backend = backend
        self.registry = registry
        self.contacts = contacts
        self._server = None

    async def start(self):
        # Clean up stale socket
        self.IPC_SOCKET.unlink(missing_ok=True)
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(self.IPC_SOCKET)
        )
        self.IPC_SOCKET.chmod(0o600)  # Owner-only access
        log.info(f"IPC server listening on {self.IPC_SOCKET}")

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self.IPC_SOCKET.unlink(missing_ok=True)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.readline(), timeout=30)
            if not data:
                return

            request = json.loads(data.decode())
            response = await self._dispatch(request)
            writer.write((json.dumps(response) + "\n").encode())
            await writer.drain()
        except Exception as e:
            try:
                writer.write((json.dumps({"ok": False, "error": str(e)}) + "\n").encode())
                await writer.drain()
            except Exception:
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch(self, request: dict) -> dict:
        cmd = request.get("cmd")

        if cmd == "inject":
            return await self._cmd_inject(request)
        elif cmd == "kill_session":
            chat_id = request.get("chat_id")
            if not chat_id:
                return {"ok": False, "error": "Missing chat_id"}
            ok = await self.backend.kill_session(chat_id)
            return {"ok": ok, "message": f"Killed {chat_id}" if ok else "Session not found"}
        elif cmd == "restart_session":
            chat_id = request.get("chat_id")
            tier = request.get("tier")  # Optional tier override
            if not chat_id:
                return {"ok": False, "error": "Missing chat_id"}
            session = await self.backend.restart_session(chat_id, tier_override=tier)
            return {"ok": session is not None, "message": f"Restarted {chat_id}" if session else "Failed to restart"}
        elif cmd == "set_model":
            chat_id = request.get("chat_id")
            model = request.get("model")
            if not chat_id:
                return {"ok": False, "error": "Missing chat_id"}
            if model not in ("opus", "sonnet", "haiku"):
                return {"ok": False, "error": f"Invalid model: {model}"}
            # Update registry with new model
            existing = self.registry.get(chat_id)
            if not existing:
                return {"ok": False, "error": f"Session not found: {chat_id}"}
            existing["model"] = model
            self.registry.register(**existing)
            # Restart session to pick up new model
            session = await self.backend.restart_session(chat_id)
            return {"ok": session is not None, "message": f"Set model to {model} for {chat_id}"}
        elif cmd == "kill_all_sessions":
            count = await self.backend.kill_all_sessions()
            return {"ok": True, "message": f"Killed {count} sessions"}
        elif cmd == "status":
            sessions = await self.backend.get_all_sessions()
            # Enrich with registry data (session_name, etc.)
            for s in sessions:
                s_chat_id = s.get("chat_id")
                reg = self.registry.get(s_chat_id) if s_chat_id else None
                if reg:
                    s["session_name"] = reg.get("session_name", "")
                    if not s.get("tier"):
                        s["tier"] = reg.get("tier", "")
            return {"ok": True, "sessions": sessions}
        else:
            return {"ok": False, "error": f"Unknown command: {cmd}"}

    async def _cmd_inject(self, req: dict) -> dict:
        chat_id = req.get("chat_id")
        prompt = req.get("prompt", "")
        is_sms = req.get("sms", False)
        is_admin = req.get("admin", False)
        is_sven_app = req.get("sven_app", False)
        is_bg = req.get("bg", False)
        contact_name = req.get("contact_name")
        tier = req.get("tier")
        source = req.get("source", "imessage")
        reply_to = req.get("reply_to")
        attachment = req.get("attachment")  # Optional: {"path": "/path/to/image.jpg"}

        if not chat_id or not prompt:
            return {"ok": False, "error": "chat_id and prompt required"}

        # Wrap prompt if needed
        final_prompt = prompt
        if is_sms and contact_name and tier:
            final_prompt = wrap_sms(final_prompt, contact_name, tier, chat_id, reply_to_guid=reply_to, source=source, sven_app=is_sven_app)
        if is_admin:
            final_prompt = wrap_admin(final_prompt)

        # Append tier-specific rules reminder suffix (only for tiers with rules files)
        if tier in ["admin", "wife", "family", "favorite", "bots", "unknown"]:
            rules_file = f"~/.claude/skills/sms-assistant/{tier}-rules.md"
            suffix = f"\n\nREMINDER: If you haven't already, read {rules_file} for important behavioral guidelines for {tier} tier contacts."
            final_prompt = final_prompt + suffix

        # Determine if this is a group
        is_group = is_group_chat_id(chat_id)

        # Build attachments list if attachment provided
        attachments = None
        message_timestamp = None
        if attachment:
            attachments = [attachment]
            # Use current time as message timestamp for CLI injections
            from datetime import datetime
            message_timestamp = datetime.now()

        try:
            if is_bg:
                await self.backend.inject_consolidation(contact_name or "Unknown", chat_id)
            elif is_group:
                await self.backend.inject_group_message(
                    chat_id=chat_id,
                    display_name=contact_name or "Group",
                    sender_name=contact_name or "Admin",
                    sender_tier=tier or "admin",
                    text=final_prompt,
                    attachments=attachments,
                    source=source,
                    message_timestamp=message_timestamp,
                )
            else:
                await self.backend.inject_message(
                    contact_name or "Unknown", chat_id, final_prompt, tier or "admin",
                    attachments=attachments,
                    source=source,
                    message_timestamp=message_timestamp,
                )

            reg_data = self.registry.get(chat_id)
            session_name = reg_data.get("session_name", chat_id) if reg_data else chat_id
            return {"ok": True, "message": f"Injected into {session_name}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


class Manager:
    """Main manager that orchestrates everything."""

    def __init__(self):
        self.contacts = ContactsManager()
        self.messages = MessagesReader(contacts_manager=self.contacts)
        self.registry = SessionRegistry(SESSION_REGISTRY_FILE)
        self.sessions = SDKBackend(
            registry=self.registry,
            contacts_manager=self.contacts,
        )
        self.reminders = ReminderPoller(self.sessions, self.contacts)
        self.ipc = IPCServer(self.sessions, self.registry, self.contacts)

        # Spawn search daemon as child process (unless disabled)
        if SEARCH_DAEMON_ENABLED:
            self.search_daemon = self._spawn_search_daemon()
        else:
            log.info("Search daemon disabled via DISABLE_SEARCH_DAEMON env var")
            self.search_daemon = None

        # Spawn Sven API as child process
        self.sven_api_daemon = self._spawn_sven_api_daemon()

        # Signal integration
        self.signal_queue = queue.Queue()
        self.signal_daemon = None
        self.signal_listener = None

        # Test message integration
        self.test_queue = queue.Queue()
        self.test_watcher = None

        # Load last processed ROWID
        self.last_rowid = self._load_state()

        # Shutdown flag
        self._shutdown_flag = False

        # Health check background task flag (prevents overlapping runs)
        self._health_check_running = False

    def _load_state(self) -> int:
        """Load the last processed message ROWID."""
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if STATE_FILE.exists():
            return int(STATE_FILE.read_text().strip())
        # Start from current position (don't process old messages)
        return self.messages.get_latest_rowid()

    def _save_state(self, rowid: int):
        """Save the last processed message ROWID."""
        STATE_FILE.write_text(str(rowid))
        self.last_rowid = rowid

    def _spawn_search_daemon(self) -> Optional[subprocess.Popen]:
        """Spawn the search daemon as a child process.

        Returns the Popen object or None if spawn failed.
        """
        if not SEARCH_DAEMON_SCRIPT.exists():
            log.warning(f"Search daemon script not found at {SEARCH_DAEMON_SCRIPT}")
            return None

        search_log_path = LOGS_DIR / "search-daemon.log"
        self._search_log_fh = open(search_log_path, "a")

        try:
            proc = subprocess.Popen(
                [str(BUN), "run", str(SEARCH_DAEMON_SCRIPT)],
                stdout=self._search_log_fh,
                stderr=self._search_log_fh,
                cwd=str(SEARCH_DAEMON_DIR),
            )
            log.info(f"Spawned search daemon (PID: {proc.pid})")
            lifecycle_log.info(f"SEARCH_DAEMON | SPAWNED | pid={proc.pid}")
            return proc
        except Exception as e:
            log.error(f"Failed to spawn search daemon: {e}")
            return None

    def _check_search_daemon_health(self) -> bool:
        """Check if search daemon is responding."""
        try:
            import urllib.request
            url = f"http://localhost:{SEARCH_DAEMON_PORT}/health"
            with urllib.request.urlopen(url, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _spawn_sven_api_daemon(self) -> Optional[subprocess.Popen]:
        """Spawn the Sven API server as a child process.

        Returns the Popen object or None if spawn failed.
        """
        if not SVEN_API_SCRIPT.exists():
            log.warning(f"Sven API script not found at {SVEN_API_SCRIPT}")
            return None

        sven_api_log_path = LOGS_DIR / "sven-api.log"
        self._sven_api_log_fh = open(sven_api_log_path, "a")

        try:
            proc = subprocess.Popen(
                [str(UV), "run", str(SVEN_API_SCRIPT)],
                stdout=self._sven_api_log_fh,
                stderr=self._sven_api_log_fh,
                cwd=str(SVEN_API_DIR),
            )
            log.info(f"Spawned Sven API daemon (PID: {proc.pid})")
            lifecycle_log.info(f"SVEN_API | SPAWNED | pid={proc.pid}")
            return proc
        except Exception as e:
            log.error(f"Failed to spawn Sven API daemon: {e}")
            return None

    def _check_sven_api_health(self) -> bool:
        """Check if Sven API is responding."""
        try:
            import urllib.request
            url = f"http://localhost:{SVEN_API_PORT}/health"
            with urllib.request.urlopen(url, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _kill_existing_signal_daemons(self):
        """Kill any existing signal-cli daemon processes to avoid pile-up."""
        try:
            result = subprocess.run(
                ["pkill", "-f", "signal-cli.*daemon.*--socket"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                log.info("Killed existing signal-cli daemon processes")
                time.sleep(1)  # Let processes die
        except Exception as e:
            log.debug(f"pkill signal-cli: {e}")

    def _spawn_signal_daemon(self) -> Optional[subprocess.Popen]:
        """Spawn the signal-cli daemon as a child process.

        Returns the Popen object or None if spawn failed.
        """
        # Kill any orphaned signal-cli processes first
        self._kill_existing_signal_daemons()

        # Clean up any stale socket
        if SIGNAL_SOCKET.exists():
            SIGNAL_SOCKET.unlink()

        signal_log_path = LOGS_DIR / "signal-daemon.log"
        # Close previous file handle if respawning
        if hasattr(self, '_signal_log_fh') and self._signal_log_fh:
            try:
                self._signal_log_fh.close()
            except Exception:
                pass
        self._signal_log_fh = open(signal_log_path, "a")

        try:
            proc = subprocess.Popen(
                [str(SIGNAL_CLI), "-a", signal_account(), "daemon", "--socket", str(SIGNAL_SOCKET), "--receive-mode", "on-connection", "--no-receive-stdout"],
                stdout=self._signal_log_fh,
                stderr=self._signal_log_fh,
            )
            log.info(f"Spawned signal-cli daemon (PID: {proc.pid})")
            lifecycle_log.info(f"SIGNAL_DAEMON | SPAWNED | pid={proc.pid}")

            # Wait for socket to be ready (up to 30s - Java is slow to start)
            for _ in range(300):
                if SIGNAL_SOCKET.exists():
                    log.info("Signal daemon socket ready")
                    return proc
                time.sleep(0.1)

            log.warning("Signal daemon started but socket not ready after 30s")
            return proc
        except Exception as e:
            log.error(f"Failed to spawn signal daemon: {e}")
            return None

    def _start_signal_listener(self):
        """Start the Signal listener thread."""
        if self.signal_listener is not None and self.signal_listener.is_alive():
            log.debug("Signal listener already running")
            return

        self.signal_listener = SignalListener(self.signal_queue)
        self.signal_listener.start()
        log.info("Started Signal listener thread")
        lifecycle_log.info("SIGNAL_LISTENER | STARTED")

    def _stop_signal(self):
        """Stop Signal daemon and listener."""
        if self.signal_listener:
            self.signal_listener.stop()
            self.signal_listener = None

        if self.signal_daemon:
            self.signal_daemon.terminate()
            try:
                self.signal_daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.signal_daemon.kill()
            self.signal_daemon = None
            log.info("Stopped signal daemon")

        if SIGNAL_SOCKET.exists():
            SIGNAL_SOCKET.unlink()

    def _stop_sven_api(self):
        """Stop Sven API daemon."""
        if self.sven_api_daemon:
            self.sven_api_daemon.terminate()
            try:
                self.sven_api_daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.sven_api_daemon.kill()
            self.sven_api_daemon = None
            log.info("Stopped Sven API daemon")

    async def _run_health_checks(self):
        """Run all health checks in background (non-blocking).

        This runs as a separate async task so health checks don't block
        the main message processing loop. Includes:
        - Session health_check_all (liveness)
        - Tier 2 deep Haiku analysis
        - Search daemon health
        - Signal daemon health
        - Sven API health
        """
        try:
            log.info("Running session health check (background)...")

            # Session liveness check
            await self.sessions.health_check_all()

            # Tier 2: Haiku deep analysis (skip recently healed)
            try:
                recently_healed = set(self.sessions._recently_healed.keys())
                await self.sessions.deep_health_check(skip_chat_ids=recently_healed)
            except Exception as e:
                log.error(f"Deep health check failed: {e}")

            # Check search daemon health
            if self.search_daemon is not None:
                if self.search_daemon.poll() is not None:
                    log.warning("Search daemon died, restarting...")
                    lifecycle_log.info(f"SEARCH_DAEMON | DIED | restarting")
                    self.search_daemon = self._spawn_search_daemon()
                elif not self._check_search_daemon_health():
                    log.warning("Search daemon not responding, restarting...")
                    lifecycle_log.info(f"SEARCH_DAEMON | UNRESPONSIVE | restarting")
                    self.search_daemon.kill()
                    self.search_daemon = self._spawn_search_daemon()

            # Check Signal daemon health
            if self.signal_daemon is not None:
                if self.signal_daemon.poll() is not None:
                    log.warning("Signal daemon died, restarting...")
                    lifecycle_log.info(f"SIGNAL_DAEMON | DIED | restarting")
                    self.signal_daemon = self._spawn_signal_daemon()
                    if self.signal_daemon:
                        self._start_signal_listener()
                elif not SIGNAL_SOCKET.exists():
                    log.warning("Signal socket missing, restarting daemon...")
                    lifecycle_log.info(f"SIGNAL_DAEMON | SOCKET_MISSING | restarting")
                    self.signal_daemon.terminate()
                    try:
                        self.signal_daemon.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.signal_daemon.kill()
                    self.signal_daemon = self._spawn_signal_daemon()
                    if self.signal_daemon:
                        self._start_signal_listener()

            # Check Sven API health
            if self.sven_api_daemon is not None:
                if self.sven_api_daemon.poll() is not None:
                    log.warning("Sven API died, restarting...")
                    lifecycle_log.info(f"SVEN_API | DIED | restarting")
                    self.sven_api_daemon = self._spawn_sven_api_daemon()
                elif not self._check_sven_api_health():
                    log.warning("Sven API not responding, restarting...")
                    lifecycle_log.info(f"SVEN_API | UNRESPONSIVE | restarting")
                    self.sven_api_daemon.kill()
                    self.sven_api_daemon = self._spawn_sven_api_daemon()

            log.info("Health check completed (background)")

        except Exception as e:
            log.error(f"Background health check failed: {e}")
        finally:
            self._health_check_running = False

    def _send_sms(self, phone: str, message: str) -> bool:
        """Send an SMS message via the send-sms CLI.

        Returns True on success, False on failure.
        """
        try:
            result = subprocess.run(
                [str(HOME / "code/sms-cli/send-sms"), phone, message],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                log.error(f"Failed to send SMS to {phone}: {result.stderr}")
                return False
            return True
        except Exception as e:
            log.error(f"Error sending SMS to {phone}: {e}")
            return False

    def _send_sms_image(self, phone: str, image_path: str, caption: str | None = None) -> bool:
        """Send an image via SMS using the send-sms CLI.

        Returns True on success, False on failure.
        """
        try:
            cmd = [str(HOME / "code/sms-cli/send-sms"), phone]
            if caption:
                cmd.append(caption)
            cmd.extend(["--image", image_path])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                log.error(f"Failed to send image to {phone}: {result.stderr}")
                return False
            return True
        except Exception as e:
            log.error(f"Error sending image to {phone}: {e}")
            return False

    def _send_signal(self, chat_id: str, message: str) -> bool:
        """Send a Signal message via signal-cli.

        Args:
            chat_id: Either a phone number (+1...) or group ID (base64 string)
            message: The message text to send

        Returns True on success, False on failure.
        """
        try:
            # Determine if this is a group or individual chat
            if is_group_chat_id(chat_id):
                # Group message: use --group-id flag
                cmd = [
                    str(SIGNAL_CLI), "-a", signal_account(),
                    "send", "-g", chat_id, "--message-from-stdin"
                ]
            else:
                # Individual message: recipient is positional arg
                # Strip signal: prefix if present
                recipient = chat_id.replace("signal:", "")
                cmd = [
                    str(SIGNAL_CLI), "-a", signal_account(),
                    "send", recipient, "--message-from-stdin"
                ]

            result = subprocess.run(
                cmd,
                input=message,
                capture_output=True,
                text=True,
                timeout=60  # Increased timeout for group messages
            )
            if result.returncode != 0:
                log.error(f"Failed to send Signal to {chat_id}: {result.stderr}")
                return False
            log.info(f"Sent Signal message to {chat_id}")
            return True
        except Exception as e:
            log.error(f"Error sending Signal to {chat_id}: {e}")
            return False

    async def _spawn_healing_session(self, admin_name: str, admin_phone: str, custom_prompt: str | None = None):
        """Spawn a healing Claude session to diagnose and fix system issues.

        Uses asyncio.create_subprocess_exec with claude -p for a one-shot session.
        """
        # Build the healing prompt
        custom_context = custom_prompt if custom_prompt else "None provided"
        session_name = get_session_name(admin_name)

        healing_prompt = f'''EMERGENCY HEALING MODE

CRITICAL FIRST STEP - VERIFY SENDER:
1. Check who sent HEALME:
   ~/.claude/skills/sms-assistant/scripts/read-sms --chat "{admin_phone}" --limit 5

2. Look up their tier:
   ~/.claude/skills/contacts/scripts/contacts lookup "{admin_phone}"

The sender MUST be in the "admin" tier. If NOT admin tier, this is unauthorized:
~/.claude/skills/sms-assistant/scripts/send-sms "{admin_phone}" "[HEALING] ABORTED - unauthorized sender (not admin tier)"
Then STOP immediately.

Only proceed if sender is verified as admin tier.

---

HEALME was triggered from {admin_phone}.

Custom context: {custom_context}

Your job is to diagnose and fix the issue. Follow these steps:

1. FIRST (after verification): Send an SMS to let them know you're on it:
   ~/.claude/skills/sms-assistant/scripts/send-sms "{admin_phone}" "[HEALING] Starting diagnosis..."

2. Take and send a screenshot of the current screen state:
   screencapture -x /tmp/healme-screenshot.png && ~/.claude/skills/sms-assistant/scripts/send-sms "{admin_phone}" /tmp/healme-screenshot.png

3. Check system resources:
   uv run ~/.claude/skills/system-info/scripts/sysinfo.py

4. Check active SDK sessions:
   claude-assistant status

5. Check recent logs for errors:
   tail -100 ~/dispatch/logs/manager.log | grep -iE "(error|fail|exception)"
   tail -50 ~/dispatch/logs/session_lifecycle.log

6. Check recent SMS history with admin:
   ~/.claude/skills/sms-assistant/scripts/read-sms --chat "{admin_phone}" --limit 20

7. Check the admin transcript for context:
   Look at ~/transcripts/{session_name}/ if it exists

8. Send [HEALING] updates as you find issues:
   ~/.claude/skills/sms-assistant/scripts/send-sms "{admin_phone}" "[HEALING] Found: <issue>"

9. Fix what you can:
   - Kill stuck Claude processes: kill <pid>
   - Close stale Chrome tabs: ~/.claude/skills/chrome-control/scripts/chrome close <tab_id>
   - Kill broken sessions: claude-assistant kill-session <name>

10. Restart the daemon:
    claude-assistant restart

11. Restart the admin session:
    claude-assistant restart-session {session_name}

12. Send completion message:
    ~/.claude/skills/sms-assistant/scripts/send-sms "{admin_phone}" "[HEALING] Complete - <summary of what you found and fixed>"

If you CANNOT fix the issue, send:
~/.claude/skills/sms-assistant/scripts/send-sms "{admin_phone}" "[HEALING] FAILED - manual intervention needed: <reason>"

You have 15 minutes. Work efficiently.
'''

        # Write prompt to temp file to avoid shell escaping issues
        prompt_file = Path("/tmp/healing_prompt.txt")
        prompt_file.write_text(healing_prompt)

        try:
            proc = await asyncio.create_subprocess_exec(
                str(CLAUDE), "--dangerously-skip-permissions", "-p", healing_prompt,
                cwd=str(HOME),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            log.info(f"Spawned healing session for {admin_name} (PID: {proc.pid})")
            lifecycle_log.info(f"HEALME | SPAWNED | pid={proc.pid}")

            # Track the healing process so it gets awaited (prevents zombies)
            async def _await_healing(p):
                try:
                    await p.wait()
                    lifecycle_log.info(f"HEALME | COMPLETED | pid={p.pid} returncode={p.returncode}")
                except Exception as e:
                    log.error(f"Healing session error: {e}")
            asyncio.create_task(_await_healing(proc))
        except Exception as e:
            log.error(f"Failed to spawn healing session: {e}")
            # Try to notify admin
            self._send_sms(admin_phone, "[HEALING] FAILED to start healing session - manual intervention needed")

    async def process_message(self, msg: dict):
        """Process a single incoming message."""
        phone = msg["phone"]
        text = msg["text"]
        rowid = msg["rowid"]
        attachments = msg.get("attachments", [])
        is_group = msg.get("is_group", False)
        group_name = msg.get("group_name")
        chat_identifier = msg.get("chat_identifier")
        audio_transcription = msg.get("audio_transcription")
        thread_originator_guid = msg.get("thread_originator_guid")
        source = msg.get("source", "imessage")  # Default to iMessage for backwards compat
        message_timestamp = msg.get("timestamp")  # datetime for Gemini vision context

        # Log message preview
        text_preview = (text[:50] + "...") if text else "(attachment only)"
        attachment_info = f" + {len(attachments)} attachment(s)" if attachments else ""
        group_info = f" [GROUP: {group_name or chat_identifier}]" if is_group else ""
        log.info(f"Processing message {rowid} from {phone}{group_info}: {text_preview}{attachment_info}")

        # Lookup contact (sender) - supports both phone and email identifiers
        contact = self.contacts.lookup_identifier(phone)

        if contact:
            sender_name = contact["name"]
            sender_tier = contact["tier"]
            log.info(f"Sender: {sender_name} (tier: {sender_tier})")
        else:
            sender_name = None
            sender_tier = None

        # HEALME intercept - works even if contacts lookup fails!
        # This is critical because HEALME is needed most when systems are broken.
        # Hardcoded admin phone as emergency fallback.
        from assistant import config
        ADMIN_PHONE = config.require("owner.phone")
        is_admin = (sender_tier == "admin") or (phone == ADMIN_PHONE)

        if text and text.strip().startswith("HEALME") and is_admin:
            admin_name = sender_name or "Admin"
            custom_prompt = text.strip()[6:].strip() or None
            log.info(f"HEALME triggered by {admin_name} ({phone}) with custom prompt: {custom_prompt}")
            lifecycle_log.info(f"HEALME | TRIGGERED | by={admin_name} custom={custom_prompt is not None}")
            await self._spawn_healing_session(admin_name, phone, custom_prompt)
            return

        # MASTER intercept - routes to persistent master session
        if text and text.strip().startswith("MASTER") and is_admin:
            master_prompt = text.strip()[6:].strip()  # Strip "MASTER" prefix
            if master_prompt:
                log.info(f"MASTER command from {phone}: {master_prompt[:50]}...")
                lifecycle_log.info(f"MASTER | TRIGGERED | prompt_len={len(master_prompt)}")
                await self.sessions.inject_master_prompt(phone, master_prompt)
            else:
                log.warning(f"MASTER command with empty prompt, ignoring")
            return

        # RESTART intercept - daemon restarts the session for this chat
        if text and text.strip() == "RESTART" and is_admin:
            # Determine which chat this is (group vs individual)
            target_chat_id = chat_identifier if is_group else phone
            if not target_chat_id:
                log.warning("RESTART: No chat_id available")
                return

            # Look up session from registry
            session_data = self.registry.get(target_chat_id)
            if session_data:
                session_name = session_data.get("session_name")
                if session_name:
                    log.info(f"RESTART command for session: {session_name} (chat_id: {target_chat_id})")
                    lifecycle_log.info(f"RESTART | TRIGGERED | session={session_name} chat_id={target_chat_id}")

                    result_session = await self.sessions.restart_session(target_chat_id)

                    # Send SMS confirmation
                    if result_session:
                        self._send_sms(phone, f"[RESTART] {session_name} restarted")
                    else:
                        self._send_sms(phone, f"[RESTART] Failed to restart {session_name}")
                else:
                    log.warning(f"RESTART: No session_name in registry for {target_chat_id}")
                    self._send_sms(phone, f"[RESTART] No session found for this chat")
            else:
                log.warning(f"RESTART: No registry entry for chat_id {target_chat_id}")
                self._send_sms(phone, f"[RESTART] No session found for this chat")
            return

        # Route based on group vs individual
        if is_group:
            # Group chat - route to group session
            # chat_identifier is the canonical chat_id for groups
            if not chat_identifier:
                log.error(f"Missing chat_identifier for group message from {phone}")
                return

            # Check if a session already exists for this group
            existing_session = self.registry.get(chat_identifier)

            # Allow messages from unknown senders if:
            # 1. Sender is in a blessed tier, OR
            # 2. A session already exists for this group (meaning we've already engaged with it), OR
            # 3. A blessed contact is a participant in this group (handles email identifier case)
            if sender_tier in ("admin", "wife", "family", "favorite"):
                await self.sessions.inject_group_message(
                    chat_id=chat_identifier,
                    display_name=group_name,
                    sender_name=sender_name or phone,  # Fallback to phone/email if name unknown
                    sender_tier=sender_tier,
                    text=text,
                    attachments=attachments,
                    audio_transcription=audio_transcription,
                    thread_originator_guid=thread_originator_guid,
                    source=source,
                    message_timestamp=message_timestamp,
                )
            elif existing_session:
                # Unknown sender but we've already engaged with this group
                log.info(f"Unknown sender {phone} in existing group session, allowing message")
                await self.sessions.inject_group_message(
                    chat_id=chat_identifier,
                    display_name=group_name,
                    sender_name=phone,  # Use the identifier as name (email or phone)
                    sender_tier="unknown",  # Mark as unknown tier for ACL purposes
                    text=text,
                    attachments=attachments,
                    audio_transcription=audio_transcription,
                    thread_originator_guid=thread_originator_guid,
                    source=source,
                    message_timestamp=message_timestamp,
                )
            elif await asyncio.get_event_loop().run_in_executor(
                None, self.messages._group_has_blessed_participant, chat_identifier, self.contacts
            ):
                # Unknown sender BUT a blessed contact is in this group
                log.info(f"Unknown sender {phone} but group has blessed participant, allowing message and creating session")
                await self.sessions.inject_group_message(
                    chat_id=chat_identifier,
                    display_name=group_name,
                    sender_name=phone,
                    sender_tier="unknown",
                    text=text,
                    attachments=attachments,
                    audio_transcription=audio_transcription,
                    thread_originator_guid=thread_originator_guid,
                    source=source,
                    message_timestamp=message_timestamp,
                )
            else:
                # Ignore group messages from non-blessed contacts if no existing session
                log.info(f"Ignoring group message from non-blessed sender {sender_name or phone} (no existing session and no blessed participants)")
        elif not contact:
            # Unknown sender for individual (non-group) message - ignore
            log.info(f"Unknown sender {phone}, ignoring (not in any Claude tier group)")
        elif sender_tier in ("admin", "wife", "family", "favorite"):
            # Blessed individual: route to their SDK session
            # For individuals, phone IS the chat_id
            if not phone:
                log.error(f"Missing phone (chat_id) for individual message")
                return
            await self.sessions.inject_message(
                sender_name or phone, phone, text, sender_tier,
                attachments, audio_transcription, thread_originator_guid,
                source=source,
                message_timestamp=message_timestamp,
            )
        else:
            # Contact exists but has unknown/unrecognized tier
            log.warning(f"Contact {sender_name} has unexpected tier '{sender_tier}', ignoring")

    async def process_reaction(self, reaction: dict):
        """Process a single incoming reaction.

        Reactions are injected into the session with context about what was reacted to.
        Only 👎 reactions require the session to respond; others are silent acknowledgments.
        """
        phone = reaction["phone"]
        emoji = reaction["emoji"]
        rowid = reaction["rowid"]
        is_removal = reaction.get("is_removal", False)
        target_text = reaction.get("target_text")
        target_is_from_me = reaction.get("target_is_from_me", False)
        is_group = reaction.get("is_group", False)
        chat_identifier = reaction.get("chat_identifier")
        source = reaction.get("source", "imessage")

        # Skip reaction removals - they don't need to be surfaced
        if is_removal:
            log.debug(f"Ignoring reaction removal {rowid} from {phone}: {emoji}")
            return

        # Only care about reactions to OUR messages (is_from_me on target)
        if not target_is_from_me:
            log.debug(f"Ignoring reaction {rowid} to someone else's message from {phone}")
            return

        # Lookup contact
        contact = self.contacts.lookup_identifier(phone)
        if not contact:
            log.debug(f"Ignoring reaction {rowid} from unknown contact {phone}")
            return

        sender_name = contact["name"]
        sender_tier = contact["tier"]

        # Only process reactions from blessed tiers
        if sender_tier not in ("admin", "wife", "family", "favorite"):
            log.debug(f"Ignoring reaction {rowid} from {sender_name} (tier: {sender_tier})")
            return

        # Determine chat_id (group vs individual)
        chat_id: str = chat_identifier if is_group and chat_identifier else phone

        # Build the reaction notification
        target_preview = f': "{target_text[:100]}..."' if target_text and len(target_text) > 100 else f': "{target_text}"' if target_text else ""

        # Format reaction for injection
        reaction_text = f"""
---REACTION from {sender_name}---
{emoji} reacted to your message{target_preview}
---END REACTION---
"""

        log.info(f"Processing reaction {rowid} from {sender_name}: {emoji} on message{target_preview[:50]}")

        # Inject into session (if it exists)
        await self.sessions.inject_reaction(
            chat_id=chat_id,
            reaction_text=reaction_text.strip(),
            emoji=emoji,
            sender_name=sender_name,
            sender_tier=sender_tier,
            source=source,
        )

    async def _shutdown(self):
        """Graceful shutdown."""
        # Guard against concurrent shutdown calls (e.g., SIGTERM + SIGINT race)
        if self._shutdown_flag:
            log.info("DAEMON | SHUTDOWN | Already in progress, skipping")
            return
        self._shutdown_flag = True
        log.info("DAEMON | SHUTDOWN | START")
        lifecycle_log.info("DAEMON | SHUTDOWN | START")
        try:
            await self.ipc.stop()
        except (Exception, asyncio.CancelledError) as e:
            log.error(f"Error stopping IPC: {e}")
        try:
            await self.sessions.shutdown()
        except (Exception, asyncio.CancelledError) as e:
            log.error(f"Error during session shutdown: {e}")
        finally:
            # Clear ALL stacked cancellations from SDK client anyio internals
            task = asyncio.current_task()
            if task is not None:
                while task.cancelling() > 0:
                    task.uncancel()
        self._stop_signal()
        self._stop_sven_api()
        log.info("DAEMON | SHUTDOWN | COMPLETE")
        lifecycle_log.info("DAEMON | SHUTDOWN | COMPLETE")

    async def _run_nightly_consolidation(self):
        """Run memory consolidation at 2am:
        1. Person-facts → Contacts.app notes (consolidate_3pass.py)
        2. Chat context → CONTEXT.md per chat (consolidate_chat.py)
        3. Inject summary into admin session for review and texting

        Uses asyncio subprocess to avoid blocking the event loop.
        """
        person_facts_script = HOME / "dispatch/prototypes/memory-consolidation/consolidate_3pass.py"
        chat_context_script = HOME / "dispatch/prototypes/memory-consolidation/consolidate_chat.py"

        # Track outputs for admin summary
        person_facts_output = ""
        person_facts_error = ""
        chat_context_output = ""
        chat_context_error = ""

        # 1. Person-facts consolidation
        log.info("Running nightly person-facts consolidation to Contacts.app...")
        try:
            proc = await asyncio.create_subprocess_exec(
                "uv", "run", str(person_facts_script), "--all",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3600)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                log.error("Person-facts consolidation timed out after 1 hour")
                person_facts_error = "TIMEOUT after 1 hour"
            else:
                person_facts_output = stdout.decode() if stdout else ""
                person_facts_error = stderr.decode() if stderr else ""
                log.info(f"Person-facts consolidation complete: {person_facts_output[-500:] if person_facts_output else 'no output'}")
                if proc.returncode != 0:
                    log.error(f"Person-facts errors: {person_facts_error[-500:] if person_facts_error else 'none'}")
        except Exception as e:
            log.error(f"Person-facts consolidation failed: {e}")
            person_facts_error = str(e)

        # 2. Chat context consolidation
        log.info("Running nightly chat context consolidation to CONTEXT.md...")
        try:
            proc = await asyncio.create_subprocess_exec(
                "uv", "run", str(chat_context_script), "--all",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3600)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                log.error("Chat context consolidation timed out after 1 hour")
                chat_context_error = "TIMEOUT after 1 hour"
            else:
                chat_context_output = stdout.decode() if stdout else ""
                chat_context_error = stderr.decode() if stderr else ""
                log.info(f"Chat context consolidation complete: {chat_context_output[-500:] if chat_context_output else 'no output'}")
                if proc.returncode != 0:
                    log.error(f"Chat context errors: {chat_context_error[-500:] if chat_context_error else 'none'}")
        except Exception as e:
            log.error(f"Chat context consolidation failed: {e}")
            chat_context_error = str(e)

        # 3. Inject summary into admin session
        await self._inject_consolidation_summary(
            person_facts_output, person_facts_error,
            chat_context_output, chat_context_error
        )

    async def _inject_consolidation_summary(
        self,
        person_facts_output: str,
        person_facts_error: str,
        chat_context_output: str,
        chat_context_error: str,
    ):
        """Inject consolidation summary into admin session for review."""
        from assistant import config

        admin_phone = config.require("owner.phone")
        admin_name = config.require("owner.name")

        # Build the summary prompt
        summary_prompt = f"""<admin>
🌙 2am memory consolidation just completed. Here's what happened:

## Person-Facts Consolidation (→ Contacts.app notes)
```
{person_facts_output if person_facts_output else "(no output)"}
```
{f"**Errors:** {person_facts_error}" if person_facts_error else ""}

## Chat Context Consolidation (→ CONTEXT.md per chat)
```
{chat_context_output if chat_context_output else "(no output)"}
```
{f"**Errors:** {chat_context_error}" if chat_context_error else ""}

---

**Your task:**
1. Review the results above
2. Explore anything interesting (read new facts, check CONTEXT.md files)
3. If there were errors, investigate and note what went wrong
4. Send me a summary text with:
   - How many contacts/chats were processed
   - Any notable new facts learned
   - Any errors that need attention

Keep the text concise - this is a nightly check-in, not a full report.
</admin>"""

        try:
            # Inject into admin's foreground session
            await self.sessions.inject_message(
                admin_name, admin_phone, summary_prompt, "admin",
                source="imessage"
            )
            log.info(f"Injected consolidation summary into admin session")
            lifecycle_log.info("CONSOLIDATION | SUMMARY_INJECTED | admin")
        except Exception as e:
            log.error(f"Failed to inject consolidation summary: {e}")

    async def run(self):
        """Main async loop."""
        log.info("=" * 60)
        log.info("Claude Assistant Manager starting (SDK backend)...")
        log.info(f"Polling interval: {POLL_INTERVAL}s")
        log.info(f"Starting from ROWID: {self.last_rowid}")
        log.info("=" * 60)
        lifecycle_log.info(f"DAEMON | START | rowid={self.last_rowid}")

        # Ensure global settings.json symlink is correct
        global_settings_target = HOME / "dispatch" / "config" / "global-settings.json"
        global_settings_link = HOME / ".claude" / "settings.json"
        if global_settings_target.exists():
            if global_settings_link.is_symlink():
                if global_settings_link.resolve() != global_settings_target.resolve():
                    log.info(f"Fixing global settings.json symlink -> {global_settings_target}")
                    global_settings_link.unlink()
                    global_settings_link.symlink_to(global_settings_target)
            elif global_settings_link.exists():
                log.warning(f"Global settings.json is a regular file, replacing with symlink")
                global_settings_link.unlink()
                global_settings_link.symlink_to(global_settings_target)
            else:
                log.info(f"Creating global settings.json symlink -> {global_settings_target}")
                global_settings_link.symlink_to(global_settings_target)

        # Setup signal handlers
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(self._shutdown()))
        loop.add_signal_handler(signal.SIGINT, lambda: asyncio.create_task(self._shutdown()))

        # Start IPC server
        await self.ipc.start()

        # Lazy loading: sessions created on first message (not pre-warmed)
        log.info("Lazy loading enabled - sessions will be created on first message")

        # Recreate sessions that have pending summaries from previous shutdown
        # This preserves context across daemon restarts
        recreated = await self.sessions.recreate_sessions_with_pending_summaries()
        if recreated:
            log.info(f"Recreated {recreated} sessions with pending context from previous shutdown")

        # Start Signal daemon and listener (if not disabled)
        if SIGNAL_ENABLED:
            log.info("Starting Signal integration...")
            self.signal_daemon = self._spawn_signal_daemon()
            if self.signal_daemon:
                self._start_signal_listener()
        else:
            log.info("Signal integration disabled via DISABLE_SIGNAL env var")

        # Start test message watcher
        log.info("Starting test message watcher...")
        self.test_watcher = TestMessageWatcher(self.test_queue)
        self.test_watcher.start()

        # Track last health check time
        last_health_check = time.time()
        HEALTH_CHECK_INTERVAL = 300  # 5 minutes

        # Track fast health check (Tier 1: regex-based fatal error detection)
        last_fast_health = time.time()
        FAST_HEALTH_INTERVAL = 60  # 1 minute

        # Track last idle check time
        last_idle_check = time.time()
        IDLE_CHECK_INTERVAL = 300  # Check for idle sessions every 5 minutes
        IDLE_TIMEOUT_HOURS = 2.0  # Kill sessions idle for more than 2 hours

        # Track last reminder check time
        last_reminder_check = time.time()
        REMINDER_CHECK_INTERVAL = 5  # Check reminders every 5 seconds

        # Track last consolidation run (nightly memory processing)
        # Persist to file so daemon restarts don't cause double-runs
        last_consolidation_date = None
        if CONSOLIDATION_STATE_FILE.exists():
            try:
                date_str = CONSOLIDATION_STATE_FILE.read_text().strip()
                last_consolidation_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except (ValueError, OSError):
                pass  # Invalid file, will run consolidation
        CONSOLIDATION_HOUR = 2  # Run at 2am

        self._shutdown_flag = False
        spurious_cancel_count = 0
        imessage_error_logged = False
        last_poll_log_time = 0  # Telemetry: log poll status every 5 minutes
        POLL_LOG_INTERVAL = 300  # 5 minutes
        while not self._shutdown_flag:
            try:
                # Run blocking SQLite poll in executor
                poll_start = time.time()
                try:
                    messages = await loop.run_in_executor(
                        None, self.messages.get_new_messages, self.last_rowid
                    )
                    poll_duration_ms = (time.time() - poll_start) * 1000
                    # Perf: log poll cycle (sample every 10th to avoid log bloat)
                    perf.timing("poll_cycle_ms", poll_duration_ms, sample_rate=10, component="daemon")
                    if messages:
                        perf.incr("messages_read", count=len(messages), component="daemon", source="imessage")
                    if imessage_error_logged:
                        log.info("iMessage chat.db access restored")
                        imessage_error_logged = False
                    # Telemetry: log poll status periodically or if messages found
                    now = time.time()
                    if messages or (now - last_poll_log_time > POLL_LOG_INTERVAL):
                        log.info(f"POLL_TELEMETRY | rowid={self.last_rowid} | found={len(messages)} | duration={poll_duration_ms:.1f}ms")
                        last_poll_log_time = now
                except Exception as db_err:
                    if "unable to open database" in str(db_err) or "authorization denied" in str(db_err):
                        if not imessage_error_logged:
                            log.error(f"iMessage chat.db unavailable (FDA required): {db_err}")
                            imessage_error_logged = True
                        messages = []
                    else:
                        raise

                for msg in messages:
                    msg["source"] = "imessage"  # Tag source
                    # Log message staleness (time from message creation to discovery)
                    if msg.get("timestamp"):
                        staleness_ms = (time.time() - msg["timestamp"].timestamp()) * 1000
                        perf.timing("message_staleness_ms", staleness_ms, component="daemon", source="imessage")
                        if staleness_ms > 30000:  # Warn if >30s stale
                            log.warning(f"STALENESS | rowid={msg['rowid']} | staleness={staleness_ms:.0f}ms")
                    try:
                        await self.process_message(msg)
                        self._save_state(msg["rowid"])
                    except asyncio.CancelledError:
                        raise  # Don't swallow cancellation
                    except Exception as e:
                        log.error(f"Failed to process message {msg['rowid']}: {e}")
                        # Still advance rowid to avoid infinite retry on bad messages
                        self._save_state(msg["rowid"])

                # Poll for reactions (same rowid sequence as messages)
                reactions = await loop.run_in_executor(
                    None, self.messages.get_new_reactions, self.last_rowid
                )

                for reaction in reactions:
                    reaction["source"] = "imessage"
                    try:
                        await self.process_reaction(reaction)
                        self._save_state(reaction["rowid"])
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        log.error(f"Failed to process reaction {reaction['rowid']}: {e}")
                        self._save_state(reaction["rowid"])

                # Process Signal messages from queue
                signal_count = 0
                while not self.signal_queue.empty():
                    try:
                        signal_msg = self.signal_queue.get_nowait()
                        await self.process_message(signal_msg)
                        signal_count += 1
                    except queue.Empty:
                        break
                if signal_count > 0:
                    perf.incr("messages_read", count=signal_count, component="daemon", source="signal")

                # Process test messages from queue
                while not self.test_queue.empty():
                    try:
                        test_msg = self.test_queue.get_nowait()
                        await self.process_message(test_msg)
                    except queue.Empty:
                        break

                # Check for due reminders
                if time.time() - last_reminder_check > REMINDER_CHECK_INTERVAL:
                    await self.reminders.process_due_reminders()
                    last_reminder_check = time.time()

                # Fast health check (Tier 1: regex-based fatal error detection)
                if time.time() - last_fast_health > FAST_HEALTH_INTERVAL:
                    try:
                        await self.sessions.fast_health_check()
                    except Exception as e:
                        log.error(f"Fast health check failed: {e}")
                    last_fast_health = time.time()

                # Periodic health check (runs in background, non-blocking)
                if time.time() - last_health_check > HEALTH_CHECK_INTERVAL:
                    if not self._health_check_running:
                        self._health_check_running = True
                        asyncio.create_task(
                            self._run_health_checks(),
                            name="health-check-background"
                        )
                    else:
                        log.debug("Health check still running, skipping this cycle")
                    last_health_check = time.time()

                # Periodic idle session check
                if time.time() - last_idle_check > IDLE_CHECK_INTERVAL:
                    try:
                        await self.sessions.check_idle_sessions(IDLE_TIMEOUT_HOURS)
                    except asyncio.CancelledError:
                        # SDK client disconnect can leak CancelledError via anyio
                        # cancel scopes. Clear ALL stacked cancellations.
                        task = asyncio.current_task()
                        if task is not None:
                            while task.cancelling() > 0:
                                task.uncancel()
                        if self._shutdown_flag:
                            raise
                        log.warning("CancelledError during idle check (SDK cancel scope leak), recovered")
                    except Exception as e:
                        log.error(f"Error during idle session check: {e}")
                    last_idle_check = time.time()

                # Nightly memory consolidation at 2am
                now = datetime.now()
                today = now.date()
                if now.hour == CONSOLIDATION_HOUR and last_consolidation_date != today:
                    log.info("Starting nightly memory consolidation...")
                    lifecycle_log.info(f"CONSOLIDATION | START | date={today}")
                    await self._run_nightly_consolidation()
                    last_consolidation_date = today
                    # Persist to file so daemon restarts don't cause double-runs
                    CONSOLIDATION_STATE_FILE.write_text(today.strftime("%Y-%m-%d"))
                    lifecycle_log.info(f"CONSOLIDATION | COMPLETE | date={today}")

                await asyncio.sleep(POLL_INTERVAL)
                spurious_cancel_count = 0  # Reset on successful iteration

            except asyncio.CancelledError:
                if self._shutdown_flag:
                    log.info("CancelledError in main loop, shutting down...")
                    break
                # Clear ALL stacked cancellations from SDK anyio cancel scopes
                task = asyncio.current_task()
                cancel_depth = 0
                if task is not None:
                    while task.cancelling() > 0:
                        task.uncancel()
                        cancel_depth += 1
                spurious_cancel_count += 1
                log.warning(f"Spurious CancelledError in main loop (#{spurious_cancel_count}), "
                            f"cleared {cancel_depth} cancellation(s)")
                if spurious_cancel_count >= 500:
                    log.error("Too many spurious CancelledErrors, shutting down to avoid infinite loop")
                    await self._shutdown()
                    break
                # Small yield to break tight loops if cancel keeps firing
                await asyncio.sleep(0.01)
                continue
            except Exception as e:
                log.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)  # Back off on error


def main():
    # Validate config before anything else
    from assistant import config
    config.load()
    config.require("owner.name")
    config.require("owner.phone")

    # Ensure directories exist
    (ASSISTANT_DIR / "state").mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    manager = Manager()
    asyncio.run(manager.run())


if __name__ == "__main__":
    main()
