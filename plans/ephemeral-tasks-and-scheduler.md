# Plan: Ephemeral Tasks + Generalized Reminder-as-Scheduler

**Status: DRAFT**

## Goal

Two connected changes:

1. **Ephemeral tasks**: A new event type (`task.requested`) that spins up a short-lived agent session, executes a task, produces a summary, and shuts down. Uses the same session infrastructure as normal chats.

2. **Generalized scheduler**: Reminders become a cron-for-the-bus. Instead of producing a hardcoded `reminder.due` event, a reminder stores an arbitrary bus event and replays it at the scheduled time. This makes the reminder system maximally general — it can schedule ANY bus event.

## Why

**Ephemeral tasks** solve a real gap: many operations don't belong in a user's chat session (analytics, cleanup, long-running analysis, background maintenance). Currently these either don't happen, or get awkwardly injected into the admin's foreground session. Ephemeral tasks give them a clean home with lifecycle tracking.

**Generalized scheduler** eliminates special-casing. Right now we'd need `reminder.due` for reminders, `task.scheduled` for scheduled tasks, etc. If the scheduler can produce any event, it's just one system that handles all scheduling needs.

## Part 1: Ephemeral Tasks

### New Topic: "tasks"

```
tasks — task.requested, task.started, task.completed, task.failed,
         task.timeout (keyed by chat_id of requester)
```

### task.requested Payload

```python
{
    "task_id": "task-abc12345",       # unique ID
    "title": "Analyze weekly message volume",
    "requested_by": "+15551234567",   # who requested it (for summary delivery)
    "instructions": "...",            # full prompt for the agent
    "notify": True,                   # text requester on start/finish?
    "timeout_minutes": 30,            # auto-kill after this
}
```

**Bus record key**: `requested_by` (chat_id of requester — routes to their partition for summary delivery)

### Lifecycle

```
1. Producer writes task.requested to bus
   (could be: CLI, reminder scheduler, another session, HTTP webhook)

2. Session-router consumer sees task.requested
   ├─ Creates ephemeral SDK session:
   │   session_name = "ephemeral-{task_id}"
   │   cwd = ~/dispatch/state/ephemeral/{task_id}/
   │   .claude symlink for skill access
   │
   ├─ Produces task.started event
   │
   ├─ If notify=True, texts requester:
   │   "[TASK abc12345] Starting: Analyze weekly message volume"
   │
   └─ Injects instructions into session

3. Ephemeral session runs autonomously
   ├─ Has access to all skills, tools, bus
   ├─ Can produce its own bus events
   └─ Session prompt includes: "When done, write your summary
      to stdout and exit cleanly."

4. Session completes (or times out)
   ├─ On completion:
   │   ├─ Produce task.completed with summary in payload
   │   ├─ If notify=True, text requester:
   │   │   "[TASK abc12345] Done: <summary>"
   │   └─ Kill session, clean up cwd
   │
   └─ On timeout:
       ├─ Produce task.timeout
       ├─ If notify=True, text requester:
       │   "[TASK abc12345] Timed out after 30min"
       └─ Force-kill session, clean up cwd
```

### Shared Code with Normal Chat Sessions

Ephemeral tasks reuse existing infrastructure — no parallel session system:

| Component | Normal Chat | Ephemeral Task |
|-----------|------------|----------------|
| Session creation | `create_session()` | Same `create_session()` |
| Injection | `session.inject()` | Same `session.inject()` |
| Skills access | `.claude` symlink | Same `.claude` symlink |
| Bus events | `session.injected` etc. | Same + task-specific events |
| Health monitoring | health_check_all | Same (ephemeral sessions included) |
| Session kill | `kill_session()` | Same `kill_session()` |

**Differences:**
- No transcript directory (ephemeral sessions don't persist conversations)
- No reply CLI (no user to reply to — though can text requester via send-sms)
- Auto-kills on completion or timeout (normal sessions persist)
- Session name prefix: `ephemeral-{task_id}` (easy to identify/filter)

### Timeout Supervision

The session-router (or a dedicated supervisor) tracks active ephemeral tasks:

```python
# In-memory tracker
ephemeral_tasks = {
    "task-abc12345": {
        "session_name": "ephemeral-task-abc12345",
        "started_at": datetime(...),
        "timeout_minutes": 30,
        "requested_by": "+15551234567",
        "notify": True,
    }
}
```

Each poll cycle, check for timed-out tasks. Produce `task.timeout` event and force-kill the session.

## Part 2: Generalized Scheduler (Reminder Evolution)

### Current Model (reminder.due — specific)

```python
# Reminder fires → produces hardcoded reminder.due event
{
    "id": "abc123",
    "title": "Check weather",
    "contact": "+15551234567",
    "schedule": {"type": "cron", "value": "0 9 * * *"},
    "target": "fg",
    # Produces: reminder.due on "reminders" topic
}
```

### New Model (arbitrary event — general)

```python
# Reminder fires → produces whatever event is configured
{
    "id": "abc123",
    "schedule": {"type": "cron", "value": "0 9 * * *"},
    "event": {
        "topic": "tasks",
        "type": "task.requested",
        "key": "+15551234567",
        "payload": {
            "task_id": "scheduled-abc123",
            "title": "Check weather and text forecast",
            "requested_by": "+15551234567",
            "instructions": "Check weather for Boston, text the forecast to the user.",
            "notify": True,
            "timeout_minutes": 10,
        }
    }
}
```

When the reminder fires, the poller just does:

```python
producer.send(
    topic=r["event"]["topic"],
    type=r["event"]["type"],
    key=r["event"]["key"],
    payload=r["event"]["payload"],
)
```

The scheduler doesn't know or care what the event IS. It's a cron-for-the-bus.

### Migration from Current Reminders

Current reminders have `title`, `contact`, `target` fields at the top level. The new model puts everything inside `event`. Migration:

**Old format (still supported during transition):**
```python
{
    "id": "abc123",
    "title": "Check weather",
    "contact": "+15551234567",
    "target": "fg",
    "schedule": {"type": "cron", "value": "0 9 * * *"},
}
```

**New format:**
```python
{
    "id": "abc123",
    "schedule": {"type": "cron", "value": "0 9 * * *"},
    "event": {
        "topic": "reminders",
        "type": "reminder.due",
        "key": "+15551234567",
        "payload": {
            "reminder_id": "abc123",
            "title": "Check weather",
            "contact": "+15551234567",
            "chat_id": "+15551234567",
            "tier": "admin",
            "target": "fg",
            ...
        }
    }
}
```

**Migration strategy**: `_fire_reminder()` checks for `event` key. If present, uses new path (generic produce). If absent, uses old path (builds reminder.due payload from top-level fields). This lets existing reminders keep working while new reminders use the generic format.

### What the Scheduler Can Now Schedule

| Use Case | Event | Topic |
|----------|-------|-------|
| Remind user to do something | reminder.due | reminders |
| Spin up ephemeral task | task.requested | tasks |
| Scheduled health check | health.check_requested | system |
| Nightly analytics export | analytics.export_requested | system |
| Periodic cleanup | cleanup.requested | system |
| Any custom event | anything | any topic |

### CLI Updates

```bash
# Current (still works):
claude-assistant remind add "Check weather" --contact "Alice" --cron "0 9 * * *"

# New: schedule arbitrary bus events
claude-assistant schedule add --event '{
  "topic": "tasks",
  "type": "task.requested",
  "key": "+15551234567",
  "payload": {"title": "Weekly report", "requested_by": "+15551234567", ...}
}' --cron "0 9 * * 1"

# Convenience shorthand for common patterns:
claude-assistant schedule add --task "Weekly report" --for "+15551234567" --cron "0 9 * * 1"
# ^ Automatically wraps in task.requested event
```

The `remind add` command continues to work by building a `reminder.due` event internally.

## Steps

### Phase 1: Ephemeral Task Infrastructure (implement now)

1. **Create "tasks" topic** in bus initialization
2. **Add task processing to session-router consumer** — handle `task.requested` events
3. **Ephemeral session creation** — `create_ephemeral_session()` in SDKBackend
   - Creates session with `ephemeral-{task_id}` name
   - Sets up temporary cwd with .claude symlink
   - Injects task instructions
   - Returns session reference
4. **Timeout supervision** — track active ephemeral tasks, kill on timeout
5. **Task lifecycle events** — produce task.started, task.completed, task.failed, task.timeout
6. **Notification** — text requester on start/finish if notify=True
7. **Cleanup** — remove cwd after task completes/times out
8. **Tests** — task creation, injection, timeout, completion, notification

### Phase 2: Generalized Scheduler (implement after Phase 1)

1. **Update reminder JSON schema** — add optional `event` field
2. **Update `_fire_reminder()`** — check for `event` key, use generic produce if present
3. **Backward compatibility** — old-format reminders still work via existing reminder.due path
4. **Update `remind add` CLI** — internally builds event wrapper
5. **Add `schedule add` CLI** — for arbitrary event scheduling
6. **Tests** — old format compat, new format produce, round-trip, CLI
7. **Update SKILL.md** — document new scheduling capabilities

## Risks

### Risk 1: Ephemeral session resource leaks
**Problem**: If the timeout supervisor crashes or misses a task, ephemeral sessions run forever.
**Mitigation**: Health check includes ephemeral sessions. Add a hard max lifetime (e.g., 2 hours) enforced by health check regardless of configured timeout. Clean up orphaned ephemeral cwds on daemon startup.

### Risk 2: Arbitrary event injection as security vector
**Problem**: The generalized scheduler can produce ANY event to ANY topic. A compromised reminder JSON file could inject malicious events.
**Mitigation**: reminders.json is only writable by the daemon and CLI (both run as same user). The bus is local-only (sqlite file). Same trust boundary as the daemon itself. If paranoid, add an allowlist of schedulable topics/types.

### Risk 3: Task notification spam
**Problem**: Frequent scheduled tasks (every 5 minutes) texting the admin gets noisy.
**Mitigation**: `notify` defaults to False for scheduled tasks. Only explicitly requested notifications fire. Add rate limiting if needed.

### Risk 4: Backward compatibility during schema migration
**Problem**: Old reminders without `event` key must keep working.
**Mitigation**: `_fire_reminder()` checks for `event` key. If absent, uses current dual-path logic (builds reminder.due payload from top-level fields). Migration is gradual — old reminders work until they're naturally deleted (once) or manually updated (cron).

### Risk 5: Event payload validation
**Problem**: Scheduler fires arbitrary event payloads. If payload is malformed, consumer crashes.
**Mitigation**: `_ensure_json_safe()` already sanitizes payloads. Consumer already handles poison messages (log + skip + commit). Add schema validation per event type in the consumer if needed later.

## Out of Scope
- HTTP webhook trigger for tasks (could produce task.requested via API later)
- Task queue priorities / ordering
- Task dependencies (task B waits for task A)
- Persistent task history (beyond bus retention)
- Task result storage (beyond bus event payload)
- Web UI for task monitoring
