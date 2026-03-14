---
name: infra-self-improvement
description: Guide for safely improving claude-assistant infrastructure. Use when editing daemon code, SDK sessions, messaging backends, or any core system component. Covers testing strategy, performance baselines, and how to avoid breaking the running daemon.
---

# Infrastructure Self-Improvement Guide

When modifying the claude-assistant system, follow this guide to ensure you don't break the running daemon and maintain performance/reliability.

## Golden Rule

**Never push changes to the running daemon without testing first.** The daemon manages real conversations for real people. A broken daemon means dropped messages and unresponsive sessions.

## Pre-Change Checklist

Before editing any file in `~/dispatch/assistant/`:

1. **Check daemon status**: `claude-assistant status`
2. **Note active sessions**: Don't restart during active conversations
3. **Read the relevant test file** (see mapping below)
4. **Understand what you're changing** before writing code

## Test Tiers

### Tier 1: Unit Tests (always run, no cost)

```bash
cd ~/dispatch
uv run --group dev pytest tests/ -v --ignore=tests/unit/test_tts_chunk.py
```

**Run these after EVERY change.** They use `FakeClaudeSDKClient` - no API calls, no side effects. Takes ~40s.

| Changed file | Tests to run |
|---|---|
| `backends.py` | `test_backends.py` |
| `common.py` | `test_backends.py` + `test_message_routing.py` |
| `sdk_session.py` | `test_session_lifecycle.py` |
| `sdk_backend.py` | `test_session_lifecycle.py` + `test_health_checks.py` + `test_performance.py` |
| `manager.py` | `test_message_routing.py` |
| `cli.py` | `test_registry.py` |
| `bus_helpers.py` | `test_bus_helpers.py` |
| `bus/bus.py` | `test_bus.py` |
| `bus/consumers.py` | `test_consumers.py` |
| `health.py` | `test_health_checks.py` |
| `reminders.py` | `unit/test_poll_due.py` + `unit/test_add_reminder.py` |

### Tier 2: Smoke Tests - No API (run before daemon restart)

```bash
cd ~/dispatch
uv run python tests/smoke/run_smoke_tests.py --skip-api
```

Tests real integrations without API cost (~1.3s):
- iMessage send-sms → chat.db round-trip
- Signal send + socket subscribe
- Daemon message throughput (20 msgs via TestMessageWatcher)
- Signal socket stress (10x rapid connect/disconnect)
- Registry persistence under load (2000 rapid writes)

### Tier 3: Smoke Tests - With API (run for SDK changes)

```bash
cd ~/dispatch
uv run python tests/smoke/run_smoke_tests.py
```

Full suite including real Claude API calls (~32s, costs credits):
- SDK connect/query/disconnect lifecycle
- Session resume with context recall
- 3 concurrent SDK sessions
- Interrupt mid-query + recovery
- Force disconnect during query
- Memory leak detection (5 create/destroy cycles)

### Tier 4: Manual Verification (run after daemon restart)

After restarting the daemon:
1. Send yourself a test message - verify it routes and gets a response
2. Check `claude-assistant status` - sessions should come up healthy
3. Tail the log: `claude-assistant logs` - no errors in first 30s
4. Check session logs: `claude-assistant attach <session>` - verify system prompt injected

## Performance Baselines (2026-02-01)

These are the numbers to beat. If a change makes things slower, investigate.

| Metric | Baseline | Concern threshold |
|--------|----------|-------------------|
| send-sms latency | 154ms | >500ms |
| chat.db write latency | 111ms | >500ms |
| Signal send latency | 294ms | >1s |
| Signal socket subscribe | 7ms | >100ms |
| Daemon msg pickup (20 msgs) | 110ms | >500ms |
| Per-message routing | ~7ms | >50ms |
| SDK connect | 1.0-1.3s | >3s |
| SDK first response | 29ms | >200ms |
| SDK full query | 1.5-1.9s | >5s |
| SDK disconnect | 5-10ms | >1s |
| SDK resume connect | 0.9-1.0s | >3s |
| Interrupt latency | 4ms | >100ms |
| Registry 2000 updates | 5ms | >2s |
| Memory per 5 SDK cycles | 0-368KB | >5MB |
| Orphan tasks after cleanup | 0 | >0 |

## Architecture Danger Zones

These areas are most likely to cause production issues:

### 1. The Lock (`self._lock` in SDKBackend)
- **What it protects**: Session creation/deletion in `self.sessions` dict
- **Danger**: Holding the lock too long blocks ALL session operations
- **Rule**: Only hold lock for dict mutation. Inject, wrap, registry update, system prompt build all happen OUTSIDE the lock
- **Test**: `test_performance.py::TestLockFairness`

### 2. Error Backoff (`sdk_session.py` run loop)
- **Current**: `2 * error_count` seconds between retries, dies at 3 errors
- **Danger**: Too aggressive = spam retries. Too conservative = slow recovery
- **Test**: `test_session_lifecycle.py::TestSessionErrorHandling`

### 3. Registry Debounce (`_save_debounced` in SessionRegistry)
- **What**: Writes at most once per second, `flush()` on shutdown
- **Danger**: Data loss if daemon crashes between debounced writes
- **Acceptable risk**: Only `last_message_time` is debounced; session creation/deletion writes immediately
- **Test**: `test_performance.py::TestRegistryWritePerformance`

### 4. System Prompt Build (subprocess for memory)
- **What**: `_get_memory_summary()` calls `uv run memory.py summary` with 10s timeout
- **Danger**: Blocks session creation if slow. Now runs outside the lock.
- **Test**: Smoke test 4 (SDK lifecycle) covers this implicitly

### 5. Health Checks (`check_idle_sessions`, `health_check_all`)
- **Interval**: Every 5 minutes
- **Idle kill**: 2 hours (except background/master sessions)
- **Auto-restart**: Sessions with 3+ errors get restarted
- **Test**: `test_health_checks.py`

### 6. Bus Write Queue (`bus/bus.py`)
- **What**: In-memory queue drained by background writer thread. `produce_event()` enqueues (~microseconds).
- **Danger**: Queue can grow unbounded if writer thread dies silently. Queue depth >1000 logged as warning.
- **Danger**: SQLite WAL contention between producer writes and consumer reads (mitigated by WAL mode)
- **Danger**: `sdk_events` table growth — 3-day retention with auto-prune, but bulk SDK activity could grow faster
- **Danger**: Bus init failure on startup (corrupted bus.db, disk full) — should be fatal, let watchdog recover
- **Test**: `test_bus.py`

### 7. Message Polling (manager.py)
- **iMessage**: 100ms poll interval via SQLite on chat.db
- **Signal**: JSON-RPC socket with push notifications
- **Test messages**: TestMessageWatcher polls `~/.claude/test-messages/` every 100ms
- **Sessions**: All sessions are SDK-based (Agent SDK), not tmux. Each contact gets a persistent SDK session with resume support.
- **Danger**: chat.db race condition when `chat_style` is NULL (handled with 50ms retry)
- **Test**: `test_message_routing.py`, `unit/test_messages_race.py`

## Safe Restart Procedure

```bash
# 1. Check what's running
claude-assistant status

# 2. If sessions are idle, restart
claude-assistant restart

# 3. Verify it came back
claude-assistant status
claude-assistant logs  # watch for 30s

# 4. Test with a message
# Send yourself a test via the test adapter:
echo '{"from":"+15555551234","text":"restart test","chat_id":"+15555551234"}' > ~/.claude/test-messages/test.json
```

## How to Add New Tests

### Unit test (mock SDK):
Add to the appropriate `tests/test_*.py` file. Use the `sdk_session` and `sdk_backend` fixtures from `conftest.py`. These use `FakeClaudeSDKClient`.

### Smoke test (real integrations):
Add a function to `tests/smoke/run_smoke_tests.py`. Follow the pattern:
1. Function name: `test_*` (sync) or `async def test_*` (async for SDK)
2. Use `report(name, passed, duration, details)` for results
3. If it hits Claude API, add to `run_api_tests()` and mark `[API]` in the section title

### Integration test via TestMessageWatcher:
Drop JSON files in `~/.claude/test-messages/`:
```json
{
    "from": "+15555550000",
    "text": "test message",
    "is_group": false,
    "chat_id": "+15555550000"
}
```
The daemon picks these up within 100ms and processes them through the full routing pipeline.

## Common Pitfalls

1. **Editing sdk_backend.py without running tests** → Most dangerous file, touches everything
2. **Changing lock scope** → Can cause race conditions or deadlocks. Always run `test_performance.py`
3. **Modifying message normalization** → Breaks routing for all backends. Run `test_backends.py` + `test_message_routing.py`
4. **Changing error handling** → Can cause infinite restarts or silent failures. Run `test_session_lifecycle.py`
5. **Adding new tools to tier configs** → Security implications. Check `_permission_check` in `sdk_session.py`
6. **Forgetting `flush()` on registry** → Data loss on shutdown. The debounce system handles this but verify
7. **Running `asyncio.gather` with SDK clients** → Each client's cancel scope is task-bound. Connect+disconnect must happen in the same task
