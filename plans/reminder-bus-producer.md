# Plan: Route Reminder Firing Through Bus + Unified Consumer Design

**Status: IMPLEMENTED** (2026-03-14)

## Goal

Two parts:
1. **Write path** (implement now): When a reminder fires, produce a `reminder.due` event to the bus. The reminder system becomes a pure schedule engine.
2. **Consumer direction** (design now, implement later): Consumers are just anything that calls `bus.consumer()` and polls. They can live in-process (daemon) or as standalone scripts. SQLite WAL supports unlimited concurrent readers, so there's no need for a centralized dispatcher — each consumer polls independently.

## Why

Currently reminders are tightly coupled: `ReminderPoller._fire_reminder()` → `_inject_to_session()` → `session.inject()`. This means:
- Reminders know about sessions, contacts, injection formatting, fg/bg/spawn routing
- No replay capability (if injection fails, retry is baked into the reminder system)
- Can't add new consumers of reminder events (analytics, alerting)
- Reminder tests require mocking the entire SDK session stack

After this change, the reminder system becomes a pure schedule engine that writes to the bus. A separate consumer (future work) handles the injection/routing.

## Current Flow
```
ReminderPoller.process_due_reminders()
  → _should_fire(r) → True
  → _fire_reminder(r)
    → _inject_to_session(r, late=False)
      → resolve contact → build injection message → session.inject(msg)
    → advance next_fire / delete once
    → produce_event("reminder.fired")  ← audit only, AFTER injection
```

## Target Flow (Option A: Dual Path During Transition)
```
ReminderPoller.process_due_reminders()
  → _should_fire(r) → True
  → _fire_reminder(r)
    → resolve contact → chat_id + tier
    → build reminder payload (full data needed by future consumer)
    → produce_event("reminders", "reminder.due", payload)  ← fire-and-forget, may silently fail
    → _inject_to_session(r)                                ← PRIMARY delivery, keeps reminders working
    → advance next_fire / delete once
    → log success
```

**Key change**: The bus produce is added alongside the existing direct inject. `produce_event` is fire-and-forget — if it fails, the direct inject still works. The direct inject remains the primary delivery mechanism until a consumer is built and validated. The existing `reminder.fired` / `reminder.failed` audit events are replaced by `reminder.due` on the new "reminders" topic.

## New Topic: "reminders"

Add a new bus topic for reminder events. This keeps reminders separate from "messages" and "sessions" topics.

**Event types on "reminders" topic:**
- `reminder.due` — a reminder has fired and needs processing (produced by ReminderPoller)

Future consumer-produced events (out of scope):
- `reminder.injected` — consumer successfully injected into session
- `reminder.injection_failed` — consumer failed to inject

## reminder.due Payload Schema

The payload must contain everything a consumer needs to inject into a session, without accessing reminders.json or ContactsManager:

```python
{
    # Reminder identity
    "reminder_id": "abc12345",
    "title": "Check the chess game",

    # Schedule info (for consumer to include in injection message)
    "schedule_type": "once" | "cron",
    "schedule_value": "2026-03-14T19:00:00Z" | "0 9 * * *",
    "timezone": "America/New_York",

    # Target routing
    "contact": "Alice Smith",       # original contact field from reminder
    "chat_id": "+15551234567",         # resolved phone/group ID
    "tier": "admin",                   # resolved tier
    "target": "fg" | "bg" | "spawn",  # where to inject

    # Timing
    "scheduled_fire_time": "2026-03-14T19:00:00Z",  # when it was supposed to fire
    "actual_fire_time": "2026-03-14T19:00:01Z",     # when we actually produced
    "is_late": false,                                # true if catch-up
    "minutes_late": 0,                               # 0 if on time

    # Metadata
    "fired_count": 1,                  # how many times this reminder has fired total
}
```

**Bus record key**: `chat_id` (NOT reminder_id). This is critical for the unified consumer — the consumer filters/routes by chat_id, so all events destined for the same session must share the same key. This means all reminder.due events for the same contact land on the same partition, and the consumer can route them without cross-partition lookups.

## Steps

### Step 0: Create "reminders" topic in bus initialization

Add `bus.create_topic("reminders", partitions=1)` alongside existing `create_topic("messages")` and `create_topic("sessions")` calls in daemon startup. Partitions=1 is fine — reminder volume is low. Can increase later if throughput demands it.

### Step 1: Add contact resolution to ReminderPoller (extract from _inject_to_session)

Currently `_inject_to_session()` handles both contact resolution AND injection. Extract contact resolution into a separate method so `_fire_reminder()` can resolve contact → chat_id + tier before producing to the bus.

**File**: `assistant/manager.py`

```python
def _resolve_reminder_contact(self, r: dict) -> tuple[str, str]:
    """Resolve reminder contact to (chat_id, tier).

    Returns (chat_id, tier) or raises ValueError if contact not found.
    """
    contact = r.get("contact")
    if not contact:
        raise ValueError(f"Reminder has no contact: {r.get('id')}")

    if re.match(r'^[0-9a-f]{32}$', contact) or contact.startswith('+'):
        return contact, "admin"

    contact_info = self.contacts.lookup_phone_by_name(contact)
    if not contact_info:
        raise ValueError(f"Contact not found: {contact}")
    chat_id = contact_info.get("phone")
    if not chat_id:
        raise ValueError(f"No phone for contact: {contact}")
    return chat_id, contact_info.get("tier", "admin")
```

### Step 2: Update event taxonomy in bus_helpers.py docstring

Add `reminder.due` to the event taxonomy and add "reminder-poller" to allowed sources. No separate payload builder function — use a dict literal in `_fire_reminder()` since there's exactly one call site. Add a builder when the consumer plan arrives and needs a shared schema.

### Step 3: Rewrite `_fire_reminder()` to produce to bus AND inject (dual path)

**File**: `assistant/manager.py`

Update `_fire_reminder()` to produce to the bus AND inject directly (dual path):

```python
async def _fire_reminder(self, r: dict, late: bool = False):
    """Fire a reminder: produce to bus + inject directly (dual path).

    Bus produce is fire-and-forget (may silently fail).
    Direct inject is the PRIMARY delivery path — keeps reminders working
    until a bus consumer is built and validated.

    # TODO: Remove direct _inject_to_session() once reminder consumer is live.
    # See "Definition of Done for Dual Path Removal" section below.
    """
    from datetime import datetime, timezone

    try:
        # Resolve contact to chat_id + tier (extracted for bus payload)
        chat_id, tier = self._resolve_reminder_contact(r)

        now_utc = datetime.now(timezone.utc)
        scheduled_time = r.get("next_fire", now_utc.isoformat())
        minutes_late = 0
        if late:
            fire_time = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
            minutes_late = (now_utc - fire_time).total_seconds() / 60

        tz = self._get_reminder_timezone(r)

        # 1. Produce to bus (fire-and-forget — failure is logged, not fatal)
        self._produce_event(
            "reminders", "reminder.due",
            {
                "reminder_id": r["id"],
                "title": r.get("title", ""),
                "contact": r.get("contact", ""),
                "chat_id": chat_id,
                "tier": tier,
                "target": r.get("target", "fg"),
                "schedule_type": r["schedule"]["type"],
                "schedule_value": r["schedule"]["value"],
                "timezone": tz,
                "scheduled_fire_time": scheduled_time,
                "actual_fire_time": now_utc.isoformat().replace('+00:00', 'Z'),
                "is_late": late,
                "minutes_late": round(minutes_late, 1),
                "fired_count": r.get("fired_count", 0) + 1,
            },
            key=chat_id,
            source="reminder-poller"
        )

        # 2. Direct inject — PRIMARY delivery path (TODO: remove once consumer is live)
        #    Pass resolved chat_id + tier to avoid double resolution
        await self._inject_to_session(r, late, resolved_chat_id=chat_id, resolved_tier=tier)

        # Success — update reminder state
        r["last_fired"] = now_utc.isoformat().replace('+00:00', 'Z')
        r["fired_count"] = r.get("fired_count", 0) + 1
        r["last_error"] = None
        r["retry_count"] = 0

        if r["schedule"]["type"] == "once":
            self.reminders.remove(r)
            log.info(f"REMINDER_DELETED | id={r['id']} | reason=completed")
        else:
            from assistant.reminders import next_cron_fire
            r["next_fire"] = next_cron_fire(r["schedule"]["value"], tz)
            log.info(f"REMINDER_SCHEDULED | id={r['id']} | next={r['next_fire']}")

        log.info(f"REMINDER_FIRED | id={r['id']} | late={late} | target={r.get('target', 'fg')} | bus=produced")

    except Exception as e:
        r["retry_count"] = r.get("retry_count", 0) + 1
        r["last_error"] = str(e)
        r["last_fired"] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        log.error(f"REMINDER_FAILED | id={r['id']} | attempt={r['retry_count']} | {e}")

        max_retries = self.config.get("max_retries", 3)
        if r["retry_count"] >= max_retries:
            log.error(f"REMINDER_DEAD | id={r['id']}")
            await self._alert_admin(r)
```

**Note on `_produce_event` failure**: `_produce_event` is fire-and-forget during dual path — if bus write fails, direct inject still fires. See Definition of Done criterion #4 for when this must change.

### Step 4: Keep `_inject_to_session()`, remove old audit events

`_inject_to_session()` stays (it's the primary delivery path during dual mode). Add optional `resolved_chat_id` and `resolved_tier` parameters so it skips its own contact resolution when the caller has already resolved (avoids double resolution and a subtle race if contact data changes between the two calls).

Remove the old `reminder.fired` / `reminder.failed` produce calls from `_fire_reminder()` — they're replaced by `reminder.due`. **Note**: the old events were keyed by `reminder_id`, the new `reminder.due` is keyed by `chat_id`. This is intentional — chat_id is the routing key for consumers.

Keep `_produce_session_injected()` since `_inject_to_session()` still uses it.

Keep `_alert_admin()` — dead reminders still need to alert the admin directly. Add a code comment: `_alert_admin` is exempt from the bus pattern because it's a system alert, not a reminder delivery, and must not depend on a consumer being alive.

### Step 5: Update the reminders SKILL.md

Update `~/.claude/skills/reminders/SKILL.md` to reflect:
- Reminders now produce to bus instead of injecting directly
- `reminder.due` events on "reminders" topic
- Consumer handles injection (future work)
- No user-facing behavior change (reminders still fire on time)

### Step 6: Tests

**New tests:**
1. **`_resolve_reminder_contact()` unit tests**: phone number → (phone, "admin"), contact name → resolved (chat_id, tier), missing contact → ValueError
2. **`_fire_reminder()` produces correct bus event**: mock `_produce_event`, verify topic="reminders", type="reminder.due", payload has all required fields
3. **`_fire_reminder()` still injects directly**: verify `_inject_to_session()` is still called (dual path)
4. **`_fire_reminder()` advances schedule on success**: once → deleted, cron → next_fire advanced
5. **`_fire_reminder()` retry on failure**: inject raises → retry_count incremented, last_error set
6. **`_fire_reminder()` dead reminder alerts admin**: retry_count >= max_retries → _alert_admin called
7. **Late reminder**: is_late=True, minutes_late > 0 in payload
8. **Dual path divergence: bus fails, inject succeeds**: mock `_produce_event` to silently fail (return None / swallow exception), verify `_inject_to_session()` still fires, reminder state still advances, warning is logged. This is the most likely real failure mode (bus.db locked, disk pressure).
9. **Payload is JSON-serializable**: the dict literal in `_fire_reminder()` round-trips through `json.dumps/loads`

**Updated tests:**
- Update existing `_fire_reminder` tests to verify both bus produce AND direct inject are called

## Consumer Architecture: Independent Consumers, Simple Model

### Design: Each Consumer Polls Independently

SQLite WAL mode supports unlimited concurrent readers with zero contention. Readers never block writers, writers never block readers. Each consumer opens its own connection and polls at its own pace.

No dispatcher, no fan-out, no handler registration. Just consumers.

```
                        Bus (SQLite WAL)
                    ┌─────────────────┐
                    │  messages topic  │
                    │  reminders topic │
                    │  sessions topic  │
                    │  system topic    │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
┌─────────▼──────┐  ┌───────▼───────┐  ┌───────▼───────┐
│ session-router  │  │  analytics    │  │   alerting    │
│ (in daemon)     │  │  (standalone) │  │  (standalone) │
│                 │  │               │  │               │
│ group: "router" │  │ group: "anly" │  │ group: "alrt" │
│ topics: msgs,   │  │ topics: all   │  │ topics: sys,  │
│   reminders     │  │               │  │   sessions    │
│                 │  │ own process   │  │ own process   │
│ needs session   │  │ ~/dispatch/   │  │ ~/dispatch/   │
│ objects → must  │  │ consumers/    │  │ consumers/    │
│ live in daemon  │  │ analytics.py  │  │ alerting.py   │
└─────────────────┘  └───────────────┘  └───────────────┘
```

**Rules:**

1. **A consumer = anything that calls `bus.consumer()` and polls.** That's it. In-process or standalone script, doesn't matter.

2. **In-process consumers** live in the daemon for things that need internal state (session-router needs `session.inject()`). These are asyncio tasks, same as the current `_run_message_consumer()`.

3. **Standalone consumers** are independent scripts in `~/dispatch/consumers/`. They open bus.db, create a consumer group, poll, and process. No daemon coordination needed. The bus handles offset tracking per consumer group.

4. **All events keyed by chat_id** — messages already use chat_id. Reminders now use chat_id too. Any consumer can route by `record.key`.

5. **Consumer groups are independent** — each group has its own offsets. The session-router committing doesn't affect analytics. Analytics can lag, replay, or be down entirely without affecting message delivery.

6. **No registration** — consumers don't register with the daemon. They just exist and poll. For visibility, `claude-assistant status` could optionally list active consumer groups from the bus metadata, but this is informational, not coordination.

### Alternatives Considered and Rejected

**Per-chat consumers** (one consumer per session): Rejected. 7+ consumers each polling independently = 7x queries for same throughput. Consumer lifecycle complexity (create/destroy with sessions). Our bus uses partition-based assignment, not key-based subscriptions.

**Centralized dispatcher** (one reader fans out to handlers): Rejected. Adds unnecessary abstraction. SQLite WAL makes concurrent readers cheap (~50KB memory, ~0 contention). The dispatcher would be solving a problem that doesn't exist at our scale. If a slow handler blocks the loop, you'd need to split it out anyway — at which point it's just an independent consumer.

### Session-Router Consumer (Future Implementation)

Expand the existing `_run_message_consumer()` to subscribe to both "messages" and "reminders" topics:

```python
# Current:
consumer = bus.consumer(group_id="message-router", topics=["messages"])

# After:
consumer = bus.consumer(group_id="session-router", topics=["messages", "reminders"])

# Processing loop:
for record in records:
    if record.type == "message.received":
        msg = reconstruct_msg_from_bus(record.payload)
        await process_message(msg)
    elif record.type == "reminder.due":
        await process_reminder_from_bus(record.payload)
    # Future: elif record.type == "reaction.received": ...
```

**process_reminder_from_bus()** would:
1. Read payload (chat_id, title, target, schedule info, is_late, etc.)
2. Build injection message (the formatted reminder text)
3. Route to session by target (fg/bg/spawn) using chat_id
4. Produce `reminder.injected` event

### Adding a New Consumer (Future Pattern)

```python
#!/usr/bin/env -S uv run --script
# ~/dispatch/consumers/analytics.py
# Standalone consumer — no daemon dependency

from bus import Bus

bus = Bus("~/dispatch/state/bus.db")
consumer = bus.consumer(group_id="analytics", topics=["messages", "reminders", "sessions", "system"])

while True:
    records = consumer.poll(timeout_ms=1000)
    for record in records:
        # count, histogram, whatever
        pass
    consumer.commit()
```

No daemon changes. No registration. Just a script that reads the bus.

### Adding a New Event Source (Future Pattern)

1. **Producer side**: produce events to appropriate topic with `key=chat_id`
2. **Consumer side**: add an `elif` branch in session-router, or write a standalone consumer
3. **No infrastructure changes** — bus handles it all

## What Changes for Users

**Nothing.** This is an internal refactoring. Reminders still fire on time via direct inject. The only new observable is `bus tail --topic reminders` showing `reminder.due` events.

## Definition of Done for Dual Path Removal

The direct inject path (`_inject_to_session()`) should be removed from `_fire_reminder()` only when ALL of these criteria are met:

1. **Session-router consumer handles reminder.due** — the unified consumer (expanded from message-router) reads `reminder.due` events and calls `session.inject()`
2. **Consumer has processed ≥20 reminder.due events without failure** — verified via `bus stats`
3. **No dropped events over 1 week** — `bus tail --topic reminders` count matches reminder fired_count
4. **`_produce_event` is made fallible for the consumer path** — when direct inject is removed, produce failures must trigger reminder retry (not fire-and-forget)

Until all criteria are met, the dual path stays.

## Risks

### Risk 1: produce_event failure treated as success
**Problem**: If `_produce_event()` silently fails (bus not initialized, disk full), we still advance next_fire. The reminder fires via direct inject (Option A) but the bus has no record.
**Mitigation**: For the write-path-only change, this is acceptable. The direct inject is the backup. Log a warning if produce fails. Once we remove the direct path, produce_event failure should trigger retry.

### Risk 2: Payload drift
**Problem**: Consumer expects certain fields in `reminder.due` payload, but the schema evolves.
**Mitigation**: The inline dict literal in `_fire_reminder()` is the source of truth during dual path. When the consumer plan lands, extract a shared payload builder function that both producer and consumer import. Add a schema version field if needed later.

### Risk 3: Contact resolution at fire time vs consume time
**Problem**: Contact might change tier or phone between produce and consume.
**Mitigation**: Resolve at produce time (fire time). The payload is a snapshot. If contact changes, next fire will pick up the new data. This is correct — the reminder was due at fire time with that contact's state.

### Risk 4: Cross-topic ordering in session-router
**Problem**: The session-router subscribes to multiple topics. `consumer.poll()` returns records from multiple topics — ordering across topics is not guaranteed. If a message and a reminder fire at the same time for the same chat_id, which gets processed first?
**Mitigation**: This is acceptable. Messages and reminders are independent events. There's no semantic requirement that a reminder must be processed before/after a message. The session handles them sequentially regardless of arrival order. If strict ordering is ever needed, put both event types on the same topic.

### Risk 5: Consumer group rename (message-router → session-router)
**Problem**: When we rename the consumer group, the new group starts with no committed offsets.
**Mitigation**: Either: (a) seed the new group's offsets from message-router's committed offsets, or (b) accept a clean cut (old group drained, new group starts fresh with "latest"). Since the dual path is still active during transition, no reminders are lost.

## Out of Scope (Implement Later)
- Expanding message-router → session-router (subscribe to reminders topic, add `elif reminder.due` branch)
- `process_reminder_from_bus()` implementation
- Removing direct inject (after session-router handles reminder.due)
- Standalone consumer scripts in `~/dispatch/consumers/`
- New bus CLI commands for reminders
- Reminder replay from bus
