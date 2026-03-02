---
name: perf
description: Analyze daemon and tool execution performance metrics. Trigger words - perf, performance, latency, metrics, slow, timing, bottleneck.
---

# Performance Analysis

Analyze performance metrics from the dispatch daemon and SDK sessions.

## Quick Start

```bash
# Summary of all metrics (today)
~/dispatch/bin/perf-analyze

# Specific metric details
~/dispatch/bin/perf-analyze poll_cycle_ms
~/dispatch/bin/perf-analyze inject_ms
~/dispatch/bin/perf-analyze send_sms_ms

# Last N days
~/dispatch/bin/perf-analyze --days 7

# Filter by component
~/dispatch/bin/perf-analyze --component daemon
~/dispatch/bin/perf-analyze --component session
~/dispatch/bin/perf-analyze --component sven-api
```

## Available Metrics

### Daemon Component - Core
- `poll_cycle_ms` - Main poll loop time (sampled 1/10)
- `poll_gap_ms` - Actual time between poll cycles (should be ~100ms, drift = CPU pressure)
- `messages_read` - Messages ingested per poll (by source: imessage/signal)
- `contact_lookup_ms` - Contact tier lookup time
- `session_spawn_ms` - Time to create new SDK session
- `inject_ms` - Time to inject message into session
- `active_sessions` - Current session count (gauge)
- `gemini_vision_ms` - Gemini image analysis time
- `error_count` - Errors by type

### Daemon Component - Message Lifecycle (PR #10)
- `message_staleness_ms` - Age of message when first processed (chat.db timestamp vs now)
- `messages_batch_size` - Messages arriving per poll batch (>5 = backlog indicator)
- `poll_to_inject_ms` - End-to-end time from poll start to session inject complete

### Daemon Component - System Health (PR #10)
- `wal_checkpoint_status` - SQLite WAL checkpoint result (0=ok, 1=busy, -2=error)

### Session Component
- `send_sms_ms` - Time for send-sms CLI to complete
- `tool_execution` - Per-tool call timing (Bash, Read, Grep, etc.)
- `sdk_queue_depth` - Messages waiting in session queue (catches backup)
- `session_wake_latency_ms` - Time from queue get to query completion (for idle sessions)

### sven-api Component
- `request_ms` - HTTP request latency (by endpoint)

## Log Location

Metrics are stored as JSONL in:
```
~/dispatch/logs/perf-YYYY-MM-DD.jsonl
```

## Log Format

Each line is a JSON object:
```json
{"v": 1, "ts": "2026-02-23T21:22:00.123", "metric": "poll_cycle_ms", "value": 45.2, "component": "daemon"}
```

Fields:
- `v` - Schema version (currently 1)
- `ts` - ISO timestamp
- `metric` - Metric name
- `value` - Numeric value
- `component` - Source component (daemon, session, sven-api)
- Additional labels vary by metric

### Tool Execution Schema

For `tool_execution` events, the schema includes smart-parsed fields per tool type:

```json
{
  "v": 1,
  "ts": "2026-02-24T13:27:00.123",
  "metric": "tool_execution",
  "value": 72.5,
  "event": "tool_execution",
  "session": "imessage/+15555550001",
  "tool": "Bash",
  "is_error": false,
  "input": {
    "command": "~/.claude/skills/contacts/scripts/contact-lookup +1617",
    "cmd_argv": ["~/.claude/skills/contacts/scripts/contact-lookup", "+1617"],
    "skill": "contacts",
    "cmd_name": "contact-lookup"
  }
}
```

**Parsed fields by tool type:**

| Tool | Parsed Fields |
|------|---------------|
| **Bash** | `skill`, `cmd_name`, `cmd_argv` (extracted from command path) |
| **Read/Write/Edit** | `extension`, `directory` (from file_path) |
| **WebFetch** | `domain` (from URL) |
| **Grep/Glob/Task** | Raw input passthrough (already structured) |
| **Unknown tools** | Raw input dict (future-proof fallback) |

## Raw Query Examples (jq)

```bash
# All poll cycle times today
jq 'select(.metric=="poll_cycle_ms")' ~/dispatch/logs/perf-*.jsonl

# Inject times over 1 second
jq 'select(.metric=="inject_ms" and .value > 1000)' ~/dispatch/logs/perf-*.jsonl

# Errors only
jq 'select(.metric=="error_count")' ~/dispatch/logs/perf-*.jsonl

# Group by component
jq -s 'group_by(.component) | map({component: .[0].component, count: length})' ~/dispatch/logs/perf-*.jsonl
```

## Message Lifecycle Queries (jq)

```bash
# Message staleness (how old were messages when processed)
jq 'select(.metric=="message_staleness_ms")' ~/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl

# Batch sizes (>5 indicates backlog)
jq 'select(.metric=="messages_batch_size" and .value > 5)' ~/dispatch/logs/perf-*.jsonl

# Poll gaps over 500ms (CPU pressure indicator)
jq 'select(.metric=="poll_gap_ms" and .value > 500)' ~/dispatch/logs/perf-*.jsonl

# Session queue depth (backup detection)
jq 'select(.metric=="sdk_queue_depth" and .value > 3)' ~/dispatch/logs/perf-*.jsonl

# WAL checkpoint issues
jq 'select(.metric=="wal_checkpoint_status" and .value != 0)' ~/dispatch/logs/perf-*.jsonl
```

## Tool Execution Queries (jq)

```bash
# All tool executions today
jq 'select(.metric=="tool_execution")' ~/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl

# Slowest tools (>500ms)
jq 'select(.metric=="tool_execution" and .value > 500) | {tool, duration_ms: .value, session}' ~/dispatch/logs/perf-*.jsonl

# Bash commands by skill
jq 'select(.metric=="tool_execution" and .tool=="Bash") | .input.skill' ~/dispatch/logs/perf-*.jsonl | sort | uniq -c | sort -rn

# Tool errors
jq 'select(.metric=="tool_execution" and .is_error==true) | {tool, session, input}' ~/dispatch/logs/perf-*.jsonl

# Average duration by tool type
jq -s 'group_by(.tool) | map({tool: .[0].tool, avg_ms: (map(.value) | add / length), count: length}) | sort_by(-.avg_ms)' \
  <(jq 'select(.metric=="tool_execution")' ~/dispatch/logs/perf-*.jsonl)
```

## DuckDB Queries (Recommended for Complex Analysis)

DuckDB can query JSONL files directly with SQL - much faster than jq for large datasets:

```bash
# Install: brew install duckdb

# Interactive mode
duckdb -c "
  SELECT tool,
         COUNT(*) as count,
         ROUND(AVG(value), 1) as avg_ms,
         ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value), 1) as p95_ms
  FROM read_json_auto('~/dispatch/logs/perf-*.jsonl')
  WHERE metric = 'tool_execution'
  GROUP BY tool
  ORDER BY avg_ms DESC
"

# Slowest skills
duckdb -c "
  SELECT input.skill,
         COUNT(*) as calls,
         ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value), 1) as p95_ms
  FROM read_json_auto('~/dispatch/logs/perf-*.jsonl')
  WHERE metric = 'tool_execution'
    AND tool = 'Bash'
    AND input.skill IS NOT NULL
  GROUP BY input.skill
  ORDER BY p95_ms DESC
"

# Error rate by tool
duckdb -c "
  SELECT tool,
         COUNT(*) as total,
         SUM(CASE WHEN is_error THEN 1 ELSE 0 END) as errors,
         ROUND(100.0 * SUM(CASE WHEN is_error THEN 1 ELSE 0 END) / COUNT(*), 2) as error_pct
  FROM read_json_auto('~/dispatch/logs/perf-*.jsonl')
  WHERE metric = 'tool_execution'
  GROUP BY tool
  ORDER BY error_pct DESC
"

# File extension analysis (Read/Write/Edit)
duckdb -c "
  SELECT input.extension,
         COUNT(*) as count,
         ROUND(AVG(value), 1) as avg_ms
  FROM read_json_auto('~/dispatch/logs/perf-*.jsonl')
  WHERE metric = 'tool_execution'
    AND tool IN ('Read', 'Write', 'Edit')
    AND input.extension IS NOT NULL
  GROUP BY input.extension
  ORDER BY count DESC
"

# Hourly tool usage pattern
duckdb -c "
  SELECT EXTRACT(HOUR FROM ts::TIMESTAMP) as hour,
         tool,
         COUNT(*) as count
  FROM read_json_auto('~/dispatch/logs/perf-*.jsonl')
  WHERE metric = 'tool_execution'
  GROUP BY hour, tool
  ORDER BY hour, count DESC
"
```

## Finding Bottlenecks

### 1. Identify Slow Skills
```bash
duckdb -c "
  SELECT input.skill, input.cmd_name,
         COUNT(*) as calls,
         ROUND(AVG(value), 1) as avg_ms,
         ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value), 1) as p95_ms,
         MAX(value) as max_ms
  FROM read_json_auto('~/dispatch/logs/perf-*.jsonl')
  WHERE metric = 'tool_execution' AND tool = 'Bash'
  GROUP BY input.skill, input.cmd_name
  HAVING COUNT(*) > 5
  ORDER BY p95_ms DESC
  LIMIT 20
"
```

### 2. Tool Mix Analysis
```bash
duckdb -c "
  SELECT tool,
         COUNT(*) as count,
         ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) as pct_of_total,
         ROUND(SUM(value), 0) as total_time_ms
  FROM read_json_auto('~/dispatch/logs/perf-*.jsonl')
  WHERE metric = 'tool_execution'
  GROUP BY tool
  ORDER BY total_time_ms DESC
"
```

### 3. Session Performance Comparison
```bash
duckdb -c "
  SELECT session,
         COUNT(*) as tool_calls,
         ROUND(AVG(value), 1) as avg_tool_ms,
         ROUND(SUM(value) / 1000, 1) as total_tool_time_sec
  FROM read_json_auto('~/dispatch/logs/perf-*.jsonl')
  WHERE metric = 'tool_execution'
  GROUP BY session
  ORDER BY total_tool_time_sec DESC
  LIMIT 10
"
```

### 4. Correlation: Slow Tools by Time of Day
```bash
duckdb -c "
  SELECT
    EXTRACT(HOUR FROM ts::TIMESTAMP) as hour,
    ROUND(AVG(value), 1) as avg_ms,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value), 1) as p95_ms
  FROM read_json_auto('~/dispatch/logs/perf-*.jsonl')
  WHERE metric = 'tool_execution'
  GROUP BY hour
  ORDER BY hour
"
```

## Interpreting Results

### Healthy Baselines
- `poll_cycle_ms` p95 < 100ms
- `poll_gap_ms` p95 < 500ms (should hover around 100ms)
- `inject_ms` p95 < 500ms
- `send_sms_ms` p95 < 5s (AppleScript is slow)
- `contact_lookup_ms` p95 < 10ms (SQLite cache)
- `message_staleness_ms` p95 < 5000ms (messages processed within 5s)
- `sdk_queue_depth` max < 5 (no message backup)

### Warning Signs
- `poll_cycle_ms` p99 > 500ms - check iMessage FDA access
- `poll_gap_ms` p95 > 500ms - CPU pressure or daemon stall
- `inject_ms` p95 > 2s - session may need restart
- `session_spawn_ms` > 10s - SDK slow to initialize
- `message_staleness_ms` > 30000ms - delivery delays (check apsd, Amphetamine)
- `messages_batch_size` > 5 - message backlog building up
- `sdk_queue_depth` > 10 - session falling behind on processing
- `wal_checkpoint_status` != 0 - SQLite WAL issues
- `error_count` increasing - check specific error_type

## Visualization

Generate scatter plots of metrics over time with percentile lines:

```bash
cat > /tmp/plot_perf.py << 'EOF'
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib"]
# ///

import json
import matplotlib.pyplot as plt
from collections import defaultdict
from datetime import datetime
import sys

# Read JSONL
metrics_data = defaultdict(list)
with open(sys.argv[1]) as f:
    for line in f:
        entry = json.loads(line)
        metric = entry['metric']
        value = entry['value']
        ts = datetime.fromisoformat(entry['ts'])
        metrics_data[metric].append((ts, value))

# Filter to timing metrics only
timing_metrics = ['send_sms_ms', 'inject_ms', 'session_spawn_ms', 'poll_cycle_ms', 'contact_lookup_ms']
timing_data = {k: v for k, v in metrics_data.items() if k in timing_metrics}

# Create figure with subplots
fig, axes = plt.subplots(len(timing_data), 1, figsize=(12, 3*len(timing_data)))
if len(timing_data) == 1:
    axes = [axes]

colors = {'send_sms_ms': '#e74c3c', 'inject_ms': '#3498db', 'session_spawn_ms': '#2ecc71',
          'poll_cycle_ms': '#9b59b6', 'contact_lookup_ms': '#f39c12'}

for idx, (metric, data) in enumerate(sorted(timing_data.items())):
    ax = axes[idx]
    times, values = zip(*data)
    ax.scatter(times, values, alpha=0.7, c=colors.get(metric, '#333'), s=50)
    ax.set_ylabel(f'{metric}\n(ms)')
    ax.grid(True, alpha=0.3)

    # Add horizontal lines for percentiles
    sorted_vals = sorted(values)
    p50 = sorted_vals[len(sorted_vals)//2]
    p95 = sorted_vals[int(len(sorted_vals)*0.95)] if len(sorted_vals) > 1 else sorted_vals[0]
    ax.axhline(y=p50, color='green', linestyle='--', alpha=0.7, label=f'p50={p50:.1f}ms')
    ax.axhline(y=p95, color='orange', linestyle='--', alpha=0.7, label=f'p95={p95:.1f}ms')
    ax.legend(loc='upper right')

plt.suptitle('Daemon Performance Metrics Over Time', fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('/tmp/perf_plot.png', dpi=150, bbox_inches='tight')
print('saved to /tmp/perf_plot.png')
EOF

# Run it
uv run /tmp/plot_perf.py ~/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl
```

Output goes to `/tmp/perf_plot.png`.

## Log Rotation

Logs are kept for 30 days. Old files are cleaned by:
```bash
find ~/dispatch/logs -name "perf-*.jsonl" -mtime +30 -delete
```
