---
name: memory
description: Store and retrieve persistent memories about contacts. Use when asked what you know/remember about someone, viewing memories, searching conversation history, or saving new memories. Trigger phrases - 'what do you know about', 'what's in memories', 'show memories', 'what do you remember', 'remember this', 'search memory', 'find when we discussed', 'when did we talk about'.
allowed-tools: Bash(uv:*), Bash(cd:*)
---

# Memory System

Persistent memory for contacts backed by three layers:

## Memory Layers

1. **Bus FTS5 Search** — Full-text search across ALL conversation events (messages, sessions, system events). Primary search for "find when we discussed X" or "search for Y in messages". Searches both hot and archived records in `bus.db`.
2. **Structured Facts** (`facts` table in bus.db) — Queryable structured data about contacts: travel, events, preferences. Extracted nightly and injected into CLAUDE.md. Use `~/dispatch/scripts/fact` CLI to query.
3. **CLAUDE.md** (per transcript folder) — Hot cache summary of ongoing work, preferences, and context. Auto-loaded by Claude Code. Includes `## Active Facts` section from the facts table.
4. **Contacts.app notes** — Contact facts (who they are, relationships, preferences). Populated by nightly consolidation.

## Bus Search (Primary — for conversation history)

Search across all bus events using FTS5:

```bash
# Search messages about a topic
cd ~/dispatch && uv run -m bus.cli search "WebGPU matmul" --topic messages

# Search what a specific contact said
cd ~/dispatch && uv run -m bus.cli search "deploy" --key "+16175969496" --since 7

# Search with FTS5 operators
cd ~/dispatch && uv run -m bus.cli search "matmul OR shader" --topic messages

# Phrase search
cd ~/dispatch && uv run -m bus.cli search '"buffer pooling"' --topic messages

# Search SDK events (tool usage, errors)
cd ~/dispatch && uv run -m bus.cli search-sdk "error" --event-type error

# Check FTS health
cd ~/dispatch && uv run -m bus.cli fts-status

# Rebuild FTS indexes if drift detected
cd ~/dispatch && uv run -m bus.cli fts-rebuild
```

**When to use bus search:**
- "find when we discussed X" → `bus search "X" --topic messages`
- "what did Nikhil say about Y" → `bus search "Y" --key "+16175969496"`
- "search for Z in the last 3 days" → `bus search "Z" --since 3`
- "when did we work on A" → `bus search "A" --topic messages`

**Bus search options:**
- `--topic` — filter by topic (messages, sessions, system, tasks)
- `--key` — filter by chat_id/phone number
- `--type` — filter by event type (message.in, message.sent, etc.)
- `--source` — filter by source (imessage, signal, system)
- `--since N` — only last N days
- `--limit N` — max results (default 20)

## Memory Consolidation (Nightly to Contacts.app)

Extracts personal facts from conversations and writes them to Contacts.app notes.
Runs automatically at 2am via the manager daemon.

```bash
# Manual run for one contact
uv run ~/.claude/skills/memory/scripts/memory.py consolidate "contact-name"

# Run for all contacts
uv run ~/.claude/skills/memory/scripts/memory.py consolidate --all

# Dry run (preview without writing)
uv run ~/.claude/skills/memory/scripts/memory.py consolidate --dry-run "contact-name"

# Verbose output (shows extraction details)
uv run ~/.claude/skills/memory/scripts/memory.py consolidate --verbose "contact-name"
```

**What gets extracted:**
- Family/relationships (spouse, kids, pets)
- Location/living situation
- Hobbies/interests
- Important dates (birthday, anniversary)
- Preferences (food, music, travel)
- Life events (expecting baby, moving, new job)

**What does NOT get extracted:**
- Technical/coding preferences (those stay in CLAUDE.md)
- Transactional details ("asked about weather")
- System/infrastructure details

**Tier-aware prompts:** Partner tier gets extra emphasis on birthdays, anniversaries, and health info. Family tier emphasizes kids' names and where they live.

**Safety:**
- Backups saved to `~/.claude/state/notes-backup/` before each write
- User Notes section in Contacts.app is preserved
- 2-pass review rejects updates that lose important info

**Check status:** `claude-assistant status` shows last consolidation run.

## Structured Facts (queryable facts database)

Structured facts store concrete, actionable knowledge about contacts (travel, events, preferences) in a queryable SQLite table. Facts are extracted nightly and injected into CLAUDE.md as `## Active Facts`.

```bash
# Query facts
~/dispatch/scripts/fact list --contact "+16175969496" --active
~/dispatch/scripts/fact list --contact "+16175969496" --type travel --active
~/dispatch/scripts/fact search "california"
~/dispatch/scripts/fact upcoming --days 14

# Save a fact manually
~/dispatch/scripts/fact save --contact "+16175969496" --type travel \
  --summary "Flying to SF March 20-25" \
  --details '{"destination": "San Francisco", "depart": "2026-03-20"}' \
  --starts "2026-03-20" --ends "2026-03-25"

# Get formatted context for a contact
~/dispatch/scripts/fact context --contact "+16175969496"

# JSON output for programmatic use
~/dispatch/scripts/fact list --active --json
~/dispatch/scripts/fact upcoming --days 7 --json
```

**Fact types (Phase 1):** travel, event, preference
**Confidence levels:** high, medium, low (only high/medium shown in CLAUDE.md)
**Bus events:** fact.created, fact.updated, fact.expired on `facts` topic

**When to use facts vs other memory layers:**
- "Where is Nikhil?" → `fact list --contact "+16175969496" --type travel --active`
- "What's coming up?" → `fact upcoming --days 14`
- "When did we discuss X?" → `bus search "X" --topic messages` (use bus FTS, not facts)
- "What do I know about them?" → Check CLAUDE.md + Contacts.app notes

**Tier access:** Admin gets full CRUD. Favorites/family get read-only (list, search, upcoming).

## Saving Memories

When a user says "remember this" or you learn something important:

1. **Contact facts** (birthday, relationships, preferences) → Update Contacts.app notes via consolidation or manually via the contacts skill
2. **Structured facts** (travel, events, short-term plans) → `~/dispatch/scripts/fact save` or wait for nightly extraction
3. **Technical context / ongoing work** → Update the contact's CLAUDE.md at `~/transcripts/{backend}/{sanitized_chat_id}/CLAUDE.md`

## Memory Permissions

**Who can see what:**
- Admin + Partner: Can access ALL memories and bus search
- Favorites: Can ONLY see their own memories and search results
- Family/Unknown: No memory access (stateless)

**If a favorites user asks about other people's memories:**
- "What do you know about Sam?" → "I can only share what I remember about you."
- "What did the admin say?" → "I keep conversations private."

## CLAUDE.md Location

Per-contact summaries live in transcript folders:
`~/transcripts/{backend}/{sanitized_chat_id}/CLAUDE.md`

Examples:
- `~/transcripts/imessage/_15555550100/CLAUDE.md`
- `~/transcripts/signal/_15555550100/CLAUDE.md`

These are auto-loaded by Claude Code when working in that directory.
