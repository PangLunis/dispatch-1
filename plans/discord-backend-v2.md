# Discord Backend Integration Plan (v2 — adapted for Sven/dispatch)

**Goal:** Add Discord as a third messaging backend alongside iMessage and Signal, so Sven can participate in Discord channels and respond to messages.

**Approach:** Discord Bot (not selfbot). Compliant with Discord TOS, stable, easy to set up. Only cosmetic downside is the "BOT" tag next to the username.

**Prior art:** An earlier plan exists at `plans/discord-backend.md` written for Seb's VPS. This v2 adapts it for Sven's `~/dispatch/` architecture which differs in important ways (threaded listeners + queue → bus pipeline, BackendConfig system, macOS Contacts-based tiers).

---

## 0. Prerequisites

### Discord Bot Setup (Developer Portal)

1. Go to https://discord.com/developers/applications
2. Create a new application (e.g., "Sven")
3. **Bot** tab:
   - Copy the **bot token** (save to keychain: `security add-generic-password -s discord_bot_token -a sven -w "TOKEN_HERE"`)
   - Enable **Message Content Intent** under Privileged Gateway Intents (REQUIRED — without this, `message.content` is empty for messages not @mentioning the bot)
   - Disable "Public Bot" (prevents others from adding it to their servers)
4. **OAuth2 > URL Generator**:
   - Scopes: `bot`
   - Permissions: `Send Messages`, `Read Message History`, `View Channels`, `Attach Files`
   - Generate invite URL and have the server owner authorize
5. Note target **channel ID(s)** (Discord Developer Mode → right-click channel → Copy ID)
6. Server owner restricts bot role to only see target channel(s) (platform-level enforcement)

### Existing Assets

- **Keychain entry:** `discord` service with `<discord-account-email>` — this is a Discord *account* password, NOT a bot token. A new bot token needs to be created via Developer Portal and stored as `discord_bot_token`.
- **Old plan:** `plans/discord-backend.md` — reference implementation for Seb's VPS architecture.

---

## 1. Architecture

Discord follows the exact same pattern as Signal: a threaded listener pushes messages to a `queue.Queue`, which the main poll loop drains and produces to the bus. The bus consumer calls `process_message()` which routes to SDK sessions.

```
Discord Gateway (discord.py websocket)
       │
       ▼
DiscordListener (threading.Thread)
  - discord.py client with on_message handler
  - Channel restriction: Discord permissions (primary) + code-level check (defense-in-depth)
  - Pushes normalized messages to discord_queue
       │
       ▼
Main poll loop (manager.py)
  - Drains discord_queue alongside signal_queue and test_queue
  - Produces "message.received" events to bus
       │
       ▼
Bus consumer → process_message()
  - Discord-specific tier resolution (config-based, not Contacts.app)
  - Routes to SDKBackend (platform-agnostic from here)
       │
       ▼
SDK Session (Claude)
  - Calls send-discord CLI to reply
  - Transcript at ~/transcripts/discord/{channel_id}/
```

### Key Design Decisions

1. **Threading, not async.** Signal uses `threading.Thread` + `queue.Queue`. Discord follows the same pattern for consistency, even though discord.py is async internally. The thread runs its own event loop via `asyncio.new_event_loop()` + `run_until_complete()` (NOT `asyncio.run()`, which would fail because it tries to set signal handlers that only work in the main thread).

2. **One channel = one group session.** Each channel ID is a chat_id. All messages in a channel go to a single group-like session. Multiple channels = multiple sessions.

3. **Config-based tier lookup.** Discord users don't have phone numbers, so Contacts.app lookup returns None. Instead, `config.local.yaml` maps Discord user IDs → name + tier. Unmapped users default to "unknown" tier (ignored) — explicit opt-in required.

6. **Sonnet model for Discord sessions.** Discord channels are higher-volume than SMS/Signal, so Discord sessions use Sonnet by default (not Opus) to manage costs. This is configured via the BackendConfig or session creation logic — Discord source triggers Sonnet model selection.

4. **Bot ignores its own messages** (standard discord.py `on_message` filtering).

5. **Multi-channel support.** Supports a list of channel IDs. Each gets its own session. Channel restriction is enforced at Discord level + code level.

6. **Guarded import.** discord.py is imported inside `_run_with_registry()` behind a try/except, so a missing dependency doesn't crash the daemon — just logs a warning and skips Discord.

### normalize_chat_id / is_group_chat_id Behavior

Discord channel IDs are 18-19 digit numeric strings (e.g., `"1234567890123456789"`). After stripping the `discord:` prefix:
- **`normalize_chat_id()`:** Falls through hex UUID check (too short at <20 chars) and phone normalization (too long at >11 digits). Returns the original `discord:{id}` unchanged. ✓
- **`is_group_chat_id()`:** Returns False (doesn't match hex/base64 patterns, doesn't start with `+`). However this is OK because: (a) the message dict always sets `is_group: True`, and (b) the registry stores `type: "group"`, so downstream code uses those rather than the heuristic.
- **`sanitize_chat_id()`:** Already iterates over `BACKENDS.values()` to strip prefixes, so adding `"discord"` to BACKENDS handles this automatically. ✓

---

## 2. Files to Create

### 2.1 `~/.claude/skills/discord/SKILL.md`

```yaml
---
name: discord
description: Send and receive Discord messages via bot. Use for Discord channel communication. Trigger words - discord, send discord.
---

# Discord Skill

Send and receive messages in Discord channels via a bot integration.

## Usage

### Send a message
```bash
~/.claude/skills/discord/scripts/send-discord <channel_id> "message"
```

### Reply from a Discord transcript directory
```bash
# From ~/transcripts/discord/{channel_id}/
~/.claude/skills/sms-assistant/scripts/reply "message"
```

## How It Works

- Bot connects to Discord Gateway via discord.py (runs in a daemon thread)
- Incoming messages are normalized and routed through the bus pipeline (same as iMessage/Signal)
- Outgoing messages use the Discord REST API (httpx POST, no Gateway needed)
- Each channel gets its own SDK session at `~/transcripts/discord/{channel_id}/`
- Messages are auto-chunked at 2000 characters (Discord's limit)

## Configuration

Discord config lives in `~/dispatch/config.local.yaml`:

```yaml
discord:
  channel_ids:
    - "1234567890"
  users:
    "DISCORD_USER_ID":
      name: "Name"
      tier: "admin"
```

Bot token stored in macOS Keychain as `discord_bot_token`.

## Token

Stored in keychain:
```bash
# Store
security add-generic-password -s discord_bot_token -a sven -w "TOKEN"

# Read
security find-generic-password -s discord_bot_token -w
```
```

### 2.2 `~/.claude/skills/discord/scripts/send-discord`

Standalone Python script (uv shebang) that posts a message to a Discord channel via REST API. Uses `httpx` for a simple HTTP POST — intentionally separate from the discord.py gateway client. This is the out-of-process send path used by the reply CLI and Claude sessions.

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
"""
send-discord - Send a message to a Discord channel

Usage:
    send-discord <channel_id> <message>
"""
import sys
import os
import subprocess
import httpx

DISCORD_API = "https://discord.com/api/v10"

def get_token() -> str:
    """Get Discord bot token from keychain (primary), then env var, then secrets file."""
    # Try keychain first (macOS-idiomatic secure storage)
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "discord_bot_token", "-w"],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    # Try env var
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if token:
        return token

    # Try secrets file
    secrets_path = os.path.expanduser("~/.claude/secrets.env")
    if os.path.exists(secrets_path):
        for line in open(secrets_path):
            if line.startswith("DISCORD_BOT_TOKEN="):
                return line.strip().split("=", 1)[1].strip('"').strip("'")

    print("Error: DISCORD_BOT_TOKEN not found in keychain, env, or secrets", file=sys.stderr)
    sys.exit(1)

def split_message(message: str, limit: int = 2000) -> list[str]:
    """Split message into chunks respecting Discord's 2000 char limit."""
    chunks = []
    while message:
        if len(message) <= limit:
            chunks.append(message)
            break
        split_at = message.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = message.rfind(" ", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(message[:split_at])
        message = message[split_at:].lstrip()
    return chunks

def main():
    if len(sys.argv) < 3:
        print("Usage: send-discord <channel_id> <message>", file=sys.stderr)
        sys.exit(1)

    channel_id = sys.argv[1]
    message = sys.argv[2]
    message = message.replace("\\!", "!")  # Same pattern as send-signal

    token = get_token()
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }

    for chunk in split_message(message):
        resp = httpx.post(
            f"{DISCORD_API}/channels/{channel_id}/messages",
            headers=headers,
            json={"content": chunk},
        )
        if resp.status_code == 429:
            import time
            retry_after = resp.json().get("retry_after", 1)
            time.sleep(retry_after)
            resp = httpx.post(
                f"{DISCORD_API}/channels/{channel_id}/messages",
                headers=headers,
                json={"content": chunk},
            )
        if resp.status_code not in (200, 201):
            print(f"Error: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(1)

    print("OK")

if __name__ == "__main__":
    main()
```

### 2.3 `~/dispatch/assistant/discord_listener.py`

New listener module following the `SignalListener` pattern (threading.Thread + queue.Queue).

```python
"""
Discord listener — threading.Thread that runs discord.py in its own event loop.

Follows the same pattern as SignalListener:
  - Runs in a daemon thread
  - Pushes normalized messages to a queue.Queue
  - Main poll loop drains the queue and produces to bus

Key threading note: discord.py is async-native. We run it in a dedicated thread
with its own asyncio event loop (asyncio.new_event_loop + run_until_complete),
not asyncio.run() which tries to set signal handlers (main thread only).
Only primitive data (dicts) cross the thread boundary via queue — never discord.py
objects, which are not thread-safe.
"""

import asyncio
import logging
import queue
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Guard import — discord.py may not be installed
try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False


class DiscordListener:
    """Listens to Discord messages and queues them for processing.

    Follows Sven's listener interface:
      - Runs as a daemon thread (call .start())
      - Pushes messages to a queue.Queue
      - Main poll loop drains queue → produces to bus
    """

    def __init__(self, message_queue: queue.Queue, channel_ids: list[str], bot_token: str):
        if not DISCORD_AVAILABLE:
            raise ImportError("discord.py is not installed. Run: uv add 'discord.py>=2.3.0'")

        import threading
        self._thread = threading.Thread(target=self._run, daemon=True, name="DiscordListener")
        self.message_queue = message_queue
        self.channel_ids = set(int(c) for c in channel_ids)
        self.bot_token = bot_token
        self.running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: discord.Client | None = None

    def start(self):
        """Start the listener thread."""
        self._thread.start()

    def is_alive(self) -> bool:
        """Check if the listener thread is alive."""
        return self._thread.is_alive()

    def _run(self):
        """Start discord.py client in a new event loop (runs in thread)."""
        self.running = True
        while self.running:
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._loop.run_until_complete(self._connect())
            except Exception as e:
                log.error(f"DiscordListener error: {e}")
            finally:
                if self._loop and not self._loop.is_closed():
                    self._loop.close()
                self._loop = None
                self._client = None

            if self.running:
                log.info("[discord] Reconnecting in 5s...")
                time.sleep(5)  # Backoff before reconnect

    async def _connect(self):
        """Connect to Discord Gateway and listen for messages."""
        intents = discord.Intents.default()
        intents.message_content = True  # Privileged intent — required for message.content

        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready():
            log.info(f"DiscordListener connected as {client.user} (channels: {self.channel_ids})")

        @client.event
        async def on_message(message):
            # Ignore own messages
            if message.author == client.user:
                return

            # Ignore DMs — bot only responds in guild channels
            if not message.guild:
                return

            # Defense-in-depth channel filter (Discord permissions are primary gate)
            if message.channel.id not in self.channel_ids:
                return

            text = message.content
            if not text:
                if message.attachments:
                    text = "(attachment)"
                else:
                    return

            sender_id = str(message.author.id)
            sender_name = message.author.display_name or message.author.name
            channel_id = str(message.channel.id)

            # Normalize to match SignalListener message format exactly
            # NOTE: No "date" field — SignalListener doesn't have it either.
            # Only "timestamp" (datetime) is used by process_message().
            msg = {
                "rowid": message.id,  # Discord message snowflake as unique ID
                "phone": sender_id,  # Discord user ID as "phone" field
                "is_from_me": 0,
                "text": text,
                "is_group": True,  # Discord channels are always group-like
                "is_audio_message": False,  # Discord doesn't have audio messages
                "group_name": message.channel.name,
                "chat_identifier": channel_id,
                "attachments": [
                    {
                        "mime_type": a.content_type or "application/octet-stream",
                        "transfer_name": a.filename,
                        "total_bytes": a.size,
                        "file_path": a.url,  # Discord CDN URL
                    }
                    for a in message.attachments
                ],
                "audio_transcription": None,
                "thread_originator_guid": None,
                "source": "discord",
                "sender_name": sender_name,  # Display name for group message wrapping
                "timestamp": message.created_at.astimezone(timezone.utc),  # datetime for Gemini vision context
            }

            log.info(f"DiscordListener: queued message from {sender_name} ({sender_id}) in #{message.channel.name}: {text[:80]}...")
            self.message_queue.put(msg)

        @client.event
        async def on_disconnect():
            log.warning("[discord] Disconnected from Gateway — discord.py will auto-reconnect")

        @client.event
        async def on_resumed():
            log.info("[discord] Resumed Gateway connection")

        try:
            await client.start(self.bot_token)
        except Exception as e:
            log.error(f"[discord] Fatal connection error: {e}")
            raise
        finally:
            if not client.is_closed():
                await client.close()
            self._client = None

    def stop(self):
        """Gracefully stop the listener.

        1. Close the Discord client (async, via threadsafe call)
        2. Stop the event loop
        3. The _run() while loop exits because self.running is False
        """
        self.running = False
        # Gracefully close the Discord client before stopping the loop
        if self._client and self._loop and self._loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
                future.result(timeout=5)  # Wait for graceful close
            except Exception as e:
                log.warning(f"[discord] Error during graceful close: {e}")
            # Loop should exit naturally after client.close()
        elif self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    @property
    def is_ready(self) -> bool:
        """Check if the Discord client is connected and ready."""
        return self._client is not None and self._client.is_ready()

    @property
    def latency(self) -> float | None:
        """Get the Discord Gateway latency in seconds, or None if not connected."""
        if self._client and self._client.is_ready():
            return self._client.latency
        return None
```

---

## 3. Files to Modify

### 3.1 `assistant/backends.py` — Add Discord backend config

Add to `BACKENDS` dict:

```python
"discord": BackendConfig(
    name="discord",
    label="DISCORD",
    session_suffix="-discord",
    registry_prefix="discord:",
    send_cmd='~/.claude/skills/discord/scripts/send-discord "{chat_id}"',
    send_group_cmd='~/.claude/skills/discord/scripts/send-discord "{chat_id}"',
    history_cmd="",  # No history CLI yet (could add later via Discord REST API)
    supports_image_context=False,  # Discord CDN URLs, not local files
),
```

### 3.2 `assistant/manager.py` — Wire up Discord listener + drain queue + tier lookup

**7 changes needed, each shown with exact placement:**

#### Change 1: Initialize discord_queue and discord_listener in `__init__` (alongside signal)

```python
# After line 1560 (self.test_watcher = None):
# Discord integration
self.discord_queue = queue.Queue()
self.discord_listener = None
```

#### Change 2: Discord tier resolution in `process_message()`

Insert after the contact lookup block (after line ~2983 where `sender_tier = None`):

```python
# Discord users don't have phone numbers — use config-based tier lookup
if not contact and source == "discord":
    from assistant import config as app_config
    discord_users = app_config.get("discord.users", {})
    discord_user = discord_users.get(phone)  # phone = discord user ID
    if discord_user:
        sender_name = discord_user.get("name", phone)
        sender_tier = discord_user.get("tier", "unknown")
        contact = {"name": sender_name, "tier": sender_tier}
        log.info(f"Discord user resolved: {sender_name} (tier: {sender_tier})")
    else:
        # Unmapped Discord users are ignored (unknown tier) — explicit opt-in required
        # Use display name from message for logging
        sender_name = msg.get("sender_name", phone)
        sender_tier = "unknown"
        log.info(f"[discord] Unmapped user: {sender_name} ({phone}) — ignoring (add to discord.users config for access)")
```

#### Change 3: Add `_start_discord_listener()` method + call in `_run_with_registry()`

Add a helper method (mirrors `_start_signal_listener()` pattern — deduplicates startup logic between init and health check):

```python
def _start_discord_listener(self):
    """Start the Discord listener thread."""
    if self.discord_listener is not None and self.discord_listener.is_alive():
        log.debug("Discord listener already running")
        return

    from assistant import config as app_config
    discord_channels = app_config.get("discord.channel_ids", [])
    if not discord_channels:
        log.info("Discord not configured — skipping (set discord.channel_ids in config)")
        return

    # Token resolution: keychain first (matches send-discord CLI), then config
    discord_token = None
    import subprocess
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "discord_bot_token", "-w"],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            discord_token = result.stdout.strip()
    except Exception:
        pass

    if not discord_token:
        discord_token = app_config.get("discord.bot_token")

    if not discord_token:
        log.warning("Discord token not found in keychain or config — skipping")
        return

    try:
        from assistant.discord_listener import DiscordListener
        self.discord_listener = DiscordListener(self.discord_queue, discord_channels, discord_token)
        self.discord_listener.start()
        log.info(f"Started Discord listener for channels: {discord_channels}")
        lifecycle_log.info(f"DISCORD_LISTENER | STARTED | channels={discord_channels}")
    except ImportError as e:
        log.warning(f"Discord not available (discord.py not installed): {e}")
    except Exception as e:
        log.error(f"Failed to start Discord listener: {e}")
```

Call in `_run_with_registry()` (after Signal startup):

```python
# Start Discord listener (if configured)
self._start_discord_listener()
```

#### Change 4: Drain discord_queue in poll loop (after test queue drain block)

```python
# Process Discord messages from queue → produce to bus
discord_count = 0
while not self.discord_queue.empty():
    try:
        discord_msg = self.discord_queue.get_nowait()
        disc_source = discord_msg.get("source", "discord")
        disc_raw_key = discord_msg.get("chat_identifier") or discord_msg.get("phone")
        produce_event(self._producer, "messages", "message.received",
            sanitize_msg_for_bus(discord_msg),
            key=f"{disc_source}/{disc_raw_key}", source=disc_source)
        discord_count += 1
    except queue.Empty:
        break
if discord_count:
    self._consumer_notify.set()
    perf.incr("messages_read", count=discord_count, component="daemon", source="discord")
```

#### Change 5: Stop Discord listener in `_shutdown()` (after Signal listener stop)

```python
# Stop Discord listener
if self.discord_listener:
    self.discord_listener.stop()
    self.discord_listener = None
```

#### Change 6: Health check Discord listener in `_run_health_checks()`

Add alongside Signal health checks (uses `_start_discord_listener()` helper — no duplication):

```python
# Check Discord listener health
if self.discord_listener is not None:
    if not self.discord_listener.is_alive():
        log.warning("Discord listener died, restarting...")
        lifecycle_log.info("DISCORD_LISTENER | DIED | restarting")
        produce_event(self._producer, "system", "health.service_restarted",
            service_restarted_payload("discord_listener", "died"), source="health")
        self._start_discord_listener()
```

#### Change 7: Add Discord status to `claude-assistant status` output

Add Discord listener state (connected/disconnected, latency) to the status display.

### 3.3 `assistant/common.py` — No changes needed

The existing functions already handle Discord correctly:
- **`sanitize_chat_id()`:** Iterates `BACKENDS.values()` to strip prefixes — adding `"discord"` to BACKENDS handles this automatically.
- **`normalize_chat_id()`:** Discord channel IDs (18-19 digit numeric strings) fall through to `return chat_id` unchanged. ✓
- **`is_group_chat_id()`:** Returns False for Discord IDs (doesn't match patterns), but this is OK — `process_message()` uses `msg["is_group"]` directly, and the registry stores `type: "group"`. The heuristic is only a fallback in the reply CLI, which checks registry `entry_type` first.

### 3.4 `~/.claude/skills/sms-assistant/scripts/reply` — Add Discord routing

Three changes:

```python
# 1. Add at top (after SEND_SIGNAL_GROUP):
SEND_DISCORD = Path.home() / ".claude/skills/discord/scripts/send-discord"

# 2. Add "discord:" to BOTH prefix lists in is_group_chat_id() and strip_registry_prefix():
for prefix in ["signal:", "test:", "discord:"]:

# 3. Add Discord case after the Signal block (before the else/iMessage fallback):
elif backend == "discord":
    cmd = [str(SEND_DISCORD), bare_chat_id]
    if args.message:
        cmd.append(args.message)
```

### 3.5 `config.local.yaml` — Add Discord section

```yaml
discord:
  bot_token: "BOT_TOKEN_HERE"  # Prefer keychain: security add-generic-password -s discord_bot_token -a sven -w "TOKEN"
  channel_ids:
    - "1234567890"  # Target channel snowflake ID(s)
  users:
    "ADMIN_DISCORD_USER_ID":
      name: "Admin"
      tier: "admin"
    # Unmapped users are IGNORED (unknown tier)
    # Add users explicitly to grant access
```

### 3.6 `pyproject.toml` — Add discord.py dependency

```toml
# Add to dependencies:
"discord.py>=2.3.0"
```

---

## 4. Message Flow

### Incoming (Discord → Claude)

```
1. User posts in Discord channel
2. discord.py on_message fires in DiscordListener thread (own event loop)
3. Bot self-check — ignore own messages
4. DM filter — ignore non-guild messages
5. Channel filter: Discord permissions (primary) + code-level check (backup)
6. Message normalized to standard format with ALL required fields:
   - rowid (snowflake), phone (user ID), text, is_group (True),
   - is_audio_message (False), group_name, chat_identifier (channel ID),
   - attachments, source ("discord"), sender_name, timestamp (datetime)
7. Dict pushed to discord_queue (thread-safe, only primitives cross boundary)
8. Main poll loop drains discord_queue → produce_event("message.received") to bus
9. Bus consumer calls process_message()
10. process_message() does Discord-specific tier lookup (config.yaml, not Contacts.app)
    - Mapped users get their configured tier
    - Unmapped users get "unknown" (ignored) — explicit opt-in required
11. Routes to SDKBackend.inject_group_message() (platform-agnostic from here)
12. Session created on-demand at ~/transcripts/discord/{channel_id}/
13. Message wrapped with sender_name so Claude knows who said what
14. Claude processes and calls send-discord CLI to reply
```

### Outgoing (Claude → Discord)

```
1. Claude decides to reply
2. Calls: ~/.claude/skills/discord/scripts/send-discord "{channel_id}" "response"
3. send-discord reads bot token from keychain (no Gateway connection needed)
4. HTTP POST to Discord REST API via httpx
5. Auto-chunks at 2000 chars (Discord's limit)
6. Handles 429 rate limiting (retry after backoff)
7. Message appears in channel
```

---

## 5. Security

### Token Storage

- **Primary:** macOS Keychain as `discord_bot_token` service (read via `security find-generic-password`)
- **Fallback:** `DISCORD_BOT_TOKEN` env var
- **Last resort:** `config.local.yaml` (gitignored)
- Bot token is NOT stored in config.local.yaml by default — keychain only

### Bot Permissions (Least Privilege)

Request only: `Send Messages`, `Read Message History`, `View Channels`, `Attach Files`

Do NOT request: `Administrator`, `Manage Messages`, `Mention Everyone`, any moderation perms.

### Channel Restriction (Defense in Depth)

1. **Discord server permissions (primary):** Bot role restricted to target channel(s) — bot literally cannot see other channels
2. **Code-level filter (backup):** `message.channel.id not in self.channel_ids` — defense-in-depth if Discord permissions are misconfigured

### User Access Control

- **Mapped users:** Get their configured tier from `discord.users` in config
- **Unmapped users:** Default to "unknown" (ignored) — NOT "favorite"
- This prevents random Discord users in a channel from triggering Claude sessions
- To grant access, explicitly add their Discord user ID to config

### DM Protection

Bot ignores all DMs (`if not message.guild: return`) — prevents private backdoor usage.

---

## 6. Implementation Order

1. Create Discord bot in Developer Portal, get bot token, store in keychain
2. Have server owner invite bot and restrict to target channel(s)
3. `uv add "discord.py>=2.3.0"` — add dependency
4. Create `~/.claude/skills/discord/SKILL.md` — skill documentation
5. Create `send-discord` CLI — test independently with `send-discord CHANNEL_ID "hello"`
6. Create `discord_listener.py` — the threaded listener with guarded import
7. Add `"discord"` entry to `backends.py`
8. Add Discord config to `config.local.yaml` (token, channels, users)
9. Wire listener in `manager.py` — all 7 changes:
   a. `__init__`: discord_queue + discord_listener
   b. `process_message()`: tier resolution
   c. `_run_with_registry()`: start listener (guarded import)
   d. Poll loop: drain discord_queue
   e. `_shutdown()`: stop listener
   f. `_run_health_checks()`: restart dead listener
   g. Status output
10. Update `reply` CLI for discord routing
11. **Test sequence:**
    a. `send-discord CHANNEL_ID "hello"` — verify send CLI works standalone
    b. Post in Discord channel → check daemon logs for DiscordListener messages
    c. Verify Claude responds in channel
    d. Post from unmapped user → verify ignored
    e. `cd ~/transcripts/discord/CHANNEL_ID && reply "test"` — verify reply CLI
    f. Kill Discord listener thread → verify health check restarts it

---

## 7. Summary of All Changes

| File | Action | Description |
|------|--------|-------------|
| `~/.claude/skills/discord/SKILL.md` | Create | Full skill documentation with usage examples |
| `~/.claude/skills/discord/scripts/send-discord` | Create | Send CLI (REST API via httpx, keychain token) |
| `~/dispatch/assistant/discord_listener.py` | Create | Threaded listener with guarded import, graceful shutdown, health properties |
| `~/dispatch/assistant/backends.py` | Modify | Add `"discord"` BackendConfig entry |
| `~/dispatch/assistant/manager.py` | Modify | 7 changes: init, tier lookup, startup, drain, shutdown, health, status |
| `~/.claude/skills/sms-assistant/scripts/reply` | Modify | Add Discord routing + prefix handling |
| `~/dispatch/config.local.yaml` | Modify | Add discord section (token ref, channels, users) |
| `~/dispatch/pyproject.toml` | Modify | Add `discord.py>=2.3.0` dependency |

**Minor supporting changes:**
| `~/dispatch/assistant/bus_helpers.py` | Modify | Add `"sender_name"` to `DIRECT_FIELDS` in `sanitize_msg_for_bus` (line 323) |
| `~/dispatch/assistant/sdk_backend.py` | Modify | Pass `model="sonnet"` for Discord sessions (source == "discord") in `create_session()` |

**NOT modified (no changes needed):**
| `~/dispatch/assistant/common.py` | No change | Existing functions handle Discord automatically via BACKENDS iteration |

---

## 8. Open Questions

1. **Which Discord server/channel(s)?** Admin needs to specify the target server and channel(s).
2. **Bot name?** "Sven" is the natural choice but needs to be available on the server.
3. **User mapping:** Need admin's Discord user ID for admin tier mapping. Other participants can be added later.
4. **read-discord CLI:** Not included in v1 — could add later using Discord REST API (`GET /channels/{id}/messages`) for message history. Sessions that restart won't have Discord history context until this is implemented.
