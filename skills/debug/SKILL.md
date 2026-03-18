---
name: debug
description: Debug and diagnose the Dispatch personal assistant system. Troubleshoot sessions, trace messages, find incidents, check daemon health.
---

# /debug — Dispatch Diagnostics

## Quick Start

```bash
debug status                          # System dashboard
debug trace <phone> --since 1h        # End-to-end message trace
debug session imessage/<phone>        # Session deep-dive
debug incident --since 2h            # Auto-scan for anomalies
debug routing <phone>                # Contact routing info
```

All commands support `--json` for machine-readable output, `--verbose` for more detail, `--quiet` for terse output.

## CLI Reference

| Command | Description |
|---------|-------------|
| `debug status` | Daemon PID/uptime/memory, watchdog, signal, sessions table, bus stats, open FDs |
| `debug trace <chat_id>` | Message journey: chat.db -> bus -> session -> response. Timeline with latency |
| `debug session <name\|chat_id>` | Session info, recent bus events, sdk_events, log tail, compaction info |
| `debug incident` | Auto-detect: failed messages, crashed sessions, heartbeat gaps, restart loops, errors |
| `debug routing <chat_id>` | Contact lookup, tier, session assignment, transcript dir, backend |

## Runbooks

### Session Crashed
```bash
debug incident --since 30m                    # Find crash events
debug session <name>                          # Check session state & logs
# If session exists but is dead:
claude-assistant restart-session <name>
# If repeated crashes:
debug trace <chat_id> --since 2h              # Find what triggered it
```

### Message Not Delivered
```bash
debug trace <chat_id> --since 1h              # Find the gap
debug session <name>                          # Is session alive?
# Check if message.received exists but no message.sent:
# Gap between received and injected = routing issue
# Gap between injected and turn_complete = session stuck
# No message.sent after turn_complete = Claude didn't call send-sms
```

### Daemon Unresponsive
```bash
debug status                                  # Check PID, memory, FDs
# If PID exists but high memory/FDs:
claude-assistant restart
# If no PID:
claude-assistant start
# Check watchdog:
~/dispatch/bin/watchdog-status
```

### Slow Performance
```bash
debug status                                  # Check resource usage
debug trace <chat_id> --since 1h              # Find latency bottlenecks
# Check perf logs:
tail -20 ~/dispatch/logs/perf-$(date +%Y-%m-%d).jsonl | python3 -m json.tool
```

### Restart Loop
```bash
debug incident --since 1h                     # Detects restart loops automatically
debug session <name>                          # Check consecutive error count
# Look for session.created events close together:
# If 3+ restarts in 5 min = restart loop
# Common cause: context_length_exceeded, image_too_large
```

### Stuck Session
```bash
debug session <name>                          # Check last_inject vs last_response
debug trace <chat_id> --since 30m             # Find where it got stuck
# session.injected with no sdk.turn_complete = stuck
claude-assistant restart-session <name>
```
