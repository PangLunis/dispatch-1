# Structured Facts System (v7)

## Goal

When Nikhil texts "flying to SF March 20-25" or gets a flight confirmation email, the system:
1. Extracts a structured fact during nightly consolidation
2. Stores it in a queryable table with provenance
3. Publishes `fact.created` event to the bus
4. Downstream consumers react (e.g., a FactReminder consumer sets weather/tips reminders)
5. Any session can answer "where is Nikhil?" from the facts table

## Non-Goals

- Full knowledge graph with entity resolution
- Bitemporal model / historical point-in-time queries
- Inline extraction during conversations (extraction is nightly batch ONLY)
- Replacing CLAUDE.md or Contacts.app notes (facts AUGMENT them)
- Facts coupled to reminders (facts are just facts; reminders are a downstream consumer)
- Embedding-based similarity search (deferred until dedup issues observed in practice)
- Deterministic dedup Layer 2 upfront (deferred to Phase 2+ — LLM dedup sufficient at <100 facts)
- Change history table upfront (deferred — JSONL extraction log provides audit trail initially)

## Architecture

```
  Nightly Consolidation (existing cron, extended)
       │
       ├── reads bus.db messages (last 24h)
       ├── reads Gmail (Phase 3)
       ├── reads Google Calendar (Phase 3)
       │
       ▼
  LLM Extraction Pass (per contact, structured output mode)
       │
       ├── extracts NEW facts + updates to existing + explicit expirations
       ├── does NOT confirm existing facts (staleness is time-based)
       ├── LLM dedup: outputs existing_fact_id for updates
       │
       ▼
  Validation + Coercion Pass
       │
       ├── validates details JSON (valid JSON, required keys per type)
       ├── coerces date strings to ISO 8601 UTC
       ├── rejects malformed entries (logged, not committed)
       │
       ▼
  facts table (bus.db)  ──→  fact.created / fact.updated events on bus
       │                              │
       ▼                              ▼
  CLAUDE.md injection         FactReminder consumer (Phase 4)
  (## Active Facts,           (creates reminders for travel,
   max 15 per contact)        deadlines, events)

  extraction log (~/dispatch/logs/fact-extraction.jsonl)
  nightly summary SMS to admin
```

## Schema

One table in `~/dispatch/state/bus.db` (same Alembic migration path as FTS5):

```sql
CREATE TABLE facts (
    id INTEGER PRIMARY KEY,
    contact TEXT NOT NULL,           -- chat_id (phone number or group hex)
    fact_type TEXT NOT NULL,         -- travel, event, preference (initial types; more added later)
    summary TEXT NOT NULL,           -- "Flying to SF March 20-25"
    details TEXT,                    -- JSON blob (validated per fact_type, see Details Schema)
    confidence TEXT DEFAULT 'high',  -- high, medium, low (evidence-based, see Confidence Rules)
    starts_at TEXT,                  -- ISO 8601 UTC datetime (NULL for non-temporal facts)
    ends_at TEXT,                    -- ISO 8601 UTC datetime (NULL for open-ended facts)
    active INTEGER DEFAULT 1,       -- 0 = superseded/expired, 1 = current
    created_at TEXT NOT NULL,        -- ISO 8601 UTC datetime
    updated_at TEXT,                 -- ISO 8601 UTC datetime (when fact was modified/superseded)
    last_confirmed TEXT,             -- ISO 8601 UTC datetime (last nightly pass that saw evidence)
    source TEXT NOT NULL,            -- "sms", "signal", "email", "calendar", "manual"
    source_ref TEXT                  -- flexible provenance: "bus:12345", "gmail:msg_abc", "calendar:event_xyz"
);

CREATE INDEX idx_facts_contact ON facts(contact, fact_type) WHERE active = 1;
CREATE INDEX idx_facts_temporal ON facts(starts_at, ends_at) WHERE active = 1;
CREATE INDEX idx_facts_type ON facts(fact_type) WHERE active = 1;
```

**All datetime columns store UTC.** The CLI and extraction scripts convert local times to UTC on write and UTC to local on display.

**Note:** FTS5 on facts is deferred until >500 rows. At initial scale (<100 facts), `LIKE '%query%'` on summary or loading all active facts into LLM context is sufficient.

### Deferred Schema Additions

Added via later Alembic migrations when needed:

- **`fact_history` table**: Added when extraction is stable and change auditing becomes valuable (Phase 2+). Until then, the JSONL extraction log provides sufficient audit trail.
- **Additional fact types**: `deadline`, `relationship`, `project` added once extraction quality is validated on the initial 3 types.
- **FTS5 on facts**: Added at >500 rows.

## Details Schema (per fact_type)

The `details` JSON column is validated on write. Validation ensures valid JSON and checks required keys per type.

**Phase 1 types** (start simple, expand when validated):

| fact_type | Required keys | Optional keys | Type constraints |
|-----------|--------------|---------------|-----------------|
| travel | `destination` (str) | `depart` (ISO date), `return` (ISO date), `airline`, `flight`, `hotel`, `purpose` | `depart`/`return` coerced to ISO 8601 if present |
| event | (none) | `location`, `attendees` (list), `description`, `starts_at_local` | — |
| preference | `domain` (str) | `context` | — |

**Phase 2+ types** (added once initial types are validated):

| fact_type | Required keys | Optional keys |
|-----------|--------------|---------------|
| deadline | (none) | `description`, `recurring` (bool) |
| relationship | `relation` (str) | `context`, `email`, `company` |
| project | `name` (str) | `repo`, `tech_stack` (list), `status` |

**Validation behavior:**
- Missing required keys → fact rejected, logged as extraction error
- Date fields not in ISO 8601 → attempt coercion (e.g., "March 20" → "2026-03-20"), log warning if coerced
- Unknown keys → accepted (LLM may add useful extra fields), logged as info
- Type mismatches on known keys → attempt coercion, reject if coercion fails

This ensures downstream consumers can trust the shape of `details` for consumer-facing keys.

### Handling Sub-key Invalidation

When a fact update should invalidate old sub-keys (e.g., changing airline means old flight number is wrong), the LLM is instructed to output `"key": null` to explicitly delete keys. The merge logic removes keys set to `null`.

Example: `{"airline": "Delta", "flight": null}` → deletes the old flight number, sets airline to Delta.

### List Merge Semantics

For JSON list fields (`attendees`, `tech_stack`), updates are **absolute replacements**, not appends. The LLM sees the existing fact in the prompt and outputs the complete new list. This avoids append edge cases and keeps the LLM in control of list composition.

### Timezone Handling for Events

The `starts_at`/`ends_at` columns store UTC as "best effort" for sorting and expiration. For events where timezone matters (e.g., "dinner at 7pm" when the user might be traveling), the `details` JSON should include `local_time` and `inferred_tz`:

```json
{"location": "Oleana", "local_time": "19:00", "inferred_tz": "America/New_York"}
```

The extraction prompt instructs the LLM to infer timezone from context (active travel facts, location mentions). If ambiguous, default to system timezone. The FactReminder consumer uses `local_time` + `inferred_tz` when available for precise reminder timing.

## Fact Types

| Type | Example | Temporal? | Auto-expires? | Phase |
|------|---------|-----------|---------------|-------|
| travel | "Flying to SF Mar 20-25" | Yes (starts_at, ends_at) | Yes (ends_at < now) | 1 |
| event | "Dinner at Oleana 7pm Saturday" | Yes (starts_at) | Yes (starts_at + 1 day) | 1 |
| preference | "Prefers bun over npm" | No | No (time-decay staleness) | 1 |
| deadline | "Caroline's 30th birthday April 11" | Yes (starts_at) | Yes (starts_at + 1 day) | 2 |
| relationship | "Sam McGrail is a friend/collaborator" | No | No (time-decay staleness) | 2 |
| project | "Working on WebGPU Qwen3.5 engine" | No | No (time-decay staleness) | 2 |

## Extraction: Nightly Batch Only

**All extraction happens in the nightly consolidation pass.** No inline extraction during conversations. This keeps the message hot path untouched and gives the LLM the full day's context for better extraction.

The existing nightly consolidation cron is extended to:
1. Read day's messages from bus.db (already does this)
2. Read Gmail via `gws gmail` — **Phase 3**
3. Read Google Calendar via `gws calendar` — **Phase 3**
4. **For each contact independently** (per-contact fault isolation — one failure doesn't block others):
   a. Load active facts for this contact (prioritized subset — see Context Window Management)
   b. Run LLM extraction pass using **structured output / JSON mode**
   c. Validate and coerce extracted facts (details schema, type constraints)
   d. Write new/updated facts to facts table
   e. Produce bus events (unless `--silent` mode)
   f. On failure: log error, skip this contact, continue to next
5. Run temporal expiration pass + garbage collection
6. Log extraction run to JSONL (with wall-clock timing per contact)
7. Text admin a morning summary (includes any per-contact failures)
8. Continue existing behavior: update Contacts.app notes, CLAUDE.md
9. **Inject `## Active Facts` into each contact's CLAUDE.md** (max 15 per contact)
10. **Patch existing nightly summarizer prompt** to exclude short-term plans (see Memory Bullet Boundary)

### Extraction Prompt

The LLM receives per contact:
- Today's messages (from bus.db, filtered by contact) — **with message timestamps for resolving relative dates**
- Today's relevant emails (filtered by subject/sender) — **Phase 3**
- Upcoming calendar events — **Phase 3**
- **Prioritized active facts for this contact** (max 30 — see Context Window Management)

The extraction call uses the model's **structured output / JSON mode** to guarantee valid JSON output, eliminating the JSON parse failure class entirely.

The prompt includes **few-shot examples** covering key scenarios:

```
You are extracting structured facts from today's conversations. You will be given:
1. Today's messages for a contact (with timestamps)
2. That contact's existing active facts (for dedup)

Output JSON with new_facts, updated_facts, and expired_fact_ids.

RULES:
- Only extract facts that are concrete and actionable (travel plans, events, preferences)
- Do NOT extract small talk, opinions about weather, or transient statements
- If a message updates an existing fact, use updated_facts with the existing_fact_id
- Only expire facts when you see EXPLICIT contradiction ("trip canceled", "changed my mind")
- Resolve relative dates ("next Saturday", "tomorrow") against MESSAGE timestamps, not current time
- Assign confidence based on evidence (see rules below)
- To invalidate a sub-key in an update, set it to null: {"flight": null, "airline": "Delta"}

CONFIDENCE RULES (evidence-based, not your judgment):
- high: Direct first-person statement with specific details ("I'm flying to SF March 20-25")
- high: Confirmed booking/reservation (forwarded confirmation email, calendar invite)
- medium: Third-party or indirect mention ("Mom said she's visiting next week")
- medium: Inferred from forwarded content without explicit confirmation
- low: Vague or speculative ("might go to SF", "thinking about switching to bun")
- low: Single casual mention without details

EXAMPLES:

Input messages:
  [2026-03-18 14:32] "Hey! Flying to SF March 20-25 for a conference"
Existing facts: []
Output:
{"new_facts": [{"fact_type": "travel", "summary": "Flying to SF March 20-25 for a conference", "confidence": "high", "details": {"destination": "San Francisco", "depart": "2026-03-20", "return": "2026-03-25", "purpose": "conference"}, "starts_at": "2026-03-20T00:00:00Z", "ends_at": "2026-03-25T23:59:59Z"}], "updated_facts": [], "expired_fact_ids": []}

Input messages:
  [2026-03-18 16:00] "Actually the SF trip is canceled, work stuff"
Existing facts: [{"id": 42, "fact_type": "travel", "summary": "Flying to SF March 20-25"}]
Output:
{"new_facts": [], "updated_facts": [], "expired_fact_ids": [42]}

Input messages:
  [2026-03-18 10:15] "Been using bun a lot lately, way faster than npm"
Existing facts: []
Output:
{"new_facts": [{"fact_type": "preference", "summary": "Prefers bun over npm for package management", "confidence": "medium", "details": {"domain": "tooling"}}], "updated_facts": [], "expired_fact_ids": []}

Input messages:
  [2026-03-18 12:00] "Grabbed coffee today, weather was nice"
Existing facts: []
Output:
{"new_facts": [], "updated_facts": [], "expired_fact_ids": []}
```

**Key design decision: NO `confirmed_fact_ids`.** The LLM is only asked to extract NEW facts, UPDATE existing facts, or EXPIRE facts based on explicit contradictions. Staleness is tracked purely by time-decay (see below).

### Context Window Management

To prevent "lost in the middle" degradation as facts accumulate:

**Extraction prompt context (max 30 facts per contact):**
- All temporal facts with upcoming dates (within next 30 days)
- Most recently created/updated non-temporal facts
- If a contact has >30 active facts, oldest non-temporal facts are omitted from the prompt (but still in DB)

**CLAUDE.md injection (max 15 facts per contact):**
- Temporal facts with upcoming dates first (sorted by starts_at)
- Then most recently created non-temporal facts
- Only `high` and `medium` confidence
- If more than 15: show 15 + note "Run `fact list --contact X` for all N facts"

### Confidence Rules (Evidence-Based)

Confidence is assigned by **rules in the extraction prompt**, not LLM self-assessment. The prompt defines what each level means based on observable evidence:

| Confidence | Evidence pattern | Example |
|------------|-----------------|---------|
| **high** | Direct first-person statement with specific details | "I'm flying to SF March 20-25" |
| **high** | Confirmed booking/reservation | Forwarded flight confirmation email |
| **medium** | Third-party or indirect mention | "Mom said she's visiting next week" |
| **medium** | Inferred from forwarded content | Calendar invite without explicit discussion |
| **low** | Vague or speculative mention | "might go to SF sometime" |
| **low** | Single casual mention without specifics | "thinking about switching to bun" |

### Deduplication

**Phase 1: LLM-only dedup.** The extraction prompt includes active facts. The LLM outputs `existing_fact_id` when it recognizes an update to an existing fact. This handles semantic dedup ("SF trip" = "San Francisco trip"). At <100 facts this is sufficient.

**Phase 2+: Add deterministic post-pass** if `fact audit` reveals the LLM is producing duplicates:
- Same contact + fact_type + overlapping date range (±2 days) → merge as update
- Same contact + fact_type + text similarity > 0.8 → skip duplicate
- Similarity 0.6-0.8 logged as "near-misses" for review

**Merge semantics (for updates):**
- `summary`: new summary replaces old
- `details`: key-by-key merge — new keys added, existing keys updated, missing keys preserved, `null` values delete keys
- `starts_at`/`ends_at`: new values replace old if present
- `confidence`: takes the higher of old and new

### Staleness Management (Time-Decay Only)

Non-temporal facts (preferences, relationships, projects) don't auto-expire:

- `last_confirmed` is updated in two cases: (1) the nightly pass extracts an update referencing the fact, or (2) the contact had **any conversation activity** that day (proving the relationship is still active). The LLM is NOT asked to confirm all facts — conversation activity alone resets the staleness clock.
- Staleness thresholds are fact-type-specific:
  - **preferences**: 180 days (tool/workflow preferences change slowly)
  - **relationships**: 365 days (people relationships are very stable)
  - **projects**: 90 days (projects are more dynamic)
- `fact stale` CLI shows stale facts for manual review (uses type-specific thresholds)
- Stale facts are NOT auto-deactivated — just flagged. Admin decides.

### Temporal Fact Expiration

Temporal facts auto-expire:
- Nightly pass checks: `WHERE active = 1 AND ends_at IS NOT NULL AND ends_at < datetime('now')`
- Sets `active = 0`, `updated_at = now()`
- Produces `fact.expired` bus event
- For facts with only `starts_at` (events): expire 1 day after starts_at

### Garbage Collection

Old deactivated facts accumulate over time. Nightly pass runs:
- `DELETE FROM facts WHERE active = 0 AND updated_at < datetime('now', '-180 days')`
- These facts are already preserved in the JSONL extraction log for historical reference.

### Circuit Breaker

If a single nightly run extracts more than **20 new facts** for a single contact, or **50 new facts** total:
1. Extraction results are logged but NOT committed to the facts table
2. Admin is alerted: "⚠️ Extraction circuit breaker tripped. Review extraction log."
3. Admin can review and manually approve via `fact import --from-log <timestamp>`

## Session Integration (How Facts Reach Sessions)

**This is the critical integration point.** Facts are surfaced to sessions in two ways:

### 1. CLAUDE.md Injection (Automatic)

The nightly consolidation updates the `## Active Facts` section in each contact's CLAUDE.md.

**Boundary with existing memory bullets (Memory Bullet Boundary):**
- Memory bullets (existing `What I know about them:` section) = "who this person is" — sourced from Contacts.app notes and nightly conversation summarization
- Active Facts section = "what this person is currently doing/planning" — sourced from facts table
- If a memory bullet overlaps with a fact (e.g., both mention a project), the fact takes precedence for current state; the memory bullet provides historical context
- **IMPORTANT:** When deploying Phase 2, the existing nightly summarizer prompt must be patched to exclude short-term plans: *"Do NOT extract upcoming travel, schedules, or short-term plans into memory bullets. Focus ONLY on long-term character traits, relationship dynamics, and permanent status changes. Short-term plans are handled by the structured facts system."* This prevents duplicate extraction of the same information into both memory bullets and facts.

Only `high` and `medium` confidence facts are included, max 15 per contact.

Format in CLAUDE.md:
```markdown
## Active Facts

- 🛫 Flying to SF March 20-25 (travel)
- 🎂 Dinner at Oleana 7pm Saturday (event)
- 💻 Prefers bun over npm (preference)

*15 of 23 active facts shown. Run `fact list --contact "+16175969496"` for all.*
```

The nightly pass **regenerates** this section each night. Ordering: temporal facts with upcoming dates first, then most recent non-temporal facts.

`fact inject --contact X` can update CLAUDE.md on-demand (not just nightly) for manual fact additions.

### 2. CLI Queries (On-Demand)

For deeper queries, sessions call the `fact` CLI:
- "Where is Nikhil?" → `fact list --contact "+16175969496" --type travel --active`
- "What's coming up?" → `fact upcoming --days 14`

The memory SKILL.md is updated to teach sessions about `fact` CLI commands. Access is tier-gated: admin gets full CRUD, favorites/family get read-only (`fact list`, `fact search`, `fact upcoming`).

## Extraction Logging

Every nightly run logs to `~/dispatch/logs/fact-extraction.jsonl`:

```json
{
  "timestamp": "2026-03-19T02:00:00Z",
  "contact": "+16175969496",
  "wall_clock_ms": 3200,
  "sources": {"messages": 47, "emails": 0, "calendar_events": 0},
  "existing_facts_shown": 12,
  "new_facts": 2,
  "updated_facts": 1,
  "expired_facts": 0,
  "low_confidence_facts": 1,
  "rejected_facts": 0,
  "circuit_breaker_tripped": false
}
```

**Quality metric:** Track extraction quality weekly via `fact audit`. If duplicates exceed 5% or rejection rate exceeds 10%, tune the extraction prompt.

For deeper debugging, `--verbose` logs full LLM input/output.

## Nightly Summary

After extraction completes, text admin:
```
🌙 Nightly facts: 3 new, 1 updated, 0 expired across 4 contacts.
New: "Flying to SF Mar 20-25" (travel, high), "Dinner at Oleana Sat 7pm" (event, high), "Prefers window seats" (preference, low ⚠️)
```

Low-confidence facts are flagged with ⚠️. Uses existing send-sms. Skipped if zero changes.

## Bus Events

When a fact is created, updated, or expired, produce an event to the bus:

```python
produce_event(producer, "facts", "fact.created", key=contact, payload={
    "fact_id": fact.id,
    "contact": fact.contact,
    "fact_type": fact.fact_type,
    "summary": fact.summary,
    "details": fact.details,
    "confidence": fact.confidence,
    "starts_at": fact.starts_at,
    "ends_at": fact.ends_at,
})
```

Topic: `facts`
Types: `fact.created`, `fact.updated`, `fact.expired`

**Silent mode:** `fact rebuild` and `fact import` suppress bus events by default (use `--emit-events` to override). Prevents historical rebuilds from flooding consumers.

## Downstream: FactReminder Consumer (Phase 4)

A single **FactReminder** consumer handles all fact types that need reminders. Parameterized by fact_type, not separate agents:

```python
REMINDER_CONFIG = {
    "travel": [
        {"offset_days": -1, "template": "Check weather in {destination}, text travel tips"},
        {"offset_days": 0, "template": "Have a great trip! Here's what's happening in {destination}"},
    ],
    "deadline": [
        {"offset_days": -7, "template": "Reminder: {summary} in 1 week"},
        {"offset_days": -1, "template": "Reminder: {summary} is tomorrow"},
    ],
    "event": [
        {"offset_days": -1, "template": "Tomorrow: {summary}"},
    ],
}
```

**Behavior:**
- Listens for `fact.created` and `fact.updated` where `confidence != "low"`
- Creates reminders at configured offsets from `starts_at`
- Stores `fact_id` in reminder metadata for dedup
- On `fact.updated`: updates reminder times if dates changed
- On `fact.expired`: cancels related reminders
- Ignores events where `created_at` > 24h old (rebuild protection)

This is ONE consumer with config, not separate Travel/Deadline/Event agents.

### Future: Morning Briefing Agent
Queries facts table daily (not event-driven — just reads active facts):
- Active travel facts → "you're in SF today"
- Upcoming events → "dinner at 7pm"

## CLI: `fact` command

```bash
# Save a fact (validates details schema, coerces types)
~/dispatch/scripts/fact save \
  --contact "+16175969496" \
  --type travel \
  --summary "Flying to SF March 20-25" \
  --details '{"destination": "San Francisco", "depart": "2026-03-20", "return": "2026-03-25"}' \
  --starts "2026-03-20" \
  --ends "2026-03-25" \
  --source sms \
  --source-ref "bus:98765"

# Update an existing fact (key-by-key merge on details, null deletes keys)
~/dispatch/scripts/fact update 42 \
  --summary "Flying to SF March 20-25, staying at Marriott" \
  --details '{"hotel": "Marriott"}'

# Query facts for a contact
~/dispatch/scripts/fact list --contact "+16175969496"
~/dispatch/scripts/fact list --contact "+16175969496" --type travel --active

# Search facts
~/dispatch/scripts/fact search "california"

# Query upcoming (next N days)
~/dispatch/scripts/fact upcoming --days 7

# Deactivate a fact
~/dispatch/scripts/fact deactivate 42

# Get context for a contact (for session injection / CLAUDE.md)
~/dispatch/scripts/fact context --contact "+16175969496"

# Inject facts into CLAUDE.md on-demand (not just nightly)
~/dispatch/scripts/fact inject --contact "+16175969496"

# Expire temporal facts where ends_at < now
~/dispatch/scripts/fact expire

# Show stale non-temporal facts (uses type-specific thresholds)
~/dispatch/scripts/fact stale

# Show potential duplicates for manual review
~/dispatch/scripts/fact audit

# Rebuild facts from scratch (silent — no bus events by default)
~/dispatch/scripts/fact rebuild --since "2026-01-01"

# Import facts from extraction log (for circuit breaker recovery)
~/dispatch/scripts/fact import --from-log "2026-03-19T02:00:00Z"

# Garbage-collect old deactivated facts (>180 days)
~/dispatch/scripts/fact gc
```

## Cross-Session Queries

Any session can query facts to answer questions:

- "Where is Nikhil?" → `fact list --contact "+16175969496" --type travel --active`
- "What's coming up?" → `fact upcoming --days 14`
- "What do we know about Caroline's birthday?" → `fact search "caroline birthday"`

Additionally, active facts are in CLAUDE.md, so sessions can answer simple factual questions without CLI calls.

## Migration Path

1. Alembic migration 003: CREATE TABLE facts + indexes
2. Add `fact` CLI script to `~/dispatch/scripts/`
3. Extend nightly consolidation to extract facts + inject into CLAUDE.md
4. Run `fact audit` weekly, tune extraction prompt
5. Add `fact_history` table + additional fact types when quality validated
6. Add downstream FactReminder consumer — **after 2+ weeks of validated facts**
7. Update memory SKILL.md to document fact queries
8. Backfill: run extraction over recent bus messages (silent mode)

### Extraction Regression Tests (Golden Set)

Before deploying or modifying the extraction prompt, run a golden set of 10-15 hand-curated test cases:

```bash
~/dispatch/scripts/fact test-extraction  # runs golden set, reports pass/fail
```

Test cases cover edge cases:
- Multi-day threads spanning extraction windows
- Ambiguous dates ("next Saturday" at 11:55 PM)
- Updates to existing facts (must output `existing_fact_id`)
- Near-duplicates that should be recognized as updates
- Small talk that should NOT produce facts
- Low-confidence speculative mentions
- Explicit cancellations/contradictions

Each test case has input messages, existing facts, and expected output. Tests run the actual extraction prompt against the test LLM and compare outputs. This catches prompt regressions before they hit production.

### Rollout Strategy

- **Phase 1** (1 day): Deploy schema + CLI. Manual `fact save` only. Validate schema, CLI, details validation, CLAUDE.md injection all work correctly with manually created test facts. Build golden set test cases.
- **Phase 2** (2 weeks): Enable nightly extraction for bus.db messages only. `FACTS_ENABLED=1`. Three fact types: travel, event, preference. **First week is dry-run mode** (facts extracted and logged but NOT written to DB — admin reviews quality before committing). Patch existing nightly summarizer prompt to exclude short-term plans (Memory Bullet Boundary). Run `fact audit` weekly. **Success criteria: <5% duplicate rate, <10% rejection rate, golden set passes, admin approves fact quality.** After validation: add `fact_history` table, add remaining fact types, add deterministic dedup Layer 2.
- **Phase 3** (1-2 weeks): Add Gmail + Calendar as extraction sources. **Prerequisites:** verify `gws gmail` and `gws calendar` CLIs are production-ready. Gmail requires filtering (travel confirmations, invites — not every email; use Schema.org Reservation tags, specific labels, or high-signal senders). Calendar requires dedup against existing event facts. Archive raw Gmail/Calendar payloads for rebuild support.
- **Phase 4** (1 week): Deploy FactReminder consumer. Initially dry-run mode for 1 week (logs what it WOULD do), then enable. Only triggers on `high`/`medium` confidence facts.

### Feature Flag

`FACTS_ENABLED=1` env var. When disabled, nightly consolidation skips fact extraction entirely. Facts table still exists and is queryable but no new facts are written. CLAUDE.md injection still runs (renders existing facts). Consumer still runs (in case manual facts were added).

### Rollback

If fact extraction produces bad data:
1. Set `FACTS_ENABLED=0` (stops new extraction)
2. `fact deactivate --all` or selective cleanup
3. `fact rebuild --since <date>` to re-extract from bus history with a fixed prompt (silent mode)

Bus retains all raw messages indefinitely, so the facts table can always be rebuilt. **Note:** Gmail and Calendar data may not be replayable if messages/events are deleted. Bus.db messages are the authoritative replayable source. Consider archiving raw Gmail/Calendar payloads during Phase 3 extraction for rebuild support.

## What This Does NOT Replace

- **CLAUDE.md**: Still the hot cache for session context. **Enhanced** with `## Active Facts` section (separate from existing memory bullets). Memory bullets = "who this person is." Facts = "what they're doing/planning."
- **Contacts.app notes**: Still the source for "who is this person" facts. Not modified by fact extraction.
- **bus.db FTS5**: Still the raw message search. Facts are structured summaries; FTS5 is full-text search over raw messages.
- **Nightly consolidation**: Extended, not replaced. Existing Contacts.app notes + CLAUDE.md memory behavior untouched.
- **Reminders**: Unchanged. FactReminder consumer creates reminders via existing `claude-assistant remind add`.
