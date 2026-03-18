---
name: skillify
description: Analyze conversations to propose new skills AND improvements to existing skills. Mines transcripts for automation opportunities, recurring workflows, tool gaps, and skill quality issues. Discovery subagent reads all chats holistically, then parallel refinement subagents evaluate each idea. Trigger words - skillify, propose skills, what should we automate, skill opportunities, improve skills.
---

# Skillify

Analyze recent conversations to:
1. **Propose new skills** to automate recurring workflows, fill tool gaps, or build discussed ideas
2. **Suggest improvements to existing skills** based on user corrections, workarounds, and back-and-forth that indicates a skill's instructions are incomplete

## When to Use

- User says "skillify", "propose skills", "what should we automate"
- Nightly consolidation passes "--nightly" flag

## How It Works

### Step 1: Identify Active Sessions

```bash
cat ~/dispatch/state/sessions.json
```

- Filter to sessions active in the last 24 hours
- Include both 1:1 sessions and group chats, but for group chats only include those where the admin user is a participant (check the `participants` array)
- **IMPORTANT**: Some sessions have stale/missing `last_message_time`. Cross-check by reading recent messages for sessions with empty timestamps but known activity (e.g., sessions with "sven" in the name)
- Sort by most recent activity
- Cap at **10 sessions**

If no active sessions, report "nothing to analyze" and stop.

### Step 2: Discovery (Single Subagent — Holistic Cross-Chat Analysis)

Spawn **one discovery subagent** that reads ALL active session transcripts and identifies raw skill ideas. This must be a single subagent because skill opportunities often span multiple conversations.

The discovery subagent:

1. **Reads each transcript** sequentially:
   ```
   uv run ~/.claude/skills/sms-assistant/scripts/read_transcript.py --session {SESSION_NAME} --limit 50
   ```
   If a transcript read fails, skip it and note the skip.

2. **After reading ALL transcripts**, identifies skill opportunities using these signals:

   **HIGH SIGNAL — explicit automation intent:**
   - User explicitly asked for a tool/CLI/skill that doesn't exist
   - User brainstormed a tool in detail and deferred implementation
   - Examples: "I want a CLI that does X", "we should build a skill for this", "don't implement yet"

   **MEDIUM SIGNAL — implicit recurring need:**
   - User expressed frustration with manual work
   - Same category of work appearing across multiple chats (e.g., WebGPU benchmarking in one chat + WebGPU debugging in another = unified tooling opportunity)
   - Agent did lengthy manual work that a reusable script could handle
   - Existing skill was used but failed or needed workarounds
   - **A repeatable multi-step process was followed across chats** — even if it looks like "normal coding", ask: "Is this a process that could be applied to OTHER inputs?" If the same workflow (e.g., convert model → build shaders → benchmark → verify correctness) was done for Model A in one chat and Model B in another, that's a SKILL, not just coding.

   **SKIP:**
   - Truly one-off coding tasks (fixing a specific bug, adding a feature to a specific app)
   - One-off questions or tasks
   - Idle chat, greetings, jokes
   - Tasks already handled by existing skills

   **IMPORTANT — "normal coding" is NOT automatically a skip.** Coding that follows a repeatable process applicable to new inputs IS a skill opportunity. The question is: "Could someone say 'do this again but for X' and the same steps would apply?" If yes, it's a skill candidate.

   **SKILL IMPROVEMENT signals — look for these patterns that indicate an existing skill needs updating:**
   - User corrected the agent's behavior after a skill fired ("no, that's wrong, do X instead")
   - Lots of back-and-forth to get a skill-triggered action right (>2 corrections for one task)
   - User manually fixed or adjusted output from a skill-driven action
   - User provided extra instructions that should already be in the SKILL.md ("always do X when Y")
   - Workarounds that suggest missing edge cases ("it doesn't handle Z, so do this instead")
   - Agent apologized for doing something wrong that a skill should have prevented

3. **Returns TWO lists:**

   **a) New skill ideas** — each with:
   - `name`: kebab-case
   - `description`: 1-2 sentences
   - `signal`: high or medium
   - `evidence`: direct quote(s) from transcript(s)
   - `context`: 2-3 sentences on what user was trying to accomplish
   - `source_sessions`: list of session names this idea came from
   - `type`: "new_skill"

   **b) Skill improvement ideas** — each with:
   - `skill_name`: name of existing skill that needs improvement
   - `issue`: what went wrong or what's missing
   - `evidence`: direct quote(s) showing the correction/workaround/frustration
   - `suggested_fix`: what should change in the SKILL.md
   - `source_sessions`: list of session names
   - `type`: "skill_improvement"

### Step 3: Refinement (Parallel Subagents — One Per Idea)

For each raw idea from discovery (both new skills AND skill improvements), spawn a **refinement subagent** in parallel.

#### For new skill ideas, each refinement subagent:

1. **Checks existing skills** — reads `sed -n '/^---$/,/^---$/p' ~/.claude/skills/*/SKILL.md` to get frontmatter for all ~65+ existing skills. Decides: is this idea already covered?

2. **Checks previous proposals** — reads `cat ~/dispatch/state/skillify-proposals.json 2>/dev/null || echo '{"runs":[]}'`. Has this been proposed before?

3. **Makes a verdict**: **ACCEPT**, **REFINE**, or **REFUTE**
   - ACCEPT: idea is novel, reusable, and worth building as-is
   - REFINE: idea has potential but needs to be rescoped, narrowed, or reframed to be viable. The subagent rewrites the idea with a better framing and re-evaluates. For example: "too broad as stated, but if scoped to just X it becomes viable" → rewrite and accept
   - REFUTE: idea is a clear duplicate of an existing skill, or fundamentally not automatable. Must cite specific reason. **Be conservative with refute** — if there's any way to rescope the idea into something useful, use REFINE instead. Only refute for true duplicates or ideas that genuinely cannot be a skill.

4. **If accepted or refined**, fleshes out into a full proposal:
   - **name**: kebab-case
   - **description**: 1-2 sentences with trigger words (ready for SKILL.md frontmatter)
   - **seed_spec**: one sentence fully describing what to build — self-contained enough to hand off cold
   - **key_instructions**: 2-3 bullet points on core functionality
   - **complexity**: small (SKILL.md only) / medium (+ scripts) / large (+ external deps)
   - **source_sessions**: which session(s) this came from
   - **evidence**: direct quote(s)
   - **context**: 2-3 sentences
   - **overlap_check**: "Checked [skill-name]: not covered because [reason]" or "No similar existing skill"

#### For skill improvement ideas, each refinement subagent:

1. **Reads the existing skill's SKILL.md** — `cat ~/.claude/skills/{skill_name}/SKILL.md` to understand current instructions

2. **Evaluates the issue** — is this a real gap in the skill's instructions, or was it a one-off misunderstanding?

3. **Makes a verdict**: **ACCEPT**, **REFINE**, or **REFUTE**
   - ACCEPT: the skill's SKILL.md is genuinely missing guidance that caused the issue. Propose specific language to add.
   - REFINE: the issue is real but the fix needs to be reframed (e.g., the problem isn't the skill itself but how it interacts with another skill)
   - REFUTE: the issue was a one-off, the skill already covers this case, or the fix doesn't belong in the skill

4. **If accepted or refined**, produces an improvement proposal:
   - **skill_name**: which skill to update
   - **issue**: what went wrong
   - **proposed_change**: specific text to add/modify in the SKILL.md (show the actual language, not just "add error handling")
   - **evidence**: direct quote(s) showing the problem
   - **source_sessions**: which session(s)

5. **Returns** the verdict and proposal.

### Step 4: Rank, Persist & Present

Collect results from all refinement subagents:
- Drop refuted ideas
- Rank accepted proposals: high signal first, cross-chat patterns ranked higher, smaller complexity first
- Cap at **5 proposals**

**Persist** to `~/dispatch/state/skillify-proposals.json`:

```json
{
  "runs": [
    {
      "date": "2026-03-13",
      "proposals": [...],
      "sessions_analyzed": 5,
      "skipped_sessions": [],
      "refuted": [{"name": "...", "reason": "..."}]
    }
  ]
}
```

Append new run to the `runs` array. If more than 30 runs, drop the oldest.

**Present** results in two sections:

**## New Skills**
- Show new skill proposals with full details
- For each, end with: `To build: "build the [name] skill — [seed_spec]"`

**## Suggested Skill Improvements**
- Show improvement proposals with: skill name, issue, proposed SKILL.md change, evidence
- For each, end with: `To apply: "update [skill_name] — [proposed_change summary]"`

**Nightly mode** (prompt contains "--nightly"): Send the FULL report via SMS to admin so they can approve/deny when they wake up. Include everything — don't summarize or truncate:

```
🔧 skillify nightly — N new skills, M improvements

## New Skills

1. **skill-name** (signal, complexity)
Seed spec: [full seed_spec]
Key instructions:
- [bullet 1]
- [bullet 2]
Evidence: "[direct quote from transcript]"
Source: [session names]
Reply "build skill-name" to create it.

2. ...

## Skill Improvements

1. **skill-name** — [issue]
Proposed change: [specific SKILL.md language to add/modify — show the actual text]
Evidence: "[direct quote showing the problem]"
Source: [session names]
Reply "apply skill-name fix" to update it.

2. ...

## Refuted
- idea-name — [reason]
```

Show the FULL details for each proposal. The admin needs enough context to make approve/deny decisions without opening a laptop.

**IMPORTANT: Do NOT create or modify any skill files. Propose only.**

#### Persist Results to Bus

**After generating the report (in ALL modes)**, publish a `scan.completed` event to the bus for historical tracking:

```bash
RUN_ID=$(date +%Y%m%d-%H%M)
~/dispatch/bus/cli.py produce system \
  '{"scanner":"skillify","run_id":"'"$RUN_ID"'","mode":"nightly","duration_seconds":DURATION,"summary":{"sessions_analyzed":N,"new_skills_proposed":N,"improvements_proposed":N,"refuted":N},"findings":[ACCEPTED_PROPOSALS_AS_JSON]}' \
  --type scan.completed --source skillify --key "scan-skillify-$RUN_ID"
```

The `findings` array should include all accepted new skill proposals and skill improvement proposals with their full details (name, description, seed_spec, evidence, source_sessions, etc.). Refuted items go in `summary.refuted` count only, not in findings.

This enables `bus reports --scanner skillify` to query historical scan results (stored in archive indefinitely).

### Step 5: Build on Request

When the user says "build [name]" or "build the [name] skill", look up the proposal in `~/dispatch/state/skillify-proposals.json`, use the seed_spec and key_instructions to build it via the skill-builder skill, and update the proposal's status to "built".

## Calibration Examples

### GOOD candidates (flag these):

1. **"I want a CLI that takes a model, converts to WebGPU, benchmarks, and compares outputs"**
   → name: model-to-webgpu, signal: high, complexity: large
   Why: explicit tool request, clearly reusable, specific enough to build

2. **Agent manually scraped 3 listing sites, parsed prices, compared — user said "do this daily"**
   → name: listing-scraper, signal: medium, complexity: medium
   Why: recurring multi-step workflow, user confirmed recurrence

3. **"we should have a thing that checks ski conditions across 4 mountains"**
   → name: ski-conditions, signal: high, complexity: medium
   Why: explicit request for a tool, clearly reusable during ski season

4. **Chat A: converted data from format X, validated output. Chat B: converted different data from format X, validated output the same way.**
   → name: data-format-converter, signal: medium, complexity: medium
   Why: BOTH chats follow the same process applied to different inputs. Even though it looks like "coding", it's a repeatable workflow. Ask: "could someone say 'do this again but for Z' and the same steps apply?" If yes, it's a skill.

5. **Agent set up CI/CD pipeline in 3 different repos the same way this week**
   → name: repo-ci-setup, signal: medium, complexity: medium
   Why: same process repeated across projects = skill opportunity

### BAD candidates (SKIP these):

1. **Agent fixed a specific bug in one repo** → truly one-off, no repeatable process
2. **"What's the weather?"** → one-off question
3. **"Turn on the lights"** → already covered by hue/lutron skills
4. **Agent read a file, edited it, ran tests for a feature** → one-off feature work, not a repeatable process

## Graceful Degradation

- **Transcript read fails** → skip session, note in skipped_sessions
- **Refinement subagent fails** → note failure, continue with other results
- **Zero candidates** → "no skill opportunities found today" (normal)
- **sessions.json missing** → report error, stop
- **proposals.json doesn't exist** → create with `{"runs": []}`
- **Context too large** → reduce --limit to 30 and continue

## Nightly Integration

Called by manager.py's nightly consolidation after person-facts and chat-context. Manager.py passes "--nightly" for SMS output mode. The manager.py hook is out of scope for this skill file.

## Historical Context (Required)

Before generating findings, you MUST gather historical context to avoid re-reporting known issues or missing important changes:

### Past Reports

Query previous scan reports from the bus for what was already found, fixed, or refuted:

```bash
cd ~/dispatch && uv run python -m bus.cli reports --scanner skillify --since 7
```

This shows past findings with their verdicts (accepted/refuted). Use this to:
- Skip ideas that were already proposed and are being tracked
- Understand patterns in what gets refuted (calibrate your signal)
- Build on previous proposals rather than starting from scratch

### Recent Code Changes

Check git history for recent changes that provide context on what was built, fixed, or refactored:

```bash
cd ~/dispatch && git log --oneline --since="7 days ago" -- assistant/ bus/
cd ~/dispatch && git log --oneline --since="7 days ago" -- ~/.claude/skills/
```

This helps you:
- Understand what skills were recently created or modified (don't re-propose existing work)
- Identify automation patterns that were already landed as skills
- See what the admin was working on (provides intent behind changes)
