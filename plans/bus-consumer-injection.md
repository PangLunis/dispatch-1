# Plan: Convert Message Injection to Bus Consumer (Option A)

## Goal
Refactor the message processing pipeline so that `process_message()` is driven by a bus consumer instead of being called directly from the poll loop. Same process, minimal change.

## Why (Non-Functional Requirement: Multi-Consumer Fanout)
The bus is the foundation for multiple independent consumers reading the same message stream:
- **message-router** (this plan): routes messages to Claude SDK sessions
- **analytics** (future): message volume, send latency histograms, session health metrics
- **alerting** (future): crash rate spikes, send failures, latency degradation → SMS notification
- **replay** (future): re-process a conversation or time range by resetting consumer offset

Each consumer has its own consumer group with independent offsets. Adding a new consumer is just subscribing to the "messages" topic — no changes to the ingestion pipeline. This decoupling is the architectural payoff.

## Current Flow
```
poll loop:
  for msg in chat.db/signal/test:
    await process_message(msg)          # direct call — no bus integration yet
    _save_state(msg["rowid"])          # advance rowid even on failure

NOTE: produce_event() exists in bus_helpers.py but is NOT yet called from
manager.py. The bus infrastructure (bus.py, consumers.py) is built and tested
but not wired into the daemon. This plan describes the integration steps.
```

## Target Flow
```
poll loop (ingestion only):
  for msg in chat.db/signal/test:
    produce_event(msg, source)       # now the PRIMARY delivery path
    _save_state(msg["rowid"])          # advance rowid immediately (poller's job is done)

consumer task (processing):
  while running:
    records = consumer.poll()          # reads message.received from bus
    for record in records:
      msg = reconstruct_msg(record)    # rebuild full msg dict from payload
      try:
        await process_message(msg)     # same logic, same process
      except Exception:
        log + continue                 # never block on poison messages (same as current behavior)
    consumer.commit()                  # commit per-batch (all records processed or skipped)
```

**Key design choice**: commit-after-batch with per-record error handling. This matches current behavior (rowid always advances) while adding bus audit trail. We do NOT do "commit only on success" — that creates poison message deadlocks.

## Critical Constraint: Lossless Bus Payloads

**Problem**: Current `sanitize_msg_for_bus()` is lossy — drops attachment file paths (only stores count) and converts datetime → int. But `process_message()` needs:
- `attachments`: list of dicts with `path` keys (for Gemini vision)
- `timestamp`: datetime object (for message_timestamp in inject_message)

**Solution**: Update `sanitize_msg_for_bus()` to preserve these:
1. Attachments: serialize paths as strings (`str(path)`) instead of summarizing
2. Timestamp: already stored as `timestamp_ms` — reconstruct via `datetime.fromtimestamp(ts_ms/1000)`
3. Keep existing `has_attachments`/`attachment_count` as convenience fields

## Steps

### Step 0: Inventory all msg fields used by process_message
**Before writing any code**, grep all `msg[` and `msg.get(` accesses in `process_message()` and every function it calls (`inject_message`, `inject_group_message`, `format_message_body`, `wrap_sms`, `wrap_group_message`). Build explicit schema of required fields and verify `sanitize_msg_for_bus` preserves all of them.

Required fields (from code analysis):
- `phone` ✅ (in DIRECT_FIELDS)
- `text` ✅ (in DIRECT_FIELDS)
- `rowid` ✅ (in DIRECT_FIELDS)
- `is_group` ✅ (in DIRECT_FIELDS)
- `group_name` ✅ (in DIRECT_FIELDS)
- `chat_identifier` ✅ (in DIRECT_FIELDS)
- `audio_transcription` ✅ (in DIRECT_FIELDS)
- `thread_originator_guid` ✅ (in DIRECT_FIELDS)
- `source` ✅ (in DIRECT_FIELDS)
- `attachments` ❌ (currently dropped — needs fix)
- `timestamp` ❌ (converted to timestamp_ms — needs reconstruct)
- `is_audio_message` ✅ (in DIRECT_FIELDS, used by format_message_body)

### Step 1: Make bus payloads lossless
**File**: `assistant/bus_helpers.py`

Update `sanitize_msg_for_bus()` attachment handling. Current attachment format from MessagesReader is:
```python
[{"path": "/path/to/file.jpg", "mime_type": "image/jpeg", "filename": "IMG_001.jpg"}]
```

New serialization — convert Path objects to absolute path strings, keep everything else:
```python
elif k == "attachments":
    payload["has_attachments"] = bool(v)
    payload["attachment_count"] = len(v) if v else 0
    if v:
        safe_attachments = []
        for att in v:
            safe_att = {}
            for ak, av in att.items():
                if isinstance(av, Path):
                    safe_att[ak] = str(av.resolve())  # absolute path string
                else:
                    try:
                        json.dumps(av)
                        safe_att[ak] = av
                    except (TypeError, ValueError):
                        safe_att[ak] = str(av)
                safe_attachments.append(safe_att)
        payload["attachments"] = safe_attachments
```

`reconstruct_msg_from_bus()` does NOT convert paths back to Path objects — `process_message` and `inject_message` work fine with string paths (they pass them to Gemini vision which accepts strings).

### Step 2: Add `reconstruct_msg_from_bus()` helper
**File**: `assistant/bus_helpers.py`

New function that converts a bus Record payload back to the msg dict format that `process_message()` expects:
```python
def reconstruct_msg_from_bus(payload: dict) -> dict:
    """Reconstruct a raw message dict from a bus payload.

    Reverses sanitize_msg_for_bus() — converts timestamp_ms back to datetime,
    restores attachment paths, etc.
    """
    msg = dict(payload)  # shallow copy

    # Restore datetime timestamp from timestamp_ms
    if "timestamp_ms" in msg:
        from datetime import datetime
        msg["timestamp"] = datetime.fromtimestamp(msg.pop("timestamp_ms") / 1000)

    # chat_id was added by sanitize — process_message doesn't use it directly
    # (it uses phone for individuals, chat_identifier for groups)

    return msg
```

### Step 3: Add consumer task to Manager
**File**: `assistant/manager.py`

Add `_run_message_consumer()` as an asyncio task started alongside the main poll loop.

**Critical design decisions:**
- **Always commit after batch** — never block on poison messages. A failed `process_message()` logs the error and continues. This matches current behavior where rowid advances even on failure.
- **Produce `message.processing_failed` event** on failure — captures the error for debugging without blocking the pipeline.
- **Run poll in executor** — consumer.poll() uses time.sleep() internally which blocks asyncio.

```python
async def _run_message_consumer(self):
    """Consume message.received events from bus and route to process_message.

    Uses consumer group 'message-router' with manual commit.
    Commits after every batch — failed messages are logged but never block.
    """
    if not self._bus:
        log.warning("Bus not initialized, consumer task exiting")
        return

    consumer = self._bus.consumer(
        group_id="message-router",
        topics=["messages"],
        auto_commit=False,
        auto_offset_reset="latest",  # Don't replay historical on first start
    )

    log.info("Message consumer started (group=message-router, offset=latest)")
    loop = asyncio.get_event_loop()
    consecutive_errors = 0

    while not self._shutdown_flag:
        try:
            # poll() uses time.sleep() internally — run in executor to avoid blocking
            records = await loop.run_in_executor(
                None, consumer.poll, 100  # 100ms timeout
            )

            processed = 0
            failed = 0
            for record in records:
                if record.type != "message.received":
                    continue  # Skip message.sent/failed events

                try:
                    msg = reconstruct_msg_from_bus(record.payload)
                    await self.process_message(msg)
                    processed += 1
                except asyncio.CancelledError:
                    # Graceful shutdown: commit what we've processed so far, then exit
                    if records:
                        consumer.commit()
                    raise
                except Exception as e:
                    failed += 1
                    log.error(
                        f"Consumer: failed to process message "
                        f"(offset={record.offset}, key={record.key}): {e}"
                    )
                    # Produce failure event for debugging (fire-and-forget)
                    self._produce_event("messages", "message.processing_failed", {
                        "chat_id": record.key,
                        "error": str(e),
                        "original_offset": record.offset,
                        "original_partition": record.partition,
                    }, key=record.key, source="consumer")

            # ALWAYS commit after batch — never block on poison messages
            if records:
                consumer.commit()
                if processed or failed:
                    log.debug(f"Consumer batch: {processed} processed, {failed} failed")

            consecutive_errors = 0  # Reset on successful poll cycle

        except asyncio.CancelledError:
            log.info("Message consumer shutting down gracefully")
            break
        except Exception as e:
            consecutive_errors += 1
            log.error(f"Consumer loop error ({consecutive_errors}): {e}")
            # Exponential backoff capped at 30s
            backoff = min(30, 2 ** consecutive_errors)
            await asyncio.sleep(backoff)

    log.info("Message consumer stopped")
```

### Step 4: Remove direct process_message calls from poll loop
**File**: `assistant/manager.py`

In the main `run()` method, change from:
```python
# Before:
self.produce_event(msg, "imessage")
await self.process_message(msg)
self._save_state(msg["rowid"])
```

To:
```python
# After:
self.produce_event(msg, "imessage")
self._save_state(msg["rowid"])  # Poller's only job: ingest and advance
# process_message is now called by the consumer task
```

Same change for signal and test queues (remove `await self.process_message()` calls).

### Step 5: Start consumer task in run() with supervisor
**File**: `assistant/manager.py`

In the `run()` method, start the consumer task with a done callback that detects silent death and restarts:

```python
# Start message consumer task with crash supervision
self._consumer_task = asyncio.create_task(
    self._run_message_consumer(),
    name="message-consumer"
)
self._consumer_task.add_done_callback(self._on_consumer_task_done)
```

Done callback that auto-restarts:
```python
def _on_consumer_task_done(self, task):
    """Detect consumer task death and restart unless shutting down."""
    if self._shutdown_flag:
        return
    try:
        exc = task.exception()
        if exc:
            log.error(f"Consumer task crashed: {exc}. Restarting in 5s...")
        else:
            log.warning("Consumer task exited unexpectedly. Restarting in 5s...")
    except asyncio.CancelledError:
        return  # Normal shutdown

    # Schedule restart
    async def _restart_consumer():
        await asyncio.sleep(5)
        if not self._shutdown_flag:
            self._consumer_task = asyncio.create_task(
                self._run_message_consumer(),
                name="message-consumer"
            )
            self._consumer_task.add_done_callback(self._on_consumer_task_done)
            log.info("Consumer task restarted")

    asyncio.ensure_future(_restart_consumer())
```

And cancel on shutdown:
```python
self._consumer_task.cancel()
await asyncio.gather(self._consumer_task, return_exceptions=True)
```

### Step 6: Handle reactions
Reactions currently don't go through the bus. Two options:
- **Option A (recommended)**: Leave reactions on direct path for now. They're low-volume and don't need retry semantics.
- **Option B**: Add `message.reaction` event type and route through consumer too.

### Step 7: Update tests
- **Round-trip test (write first — TDD)**: `reconstruct_msg_from_bus(sanitize_msg_for_bus(msg))` preserves all required fields (phone, text, rowid, attachments paths, timestamp as datetime, is_group, etc)
- **Poison message test**: process_message raises → offset still committed, message.processing_failed event produced
- **Consumer lifecycle**: startup logs initial offset, shutdown cancels cleanly
- **Supervisor test**: consumer task crash → auto-restart via done_callback
- **Bus init failure**: daemon refuses to start (no silent fallback)

## Risks and Mitigations

### Risk 1: Double processing during migration
**Problem**: If both direct call AND consumer are active, messages get processed twice.
**Mitigation**: Remove direct `process_message()` calls in the same commit as adding the consumer task. There's no gradual migration — it's a swap.

### Risk 2: Consumer falls behind
**Problem**: If consumer is slower than producer, messages queue up.
**Mitigation**: Same process, same event loop — consumer processes at roughly the same speed as before. The only added latency is the sqlite write+read (~1-2ms). Monitor with `bus stats`.

### Risk 3: Bus initialization failure
**Problem**: If bus fails to init, no messages get processed.
**Mitigation**: Bus init failure should be fatal — crash the daemon on startup so the watchdog can recover. The bus is a sqlite file on local disk; if it fails to init, something is seriously wrong (disk full, permissions, corrupted db). A fallback dual code path would rot and mask real problems. If bus.db is corrupted, delete it and let it recreate on restart.

### Risk 4: consumer.poll() blocking the event loop
**Problem**: `consumer.poll()` internally calls `time.sleep(0.01)` which blocks asyncio.
**Mitigation**: Run `consumer.poll()` in `run_in_executor()` (thread pool). This is the standard asyncio pattern for blocking I/O.

### Risk 5: SQLite contention
**Problem**: Producer and consumer both access bus.db. Producer holds BEGIN IMMEDIATE during writes.
**Mitigation**: WAL mode (already enabled in bus.py) allows concurrent reads during writes. Consumer reads are non-blocking. The poll executor thread means the asyncio loop isn't blocked during contention waits.

### Risk 6: Attachment file paths become stale
**Problem**: Attachments are stored as file paths. If processed later (consumer lag), files might be gone.
**Mitigation**: In practice, consumer lag is <100ms in same-process. Files won't disappear. But if this becomes an issue later (Option B/C), we'd need to copy files to a staging area.

### Risk 7: Silent consumer task death
**Problem**: If the consumer asyncio task crashes with an unhandled exception, asyncio silently swallows it. Messages pile up with no processing and no alert.
**Mitigation**: `add_done_callback()` supervisor (Step 5) detects death and auto-restarts with a 5s delay. Logs the crash reason. Consecutive crashes will naturally back off since the consumer has exponential backoff on errors internally.

### Risk 8: auto_offset_reset="latest" misses messages on first start
**Problem**: First time the consumer starts, it skips all existing message.received records.
**Mitigation**: This is intentional — we don't want to replay 165+ historical messages. The poller already processed them via direct calls before this change. On subsequent daemon restarts, the consumer resumes from its committed offset.

## Rollback Plan
If something breaks: revert the commit. The change is isolated to:
1. `bus_helpers.py` (sanitize attachments + reconstruct helper)
2. `manager.py` (consumer task + remove direct calls)

The bus continues to record events regardless — it's just whether processing goes through the consumer or directly.

## Not In Scope
- Separate process consumer (Option C) — future work
- Reaction routing through bus — keep direct for now
- Analytics/alerting consumers — separate feature
- Bus CLI was already built separately
