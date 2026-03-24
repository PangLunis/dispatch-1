---
name: ccusage
description: Check Claude Code API usage, token consumption, and quota remaining. Use when asked about usage, tokens, costs, quota, or how much Claude Code capacity is left.
---

# Claude Code Usage Tracking

Two data sources: **local** (ccusage npm package, reads JSONL logs) and **server-side** (claude.ai API, real quota data).

## Quick Commands

```bash
# Combined view: local block stats + server-side quota (default)
~/.claude/skills/ccusage/scripts/usage

# Local only
~/.claude/skills/ccusage/scripts/usage daily
~/.claude/skills/ccusage/scripts/usage weekly
~/.claude/skills/ccusage/scripts/usage monthly

# Server-side only (real quota from Anthropic)
~/.claude/skills/ccusage/scripts/usage server              # Human-readable
~/.claude/skills/ccusage/scripts/usage server --json        # Raw JSON
~/.claude/skills/ccusage/scripts/usage server --check 80    # Exit 0 if < 80%
~/.claude/skills/ccusage/scripts/usage server --reset-time  # ISO 8601 reset time
~/.claude/skills/ccusage/scripts/usage server --hours-until-reset  # Hours as float
```

## Server-Side Usage

Two auth methods, tried in order:

### 1. OAuth (preferred, no browser needed)
- **Endpoint**: `api.anthropic.com/api/oauth/usage`
- **Auth**: `Authorization: Bearer <oauth-token>`
- **Required header**: `anthropic-beta: oauth-2025-04-20`
- **Token location**:
  - macOS: keychain entry "Claude Code-credentials" → `claudeAiOauth.accessToken`
  - Linux: `~/.claude/.credentials.json` → `claudeAiOauth.accessToken`

### 2. Chrome cookies (fallback)
- **Endpoint**: `claude.ai/api/organizations/{org_id}/usage`
- **Auth**: Chrome session cookies (requires being logged into claude.ai)
- **org_id**: From `lastActiveOrg` cookie

Returns:
- **5-hour block**: Current utilization % and reset time
- **7-day all models**: Weekly quota utilization % and exact rolling reset time
- **7-day sonnet**: Separate sonnet-only quota
- **7-day opus**: Separate opus-only quota (if applicable)
- **Extra usage**: Credit-based overage spending (if enabled)
- **Rate limit tier**: Concurrent request limits per model (cookies only)

## Understanding Blocks (Local)

Claude Code uses 5-hour billing blocks. The `blocks` command shows:

- **Current block**: When it started, time elapsed/remaining
- **Used %**: Tokens consumed in this block vs limit
- **Remaining %**: What's left in the current block
- **Projected %**: Estimated usage by block end (based on burn rate)

## Scheduling Heavy Tasks Around Reset

The `--hours-until-reset` flag enables quota-aware scheduling:

```bash
# In task scheduler: only run if reset is within 5 hours
HOURS=$(~/.claude/skills/ccusage/scripts/server-usage --hours-until-reset 2>/dev/null)
if [ "$(echo "$HOURS <= 5" | bc)" -eq 1 ]; then
  # Run heavy tasks — tokens would be wasted anyway
fi
```

## Quota-Gate Pattern for Expensive Tasks

When scheduling expensive agent tasks (bugfinder, latency finder, etc.), use this pattern to only run them when the weekly quota is about to reset — burning tokens that would otherwise be wasted:

```bash
# Quota-gate: skip if reset is more than 5 hours away
HOURS=$(~/.claude/skills/ccusage/scripts/server-usage --hours-until-reset 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$HOURS" ]; then
  echo "Could not check quota — skipping"
  exit 0
fi
if [ "$(echo "$HOURS > 5.0" | bc)" -eq 1 ]; then
  echo "Skipping — reset not within 5h window (${HOURS}h remaining)"
  exit 0
fi
# Proceed with expensive task...
```

In agent task prompts, use the inline version:
```
FIRST: Run ~/.claude/skills/ccusage/scripts/server-usage --hours-until-reset
If result > 5.0 hours, log 'Skipping — reset not within 5h window' and EXIT.
ONLY proceed if hours until reset <= 5.0.
```

This pattern is used by nightly bugfinder and latency finder tasks in `~/dispatch/scripts/setup-nightly-tasks.py`.

## SMS Response Format

When reporting to user via SMS, include both local and server numbers:

```
Server-side: X% weekly (resets Day Time)
5-hour block: X% used, Xh Xm remaining
Local estimate: XM tokens ($X) this block
```
