---
name: reminders
description: Create and manage reminders using native JSON system. Use when asked to set a reminder, check reminders, or schedule something for later.
---

# Reminders Skill

Native reminder system with local timezone support, crash safety, and automatic retry.

## ⚠️ CRITICAL: Reminders MUST have a contact

**Reminders without a contact are SILENTLY SKIPPED by the daemon.**

Always use `--contact "Name"` when creating reminders. The daemon routes reminders to sessions by contact - no contact = no injection.

---

**IMPORTANT**: Reminders are TASKS FOR CLAUDE TO EXECUTE, not text notifications to the user. When a reminder fires, Claude should DO the task described in the reminder title, then report results to the user.

Example: "Check the weather and text forecast" → Claude checks weather API, then texts the user the forecast.

## Add a Reminder

```bash
# In 2 hours
claude-assistant remind add "Check the chess game" --contact "John Smith" --in 2h

# At specific time (local timezone)
claude-assistant remind add "Call Tokyo office" --contact "John Smith" --at "3pm"
claude-assistant remind add "Morning standup" --contact "John Smith" --at "9:30am"

# With cron (recurring)
claude-assistant remind add "Daily standup" --contact "John Smith" --cron "0 9 * * *"
claude-assistant remind add "Weekly review" --contact "John Smith" --cron "0 10 * * 1"

# With timezone override
claude-assistant remind add "Call Tokyo" --contact "John Smith" --at "9am" --tz "Asia/Tokyo"

# With target (fg=foreground, bg=background, spawn=new agent)
claude-assistant remind add "Memory consolidation" --contact "John Smith" --cron "0 2 * * *" --target bg
claude-assistant remind add "Long analysis task" --contact "John Smith" --in 1h --target spawn
```

### Target Types

- **fg** (default): Inject into the contact's foreground session. Session texts the user when starting/finishing.
- **bg**: Inject into the contact's background session. Silent execution, no user notification.
- **spawn**: Create a fresh agent SDK session for this task. Good for isolated, long-running tasks.

### Time Formats

**Relative (`--in`)**:
- `30m` - 30 minutes from now
- `2h` - 2 hours from now
- `1d` - 1 day from now
- `1w` - 1 week from now
- `2h30m` - 2 hours 30 minutes

**Absolute (`--at`)**:
- `3pm`, `3:30pm` - today (or tomorrow if past)
- `15:00` - 24-hour format
- `2026-03-03 15:00` - specific datetime

**Cron (`--cron`)**:
- `0 9 * * *` - 9am daily
- `0 9,21 * * *` - 9am and 9pm daily
- `30 8 * * 1-5` - 8:30am weekdays
- `0 12 1 * *` - Noon on 1st of month

## List Reminders

```bash
# All reminders
claude-assistant remind list

# Filter by contact
claude-assistant remind list --contact "John Smith"

# Show failed reminders only
claude-assistant remind list --failed
```

Output:
```
ID         Title                          Next Fire                 Contact
--------------------------------------------------------------------------------
abc12345   Check chess game               2026-03-03 03:00 PM EST   John Smith
def67890   Daily standup                  2026-03-04 09:00 AM EST   John Smith
```

## Cancel a Reminder

```bash
# By ID
claude-assistant remind cancel abc12345

# By title
claude-assistant remind cancel --title "Daily standup"

# Cancel all matching (if multiple)
claude-assistant remind cancel --title "standup" --force
```

## Retry Failed Reminder

When a reminder fails 3 times, it's marked dead. To retry:

```bash
claude-assistant remind retry abc12345
```

## Preview Cron Schedule

```bash
claude-assistant remind next "0 9 * * *"
# Next 5 fire times for '0 9 * * *':
#   2026-03-04 09:00 AM EST
#   2026-03-05 09:00 AM EST
#   ...

claude-assistant remind next "0 9 * * *" --tz "Asia/Tokyo"
```

## Timezone Handling

- **Default**: System timezone (typically `America/New_York`)
- **Per-reminder override**: Use `--tz` flag
- **Cron patterns**: Evaluated in local time, handles DST automatically
- **Internal storage**: UTC (for reliable comparison)

## How It Works

1. Reminders stored in `~/dispatch/state/reminders.json`
2. Daemon polls every 5 seconds for due reminders
3. When due: produces `reminder.due` event to bus ("reminders" topic, keyed by chat_id) AND injects directly into session (dual path during transition)
4. Session executes task and reports results
5. On success: `once` reminders deleted, `cron` reminders advance to next fire time
6. On failure: retries 3 times with exponential backoff (1min, 2min, 4min)
7. After 3 failures: marked dead, admin alerted

### Bus Integration

Reminders produce `reminder.due` events to the "reminders" bus topic. Each event contains the full payload needed for a consumer to inject into a session (reminder_id, title, chat_id, tier, target, schedule info, timing). Currently the direct inject is the primary delivery path; the bus events enable future consumer-driven injection and analytics. See `plans/reminder-bus-producer.md` for the full design.

## Reliability Features

- **Atomic writes**: Crash-safe JSON persistence with fsync
- **File locking**: CLI and daemon share lock to prevent corruption
- **Catch-up**: Missed reminders (e.g., daemon restart) fire on startup (up to 24h late)
- **Retry with backoff**: Transient failures auto-retry
- **Admin alerts**: Dead reminders notify admin

## Migration from Reminders.app

The old Reminders.app-based system is deprecated. The native system:
- No longer polls SQLite databases
- No longer uses osascript
- No longer requires Reminders.app

Existing reminders in Reminders.app will not fire. Create new ones with `claude-assistant remind add`.
