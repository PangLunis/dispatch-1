#!/usr/bin/env -S uv run --script
"""
Memory Consolidation v3 - 3-Pass Architecture

Pass A: SUGGESTER - Reads messages, proposes candidate facts
Pass B: REVIEWER  - Refines wording, refutes bad ones, accepts good ones
Pass C: COMMITTER - Takes accepted facts, writes to Contacts.app

Each pass is a separate SDK agent call with focused responsibility.

Usage:
    consolidate_3pass.py <contact>           # Run for one contact
    consolidate_3pass.py --all               # Run for all contacts
    consolidate_3pass.py --dry-run <contact> # Show without writing
    consolidate_3pass.py --verbose <contact> # Show all 3 passes
"""
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

# Paths
HOME = Path.home()
DISPATCH_DIR = HOME / "dispatch"
LOGS_DIR = DISPATCH_DIR / "logs"
LOG_FILE = LOGS_DIR / "memory-consolidation.log"
MEMORIES_DIR = HOME / "memories"
CHECKPOINTS_FILE = MEMORIES_DIR / "checkpoints.json"
BACKUP_DIR = MEMORIES_DIR / "backups"
REPORTS_DIR = MEMORIES_DIR / "reports"
CONTACTS_CLI = HOME / ".claude/skills/contacts/scripts/contacts"
READ_SMS_CLI = HOME / ".claude/skills/sms-assistant/scripts/read-sms"
EXCLUSIONS_FILE = MEMORIES_DIR / "exclusions.txt"

# ============================================================
# CRITICAL: PROPOSAL LEAK PROTECTION
# ============================================================
# Hardcoded protection against leaking Nikhil's proposal to Caroline.
# This is a safety net - exclusions.txt should catch these too, but
# this hardcoded check ensures nothing slips through.

PROPOSAL_LEAK_PATTERNS = [
    "proposal", "propose", "engagement", "ring", "marry",
    "museum of science", "planetarium", "may 9", "may 9th",
    "surprise", "secret", "don't tell", "top secret",
]

def is_proposal_leak_risk(text: str) -> bool:
    """Check if text contains proposal-related content."""
    text_lower = text.lower()
    return any(pattern in text_lower for pattern in PROPOSAL_LEAK_PATTERNS)

def is_caroline(contact_name: str) -> bool:
    """Check if this contact is Caroline."""
    name_lower = contact_name.lower() if contact_name else ""
    return "caroline" in name_lower or "caro" in name_lower

# Format markers
MANAGED_HEADER = "<!-- CLAUDE-MANAGED:v1 -->"
LAST_UPDATED_PATTERN = r"\*Last updated: (\d{4}-\d{2}-\d{2} \d{2}:\d{2})\*"

# Tier-specific emphasis
TIER_EMPHASIS = {
    "wife": """ESPECIALLY IMPORTANT for this person (spouse/partner):
- Birthday and anniversary dates - ALWAYS capture these
- Favorite restaurants, foods, drinks
- Gift preferences and wishlist items
- Health info (allergies, conditions)
- Relationship milestones""",

    "family": """ESPECIALLY IMPORTANT for family members:
- Birthday dates
- Kids' names and ages
- Where they live
- Health updates and concerns
- Major life events""",

    "favorite": """For close friends, focus on:
- How you know each other
- Shared interests and activities
- Major life events
- Their family situation (partner, kids)""",

    "admin": """For admin, focus on:
- Projects and technical interests
- Preferences for how Claude should operate
- Important personal facts
- Life events and milestones""",
}


# ============================================================
# PASS A: SUGGESTER
# ============================================================

def get_suggester_prompt(contact_name: str, phone: str, tier: str, existing_memories: str, since_filter: str = "") -> str:
    """System prompt for Pass A - the suggester agent."""
    tier_emphasis = TIER_EMPHASIS.get(tier, "")

    if since_filter:
        read_instructions = f"""You have access to the Bash tool. Use it to:
1. Read NEW messages only: `~/.claude/skills/sms-assistant/scripts/read-sms --chat "{phone}" --since "{since_filter}" --limit 500`
2. Search for specific topics: `~/.claude/skills/sms-assistant/scripts/read-sms --chat "{phone}" --since "{since_filter}" --grep "birthday"`

CRITICAL: ONLY use --since "{since_filter}" to read messages. Do NOT read older messages - they have already been processed."""
    else:
        read_instructions = f"""You have access to the Bash tool. Use it to:
1. Read recent messages: `~/.claude/skills/sms-assistant/scripts/read-sms --chat "{phone}" --limit 100`
2. Read more messages if needed: `~/.claude/skills/sms-assistant/scripts/read-sms --chat "{phone}" --limit 500`"""

    return f"""You are extracting personal facts about {contact_name} from their messages.

## YOUR TOOLS

{read_instructions}

## CRITICAL RULES

Extract ONLY facts that {contact_name} explicitly states about THEMSELVES.

### ✅ EXTRACT - Self-references (explicit or contextually clear):
- "I have a dog" → Has a dog
- "My birthday is March 5" → Birthday: March 5
- "Just landed in Boston!" → Currently in Boston
- "Working from home today" → Works from home

### ❌ DO NOT EXTRACT - Requests or questions:
- "Find dog-friendly places" → NOT evidence they have a dog
- "Book something with a hot tub" → Request, not preference

### ❌ DO NOT EXTRACT - Inferred from context:
- Someone asked about ski trips → Does NOT mean they ski
- In a group chat about X → Does NOT mean they like X

### ❌ DO NOT EXTRACT - Facts about OTHER people:
- "Remind Nikhil about Arjun's birthday" → This is about Nikhil/Arjun, NOT about the sender
- "My cousin just got married" → The marriage is about the cousin, not the sender
- "Can you tell X that Y" → Passing along info about others
- Only extract facts where {contact_name} IS the subject, not just the messenger

### ❌ DO NOT EXTRACT - System metadata:
- Phone number, tier, group memberships

{tier_emphasis}

## EXISTING MEMORIES (for context/dedup):
{existing_memories}

## YOUR TASK

1. Read messages FROM {contact_name} using read-sms
2. Identify candidate facts - things they say about themselves
3. For each fact, note the supporting quote

## OUTPUT FORMAT

Output candidate facts as JSON array:
```json
[
  {{"fact": "Has a dog named Max", "quote": "My dog Max loves the park"}},
  {{"fact": "Lives in Boston", "quote": "This Boston winter is killing me"}},
  {{"fact": "Birthday March 5", "quote": "My birthday is March 5"}}
]
```

If NO facts found, output: `[]`

Max 15 candidates. Include the quote that supports each fact.
Start by reading recent messages."""


# ============================================================
# PASS B: REVIEWER
# ============================================================

def get_reviewer_prompt(contact_name: str, phone: str) -> str:
    """System prompt for Pass B - the reviewer agent."""

    return f"""You are a fact-checker reviewing proposed memories about {contact_name}.

## YOUR TOOLS

You have access to the Bash tool. Use it to verify quotes:
~/.claude/skills/sms-assistant/scripts/read-sms --chat "{phone}" --grep "SEARCH_TERM"

## YOUR TASK

For each proposed fact, verify:
1. Does the quote actually exist in the messages?
2. Is {contact_name} the SUBJECT of the fact, not just the messenger?
   - "Remind X about Y's birthday" → REFUTE (fact is about X/Y, not sender)
   - "My cousin got married" → REFUTE (fact is about cousin)
   - "I got married" → ACCEPT (fact is about sender)
3. Is the fact correctly interpreted from the quote?
4. Check for negations - "I don't have a dog" should NOT become "has a dog"

## DECISIONS

For each fact, decide:
- **ACCEPT**: Quote verified, fact is accurate
- **REFINE**: Quote found but fact needs rewording (provide corrected version)
- **REFUTE**: Quote not found, or fact misinterprets the quote

## OUTPUT FORMAT

Output your decisions as JSON array:
```json
[
  {{"decision": "ACCEPT", "fact": "Has a dog named Max", "verified_quote": "My dog Max loves the park"}},
  {{"decision": "REFINE", "original": "Lives in Boston", "refined": "Grew up in Boston area", "reason": "Quote says 'grew up' not 'lives'"}},
  {{"decision": "REFUTE", "fact": "Plays tennis", "reason": "No supporting quote found in messages"}}
]
```

Be thorough. Search for each quote to verify it exists."""


# ============================================================
# PASS C: COMMITTER
# ============================================================

def get_committer_prompt(contact_name: str) -> str:
    """System prompt for Pass C - the committer agent."""

    return f"""You are committing verified facts about {contact_name} to their contact notes.

## YOUR TOOLS

You have access to the Bash tool. Use it to:
1. Read current notes: `~/.claude/skills/contacts/scripts/contacts notes "{contact_name}"`
2. Write new notes: `~/.claude/skills/contacts/scripts/contacts notes "{contact_name}" "NEW_CONTENT"`

## YOUR TASK

1. Read the current contact notes
2. Merge the new verified facts with existing facts
3. Remove duplicates
4. Preserve any "## User Notes" section
5. Write the updated notes

## FORMAT

The notes should follow this format:
```
<!-- CLAUDE-MANAGED:v1 -->
## About {contact_name}
- Fact one
- Fact two
- Fact three

---
*Last updated: YYYY-MM-DD HH:MM*
```

If there are existing "## User Notes", preserve them:
```
<!-- CLAUDE-MANAGED:v1 -->
## About {contact_name}
- Fact one
- Fact two

## User Notes
[preserved user content]

---
*Last updated: YYYY-MM-DD HH:MM*
```

## OUTPUT

After writing, output:
COMMITTED: X facts written for {contact_name}

Or if there was an error:
ERROR: [description]"""


# ============================================================
# UTILITIES
# ============================================================

def log(message: str):
    """Log to consolidation log file."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"{timestamp} | {message}\n")


def load_checkpoints() -> dict:
    if CHECKPOINTS_FILE.exists():
        return json.loads(CHECKPOINTS_FILE.read_text())
    return {}


def save_checkpoints(checkpoints: dict):
    CHECKPOINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS_FILE.write_text(json.dumps(checkpoints, indent=2, default=str))


def save_daily_report(results: list[dict]):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_file = REPORTS_DIR / f"{date_str}.json"

    report = {
        "date": date_str,
        "timestamp": datetime.now().isoformat(),
        "total_contacts": len(results),
        "summary": {},
        "contacts": results,
    }

    for r in results:
        status = r["status"]
        report["summary"][status] = report["summary"].get(status, 0) + 1

    report_file.write_text(json.dumps(report, indent=2, default=str))
    log(f"Daily report saved to {report_file}")


def get_contact_notes(name: str) -> Optional[str]:
    result = subprocess.run(
        [str(CONTACTS_CLI), "notes", name],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def backup_notes(identifier: str, content: str):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r'[^\w\-]', '_', identifier)
    backup_path = BACKUP_DIR / f"{safe_id}.txt"
    backup_path.write_text(content or "")
    log(f"Backed up notes for {identifier} to {backup_path}")


def parse_existing_memories(notes: str) -> str:
    if not notes:
        return "(none)"

    lines = notes.split('\n')
    memories = []
    for line in lines:
        if line.strip().startswith('- '):
            memories.append(line.strip())

    return '\n'.join(memories) if memories else "(none)"


def load_exclusions() -> list[str]:
    """Load exclusion patterns from file."""
    if not EXCLUSIONS_FILE.exists():
        return []
    patterns = []
    for line in EXCLUSIONS_FILE.read_text().split('\n'):
        line = line.strip()
        if line and not line.startswith('#'):
            patterns.append(line.lower())
    return patterns


def is_excluded(fact: str, exclusions: list[str]) -> bool:
    """Check if a fact matches any exclusion pattern."""
    fact_lower = fact.lower()
    for pattern in exclusions:
        if pattern in fact_lower:
            return True
    return False


def count_messages(phone: str) -> int:
    result = subprocess.run(
        [str(READ_SMS_CLI), "--chat", phone, "--limit", "1000"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        lines = result.stdout.split('\n')
        return sum(1 for line in lines if '| IN |' in line)
    return 0


def call_claude_agent(system_prompt: str, user_prompt: str, verbose: bool = False, pass_name: str = "") -> str:
    """Call Claude via CLI with tool access."""

    # Clear CLAUDECODE to allow spawning from SDK session
    clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    cmd = [
        "claude",
        "-p",
        "--tools", "Bash,Read",
        "--allowed-tools", 'Bash(*/.claude/skills/sms-assistant/scripts/read-sms*),Bash(*/.claude/skills/contacts/scripts/contacts*)',
        "--system-prompt", system_prompt,
        "--model", "opus",
    ]

    if verbose:
        print(f"  [{pass_name}] Running agent...")

    try:
        result = subprocess.run(
            cmd,
            input=user_prompt,
            capture_output=True,
            text=True,
            timeout=900,  # 15 minutes
            env=clean_env
        )

        if result.returncode != 0:
            log(f"Claude CLI failed ({pass_name}, code {result.returncode}): {result.stderr[:500]}")
            raise RuntimeError(f"Claude CLI failed: {result.stderr[:200]}")

        output = result.stdout.strip()
        if not output:
            raise RuntimeError("Claude CLI returned empty output")

        if verbose:
            # Show first few lines
            preview_lines = output.split('\n')[:5]
            print(f"  [{pass_name}] Output preview:")
            for line in preview_lines:
                print(f"    {line[:100]}")
            if len(output.split('\n')) > 5:
                print(f"    ... ({len(output.split(chr(10)))} total lines)")

        return output

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{pass_name} timed out after 15min")


def extract_json_from_output(output: str) -> list:
    """Extract JSON array from agent output (may have markdown fences)."""
    # Try to find JSON array in the output
    # Handle ```json ... ``` blocks
    json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', output)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON array
    array_match = re.search(r'\[\s*\{[\s\S]*?\}\s*\]', output)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try parsing the whole output
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return []


# ============================================================
# MAIN CONSOLIDATION FLOW
# ============================================================

def consolidate_contact(contact_name: str, phone: str, tier: str = "unknown",
                       dry_run: bool = False, verbose: bool = False) -> dict:
    """Run 3-pass consolidation for a single contact."""
    result = {
        "contact": contact_name,
        "phone": phone,
        "tier": tier,
        "status": "unknown",
        "candidates": 0,
        "accepted": 0,
        "refined": 0,
        "refuted": 0,
        "committed": 0,
        "error": None,
    }

    log(f"Starting 3-pass consolidation for {contact_name} ({phone}, tier={tier})")

    # Check checkpoint - only process messages since last run
    checkpoints = load_checkpoints()
    last_processed = checkpoints.get(phone, {}).get("last_processed_ts")
    since_filter = ""
    if last_processed:
        # Parse the ISO timestamp and format for read-sms
        since_dt = datetime.fromisoformat(last_processed)
        since_filter = since_dt.strftime("%Y-%m-%d %H:%M:%S")
        if verbose:
            print(f"  Checkpoint: processing messages since {since_filter}")

    # Check message count first (only new messages if we have a checkpoint)
    if since_filter:
        msg_result = subprocess.run(
            [str(READ_SMS_CLI), "--chat", phone, "--since", since_filter, "--limit", "1000"],
            capture_output=True, text=True
        )
        if msg_result.returncode == 0:
            msg_count = sum(1 for line in msg_result.stdout.split('\n') if '| IN |' in line)
        else:
            msg_count = 0
    else:
        msg_count = count_messages(phone)

    if msg_count == 0:
        result["status"] = "skipped"
        result["error"] = "No new messages from this contact"
        log(f"Skipped {contact_name}: 0 new messages since {since_filter or 'ever'}")
        # Still update checkpoint so we don't re-check
        checkpoints[phone] = {
            "last_processed_ts": datetime.now().isoformat(),
            "contact_name": contact_name,
        }
        save_checkpoints(checkpoints)
        return result

    if verbose:
        print(f"  New messages from contact: {msg_count}")

    # Get existing notes for context
    existing_notes = get_contact_notes(contact_name)
    existing_memories = parse_existing_memories(existing_notes)

    # ========== PASS A: SUGGESTER ==========
    if verbose:
        print(f"\n  === PASS A: SUGGESTER ===")

    suggester_system = get_suggester_prompt(contact_name, phone, tier, existing_memories, since_filter)
    if since_filter:
        suggester_user = f"Extract candidate facts about {contact_name}. ONLY read messages since {since_filter} using --since flag. Do NOT re-extract facts that are already in existing memories."
    else:
        suggester_user = f"Extract candidate facts about {contact_name}. Start by reading their messages."

    try:
        suggester_output = call_claude_agent(suggester_system, suggester_user, verbose, "PASS A")
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Pass A error: {e}"
        log(f"Pass A error for {contact_name}: {e}")
        return result

    candidates = extract_json_from_output(suggester_output)
    result["candidates"] = len(candidates)

    if not candidates:
        result["status"] = "skipped"
        result["error"] = "No candidate facts from suggester"
        log(f"Skipped {contact_name}: no candidates from pass A")
        return result

    if verbose:
        print(f"  [PASS A] {len(candidates)} candidates:")
        for c in candidates[:5]:
            print(f"    - {c.get('fact', '?')}")
        if len(candidates) > 5:
            print(f"    ... and {len(candidates) - 5} more")

    # ========== PASS B: REVIEWER ==========
    if verbose:
        print(f"\n  === PASS B: REVIEWER ===")

    reviewer_system = get_reviewer_prompt(contact_name, phone)
    reviewer_user = f"""Review these candidate facts about {contact_name}:

{json.dumps(candidates, indent=2)}

Verify each quote exists and fact is accurate."""

    try:
        reviewer_output = call_claude_agent(reviewer_system, reviewer_user, verbose, "PASS B")
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Pass B error: {e}"
        log(f"Pass B error for {contact_name}: {e}")
        return result

    decisions = extract_json_from_output(reviewer_output)

    # Collect accepted/refined facts
    final_facts = []
    for d in decisions:
        decision = d.get("decision", "").upper()
        if decision == "ACCEPT":
            final_facts.append(d.get("fact", ""))
            result["accepted"] += 1
        elif decision == "REFINE":
            final_facts.append(d.get("refined", d.get("fact", "")))
            result["refined"] += 1
        elif decision == "REFUTE":
            result["refuted"] += 1

    if verbose:
        print(f"  [PASS B] Results: {result['accepted']} accepted, {result['refined']} refined, {result['refuted']} refuted")
        for fact in final_facts[:5]:
            print(f"    ✓ {fact}")

    # Filter out excluded facts
    exclusions = load_exclusions()
    if exclusions:
        excluded_facts = [f for f in final_facts if is_excluded(f, exclusions)]
        final_facts = [f for f in final_facts if not is_excluded(f, exclusions)]
        if excluded_facts and verbose:
            print(f"  [EXCLUSIONS] Filtered out {len(excluded_facts)} facts:")
            for fact in excluded_facts:
                print(f"    ✗ {fact}")

    # CRITICAL: Extra protection for Caroline - never leak proposal info
    if is_caroline(contact_name):
        log(f"⚠️ Processing Caroline's facts - applying proposal leak protection")
        proposal_leaks = [f for f in final_facts if is_proposal_leak_risk(f)]
        final_facts = [f for f in final_facts if not is_proposal_leak_risk(f)]
        if proposal_leaks:
            log(f"⚠️ BLOCKED {len(proposal_leaks)} proposal-related facts for Caroline")
            if verbose:
                print(f"  [PROPOSAL PROTECTION] Blocked {len(proposal_leaks)} facts:")
                for fact in proposal_leaks:
                    print(f"    ⛔ {fact}")

    if not final_facts:
        result["status"] = "skipped"
        result["error"] = "No facts passed review"
        log(f"Skipped {contact_name}: no facts passed review")
        return result

    # ========== PASS C: COMMITTER ==========
    if verbose:
        print(f"\n  === PASS C: COMMITTER ===")

    if dry_run:
        # Don't actually commit in dry run
        print(f"\n{'='*60}")
        print(f"DRY RUN - Would commit these facts:")
        print(f"{'='*60}")
        for fact in final_facts:
            print(f"  - {fact}")
        print(f"{'='*60}\n")
        result["status"] = "dry_run"
        result["committed"] = len(final_facts)
        return result

    # Backup existing notes first
    backup_notes(phone or contact_name, existing_notes or "")

    committer_system = get_committer_prompt(contact_name)
    committer_user = f"""Commit these verified facts for {contact_name}:

{json.dumps(final_facts, indent=2)}

1. Read current notes
2. Merge with new facts (remove duplicates)
3. Preserve any User Notes section
4. Write updated notes with timestamp"""

    try:
        committer_output = call_claude_agent(committer_system, committer_user, verbose, "PASS C")
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Pass C error: {e}"
        log(f"Pass C error for {contact_name}: {e}")
        return result

    # Check if commit was successful
    if "COMMITTED:" in committer_output.upper() or "ERROR:" not in committer_output.upper():
        result["status"] = "updated"
        result["committed"] = len(final_facts)
        log(f"Updated {contact_name}: {len(final_facts)} facts committed")

        # Update checkpoint
        checkpoints = load_checkpoints()
        checkpoints[phone] = {
            "last_processed_ts": datetime.now().isoformat(),
            "contact_name": contact_name,
        }
        save_checkpoints(checkpoints)
    else:
        result["status"] = "error"
        result["error"] = f"Commit failed: {committer_output[:200]}"
        log(f"Commit error for {contact_name}: {committer_output[:200]}")

    return result


def get_all_contacts() -> list[dict]:
    """Get all contacts with phone numbers and tiers."""
    result = subprocess.run(
        [str(CONTACTS_CLI), "list"],
        capture_output=True, text=True
    )

    contacts = []
    for line in result.stdout.strip().split('\n'):
        if '|' not in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 3:
            name, phone, tier = parts[0], parts[1], parts[2]
            if phone and phone != "(no phone)":
                contacts.append({
                    "name": name,
                    "phone": phone,
                    "tier": tier,
                })

    return contacts


def main():
    parser = argparse.ArgumentParser(
        description="Memory consolidation v3 - 3-pass architecture"
    )
    parser.add_argument("contact", nargs="?", help="Contact name to consolidate")
    parser.add_argument("--all", action="store_true", help="Run for all contacts")
    parser.add_argument("--dry-run", action="store_true", help="Show without writing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.all:
        contacts = get_all_contacts()
        print(f"Consolidating {len(contacts)} contacts (3-pass mode)...")
        log(f"Starting 3-pass batch consolidation for {len(contacts)} contacts")

        results = []
        for i, contact in enumerate(contacts):
            print(f"\n[{i+1}/{len(contacts)}] contact ({contact['tier']})")
            result = consolidate_contact(
                contact["name"],
                contact["phone"],
                tier=contact["tier"],
                dry_run=args.dry_run,
                verbose=args.verbose
            )
            results.append(result)
            print(f"  Status: {result['status']} | candidates={result['candidates']} accepted={result['accepted']} committed={result['committed']}")

            if not args.dry_run and i < len(contacts) - 1:
                import time
                time.sleep(2)

        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        by_status = {}
        for r in results:
            status = r["status"]
            by_status[status] = by_status.get(status, 0) + 1
        for status, count in by_status.items():
            print(f"  {status}: {count}")

        total_candidates = sum(r["candidates"] for r in results)
        total_accepted = sum(r["accepted"] for r in results)
        total_committed = sum(r["committed"] for r in results)
        print(f"\n  Total: {total_candidates} candidates → {total_accepted} accepted → {total_committed} committed")

        log(f"3-pass batch complete: {by_status}")

        if not args.dry_run:
            save_daily_report(results)

    elif args.contact:
        result = subprocess.run(
            [str(CONTACTS_CLI), "list"],
            capture_output=True, text=True
        )

        contact_info = None
        for line in result.stdout.strip().split('\n'):
            if args.contact.lower() in line.lower():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 3:
                    contact_info = {
                        "name": parts[0],
                        "phone": parts[1],
                        "tier": parts[2],
                    }
                    break

        if not contact_info:
            print(f"Contact not found (redacted)")
            sys.exit(1)

        if contact_info["phone"] == "(no phone)":
            print(f"Contact has no phone number")
            sys.exit(1)

        print(f"Consolidating: contact ({contact_info['tier']}) [3-pass mode]")
        result = consolidate_contact(
            contact_info["name"],
            contact_info["phone"],
            tier=contact_info["tier"],
            dry_run=args.dry_run,
            verbose=args.verbose
        )
        print(f"\nStatus: {result['status']}")
        print(f"  Candidates: {result['candidates']}")
        print(f"  Accepted: {result['accepted']}")
        print(f"  Refined: {result['refined']}")
        print(f"  Refuted: {result['refuted']}")
        print(f"  Committed: {result['committed']}")
        if result["error"]:
            print(f"  Error: {result['error']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
