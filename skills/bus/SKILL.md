---
name: bus
description: Dispatch message bus (Kafka-on-SQLite) — schema, query patterns, anomaly detection, CLI usage. Reference for bug-finder, latency-finder, and debug skills. Trigger words - bus, bus events, bus query, bus schema, event bus.
---

# Dispatch Message Bus

The bus is a Kafka-on-SQLite event system at the core of Dispatch. All messages, session lifecycle events, health checks, and SDK tool calls flow through it.

## Architecture

- **Database**: `~/dispatch/state/bus.db` (SQLite with WAL mode)
- **Implementation**: `~/dispatch/bus/bus.py` (producer/consumer/topics)
- **CLI**: `~/dispatch/bus/cli.py` (or `~/dispatch/bin/bus`)
- **Search**: `~/dispatch/bus/search.py` (FTS5 full-text search)
- **Retention**: Hot tables auto-pruned, archive tables infinite retention
- **Timestamps**: ALL timestamps in bus.db are Unix **milliseconds** (ms since epoch)

## CLI Usage

All CLI commands run from `~/dispatch`:

```bash
cd ~/dispatch

# --- Topic management ---
uv run python -m bus.cli topics                          # List all topics
uv run python -m bus.cli info <topic>                    # Topic details (partitions, offsets, record count)
uv run python -m bus.cli create-topic <name> [--partitions N] [--retention-days N]
uv run python -m bus.cli delete-topic <name>             # Nuclear — deletes ALL records

# --- Produce & consume ---
uv run python -m bus.cli produce <topic> '<json>' --type <type> --source <src> --key <key> [--headers '<json>']
uv run python -m bus.cli consume <topic> --group <grp> [--follow] [--from-beginning] [--max N]
uv run python -m bus.cli tail <topic> [--group <grp>]    # Follow from end (like tail -f)

# --- Replay & inspect (no consumer group, direct read) ---
uv run python -m bus.cli replay <topic> [--limit N] [--from-offset N] [--from-timestamp MS] [--partition N] [--type TYPE] [--source SRC]
uv run python -m bus.cli stats [--topic <topic>]         # Record counts, timestamps, archive sizes, consumer groups

# --- Consumer group management ---
uv run python -m bus.cli groups                          # Show groups with members, generations, assignments
uv run python -m bus.cli offsets [--group GRP] [--topic T]  # Show committed offsets and lag
uv run python -m bus.cli seek --group <grp> --topic <t> [--to-beginning|--to-end|--to-offset N|--to-timestamp MS]

# --- Maintenance ---
uv run python -m bus.cli prune                           # Delete records past retention (moves to archive)

# --- Scan reports ---
uv run python -m bus.cli reports [--scanner NAME] [--since DAYS] [--findings-only] [--severity LEVEL] [--limit N]
# Examples:
uv run python -m bus.cli reports --scanner bug-finder --since 7
uv run python -m bus.cli reports --findings-only --severity high

# --- Full-text search (FTS5) ---
uv run python -m bus.cli search "error timeout" [--topic T] [--type T] [--key K] [--source S] [--since DAYS] [--limit N]
uv run python -m bus.cli search-sdk "connection refused" [--session S] [--event-type T] [--tool T] [--chat-id C] [--since DAYS] [--limit N]
uv run python -m bus.cli fts-status                      # Check FTS index health and drift
uv run python -m bus.cli fts-rebuild                     # Drop and rebuild FTS indexes
```

## Schema

### Hot Tables (retention-based, auto-pruned)

**records** (7-day default retention) — Business events: messages, health checks, session lifecycle

Table is `WITHOUT ROWID` with composite primary key.

| Column | Type | Description |
|--------|------|-------------|
| topic | TEXT | Event topic (e.g. "messages", "system"). NOT NULL |
| partition | INTEGER | Partition number within topic. NOT NULL |
| offset | INTEGER | Per-partition sequence number. NOT NULL |
| timestamp | INTEGER | Unix epoch milliseconds. NOT NULL |
| key | TEXT | Routing key (e.g. "imessage/+16175969496"). Nullable |
| type | TEXT | Event type (e.g. "message.received", "session.heartbeat"). Nullable |
| source | TEXT | Producer source (e.g. "imessage", "sdk", "health"). Nullable |
| payload | TEXT | JSON payload. NOT NULL |
| headers | TEXT | JSON headers. Nullable |

Primary key: `(topic, partition, offset)`

**sdk_events** (3-day retention) — Per-tool execution traces

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Auto-increment primary key |
| timestamp | INTEGER | Unix epoch milliseconds. NOT NULL |
| session_name | TEXT | Session identifier. NOT NULL |
| chat_id | TEXT | Contact/group chat ID. Nullable |
| event_type | TEXT | tool_use, tool_result, result, error. NOT NULL |
| tool_name | TEXT | Tool name (e.g. "Bash", "Read", "Edit"). Nullable |
| tool_use_id | TEXT | Unique tool use identifier. Nullable |
| duration_ms | REAL | Execution time in milliseconds. Nullable |
| is_error | INTEGER | 1 if error, 0 otherwise. Default 0 |
| payload | TEXT | JSON with details. Nullable |
| num_turns | INTEGER | Number of conversation turns. Nullable |

### FTS Tables (full-text search via FTS5)

**records_fts** — Full-text index over records + records_archive. Auto-populated by INSERT/DELETE triggers on both tables. Columns: topic, key, type, source, payload_text, timestamp, partition, offset_val.

**sdk_events_fts** — Full-text index over sdk_events + sdk_events_archive. Auto-populated by triggers. Columns: session_name, event_type, tool_name, payload_text, chat_id, timestamp, source_id.

Payload text extraction logic (for records_fts):
- `message.*` types: `json_extract(payload, '$.text')`
- `scan.*` types: `json_extract(payload, '$.summary')`
- `session.*` types: contact_name + session_name from payload
- `health.*` types: status + message from payload
- Everything else: first 4000 chars of raw payload

### Archive Tables (infinite retention)
- **records_archive** — Same schema as records + `archived_at INTEGER NOT NULL` column. Same composite PK.
- **sdk_events_archive** — Same schema as sdk_events + `archived_at INTEGER NOT NULL` column.

Auto-populated when records are pruned from hot tables. Use for longer-term baselines and trend analysis.

### Indexes

**records:**
- Primary key: `(topic, partition, offset)` — clustered (WITHOUT ROWID)
- `idx_records_topic_ts`: `(topic, timestamp)`
- `idx_records_key`: `(topic, key) WHERE key IS NOT NULL`
- `idx_records_type`: `(topic, type) WHERE type IS NOT NULL`
- `idx_records_source`: `(topic, source) WHERE source IS NOT NULL`
- `idx_records_chat_id`: `(topic, json_extract(payload, '$.chat_id')) WHERE topic = 'messages'` — functional index for message lookups by chat_id

**sdk_events:**
- `idx_sdk_session`: `(session_name, timestamp)`
- `idx_sdk_type`: `(event_type)`
- `idx_sdk_tool`: `(tool_name) WHERE tool_name IS NOT NULL`

**records_archive:**
- Primary key: `(topic, partition, offset)` — clustered (WITHOUT ROWID)
- `idx_archive_topic_ts`: `(topic, timestamp)`
- `idx_archive_type`: `(topic, type) WHERE type IS NOT NULL`
- `idx_archive_key`: `(topic, key) WHERE key IS NOT NULL`
- `idx_archive_archived_at`: `(archived_at)`

**sdk_events_archive:**
- `idx_sdk_archive_session`: `(session_name, timestamp)`
- `idx_sdk_archive_tool`: `(tool_name) WHERE tool_name IS NOT NULL`
- `idx_sdk_archive_archived_at`: `(archived_at)`

## Common Event Types

| Type | Source | Description |
|------|--------|-------------|
| message.received | imessage/signal/discord | Incoming message from a contact |
| message.sent | sdk_session | Outgoing message to a contact |
| message.delivered | sdk_session | Message confirmed delivered |
| session.heartbeat | sdk | Session is alive |
| session.created | daemon | New session spawned |
| session.restarted | daemon | Session restarted |
| session.killed | daemon | Session terminated |
| session.injected | inject | Prompt injected into session |
| health.fast_check_completed | health | 100ms health check |
| health.check_completed | health | Standard health check |
| health.deep_check_completed | health | Deep health check |
| health.service_restarted | health | Service auto-restarted |
| scan.completed | bug-finder/latency-finder | Nightly scan results |
| compaction.triggered | compaction | Bus compaction ran |

## Anomaly Detection Queries

### 1. Source Volume Distribution (find runaway producers)
```sql
SELECT source, COUNT(*) as cnt,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM records), 1) as pct
FROM records GROUP BY source ORDER BY cnt DESC LIMIT 15;
```
**Red flag:** Any single source >30% of total events, or any unexpected source appearing.

### 2. Retry & DLQ Spikes (processing failures)
```sql
SELECT source, type, COUNT(*) as cnt,
  MIN(datetime(timestamp/1000,'unixepoch','localtime')) as first_seen,
  MAX(datetime(timestamp/1000,'unixepoch','localtime')) as last_seen
FROM records
WHERE source LIKE '%retry%' OR source LIKE '%dlq%'
GROUP BY source, type ORDER BY cnt DESC;
```
**Red flag:** Any consumer-retry count >10 indicates a processing bug. Check payloads for the error.

### 3. Error Payload Analysis (what's actually failing)
```sql
SELECT substr(payload, 1, 500) as error_preview, COUNT(*) as cnt
FROM records WHERE source LIKE '%retry%'
GROUP BY substr(payload, 1, 200) ORDER BY cnt DESC LIMIT 10;
```
Look for repeated error patterns like `KeyError`, `ConnectionRefused`, `Timeout`.

### 4. Event Rate Spikes (15-min buckets)
```sql
SELECT datetime((timestamp/900000)*900, 'unixepoch', 'localtime') as bucket,
  source, COUNT(*) as cnt
FROM records GROUP BY bucket, source
HAVING cnt > 50 ORDER BY cnt DESC LIMIT 20;
```
**Red flag:** >100 events from one source in a 15-min window is almost always a bug.

### 5. Source x Type Breakdown (find unexpected event patterns)
```sql
SELECT source, type, COUNT(*) as cnt
FROM records GROUP BY source, type ORDER BY cnt DESC LIMIT 30;
```
Compare against expected patterns. For example, `consumer-retry` + `message.received` = retry loop.

### 6. Failed/Error Events
```sql
SELECT datetime(timestamp/1000,'unixepoch','localtime') as ts,
  type, source, key, substr(payload, 1, 300) as payload
FROM records
WHERE type LIKE '%failed%' OR type LIKE '%crashed%' OR type LIKE '%error%'
ORDER BY timestamp DESC LIMIT 20;
```

### 7. SDK Tool Failures
```sql
SELECT tool_name, event_type, COUNT(*) as cnt, AVG(duration_ms) as avg_ms,
  MAX(duration_ms) as max_ms
FROM sdk_events WHERE is_error=1
GROUP BY tool_name, event_type ORDER BY cnt DESC LIMIT 15;
```

### 8. SDK Tool Performance (slowest tools)
```sql
SELECT tool_name, COUNT(*) as calls, AVG(duration_ms) as avg_ms,
  MAX(duration_ms) as max_ms,
  SUM(CASE WHEN is_error=1 THEN 1 ELSE 0 END) as errors
FROM sdk_events WHERE tool_name IS NOT NULL
GROUP BY tool_name ORDER BY avg_ms DESC LIMIT 15;
```

### 9. Per-Session Event Volume (find chatty sessions)
```sql
SELECT session_name, COUNT(*) as cnt, AVG(duration_ms) as avg_ms
FROM sdk_events GROUP BY session_name ORDER BY cnt DESC LIMIT 20;
```

### 10. Message Delivery Gaps (received but never responded)
```sql
SELECT r1.key as chat_id,
  datetime(r1.timestamp/1000,'unixepoch','localtime') as received_at,
  json_extract(r1.payload, '$.sender_name') as sender,
  substr(json_extract(r1.payload, '$.text'), 1, 100) as preview,
  r1.source as backend
FROM records r1
WHERE r1.type = 'message.received'
  AND r1.timestamp > (strftime('%s','now','-24 hours') * 1000)
  AND NOT EXISTS (
    SELECT 1 FROM records r2
    WHERE r2.key = r1.key AND r2.type = 'message.sent'
      AND r2.timestamp > r1.timestamp
      AND r2.timestamp < r1.timestamp + 300000
  )
ORDER BY r1.timestamp DESC LIMIT 20;
```

### 11. Session Restart Loops
```sql
SELECT key, COUNT(*) as restarts,
  MIN(datetime(timestamp/1000,'unixepoch','localtime')) as first,
  MAX(datetime(timestamp/1000,'unixepoch','localtime')) as last
FROM records WHERE type = 'session.restarted'
  AND timestamp > (strftime('%s','now','-24 hours') * 1000)
GROUP BY key HAVING restarts > 2 ORDER BY restarts DESC;
```

### 12. Hourly Event Trend (detect patterns over time)
```sql
SELECT datetime((timestamp/3600000)*3600, 'unixepoch', 'localtime') as hour,
  source, COUNT(*) as cnt
FROM records
WHERE timestamp > (strftime('%s','now','-24 hours') * 1000)
GROUP BY hour, source ORDER BY hour, cnt DESC;
```

## Anomaly Pattern Reference

| Pattern | Likely Bug |
|---------|-----------|
| consumer-retry >>100 events | Message processing failure (check error payload for root cause) |
| Single source >30% of events | Runaway producer, retry loop, or spam |
| >100 events/source in 15-min bucket | Burst/spike — likely a bug not rate limiting |
| sdk_events with high is_error rate for one tool | Tool implementation bug |
| message.received with no message.sent | Dropped message or session crash |
| session.restarted >3x for same key in 24h | Session crash loop |
| DLQ events appearing | Permanent processing failures (messages exhausted retries) |

## Integration with Other Skills

- **bug-finder** (`~/dispatch/skills/bug-finder/SKILL.md`): Explorer 2 (System Health) runs all anomaly detection queries from this skill. References bus schema for retry/DLQ analysis, source volume checks, and event rate spikes.
- **latency-finder** (`~/dispatch/skills/latency-finder/SKILL.md`): Uses sdk_events for tool execution timing, records for message.received-to-message.sent latency. References archive tables for longer-term baselines beyond hot table retention windows.
- Both scanners publish `scan.completed` events to the bus (topic=system), queryable via `bus reports --scanner <name>`.

## Live Dashboard

The bus has a live dashboard at `http://10.10.10.250:9091/dashboard` (or via Tailscale). Shows stacked area charts for event rate by source, by type, and by chat, plus SDK calls and active tasks.
