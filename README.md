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
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
     ┌──────────────┐  ┌────────────┐  ┌───────────┐
     │  SDK Backend  │  │ Event Bus  │  │  Perf     │
     │  (sessions)   │  │ (audit)    │  │  Metrics  │
     └──────┬───────┘  └────────────┘  └───────────┘
            ▼                │
 ┌────────────────────┐      │  Kafka-on-SQLite
 │ Per-Contact SDK    │      │  (bus.db)
 │ Sessions (Opus)    │      │  - records table (7d)
 │ async queues,      │      │  - sdk_events table (3d)
 │ mid-turn injection │      │  - write queue + bg thread
 └────────┬───────────┘      │
          ▼                  │
 ┌────────────────────┐      │
 │ Tools & Skills     │──────┘ (future: analytics,
 │ Browser, Home,     │        alerting consumers)
 │ Memory, Messaging  │
 └────────────────────┘
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
| **Partner** | Full access with personalized warm tone |
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

### Event Bus (Kafka-on-SQLite)
- **Audit trail**: All message, session, and system events recorded to SQLite
- **Fire-and-forget writes**: In-memory write queue (~microsecond enqueue), background thread batches commits
- **Multi-consumer fanout**: Independent consumer groups with committed offsets (future: analytics, alerting)
- **SDK event tracking**: Tool calls, durations, errors in auxiliary `sdk_events` table
- **Bus CLI**: `stats`, `tail`, `export` commands for inspection
- **Fully integrated**: `produce_event()` wired throughout manager.py and sdk_backend.py — all events flow through the bus

### Resource Lifecycle
- **ResourceRegistry**: Centralized tracking of all persistent FDs, connections, and subprocesses via `AsyncExitStack`
- **ManagedSQLiteReader/Writer**: Single-connection-per-database pattern on dedicated executor threads — eliminates contention
- **FD leak detection**: Monitors `/dev/fd/` delta vs tracked resources every 5 minutes
- **Safe cleanup**: Handles non-idempotent `close()` calls (SQLite, subprocesses) via wrapped callbacks

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
│   ├── bus_helpers.py   # Bus event production helpers (taxonomy v6)
│   ├── resources.py     # ResourceRegistry, ManagedSQLiteReader/Writer
│   ├── health.py        # Health check logic (fast regex + deep LLM)
│   ├── reminders.py     # Reminder system
│   ├── readers.py       # Message readers (iMessage, Signal)
│   ├── perf.py          # Performance metric recording
│   ├── cli.py           # Command-line interface
│   └── config.py        # Configuration loader
├── bus/                 # Kafka-on-SQLite message bus
│   ├── bus.py           # Core: Producer (write queue), Consumer groups
│   ├── cli.py           # Bus CLI (stats, tail, export)
│   └── consumers.py     # Consumer framework with declarative configs
├── bin/                 # Executable scripts
│   ├── claude-assistant # Main CLI
│   ├── watchdog         # Auto-recovery daemon
│   └── watchdog-*       # Watchdog management
├── services/            # Supporting services
│   ├── memory-search/   # TypeScript FTS daemon
│   └── sven-api/        # iOS app backend
├── tests/               # Test suite (920+ tests)
├── state/               # Runtime state
│   ├── sessions.json    # Session registry
│   ├── bus.db           # Bus database (records + sdk_events)
│   └── daemon.pid       # Current PID
├── logs/                # Log files
│   ├── manager.log      # Daemon log
│   ├── perf-*.jsonl     # Performance metrics (daily)
│   └── sessions/        # Per-session logs
├── plans/               # Architecture plans
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
- `tests/test_bus.py` - Bus core: producer, consumer, write queue, retention, sdk_events
- `tests/test_bus_helpers.py` - Event production, sanitize/reconstruct, taxonomy
- `tests/test_consumers.py` - Consumer groups, offsets, commit, fanout
- `tests/unit/` - Pure function tests
- `tests/integration/` - Integration tests with fake chatdb

## Key Design Decisions

1. **No auto-send**: Claude explicitly calls `send-sms` or `send-signal` CLIs (full control over messaging)
2. **In-process sessions**: No tmux/subprocess shells, all sessions in async event loop
3. **Mid-turn steering**: New messages injected between tool calls via async queue
4. **Two-tier health**: Fast regex + slow LLM analysis balances speed vs accuracy
5. **Skills as modules**: Shared, version-controlled, injected via symlink
6. **Kafka-on-SQLite event bus**: Fire-and-forget audit trail with write queue (no event loop blocking), multi-consumer fanout for future analytics/alerting
7. **Tiered event storage**: Business events in main `records` table (7-day retention), SDK traces in `sdk_events` table (3-day retention)
8. **Centralized resource lifecycle**: All FDs, connections, and subprocesses tracked via `ResourceRegistry` (AsyncExitStack wrapper) for structural cleanup and FD leak detection

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
