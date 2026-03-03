# Dispatch

A personal AI assistant daemon that turns Claude into a full computer-controlling agent with SMS/Signal messaging, browser automation, smart home control, and persistent memory.

## Overview

Dispatch runs a daemon that:
- **Receives messages** from iMessage and Signal in real-time
- **Routes them to Claude SDK sessions** based on contact tier (admin, family, favorites, etc.)
- **Gives Claude full computer control**: browser automation, file management, smart home, messaging
- **Maintains persistent memory** across conversations with full-text search
- **Auto-recovers from crashes** via watchdog daemon with exponential backoff

Each contact gets their own persistent Claude session with conversation history, memories, and tier-appropriate tool access.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Messages.app (iMessage)      Signal (via signal-cli)       │
│  Polled every 100ms           JSON-RPC socket               │
└────────────────┬──────────────────────────┬─────────────────┘
                 │                          │
                 └──────────────┬───────────┘
                                ▼
                    ┌───────────────────────┐
                    │    Manager Daemon     │
                    │   (event loop)        │
                    └──────────┬────────────┘
                               ▼
                    ┌───────────────────────┐
                    │   Contact Lookup      │
                    │   + Tier Check        │
                    └──────────┬────────────┘
                               ▼
                    ┌───────────────────────┐
                    │   SDK Backend         │
                    │   (session factory)   │
                    └──────────┬────────────┘
                               ▼
              ┌────────────────────────────────┐
              │   Per-Contact SDK Sessions     │
              │   (Claude Opus, async queues,  │
              │    mid-turn message injection) │
              └────────────────────────────────┘
                               ▼
              ┌────────────────────────────────┐
              │   Tools & Skills               │
              │   Browser, Smart Home, Memory, │
              │   Messaging, Files, etc.       │
              └────────────────────────────────┘
```

## Features

### Messaging
- **iMessage**: Polls `chat.db` for new messages, supports individual + group chats
- **Signal**: Connects via `signal-cli` daemon with JSON-RPC socket
- **Image handling**: Gemini Vision analyzes images with conversation context
- **Mid-turn steering**: New messages reach Claude between tool calls

### Contact Tiers
| Tier | Access |
|------|--------|
| **Admin** | Full computer control, browser automation, all tools |
| **Wife** | Full access with personalized warm tone |
| **Family** | Read-only, mutations need admin approval |
| **Favorite** | Own session, restricted tools |
| **Bots** | Read-only with loop detection |
| **Unknown** | Ignored (no session created) |

Tiers are managed via macOS Contacts.app groups.

### Session Management
- Per-contact SDK sessions with automatic resumption
- Transcript storage at `~/transcripts/{backend}/{chat_id}/`
- Two-tier health monitoring: fast regex (60s) + deep LLM analysis (5min)
- Idle session reaping after 2 hours
- Session registry persists across daemon restarts

### Skills System
Skills are modular capabilities in `~/.claude/skills/`. Each has:
- `SKILL.md` with YAML frontmatter (name, description, triggers)
- Optional `scripts/` directory with CLI executables
- Template placeholders: `{{CONTACT_NAME}}`, `{{TIER}}`, `{{CHAT_ID}}`

**67+ built-in skills** including:
- `sms-assistant` - Messaging guidelines and tier rules
- `chrome-control` - Browser automation (clicks, typing, screenshots)
- `memory` - Persistent memory with FTS search
- `hue`, `lutron`, `sonos` - Smart home control
- `ios-app` - iOS development and TestFlight
- `gemini` - Vision API for image analysis
- `reminders` - Natural language reminder parsing
- And many more...

### Reliability
- **Watchdog daemon**: Auto-recovers from crashes
- **Exponential backoff**: 60s → 120s → 240s → 480s → 900s
- **Health checks**: Regex patterns + Haiku LLM analysis
- **SMS alerts**: Admin notified of recovery attempts
- **Max 5 failures** before manual intervention required

## Requirements

- macOS (uses Messages.app, Contacts.app)
- Python 3.12+ with [`uv`](https://github.com/astral-sh/uv) package manager
- Claude API access (Anthropic)
- Optional: `signal-cli` daemon for Signal messaging
- Optional: Chrome with [Chrome Control extension](~/.claude/skills/chrome-control/) for browser automation

## Installation

```bash
# Clone the repo
git clone https://github.com/svenflow/dispatch.git ~/dispatch
cd ~/dispatch

# Install dependencies
uv sync

# Copy and edit config
cp config.example.yaml config.local.yaml
# Edit config.local.yaml with your settings

# Start the daemon
./bin/claude-assistant start

# Install watchdog for auto-recovery (recommended)
./bin/watchdog-install
```

## Configuration

See `config.example.yaml` for all options. Key settings:

```yaml
assistant:
  name: "Sven"                    # Assistant's name

contacts:
  owner_phone: "+1234567890"      # Your phone (gets admin tier)

messaging:
  enabled_backends:
    - imessage
    - signal

hue:
  bridges:
    home: "192.168.1.x"
    office: "192.168.1.y"
```

## CLI Usage

```bash
# Daemon management
./bin/claude-assistant start           # Start daemon
./bin/claude-assistant stop            # Stop daemon
./bin/claude-assistant restart         # Restart (via launchctl)
./bin/claude-assistant status          # Show status and sessions
./bin/claude-assistant logs            # Tail daemon logs

# Session management
./bin/claude-assistant kill-session <name>      # Kill specific session
./bin/claude-assistant restart-session <name>   # Restart specific session
./bin/claude-assistant restart-sessions         # Restart all sessions

# Watchdog
./bin/watchdog-install     # Install auto-recovery
./bin/watchdog-uninstall   # Remove watchdog
./bin/watchdog-status      # Check watchdog status
```

## Directory Structure

```
~/dispatch/
├── assistant/           # Core daemon code
│   ├── manager.py       # Main daemon (polling, routing)
│   ├── sdk_backend.py   # Session factory and management
│   ├── sdk_session.py   # Per-contact session wrapper
│   ├── cli.py           # Command-line interface
│   └── config.py        # Configuration loader
├── bin/                 # Executable scripts
│   ├── claude-assistant # Main CLI
│   ├── watchdog         # Auto-recovery daemon
│   └── watchdog-*       # Watchdog management
├── services/            # Supporting services
│   ├── memory-search/   # TypeScript FTS daemon
│   └── sven-api/        # iOS app backend
├── tests/               # Test suite (100+ tests)
├── state/               # Runtime state
│   ├── sessions.json    # Session registry
│   └── daemon.pid       # Current PID
├── logs/                # Log files
│   ├── manager.log      # Daemon log
│   └── sessions/        # Per-session logs
└── config.local.yaml    # Local configuration
```

## Development

```bash
# Run all tests
uv run pytest tests/ -v

# Run core tests only
uv run pytest tests/test_backends.py tests/test_session_lifecycle.py \
    tests/test_registry.py tests/test_health_checks.py -v

# Type checking (uses ty, not mypy)
uv run ty check assistant/

# Linting (uses ruff)
uv run ruff check assistant/
```

### Test Structure
- `tests/test_backends.py` - Backend config, routing, normalization
- `tests/test_session_lifecycle.py` - Session create/stop/inject, health
- `tests/test_registry.py` - Registry CRUD, persistence
- `tests/test_health_checks.py` - Health monitoring, idle reaping
- `tests/test_message_routing.py` - Message normalization, file handling
- `tests/test_performance.py` - Concurrency, throughput, leaks
- `tests/unit/` - Pure function tests
- `tests/integration/` - Integration tests with fake chatdb

## Key Design Decisions

1. **No auto-send**: Claude explicitly calls `send-sms` or `send-signal` CLIs (full control over messaging)
2. **In-process sessions**: No tmux/subprocess shells, all sessions in async event loop
3. **Mid-turn steering**: New messages injected between tool calls via async queue
4. **Two-tier health**: Fast regex + slow LLM analysis balances speed vs accuracy
5. **Skills as modules**: Shared, version-controlled, injected via symlink

## Metrics & Limits

| Setting | Value |
|---------|-------|
| Polling interval | 100ms |
| Health check (Tier 1) | 60 seconds |
| Health check (Tier 2) | 5 minutes |
| Session idle reap | 2 hours |
| Watchdog cycle | 60 seconds |
| Max consecutive failures | 5 |
| Session log size | 10MB (5 backups) |

## License

MIT
