---
name: fact-check
description: Fact-check claims by extracting verifiable statements and independently verifying them against local docs, bus.db, APIs, CLIs, and web sources. Trigger words - fact check, verify claims, check facts, is this true, verify this.
---

# Fact-Check Skill

Independently verify factual claims in any text by routing each claim to the right verification source.

## Usage

`/fact-check [text]` — extract claims, verify each, report verdicts.

**Always spawn a subagent** for fact-checking. Never fact-check directly — the separation ensures the verifier only uses external sources, never its own knowledge.

**Model**: Use `model="sonnet"` for all fact-check subagents. Classification/lookup task, not complex reasoning.

## How It Works

### Step 1: Extract Claims

Spawn a subagent with this prompt structure:

```
Extract every objectively verifiable factual claim from the following text.

Rules:
- Return each claim as a single declarative sentence
- Include the original text span each claim was derived from
- Skip opinions, hedged statements ("I think", "probably"), questions, social pleasantries
- Maximum 10 claims. If more exist, extract the 10 most specific/verifiable ones and note the remainder count
- If zero verifiable claims found, say "No verifiable claims found" and stop

Format:
1. "claim text" (from: "...original span...")
2. ...

Text to analyze:
[TEXT]
```

### Step 2: Route Each Claim to Verification Source

Use this keyword-based routing table. **Order = specificity** (most-specific keywords first). When a claim matches multiple rows, try all matching sources in parallel up to the 3-source cap.

| Keywords in Claim | Source Type | Tool / Method |
|------------------|-------------|---------------|
| daemon, dispatch, bus, session, skill, manager, watchdog, poller | **local** | `Grep` in `~/dispatch/`, `~/.claude/skills/` |
| you said, last time, we discussed, you told me, previously, mentioned | **bus** | FTS query on `records_fts` + `sdk_events_fts` in `~/dispatch/state/bus.db` |
| bridge, light, hue, bulb, color, brightness | **API** | Hue bridge API via `/hue` skill CLIs |
| lutron, dimmer, shade, caseta | **API** | Lutron CLI via `/lutron` skill |
| reminder, remind, scheduled | **local** | Reminders CLI `list` command |
| flight, departure, arrival, boarding, gate | **API** | Flight tracker CLI via `/flight-tracker` skill |
| build, CI, passing, failing, test, commit, branch | **CLI** | `git log`, `gh run list`, project build commands |
| sonos, speaker, playing, music, volume | **API** | Sonos CLI via `/sonos` skill |
| computes, calculates, returns, outputs, result is, total is | **code-verify** | Independent re-implementation (see below) |
| friend said, someone told me, I heard, apparently | **none** | Unverifiable — skip immediately |
| *(anything else)* | **web** | `WebSearch` (up to 3 results) then `WebFetch` if needed |

**Fallback chain:** primary source then web search then unverified

### Step 3: Verify Independently

For each claim + source pair, actually check the source.

#### Local Codebase (Deep Read)

**CRITICAL: For claims about our own architecture (Sven, the daemon, the bus, sessions, skills, manager, watchdog, poller, signal integration, etc.), a shallow grep is NOT sufficient.** You must deeply read the actual implementation code to verify, not just find a keyword match.

Process:
1. **Grep to locate** — find the relevant files:
   ```
   Grep(pattern="relevant search terms", path="~/dispatch/")
   Grep(pattern="relevant search terms", path="~/.claude/skills/")
   ```
2. **Read the actual code** — open matching files and read the surrounding implementation (50-100 lines of context). Understand what the code actually does, not just that a keyword appears.
3. **Trace the logic** — if the claim is about behavior ("the daemon does X when Y"), read the actual control flow. Follow function calls if needed. A keyword match in a comment doesn't count — verify the runtime behavior.
4. **Check CLAUDE.md docs** — also read `~/dispatch/CLAUDE.md` and `~/.claude/CLAUDE.md` for documented architecture, but always cross-reference with actual code (docs can be stale).

Target specific directories — never broad-scan. Key locations:
- `~/dispatch/` — daemon, manager, bus, sessions, watchdog
- `~/.claude/skills/` — all skill implementations
- `~/dispatch/bus/` — bus producer, consumer, search
- `~/dispatch/state/` — session state, bus.db

#### Bus Database (FTS)
```python
import sqlite3
conn = sqlite3.connect(os.path.expanduser('~/dispatch/state/bus.db'))
# For conversation history:
results = conn.execute(
    "SELECT timestamp, topic, type, payload FROM records_fts WHERE records_fts MATCH ? ORDER BY rank LIMIT 5",
    ('search terms',)
).fetchall()
# For tool calls/results:
results = conn.execute(
    "SELECT timestamp, session_name, event_type, tool_name, payload FROM sdk_events_fts WHERE sdk_events_fts MATCH ? ORDER BY rank LIMIT 5",
    ('search terms',)
).fetchall()
```
Empty results = unverified. Malformed query / exception = catch, mark unverified with error reason.

#### APIs / CLIs
Call the specific CLI from the routing table. Examples:
- Hue: use `/hue` skill scripts to query bridge state
- Flight: use `/flight-tracker` skill scripts
- Reminders: use `/reminders` skill scripts
- Sonos: use `/sonos` skill scripts

10-second timeout per call. Exception = unverified with error reason.

#### Web
Use the built-in `WebSearch` tool (native Claude Code tool) to search for the claim. Check up to 3 results. Use `WebFetch` (native Claude Code tool) for specific URLs — official docs, pricing pages, GitHub READMEs.

#### Code Verification (Independent Re-Implementation)

For claims that a function, script, or computation **produces a specific numeric or structured output**, verify by independently re-implementing the computation — never re-run the original code.

Process:
1. **Identify the computation** — what is being computed, what are the inputs?
2. **Write a fresh implementation** — do NOT copy or re-run the original code. Write an independent implementation from scratch using first principles or a different approach.
3. **Run it** via `uv run` with appropriate inline deps:
   ```python
   # /// script
   # dependencies = ["numpy"]
   # ///
   import numpy as np
   # ... fresh implementation ...
   ```
4. **Compare outputs** — use appropriate tolerance:
   - Floats: ±0.01 (or domain-appropriate precision)
   - Integers: exact match
   - Strings: exact match
5. **Verdict**:
   - Within tolerance → **verified**
   - Outside tolerance → **wrong** (report both values)
   - Can't reproduce inputs → **unverified** with reason

**NEVER**: re-run the original script to verify itself. That proves nothing. Always use an independent approach.

#### Verification Rules

- **NEVER use LLM knowledge** — only what external sources return
- **Partial match = quote source verbatim**, flag the mismatch. Don't interpolate.
- **Contradictory sources = report both verbatim**, don't pick a winner
- **Source text neither confirms nor denies = inconclusive**, not verified

### Step 4: Verdict + Output

Five verdict categories:

| Verdict | Emoji | Meaning |
|---------|-------|---------|
| Verified | check | Source confirms. Include source quote. |
| Wrong | x | Source contradicts. Include what source actually says. |
| Inconclusive | magnifying glass | Source found relevant content, but neither confirms nor denies. Include quote for user to judge. |
| Unverified | warning | No source found, source unavailable/empty, or timed out. |
| Unverifiable | no entry | Claim type can't be independently checked (personal anecdotes, etc). |

**Key distinction:**
- Inconclusive = "found something related but doesn't directly address the claim"
- Unverified = "found nothing" or "source failed/timed out"

#### Output Format

```
## fact-check results
checked N claims in Xs

1. [verified] "signal-cli supports JSON-RPC"
   source: signal-cli README.md
   > "signal-cli can run in JSON-RPC mode..."

2. [wrong] "API costs $5/month"
   source: pricing page (fetched YYYY-MM-DD)
   > actual: "$10/month for pro tier"

3. [inconclusive] "the poller handles reconnection"
   source: ~/dispatch/poller.py (lines 42-50)
   > mentions reconnection in a different context

4. [unverified] "you mentioned this last week"
   source: bus.db records_fts — no matching records

5. [unverifiable] "my friend recommended it"
   personal anecdote — can't independently verify

verdict: 1 verified, 1 wrong, 1 inconclusive, 1 unverified, 1 unverifiable
```

## Constraints

| Constraint | Value | Behavior when exceeded |
|-----------|-------|----------------------|
| Claims per invocation | 10 max | Check first 10, note "N additional claims not checked" |
| Sources per claim | 3 max | Primary then fallback then web then stop |
| Timeout per source | 10 seconds | Mark claim unverified with "timed out", continue |
| Total budget | 30 seconds | Remaining claims get unverified "timed out" |
| Partial failure | — | Return all results so far + footer: "N claims not checked: [error]" |
| Zero claims extracted | — | "No verifiable claims found" — stop |
| Source exception | — | Catch, mark unverified with error reason, continue to next claim |

## Subagent Prompt Template

```
You are a fact-checker. Your ONLY job is to independently verify claims using external sources.

CRITICAL RULES:
1. NEVER use your own knowledge or training data to verify anything
2. ONLY use external sources: Grep, bus.db queries, API calls, WebSearch, WebFetch
3. If you can't find a source, the verdict is "unverified" — NEVER "probably correct"
4. Quote sources verbatim — never paraphrase or interpolate
5. If two sources disagree, report both — never pick a winner
6. If a source is related but doesn't directly confirm/deny, verdict is "inconclusive"

ROUTING TABLE:
[include the routing table from Step 2]

CONSTRAINTS:
- Max 10 claims, 3 sources per claim, 10s per source, 30s total
- On timeout or error: mark unverified with reason, continue to next

TEXT TO FACT-CHECK:
[TEXT]

OUTPUT FORMAT:
[include the format from Step 4]
```

## What This Skill Does NOT Do (v1 scope)

- **No auto-triggering** on outgoing messages (add later if needed)
- **No correction spiral detection** (separate skill/hook, future work)
- **No facts table caching** (could store verified claims with timestamps later)
- **No pre-flight message blocking** (manual invocation only)
- **No scoring rubric** — just verified/wrong/inconclusive/unverified/unverifiable

## Use Cases

### Checking outgoing messages
The primary use case — verify factual claims before or after sending a message to a contact. Catches stale training data, speculative assertions, and claims that contradict our own docs.

### Verifying feature/dashboard output
Feed the rendered output of a feature (dashboard, status page, settings panel) as text into `/fact-check` to verify the data is correct. Examples:
- "skills dashboard says 127 skills" → grep skills dir, count actual SKILL.md files
- "dashboard says Hue bridge at 192.168.1.x" → hit the actual Hue API to confirm
- "status page says signal healthy" → check actual socket at `/tmp/signal-cli.sock`
- "settings show poll interval 100ms" → grep config to verify

The routing table already handles these — local claims grep the codebase, API claims hit the actual APIs. Just feed it the rendered text. For visual verification, screenshot → OCR (via `/document-understanding` skill) → `/fact-check` the extracted text.

### Auditing past conversations
Review a past conversation for factual accuracy after the fact. Useful for catching patterns where the assistant made confident-but-wrong claims.

## Edge Cases

- **Long text with >10 claims**: checks first 10, notes remainder. User can re-run on specific sections.
- **Claim matches zero routing rows**: falls through to web search (the catch-all).
- **Claim matches 4+ routing rows**: uses first 3 by specificity order (table order).
- **All sources fail**: every claim gets unverified, footer explains the failure.
- **Text is a question, not claims**: extraction returns zero claims, skill reports "no verifiable claims found."
