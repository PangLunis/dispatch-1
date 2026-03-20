# Discord Backend Integration Plan

**Goal:** Add Discord as a new messaging backend so Seb can participate in a single channel in Sam's Discord server, responding to messages from anyone in that channel.

**Approach:** Discord Bot (not selfbot). Compliant with Discord TOS, stable, easy to set up. Only cosmetic downside is the "BOT" tag next to the username.

---

## 1. Discord Bot Setup (Developer Portal)

1. Go to https://discord.com/developers/applications
2. Click "New Application", name it (e.g., "Seb")
3. Go to **Bot** tab:
   - Click "Add Bot"
   - Copy the **bot token** (save immediately — shown only once)
   - Enable **Message Content Intent** under Privileged Gateway Intents
   - Disable "Public Bot" (prevents others from adding it to their servers)
4. Go to **OAuth2 > URL Generator**:
   - Scopes: `bot`
   - Bot Permissions: `Send Messages`, `Read Message History`, `View Channels`, `Attach Files`
   - Copy the generated URL and send it to Sam to authorize the bot in his server
5. After Sam authorizes, note the **channel ID** for the target channel:
   - In Discord, enable Developer Mode (User Settings > Advanced)
   - Right-click the channel > Copy Channel ID
6. **Channel restriction via Discord settings:** Sam restricts the bot role to only have visibility of the target channel in Discord's server settings (channel permissions). This provides platform-level enforcement — the bot literally cannot see other channels.

---

## 2. Architecture

Discord plugs into Seb's existing dispatch system as a new backend, following the same async pattern as the Signal listener.

**Seb's stack:** Fully async Python 3.12+ with asyncio. Each listener implements `async run()` and `async send_to_chat(chat_id, text)`. The manager wires listeners via a unified callback: `manager.on_message(platform, sender_id, chat_id, text)`.

```
Discord Bot (discord.py)
       │
       ▼
DiscordListener (async task)
  - discord.py client with on_message handler
  - Channel restriction handled by Discord server permissions
  - Calls manager.on_message("discord", sender_id, channel_id, text)
       │
       ▼
Manager.on_message()
  - Contact/tier lookup
  - Routes to SDKBackend (platform-agnostic)
  - Creates/injects into SDK session
       │
       ▼
SDK Session (Claude)
  - Calls send-discord CLI via Bash tool to reply
  - Transcript stored at ~/transcripts/discord/{channel_id}/
```

**Key files on Seb's VPS:**
- `/root/seb/seb/listeners/signal.py` — Listener pattern to follow
- `/root/seb/seb/manager.py` — Routing, tier lookup, filtering
- `/root/seb/seb/main.py` — Wiring listeners + backend (asyncio.create_task)
- `/root/seb/seb/config.py` — Tier config (extend for Discord)
- `/root/seb/seb/sdk_backend.py` — Session pool (platform-agnostic)

### Key Design Decisions

- **One channel = one session.** The channel ID is the `chat_id`. All messages in the channel go to a single group-like session, regardless of which Discord user sent them.
- **No separate daemon process.** The discord.py client runs as an asyncio task inside the existing manager process, just like the Signal WebSocket listener.
- **Async-native.** Follows Seb's pattern: `async run()` for the listener loop, `async send_to_chat()` for outbound messages. No threading or sync queues needed — discord.py is already async.
- **Discord user display names** are passed as `sender_name` so the Claude session sees who said what.
- **Bot ignores its own messages** (standard discord.py behavior with `on_message` filtering).
- **Channel restriction at platform level.** Discord server permissions limit the bot to one channel — no code-level filtering needed (but included as defense-in-depth).

---

## 3. Implementation

### 3.1 New Files to Create

#### `~/.claude/skills/discord/SKILL.md`

```yaml
---
name: discord
description: Send and receive Discord messages. Use for Discord channel communication.
---
```

Standard skill documentation with usage examples for send-discord.

#### `~/.claude/skills/discord/scripts/send-discord`

Standalone Python script (uv shebang) that posts a message to a Discord channel via the REST API. Uses `httpx` for a simple HTTP POST — intentionally separate from the discord.py gateway client. This is the **out-of-process send path** used by the reply CLI and Claude sessions (which shell out to send-discord). The in-process `send_to_chat()` on the listener uses discord.py's channel.send() when available, but the CLI is needed as a standalone fallback that works without a running gateway connection.

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
import httpx

DISCORD_API = "https://discord.com/api/v10"

def main():
    if len(sys.argv) < 3:
        print("Usage: send-discord <channel_id> <message>", file=sys.stderr)
        sys.exit(1)

    channel_id = sys.argv[1]
    message = sys.argv[2]

    # Strip backslash-escaped exclamation marks (same pattern as send-signal)
    message = message.replace("\\!", "!")

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        # Fall back to secrets file
        secrets_path = os.path.expanduser("~/.claude/secrets.env")
        if os.path.exists(secrets_path):
            for line in open(secrets_path):
                if line.startswith("DISCORD_BOT_TOKEN="):
                    token = line.strip().split("=", 1)[1].strip('"').strip("'")
                    break

    if not token:
        print("Error: DISCORD_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    # Discord has a 2000 character limit per message
    # Split long messages into chunks
    chunks = []
    while message:
        if len(message) <= 2000:
            chunks.append(message)
            break
        # Find a good split point (newline or space)
        split_at = message.rfind("\n", 0, 2000)
        if split_at == -1:
            split_at = message.rfind(" ", 0, 2000)
        if split_at == -1:
            split_at = 2000
        chunks.append(message[:split_at])
        message = message[split_at:].lstrip()

    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }

    for chunk in chunks:
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


#### `/root/seb/seb/listeners/discord.py`

New listener module following the same async pattern as `signal.py`. No threading — runs as an asyncio task in the main event loop.

```python
"""
Discord listener — async, follows the same pattern as signal.py.

Implements:
  - async run()            — main loop, connects to Discord Gateway
  - async send_to_chat()   — send message to Discord channel via REST API
"""

import logging
import os
import discord

log = logging.getLogger(__name__)

class DiscordListener:
    """Listens to Discord messages and routes them to the manager.

    Follows Seb's listener interface:
      - async run() to start listening
      - Calls manager.on_message("discord", sender_id, chat_id, text)
    """

    def __init__(self, manager, channel_id: str, bot_token: str):
        self.manager = manager
        self.channel_id = int(channel_id)
        self.bot_token = bot_token
        self._client = None

    async def run(self):
        """Start the discord.py client (runs indefinitely)."""
        intents = discord.Intents.default()
        intents.message_content = True  # Privileged intent

        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready():
            log.info(f"Discord connected as {client.user} (channel: {self.channel_id})")

        @client.event
        async def on_message(message):
            # Ignore own messages
            if message.author == client.user:
                return

            # Ignore DMs — bot only responds in guild channels
            if not message.guild:
                return

            # Defense-in-depth channel filter (Discord permissions are primary gate)
            if message.channel.id != self.channel_id:
                return

            text = message.content
            if not text:
                # Handle attachment-only messages
                if message.attachments:
                    text = "(attachment)"
                else:
                    return

            sender_id = str(message.author.id)
            sender_name = message.author.display_name or message.author.name
            chat_id = str(self.channel_id)

            log.info(f"Discord: {sender_name}: {text[:80]}")

            # Call the unified manager callback
            await self.manager.on_message(
                platform="discord",
                sender_id=sender_id,
                chat_id=chat_id,
                text=text,
                sender_name=sender_name,
                attachments=[
                    {"url": a.url, "filename": a.filename,
                     "mime_type": a.content_type, "size": a.size}
                    for a in message.attachments
                ],
            )

        # discord.py 2.x handles reconnection internally with exponential backoff.
        # Just call client.start() once — it reconnects automatically on disconnect.
        # Hook on_disconnect/on_resumed for observability.
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

    async def send_to_chat(self, chat_id: str, text: str):
        """Send a message to a Discord channel via the discord.py HTTP client.

        Uses the bot's own HTTP session (same auth, same rate limiter) rather than
        a separate httpx client — single communication path for all Discord I/O.
        """
        channel = self._client.get_channel(int(chat_id))
        if not channel:
            channel = await self._client.fetch_channel(int(chat_id))

        # Discord 2000 char limit — split long messages
        chunks = _split_message(text, 2000)
        for chunk in chunks:
            await channel.send(chunk)
            # discord.py handles rate limiting internally (429 backoff built in)

    async def stop(self):
        """Gracefully disconnect."""
        if self._client:
            await self._client.close()


def _split_message(text: str, limit: int = 2000) -> list[str]:
    """Split a message into chunks that fit Discord's character limit."""
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = text.rfind(" ", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    return chunks
```

### 3.2 Files to Modify

#### `/root/seb/seb/config.py` — Add Discord config and tier lookup

```python
# Add Discord section to config schema
discord:
  bot_token: "..."
  channel_id: "1234567890"
  users:
    "sam_discord_user_id": { name: "Sam", tier: "admin" }

# Add tier lookup function
def tier_for_discord(user_id: str) -> tuple[str, str]:
    """Return (name, tier) for a Discord user ID."""
    discord_users = config.get("discord.users", {})
    user_config = discord_users.get(user_id)
    if user_config:
        return user_config["name"], user_config["tier"]
    return None, "favorite"  # Default: restricted tools, no proactive actions
```

#### `/root/seb/seb/main.py` — Wire up Discord listener

Following Seb's async wiring pattern in main.py:

```python
# In the task creation section, alongside the Signal listener:
from seb.listeners.discord import DiscordListener

discord_channel_id = config.get("discord.channel_id")
discord_bot_token = config.get("discord.bot_token") or os.environ.get("DISCORD_BOT_TOKEN")

if discord_channel_id and discord_bot_token:
    discord_listener = DiscordListener(manager, discord_channel_id, discord_bot_token)
    asyncio.create_task(discord_listener.run())
    log.info(f"Discord listener started for channel {discord_channel_id}")
    # Register for cleanup so client.close() is called on daemon shutdown
    resource_registry.register('discord_listener', discord_listener, discord_listener.stop)
else:
    log.info("Discord not configured — skipping")
```

That's it. No queues, no polling, no threading. The listener calls `manager.on_message()` directly (async callback), which routes through the same platform-agnostic pipeline as Signal.

#### `/root/seb/seb/manager.py` — Add Discord reply routing

The manager's reply router needs to know how to send Discord messages:

```python
# In the reply routing section (where it checks platform):
elif platform == "discord":
    # Use the send-discord CLI (same pattern as send-signal-group)
    cmd = [str(SEND_DISCORD_PATH), chat_id, text]
    await asyncio.create_subprocess_exec(*cmd)
```

Or, if the manager holds a reference to the Discord listener, it can call `discord_listener.send_to_chat(chat_id, text)` directly (avoids shelling out).

#### `assistant/common.py` — Add reply routing for Discord

Add `"discord:"` to the registry prefix lists in `strip_registry_prefix`, `is_group_chat_id`, etc.

#### `~/.claude/skills/sms-assistant/scripts/reply` — Add Discord routing

Add Discord case in the reply CLI:

```python
SEND_DISCORD = Path.home() / ".claude/skills/discord/scripts/send-discord"

# In main(), after the signal branch:
elif backend == "discord":
    cmd = [str(SEND_DISCORD), bare_chat_id]
    if args.message:
        cmd.append(args.message)
```

#### `config.example.yaml` — Add Discord section

```yaml
discord:
  bot_token: "your-bot-token-here"  # Or use DISCORD_BOT_TOKEN env var
  channel_id: "1234567890"          # Target channel snowflake ID
```

#### `config.local.yaml` — Add actual Discord config (on Seb's VPS)

---

## 4. Message Flow

### Incoming (Discord → Claude)

```
1. User posts in Discord channel
2. discord.py on_message fires in DiscordListener (async, same event loop as manager)
3. Bot self-check — ignore if message from bot itself
4. Channel filtered at Discord level (bot role only sees target channel)
5. Defense-in-depth channel ID check in code
6. Call manager.on_message("discord", sender_id, channel_id, text, sender_name)
7. Manager looks up tier via config.tier_for_discord(sender_id)
8. Routes to SDKBackend (platform-agnostic) → SDK session
9. Session created on-demand at ~/transcripts/discord/{channel_id}/
10. Message wrapped with sender_name so Claude knows who said what
11. Claude processes and calls send-discord CLI (or listener.send_to_chat) to reply
```

### Outgoing (Claude → Discord)

```
1. Claude decides to reply
2. Calls: ~/.claude/skills/discord/scripts/send-discord "{channel_id}" "response"
3. send-discord does HTTP POST to Discord REST API
4. Message appears in channel
```

---

## 5. Channel Restriction

Channel restriction uses **defense-in-depth** at two levels:

1. **Discord server permissions (primary gate).** Sam restricts the bot's role to only have visibility of the target channel via Discord's server settings. The bot literally cannot see other channels — Discord enforces this at the platform level. This is the simplest and most robust approach.

2. **Code-level channel ID check (backup).** The listener also checks `message.channel.id != self.channel_id` as a safety net. This catches edge cases if Discord permissions are misconfigured.

---

## 6. User Mapping

### Default Behavior (Single Channel)

Since this is a single-channel setup, the tier system works differently from iMessage/Signal:

- **Mapped Discord users get their configured tier.** Sam's Discord ID mapped to "admin".
- **Unmapped Discord users default to "favorite" tier** (restricted tools, own session context).
- **New user logging:** First time a Discord user is seen, log a `[discord] New user: {display_name} ({user_id})` line so admin has visibility into who's interacting.

### Implementation

Add a `discord.users` section to config:

```yaml
discord:
  bot_token: "..."
  channel_id: "1234567890"
  users:
    "sam_discord_user_id": { name: "Sam", tier: "admin" }
    # All unmapped users get tier: "favorite"
```

In `process_message`, when `source == "discord"`:
- Look up `msg["phone"]` (Discord user ID) in `config.get("discord.users")`
- If found, use configured name and tier
- If not found, use Discord display name and tier="favorite"

This is simpler than the Contacts.app lookup used for iMessage/Signal, since Discord users don't have phone numbers. The contact lookup in `process_message` will return `None` for Discord user IDs (they're not phone numbers), so we need a Discord-specific path.

### Modification to `manager.on_message`

In the manager's `on_message` callback, add Discord-specific tier resolution:

```python
async def on_message(self, platform, sender_id, chat_id, text, sender_name=None, attachments=None):
    # ... existing logic ...

    if platform == "discord":
        # Discord uses user IDs, not phone numbers — use config-based lookup
        from seb.config import tier_for_discord
        name, tier = tier_for_discord(sender_id)
        if name is None:
            name = sender_name or sender_id  # Fall back to Discord display name
            log.info(f"[discord] New user: {name} ({sender_id})")  # Admin visibility
        # Route as group message (channel = group conversation)
        await self._route_group_message(platform, sender_id, chat_id, text, name, tier)
        return

    # ... existing iMessage/Signal logic ...
```

The SDK session and backend layers are fully platform-agnostic — once `on_message` resolves the tier and routes the message, everything downstream works identically to Signal.

---

## 7. Deployment (Seb's VPS)

### Dependencies

```bash
cd /root/seb
uv add "discord.py>=2.3.0"
uv sync
```

Also add `httpx` if not already present (for the send-discord CLI and listener's REST API calls).

### Configuration

Add to `/root/seb/config.local.yaml`:
```yaml
discord:
  bot_token: "BOT_TOKEN_HERE"       # From Discord Developer Portal
  channel_id: "1234567890"           # Target channel snowflake ID
  users:
    "SAM_DISCORD_USER_ID":
      name: "Sam"
      tier: "admin"
    # All unmapped users default to "favorite" tier
```

Alternatively, set `DISCORD_BOT_TOKEN` as an environment variable.

### Startup

No separate process needed. The Discord listener runs as an asyncio task inside the existing daemon. If `discord.channel_id` is not set, the listener doesn't start (graceful no-op). No systemd changes required.

### Transcript Directory

Discord sessions store transcripts at:
```
~/transcripts/discord/{channel_id}/
```
The `.claude` symlink and SKILL.md injection work identically to Signal/iMessage sessions.

### Health & Monitoring

- **Log prefix:** All Discord log lines use `[discord]` prefix for easy filtering.
- **Watchdog integration:** The existing watchdog checks daemon health — since Discord runs inside the daemon process, it's covered automatically. The `on_disconnect`/`on_resumed` events log Gateway state transitions.
- **Status page:** Add Discord listener status to `claude-assistant status` output (connected/disconnected, last message timestamp).
- **Message edits/deletions:** Ignored. Only `on_message` (new messages) is processed. Edits and deletes don't trigger the listener.

---

## 8. Testing

### Step-by-step verification

1. **Test send-discord CLI:**
   ```bash
   ~/.claude/skills/discord/scripts/send-discord "CHANNEL_ID" "Test message from CLI"
   # Verify message appears in Discord channel
   ```

2. **Test the full pipeline:**
   - Start the daemon with Discord configured
   - Post a message in the Discord channel
   - Check logs for:
     - `[discord] Connected as Seb#1234 (channel: ...)`
     - `[discord] {username}: {message text}`
     - Session creation log
   - Verify Claude responds in the channel

3. **Test channel isolation:**
   - Post in a different channel (if bot has access to any other)
   - Verify no log entries from Discord listener

4. **Test reconnection:**
   - Temporarily disconnect (e.g., revoke then re-grant token)
   - Verify `[discord] Disconnected` and `[discord] Resumed` logs
   - Verify messages flow again after reconnect

5. **Test reply CLI:**
   ```bash
   cd ~/transcripts/discord/CHANNEL_ID
   ~/.claude/skills/sms-assistant/scripts/reply "Test reply"
   ```

---

## 9. Security

### Token Storage

- **Primary:** `config.local.yaml` (gitignored, same as Signal account)
- **Alternative:** `DISCORD_BOT_TOKEN` environment variable
- **Never** commit tokens to git. `config.local.yaml` is already in `.gitignore`.

### Bot Permissions (Principle of Least Privilege)

Request only these Discord permissions:
- `Send Messages` — reply in channel
- `Read Message History` — for read-discord history CLI
- `View Channels` — see the target channel
- `Attach Files` — if sending images/files later

Do NOT request:
- `Administrator`
- `Manage Messages`
- `Mention Everyone`
- Any moderation permissions

### Server-Side Channel Restriction

Ask Sam to restrict the bot's role to only have visibility of the target channel. This is defense-in-depth — even though the code filters by channel ID, the bot shouldn't be able to see messages in other channels at all.

### Rate Limiting

Discord rate limits API calls. The `send-discord` CLI should handle 429 responses:
```python
if resp.status_code == 429:
    retry_after = resp.json().get("retry_after", 1)
    time.sleep(retry_after)
    # retry once
```

### Message Content Intent

The bot uses the Message Content privileged intent. This is required to read message text. It must be explicitly enabled in the Developer Portal. Without it, `message.content` is empty for messages not mentioning the bot.

---

## 10. Summary of All Changes

| File | Action | Description |
|------|--------|-------------|
| `/root/seb/seb/listeners/discord.py` | Create | Async listener (discord.py) |
| `~/.claude/skills/discord/SKILL.md` | Create | Skill documentation |
| `~/.claude/skills/discord/scripts/send-discord` | Create | Send CLI (REST API, standalone fallback) |
| `/root/seb/seb/main.py` | Modify | Wire up listener via asyncio.create_task |
| `/root/seb/seb/manager.py` | Modify | Add Discord reply routing + new user logging |
| `/root/seb/seb/config.py` | Modify | Add `tier_for_discord()` and Discord config schema |
| `/root/seb/pyproject.toml` | Modify | Add `discord.py>=2.3.0` dependency |
| `/root/seb/config.local.yaml` | Modify | Add bot_token, channel_id, users |

> **Note on paths:** `/root/seb/seb/` is Seb's codebase on the VPS (separate from Sven's `~/dispatch/`). Both follow the same architectural patterns but are independent codebases.

### Implementation Order

1. **Sam:** Create Discord bot in Developer Portal, get bot token, invite to server, restrict to one channel
2. **Seb:** `uv add discord.py` — add dependency
3. **Seb:** Create `/root/seb/seb/listeners/discord.py` — the async listener
4. **Seb:** Create `send-discord` CLI script — test independently
5. **Seb:** Add Discord config to `config.local.yaml` (token, channel ID, user mappings)
6. **Seb:** Wire listener in `main.py` (one `asyncio.create_task` call)
7. **Seb:** Add reply routing in `manager.py`
8. **Seb:** Add `tier_for_discord()` in `config.py`
9. **Test:** Post in Discord channel → verify Seb responds
10. **Test:** Verify channel isolation (bot can't see other channels)
