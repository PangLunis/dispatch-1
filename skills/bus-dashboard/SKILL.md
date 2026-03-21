---
name: bus-dashboard
description: Generate beautiful HTML dashboards from the dispatch bus database. Trigger words - bus dashboard, bus visualization, bus report, event dashboard.
---

# Bus Dashboard

Generate a visualization of dispatch bus events from `~/dispatch/state/bus.db`.

## Usage

```bash
# Generate dashboard for last 6 hours (default)
~/.claude/skills/bus-dashboard/scripts/generate

# Custom time window
~/.claude/skills/bus-dashboard/scripts/generate --hours 12

# Generate and publish publicly (only if explicitly needed)
~/.claude/skills/bus-dashboard/scripts/generate --public


# Custom output path
~/.claude/skills/bus-dashboard/scripts/generate --output ~/reports/bus.html
```

## What It Shows

- **Stats strip**: Messages received, injections, turns completed, avg response time, daemon starts
- **Spike callout**: Auto-detects significant activity spikes and annotates them
- **Timeline heatmap**: 15-min event volume buckets with hover tooltips
- **Message volume by source**: Which contacts/groups generated the most messages
- **Event type breakdown**: All event types color-coded by topic (messages/sessions/system)
- **Response time by session**: Avg SDK turn duration per contact session
- **Daemon lifecycle**: Visual timeline of starts, stops, healme triggers, compaction events

## Design

- Space Grotesk + JetBrains Mono typography
- Warm papery palette (`#f7f5f2` base, sepia-tinted grays)
- Single accent: `#c2410c` (signal orange)
- Responsive — works on mobile
- Staggered entry animations

## Published URL

Default publish location: `https://sven-pages-worker.nicklaudethorat.workers.dev/bus-dashboard/`
