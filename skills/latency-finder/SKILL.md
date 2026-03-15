---
name: latency-finder
description: Find performance bottlenecks using parallel discovery and refinement subagents. Analyzes perf JSONL, bus.db sdk_events, bus.db records, and system resources for slow queries, tool executions, and processing delays. Trigger words - latency finder, latency scan, what's slow, performance scan, find bottlenecks.
---

# Latency Finder

Automatically discover performance bottlenecks in the Dispatch personal assistant system using a 3-phase architecture: parallel discovery explorers, parallel refinement reviewers, and a compiled report with actionable optimization suggestions.

## When to Use

- User says "find bottlenecks", "what's slow", "latency scan", "performance scan"
- Nightly cron via "--nightly" flag
- After deploying changes that might affect performance
- System feels sluggish or users report slow responses

## Data Sources

The system has 4 key data sources for latency analysis:

1. **Perf JSONL** (`~/dispatch/logs/perf-YYYY-MM-DD.jsonl`) — Structured timing metrics recorded by `assistant/perf.py`. Daily rotation, 30-day retention. Use `~/dispatch/bin/perf-analyze` CLI for quick summaries, or DuckDB/jq for deeper analysis.

2. **bus.db sdk_events** (`~/dispatch/state/bus.db`, table `sdk_events`) — Per-tool execution traces with session_name, tool_name, duration_ms, is_error, payload. 3-day retention. Indexes on (session_name, timestamp), (event_type), (tool_name).

3. **bus.db records** (`~/dispatch/state/bus.db`, table `records`) — Business events with timestamps. Track message.received -> message.sent latency, session lifecycle timing. 7-day retention.

4. **System resources** — Process memory/CPU, open FDs, WAL file sizes, daemon health logs.

### Dynamic Baselines

**NEVER hardcode baseline thresholds.** Baselines are computed dynamically by reading historical perf data. The approach:

1. **Yesterday's p95 is today's baseline.** Compare today's metrics against yesterday's (or last N days' average) to detect regressions.
2. **Use `perf-analyze --days 2`** to get both today and yesterday side-by-side.
3. **Regression = 2x+ increase** in p95 from yesterday. A 3x+ increase is critical.
4. **Absolute thresholds only for binary metrics** like `wal_checkpoint_status` (0 = ok, != 0 = bad).
5. **If no historical data exists**, note it as "no baseline available" rather than guessing.

Explorers MUST compute their own baselines by querying historical data — never reference hardcoded threshold values.

## How It Works

### Phase 1: Discovery (Parallel Explore Subagents)

Launch **4 parallel Explore subagents** simultaneously. Each focuses on a different latency surface area. All run with `subagent_type="Explore"` and `model="opus"`.

**IMPORTANT: All subagents (both discovery and refinement) MUST use `model: "opus"`.** Never use sonnet or haiku.

**Time window:** Default to last 24 hours. For multi-day scans, adjust queries:
- Perf JSONL: glob `~/dispatch/logs/perf-*.jsonl` and filter by date, or iterate over specific date files
- bus.db: change `-24 hours` to `-48 hours`, `-7 days`, etc. in the `strftime` expressions

#### Explorer 1: Perf Metrics Analysis

Prompt for the Explore subagent:

```
You are a performance analysis agent. Analyze perf metrics for the Dispatch personal assistant system.

1. Start with the perf-analyze CLI for a quick summary:
   ~/dispatch/bin/perf-analyze 2>/dev/null
   ~/dispatch/bin/perf-analyze --days 2 2>/dev/null

2. For deeper analysis, use DuckDB on the JSONL files (preferred over jq/awk for percentile calculations):

   # Overall metric health with percentiles
   duckdb -c "
     SELECT metric,
            COUNT(*) as count,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value), 1) as p50,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value), 1) as p95,
            ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY value), 1) as p99,
            ROUND(MAX(value), 1) as max
     FROM read_json_auto('$HOME/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl')
     WHERE metric IN ('poll_cycle_ms','poll_gap_ms','inject_ms','contact_lookup_ms',
                       'message_staleness_ms','send_sms_ms','session_spawn_ms',
                       'session_wake_latency_ms','sdk_queue_depth','messages_batch_size',
                       'wal_checkpoint_status','gemini_vision_ms')
     GROUP BY metric
     ORDER BY p95 DESC
   " 2>/dev/null

   # If DuckDB is not installed, fall back to jq:
   # cat ~/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl | jq 'select(.metric=="poll_cycle_ms")' ...

3. Tool execution analysis — find slow tools and skills:
   duckdb -c "
     SELECT tool,
            COALESCE(input.skill, '') as skill,
            COALESCE(input.cmd_name, '') as cmd,
            COUNT(*) as calls,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value), 1) as p50_ms,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value), 1) as p95_ms,
            ROUND(MAX(value), 1) as max_ms,
            SUM(CASE WHEN is_error THEN 1 ELSE 0 END) as errors
     FROM read_json_auto('$HOME/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl')
     WHERE metric = 'tool_execution'
     GROUP BY tool, skill, cmd
     HAVING calls >= 3
     ORDER BY p95_ms DESC
     LIMIT 30
   " 2>/dev/null

4. Find the top 20 slowest individual events:
   duckdb -c "
     SELECT ts, metric, value as ms, session, tool,
            COALESCE(input.cmd_name, '') as cmd
     FROM read_json_auto('$HOME/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl')
     ORDER BY value DESC
     LIMIT 20
   " 2>/dev/null

5. Regression detection — compare today vs yesterday:
   duckdb -c "
     SELECT metric,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value), 1) as p95_today
     FROM read_json_auto('$HOME/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl')
     WHERE metric IN ('poll_cycle_ms','inject_ms','send_sms_ms','message_staleness_ms','contact_lookup_ms')
     GROUP BY metric
   " 2>/dev/null

   YESTERDAY=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d 2>/dev/null)
   if [ -f "$HOME/dispatch/logs/perf-${YESTERDAY}.jsonl" ]; then
     duckdb -c "
       SELECT metric,
              ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value), 1) as p95_yesterday
       FROM read_json_auto('$HOME/dispatch/logs/perf-${YESTERDAY}.jsonl')
       WHERE metric IN ('poll_cycle_ms','inject_ms','send_sms_ms','message_staleness_ms','contact_lookup_ms')
       GROUP BY metric
     " 2>/dev/null
   fi

6. Check for baseline violations by comparing today vs yesterday:
   - Use the regression detection query (step 5) results as the baseline
   - Flag any metric where today's p95 is 2x+ yesterday's p95 as a regression
   - Flag any metric where today's p95 is 3x+ yesterday's p95 as critical regression
   - For wal_checkpoint_status, any non-zero value is a violation (this is binary, not percentile-based)
   - If yesterday's data is unavailable, note "no baseline" rather than using hardcoded thresholds

7. Return a JSON array of latency candidates:
   [
     {
       "id": "PERF1-001",
       "title": "Short description of the bottleneck",
       "metric": "metric_name",
       "current_p95": 123.4,
       "baseline": 100,
       "severity_guess": "critical|high|medium|low",
       "confidence": "high|medium|low",
       "evidence": "What the data shows and why it matters",
       "affected_sessions": ["session names if specific"],
       "category": "daemon_loop|message_delivery|tool_execution|session_lifecycle|sms_send|queue_backup"
     }
   ]
```

#### Explorer 2: SDK Events Analysis (bus.db)

Prompt for the Explore subagent:

```
You are a tool execution performance analyst. Analyze the sdk_events table in bus.db for slow tool calls and session bottlenecks.

1. Check what data is available:
   sqlite3 ~/dispatch/state/bus.db "SELECT COUNT(*), MIN(datetime(timestamp/1000,'unixepoch','localtime')), MAX(datetime(timestamp/1000,'unixepoch','localtime')) FROM sdk_events"

2. Find the slowest tool executions in the last 24 hours:
   sqlite3 -header ~/dispatch/state/bus.db "
     SELECT session_name, tool_name, duration_ms, is_error,
            datetime(timestamp/1000,'unixepoch','localtime') as time,
            substr(payload, 1, 200) as payload_preview
     FROM sdk_events
     WHERE event_type = 'tool_use'
       AND timestamp > (strftime('%s','now','-24 hours') * 1000)
       AND duration_ms IS NOT NULL
     ORDER BY duration_ms DESC
     LIMIT 30
   "

3. Aggregate tool performance by tool name:
   sqlite3 -header ~/dispatch/state/bus.db "
     SELECT tool_name,
            COUNT(*) as call_count,
            ROUND(AVG(duration_ms), 1) as avg_ms,
            ROUND(MAX(duration_ms), 1) as max_ms,
            SUM(CASE WHEN is_error = 1 THEN 1 ELSE 0 END) as error_count,
            ROUND(SUM(duration_ms), 0) as total_ms
     FROM sdk_events
     WHERE event_type = 'tool_use'
       AND timestamp > (strftime('%s','now','-24 hours') * 1000)
       AND duration_ms IS NOT NULL
     GROUP BY tool_name
     ORDER BY total_ms DESC
   "

4. Find sessions with the most total tool time:
   sqlite3 -header ~/dispatch/state/bus.db "
     SELECT session_name,
            COUNT(*) as tool_calls,
            ROUND(SUM(duration_ms)/1000, 1) as total_seconds,
            ROUND(AVG(duration_ms), 1) as avg_ms,
            ROUND(MAX(duration_ms), 1) as max_ms
     FROM sdk_events
     WHERE event_type = 'tool_use'
       AND timestamp > (strftime('%s','now','-24 hours') * 1000)
       AND duration_ms IS NOT NULL
     GROUP BY session_name
     ORDER BY total_seconds DESC
   "

5. Look for error patterns correlated with latency:
   sqlite3 -header ~/dispatch/state/bus.db "
     SELECT tool_name, is_error,
            COUNT(*) as count,
            ROUND(AVG(duration_ms), 1) as avg_ms
     FROM sdk_events
     WHERE event_type = 'tool_use'
       AND timestamp > (strftime('%s','now','-24 hours') * 1000)
       AND duration_ms IS NOT NULL
     GROUP BY tool_name, is_error
     HAVING count > 3
     ORDER BY avg_ms DESC
   "

6. Find sequential tool calls with long gaps (Claude thinking time or queue delays).
   Note: If duration_ms is NULL for all records, use timestamp differences only (gap = t2 - t1):
   sqlite3 ~/dispatch/state/bus.db "
     SELECT s1.session_name,
            datetime(s1.timestamp/1000,'unixepoch','localtime') as t1,
            s1.tool_name as tool1,
            datetime(s2.timestamp/1000,'unixepoch','localtime') as t2,
            s2.tool_name as tool2,
            (s2.timestamp - s1.timestamp - COALESCE(s1.duration_ms, 0)) as gap_ms
     FROM sdk_events s1
     JOIN sdk_events s2 ON s1.session_name = s2.session_name
       AND s2.timestamp > s1.timestamp
       AND s2.id = (SELECT MIN(id) FROM sdk_events WHERE session_name = s1.session_name AND id > s1.id AND event_type = 'tool_use')
     WHERE s1.event_type = 'tool_use'
       AND s1.timestamp > (strftime('%s','now','-24 hours') * 1000)
       AND (s2.timestamp - s1.timestamp) > 10000
     ORDER BY gap_ms DESC
     LIMIT 20
   "
   IMPORTANT: Even if duration_ms is NULL, this query still works because it falls back to raw timestamp gaps. Always run this query — do NOT skip it just because duration_ms is NULL.

7. Return a JSON array of latency candidates:
   [
     {
       "id": "SDK1-001",
       "title": "Short description of the bottleneck",
       "metric": "tool_execution|inter_tool_gap|session_total_time",
       "tool_name": "tool name if specific",
       "current_value": 123.4,
       "baseline": "expected normal value",
       "severity_guess": "critical|high|medium|low",
       "confidence": "high|medium|low",
       "evidence": "What the data shows",
       "affected_sessions": ["session names"],
       "category": "slow_tool|high_error_rate|excessive_calls|long_gaps|session_bottleneck"
     }
   ]
```

#### Explorer 3: Message Delivery Latency (bus.db records)

Prompt for the Explore subagent:

```
You are a message delivery latency analyst. Measure end-to-end message delivery times using bus.db records. This covers both iMessage and Signal messages.

1. Find message.received -> message.sent pairs to measure response time:
   sqlite3 -header ~/dispatch/state/bus.db "
     SELECT r1.key as chat_id,
            datetime(r1.timestamp/1000,'unixepoch','localtime') as received_at,
            datetime(r2.timestamp/1000,'unixepoch','localtime') as sent_at,
            (r2.timestamp - r1.timestamp) / 1000.0 as response_seconds,
            json_extract(r1.payload, '$.sender_name') as sender,
            r1.source as backend
     FROM records r1
     LEFT JOIN records r2 ON r2.key = r1.key
       AND r2.type = 'message.sent'
       AND r2.timestamp > r1.timestamp
       AND r2.timestamp < r1.timestamp + 300000
       AND r2.id = (SELECT MIN(id) FROM records WHERE key = r1.key AND type = 'message.sent' AND timestamp > r1.timestamp)
     WHERE r1.type = 'message.received'
       AND r1.timestamp > (strftime('%s','now','-24 hours') * 1000)
     ORDER BY response_seconds DESC
     LIMIT 30
   "

2. Find messages that were received but never got a response (within 5 minutes):
   sqlite3 -header ~/dispatch/state/bus.db "
     SELECT r1.key as chat_id,
            datetime(r1.timestamp/1000,'unixepoch','localtime') as received_at,
            json_extract(r1.payload, '$.sender_name') as sender,
            substr(json_extract(r1.payload, '$.text'), 1, 100) as message_preview,
            r1.source as backend
     FROM records r1
     WHERE r1.type = 'message.received'
       AND r1.timestamp > (strftime('%s','now','-24 hours') * 1000)
       AND NOT EXISTS (
         SELECT 1 FROM records r2
         WHERE r2.key = r1.key
           AND r2.type = 'message.sent'
           AND r2.timestamp > r1.timestamp
           AND r2.timestamp < r1.timestamp + 300000
       )
     ORDER BY r1.timestamp DESC
     LIMIT 20
   "

3. Measure session creation to first response time (cold start latency):
   sqlite3 -header ~/dispatch/state/bus.db "
     SELECT r1.key as chat_id,
            datetime(r1.timestamp/1000,'unixepoch','localtime') as session_created,
            datetime(r2.timestamp/1000,'unixepoch','localtime') as first_response,
            (r2.timestamp - r1.timestamp) / 1000.0 as seconds_to_first_response
     FROM records r1
     LEFT JOIN records r2 ON r2.key = r1.key
       AND r2.type = 'message.sent'
       AND r2.timestamp > r1.timestamp
       AND r2.id = (SELECT MIN(id) FROM records WHERE key = r1.key AND type = 'message.sent' AND timestamp > r1.timestamp)
     WHERE r1.type = 'session.created'
       AND r1.timestamp > (strftime('%s','now','-24 hours') * 1000)
     ORDER BY seconds_to_first_response DESC
   "

4. Check for session restart overhead (restarts add latency):
   sqlite3 -header ~/dispatch/state/bus.db "
     SELECT key as chat_id,
            COUNT(*) as restart_count,
            GROUP_CONCAT(datetime(timestamp/1000,'unixepoch','localtime'), ', ') as restart_times
     FROM records
     WHERE type = 'session.restarted'
       AND timestamp > (strftime('%s','now','-24 hours') * 1000)
     GROUP BY key
     ORDER BY restart_count DESC
   "

5. Measure response time by backend (iMessage vs Signal):
   sqlite3 -header ~/dispatch/state/bus.db "
     SELECT r1.source as backend,
            COUNT(*) as messages,
            ROUND(AVG((r2.timestamp - r1.timestamp) / 1000.0), 1) as avg_response_sec,
            ROUND(MAX((r2.timestamp - r1.timestamp) / 1000.0), 1) as max_response_sec
     FROM records r1
     JOIN records r2 ON r2.key = r1.key
       AND r2.type = 'message.sent'
       AND r2.timestamp > r1.timestamp
       AND r2.timestamp < r1.timestamp + 300000
       AND r2.id = (SELECT MIN(id) FROM records WHERE key = r1.key AND type = 'message.sent' AND timestamp > r1.timestamp)
     WHERE r1.type = 'message.received'
       AND r1.timestamp > (strftime('%s','now','-24 hours') * 1000)
     GROUP BY r1.source
   "

6. Note: Message delivery gaps (long quiet periods) are NOT latency issues — they are simply idle periods. Do NOT report quiet periods as bottlenecks. Only report actual slow response times (received -> sent pairs with high latency).

7. Return a JSON array of latency candidates:
   [
     {
       "id": "MSG1-001",
       "title": "Description of the delivery bottleneck",
       "metric": "response_time|time_to_first_response|unanswered|restart_overhead",
       "current_value": 45.2,
       "baseline": "expected seconds",
       "severity_guess": "critical|high|medium|low",
       "confidence": "high|medium|low",
       "evidence": "What the data shows",
       "affected_sessions": ["chat_ids or session names"],
       "category": "slow_response|no_response|cold_start|restart_overhead|signal_specific"
     }
   ]
```

#### Explorer 4: System Resource & Daemon Health

Prompt for the Explore subagent:

```
You are a system resource analyst. Check for resource-related performance issues that affect latency.

1. Check daemon memory and resource usage:
   MANAGER_PID=$(pgrep -f "assistant.manager" | head -1)
   if [ -n "$MANAGER_PID" ]; then
     ps -o pid,rss,vsz,%mem,%cpu,etime -p $MANAGER_PID
     lsof -p $MANAGER_PID 2>/dev/null | wc -l
   fi

2. Check for WAL checkpoint issues (WAL buildup causes slow reads):
   ls -la ~/dispatch/state/bus.db-wal 2>/dev/null
   ls -la ~/Library/Messages/chat.db-wal 2>/dev/null
   # Compare WAL file sizes to previous days to detect growth trends
   # Also check wal_checkpoint_status metric from perf logs:
   cat ~/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl 2>/dev/null | grep '"metric":"wal_checkpoint_status"' | jq -r 'select(.value != 0)' | head -10

3. Check recent poll cycle health:
   cat ~/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl 2>/dev/null | grep '"metric":"poll_cycle_ms"' | tail -100 | jq -r '.value' | awk '{sum+=$1; n++; if($1>max)max=$1} END{print "last_100_polls: avg="sum/n, "max="max, "count="n}'

4. Check for CPU-intensive periods (poll_gap_ms spikes relative to yesterday's pattern):
   cat ~/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl 2>/dev/null | grep '"metric":"poll_gap_ms"' | jq -r '[.ts, .value] | @tsv' | awk -F'\t' '$2 > 1000 {print $1, $2"ms"}' | tail -20

5. Check active session count over time:
   cat ~/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl 2>/dev/null | grep '"metric":"active_sessions"' | jq -r '[.ts, .value] | @tsv' | tail -20

6. Check for Signal and Sven API health issues:
   sqlite3 ~/dispatch/state/bus.db "
     SELECT datetime(timestamp/1000,'unixepoch','localtime') as time, type,
            json_extract(payload, '$.reason') as reason
     FROM records
     WHERE (type LIKE 'signal%' OR type LIKE 'health.service%')
       AND timestamp > (strftime('%s','now','-24 hours') * 1000)
     ORDER BY timestamp DESC
     LIMIT 20
   "

7. Check sven-api health (bind failures indicate restart loop):
   tail -50 ~/dispatch/logs/sven-api.log 2>/dev/null | grep -i "error\|bind\|failed\|address already in use"

8. Check queue depth trends (compare against yesterday's pattern):
   cat ~/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl 2>/dev/null | grep '"metric":"sdk_queue_depth"' | jq -r '[.ts, .value, .session] | @tsv' | sort -t$'\t' -k2 -rn | head -20

9. Return a JSON array of latency candidates:
   [
     {
       "id": "SYS1-001",
       "title": "Description of the resource bottleneck",
       "metric": "memory_rss|open_fds|wal_size|poll_gap|cpu_usage|queue_depth|wal_checkpoint",
       "current_value": 123,
       "baseline": "expected value",
       "severity_guess": "critical|high|medium|low",
       "confidence": "high|medium|low",
       "evidence": "What the data shows",
       "category": "memory_pressure|fd_leak|wal_buildup|cpu_contention|service_health|queue_backup"
     }
   ]
```

### Phase 2: Refinement (Parallel Subagents — One Per Candidate)

Collect all latency candidates from the 4 explorers. Deduplicate by metric+category (if two explorers found the same bottleneck, merge them and keep the higher severity version).

For each unique candidate, spawn a **refinement subagent** in parallel. Use `subagent_type="general-purpose"` and `model="opus"` (refinement agents may need to run code, test queries, or read source files to verify root causes).

**Cap at 15 refinement subagents.** If more than 15 candidates, prioritize by: severity_guess (critical first), then confidence (high first), then drop the rest with a note.

Prompt for each refinement subagent:

```
You are a performance verification agent. Investigate this latency candidate and determine if it's actionable.

Latency candidate:
- ID: {id}
- Title: {title}
- Metric: {metric}
- Current value: {current_value}
- Baseline: {baseline}
- Category: {category}
- Confidence: {confidence}
- Evidence from discovery: {evidence}
- Severity guess: {severity_guess}
- Affected sessions: {affected_sessions}

Your job:
1. Verify the data. Run the relevant queries yourself to confirm the numbers.

2. Determine root cause:
   - Is this a code issue (inefficient algorithm, missing index, unnecessary work)?
   - Is this a resource issue (memory pressure, FD exhaustion, WAL buildup)?
   - Is this an architectural issue (polling frequency, serial processing, missing caching)?
   - Is this a transient spike (one-off event, deployment, system restart)?
   - Is this expected behavior (large file, complex query, cold start)?

3. Estimate impact:
   - How many users/sessions are affected?
   - What's the user-visible effect (slow responses, timeouts, dropped messages)?
   - How often does this occur (constant, periodic, rare)?

4. Propose specific fixes with effort estimates. Fixes MUST be concrete:
   - Code change: specific file path, specific function name, specific change (e.g., "In assistant/sdk_session.py:_run_loop(), add a queue.task_done() call after processing each message")
   - Config change: specific parameter name, specific value, specific file
   - Architecture change: what to redesign, with specific entry points

   **"Investigate why X" is NOT a valid fix.** If you cannot identify a specific code change, use REFINE verdict instead.

5. Make a verdict:
   - **ACCEPT**: This is a real, actionable performance bottleneck. Root cause identified AND a specific fix proposed (file + function + change). If you can identify the root cause but not a specific fix, use REFINE.
   - **REFINE**: Data is concerning but root cause unclear, OR root cause is clear but the fix requires deeper investigation. Needs monitoring or further analysis.
   - **REFUTE**: This is not actionable — expected behavior, transient spike, or within acceptable bounds.

   **IMPORTANT**: Every ACCEPT verdict MUST include at least one concrete file path in the fix.files array. "Tool configuration" or "session prompt" are NOT valid file paths. If you cannot identify the file, use REFINE.

6. Return your verdict as JSON:
   {
     "id": "{id}",
     "verdict": "ACCEPT|REFINE|REFUTE",
     "title": "Final title (may be updated)",
     "severity": "critical|high|medium|low",
     "category": "{category}",
     "metric": "{metric}",
     "current_p95": value_or_null,
     "baseline_p95": value_or_null,
     "root_cause": "Why this is slow (ACCEPT only)",
     "impact": "User-visible effect and scope (ACCEPT only)",
     "fix": {
       "description": "What to change",
       "effort": "trivial|small|medium|large",
       "files": ["list of files to modify"],
       "priority": "immediate|next_sprint|backlog"
     },
     "reason": "Why this verdict (especially for REFUTE)"
   }

Be rigorous. A performance issue must cause measurable user-visible impact under normal operating conditions. Do not accept transient spikes, expected cold starts, or theoretical concerns.
```

### Phase 3: Report

Collect all refinement results:
- Drop REFUTE verdicts (note them in a "Refuted" section for transparency)
- Group ACCEPT verdicts by severity: critical > high > medium > low
- List REFINE verdicts as "Needs Investigation"

**IMPORTANT report quality rules:**

1. **Explorer coverage**: For EACH of the 4 explorers, the report MUST either include findings from it or explicitly state "Explorer N ({name}): No anomalies detected." Do NOT silently drop an explorer's results.

2. **Explorer attribution**: Preserve the explorer source ID prefix (PERF1, SDK1, MSG1, SYS1) on each finding so readers know which data source produced it.

3. **Complete system summary**: The summary table MUST include ALL metrics found in today's perf data, plus yesterday's p95 as the baseline column. If a metric has no data, show "N/A" in its row. Never omit a metric.

4. **Consistent metric names**: Always use the exact metric names as they appear in the perf JSONL (e.g., `session_wake_latency_ms` not `session_wake_ms`). No abbreviations or variations.

5. **Specific file paths**: Every ACCEPT verdict MUST include at least one concrete file path (not "Tool configuration" or "session prompt"). If the refinement agent couldn't identify a specific file, it should be REFINE not ACCEPT.

6. **Specific fixes**: ACCEPT verdicts must propose fixes at the function level (e.g., "In `sdk_session.py:_run_loop()`, add a drain check before enqueuing"). "Investigate why X" is not an acceptable fix — that belongs in REFINE.

#### Report Format

```
Latency Scan Report — Dispatch System
Date: {date} | Window: last {hours}h
Explorers: 4 | Candidates: {N} | Accepted: {A} | Refuted: {R} | Needs Investigation: {I}

--- CRITICAL ---

1. [{source_id}] {title}
   Metric: {metric} | Current p95: {value} | Baseline: {baseline}
   Root cause: {root_cause}
   Impact: {impact}
   Fix ({effort}): {fix_description}
   Files: {files}
   Priority: {priority}

--- HIGH ---
...

--- MEDIUM ---
...

--- LOW ---
...

--- EXPLORER COVERAGE ---
- Explorer 1 (Perf JSONL): {N} candidates | {summary}
- Explorer 2 (SDK Events): {N} candidates | {summary}
- Explorer 3 (Message Delivery): {N} candidates | {summary or "No anomalies detected"}
- Explorer 4 (System Resources): {N} candidates | {summary}

--- NEEDS INVESTIGATION ---
- [{source_id}] {title} — {reason}

--- REFUTED ({R} total) ---
- [{source_id}] {title} — {reason}

--- SYSTEM SUMMARY ---
| Metric | p50 | p95 | p99 | Max | Count | Yesterday p95 | Status |
|--------|-----|-----|-----|-----|-------|---------------|--------|
| (all metrics found in today's perf data, one row each) |
| (include tool_execution as an aggregate row) |
```

**Note:** The system summary MUST include ALL metrics found in today's perf data PLUS `tool_execution` as an aggregate row. The "Yesterday p95" column serves as the dynamic baseline. If yesterday's data is unavailable, show "N/A". Status is determined by comparing today's p95 to yesterday's p95: OK (< 2x), WARN (2-3x), CRIT (> 3x). For `wal_checkpoint_status`, any non-zero value is CRIT.

#### Output Modes

**Interactive mode** (default): Print the report to the conversation.

**Nightly mode** (prompt contains "--nightly"): Send the full report via SMS to admin using the reply CLI or send-sms with the admin's phone looked up from config. Do NOT truncate or summarize — the admin needs full details.

Only send if there are ACCEPT or REFINE verdicts. If everything was refuted or within baselines, skip the SMS and log "latency-finder nightly: clean scan, all metrics within baselines."

**CI mode** (prompt contains "--ci"): Exit with non-zero status if any critical or high bottlenecks are accepted. Print report to stdout.

## Graceful Degradation

- **DuckDB not installed** — Fall back to jq/awk pipelines for perf JSONL analysis. Note the degradation.
- **No perf JSONL for today** — Fall back to yesterday's file, or most recent available. Note the data gap.
- **Empty sdk_events** — Explorer 2 reports "no sdk_events data available" and skips. Other explorers continue.
- **bus.db locked/missing** — Skip bus-dependent explorers, continue with perf JSONL analysis.
- **Explorer subagent fails** — Continue with results from other explorers. Note the failure.
- **Refinement subagent fails** — Note the failure, don't count as accepted or refuted.
- **Zero candidates** — Report "clean scan, no regressions detected vs yesterday" (good outcome).
- **Too many candidates (>15)** — Refine top 15 by severity+confidence, list the rest as "unreviewed."

## Calibration

### GOOD latency candidates (report these):
- Any metric with p95 2x+ higher than yesterday's p95 — regression
- Any metric with p95 3x+ higher than yesterday's p95 — critical regression
- Bash tool executions significantly slower than historical average for that skill
- Specific session consuming 80% of total tool execution time — resource hog
- Inter-tool gaps significantly longer than the session's historical pattern
- wal_checkpoint_status != 0 repeatedly — SQLite WAL issues causing slow reads
- One backend (Signal vs iMessage) responding 3x slower than the other — backend-specific bottleneck
- Service restart loops (health check showing repeated restarts)
- sdk_queue_depth trending upward over time (compare hour-by-hour)

### BAD candidates (do NOT report):
- Single transient spike during daemon startup — expected
- One-off slow tool execution for a clearly large operation — expected
- p50 values slightly above yesterday but p95 is stable — not impactful
- Long gap between messages during quiet hours (2am-8am) — idle period, not latency
- One-off API latency spike (Gemini, etc.) — external service variance
- Metrics that are stable day-over-day even if they seem "high" in absolute terms — that's the system's normal

## Examples

```bash
# Scan for performance bottlenecks
"find bottlenecks"
"what's slow"

# Nightly automated scan
"latency scan --nightly"

# Scan with longer time window
"latency scan --since 48h"

# After deploying a change
"check if performance regressed"

# CI check
"latency scan --ci"
```
