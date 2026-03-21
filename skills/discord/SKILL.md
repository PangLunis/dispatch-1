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

## Response Behavior

**Default: respond only when tagged** (`@bot`). Do not reply to every message in a channel.

**Exception — active turn-based games:** If context from recent messages makes it clearly your turn (e.g., a game prompt directed at you, the previous player completed their turn), respond without requiring a tag. Read game state from the last several messages to determine if it is your turn before acting.

## Bot Commands

Discord sessions recognize dot-commands (e.g., `.imdb`, `.help`) as special bot commands.

### `.imdb <title>`

Looks up movie or TV show information using the imdb-lookup skill CLI.

```bash
~/.claude/skills/imdb-lookup/scripts/imdb-lookup "<title>" --format discord
```

- Uses `--format discord` for markdown-formatted output suitable for Discord channels
- Card output includes: title, year, rating, runtime, genres, and IMDb link
- Powered by the TMDB API via the imdb-lookup CLI (no web scraping)
