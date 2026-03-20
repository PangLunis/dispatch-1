#!/usr/bin/env -S uv run --script
"""
Per-Chat Context Consolidation

Extracts conversation-level context (ongoing projects, pending follow-ups,
recent topics, preferences) and writes to CONTEXT.md in each chat's
transcript directory.

Usage:
    consolidate_chat.py <chat_id>           # Single chat
    consolidate_chat.py --all               # All active chats
    consolidate_chat.py --dry-run <chat_id> # Preview without writing
    consolidate_chat.py --verbose <chat_id> # Show all passes
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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Paths
HOME = Path.home()
DISPATCH_DIR = HOME / "dispatch"
LOGS_DIR = DISPATCH_DIR / "logs"
LOG_FILE = LOGS_DIR / "chat-context-consolidation.log"
TRANSCRIPTS_DIR = HOME / "transcripts"
READ_SMS_CLI = HOME / ".claude/skills/sms-assistant/scripts/read-sms"
CONTACTS_CLI = HOME / ".claude/skills/contacts/scripts/contacts"
SESSIONS_FILE = DISPATCH_DIR / "state/sessions.json"

# Format markers
MANAGED_HEADER = "<!-- CLAUDE-MANAGED:v1 -->"
MAX_CONTEXT_SIZE = 2048  # 2KB max
STALE_DAYS = 14  # Prune items not mentioned in 14+ days

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

def is_caroline_chat(contact_name: str, chat_id: str) -> bool:
    """Check if this chat involves Caroline."""
    name_lower = contact_name.lower() if contact_name else ""
    return "caroline" in name_lower or "caro" in name_lower


# ============================================================
# PASS A: SUGGESTER
# ============================================================

def get_suggester_prompt(chat_id: str, contact_name: str, is_group: bool) -> str:
    """System prompt for Pass A - extract context candidates."""

    chat_type = "group chat" if is_group else "conversation"

    return f"""You are extracting conversation context from a {chat_type} with {contact_name}.

## YOUR TOOLS

You have access to the Bash tool. Use it to:
~/.claude/skills/sms-assistant/scripts/read-sms --chat "{chat_id}" --limit 100

## WHAT TO EXTRACT

### Ongoing Projects/Tasks
Active things being worked on together. Examples:
- "Helping plan trip to X"
- "Debugging Y together"
- "Working on Z feature"

### Pending Follow-ups
Things requested but not yet completed:
- "Asked me to remind about X"
- "Need to send them Y"
- "Waiting for response about Z"

### Recent Topics (last 3-5)
What was discussed recently for continuity:
- "Discussed memory system architecture"
- "Talked about vacation plans"

### Communication Preferences
Explicitly stated preferences:
- "Prefers short responses"
- "Asked for more detail on X topics"
- "Uses signal for sensitive stuff"

## CRITICAL RULES

1. **ONLY extract from actual messages** - include the EXACT supporting quote
2. Focus on ACTIVE/ONGOING items, not completed ones
3. For group chats, note who initiated if relevant
4. Max 15 candidates total across all categories
5. Skip transient chatter ("ok", "thanks", "lol")

### ❌ DO NOT EXTRACT:
- Things from CLAUDE.md or system rules (those are not chat-derived)
- Inferred preferences without explicit quote
- Context from OTHER chats (stay in THIS chat only)
- General knowledge about the person (that goes in contact notes, not CONTEXT.md)

## OUTPUT FORMAT

Output as JSON:
```json
{{
  "ongoing": [
    {{"item": "Helping plan Maui trip (May 19-26)", "quote": "we're looking at May 19-26 for Maui"}}
  ],
  "pending": [
    {{"item": "Remind about flight booking by Feb 20", "quote": "can you remind me to book flights"}}
  ],
  "topics": [
    {{"item": "Memory consolidation system", "quote": "let's brainstorm per-chat memory"}}
  ],
  "preferences": [
    {{"item": "Prefers concise responses", "quote": "keep it brief please"}}
  ]
}}
```

If nothing found for a category, use empty array.
Start by reading recent messages."""


# ============================================================
# PASS B: REVIEWER
# ============================================================

def get_reviewer_prompt(chat_id: str, contact_name: str, existing_context: str) -> str:
    """System prompt for Pass B - verify and merge context."""

    today = datetime.now().strftime("%Y-%m-%d")

    return f"""You are fact-checking proposed conversation context for {contact_name}.

## YOUR TOOLS

You have access to the Bash tool. You can:

1. Read messages via CLI:
~/.claude/skills/sms-assistant/scripts/read-sms --chat "{chat_id}" --limit 200

2. Query SQLite directly for exact quote verification:
sqlite3 ~/Library/Messages/chat.db "SELECT text FROM message m JOIN chat_message_join cmj ON m.ROWID = cmj.message_id JOIN chat c ON cmj.chat_id = c.ROWID WHERE c.chat_identifier LIKE '%{chat_id}%' AND text LIKE '%search term%' LIMIT 10"

Use SQLite queries to verify exact quotes exist. This is more reliable than grep.

## EXISTING CONTEXT (to merge with):
{existing_context if existing_context else "(none)"}

## YOUR TASK

For each proposed item:
1. **SEARCH for the exact quote** in the messages - it MUST exist
2. Check if the item is still active/relevant (not completed)
3. Check for duplicates with existing context
4. Add today's date [{today}] as last-mentioned marker

## CRITICAL VERIFICATION RULES

- **REFUTE if quote not found** - don't accept items without evidence
- **REFUTE if from CLAUDE.md/system rules** - only chat-derived context
- **REFUTE if from a different chat** - watch for cross-contamination
- **REFUTE preferences without explicit quote** - "prefers X" needs "I prefer X" in messages

## DECISIONS

For each item, decide:
- **ACCEPT**: Quote verified word-for-word in THIS chat, item is current
- **MERGE**: Already exists in current context, update date
- **REFUTE**: Quote not found, from wrong source, or item is completed/stale

## OUTPUT FORMAT

Output as JSON:
```json
{{
  "ongoing": [
    {{"decision": "ACCEPT", "item": "Helping plan Maui trip (May 19-26)", "date": "{today}", "verified_quote": "we're looking at May 19-26"}},
    {{"decision": "REFUTE", "item": "Some other thing", "reason": "quote not found in messages"}}
  ],
  "pending": [...],
  "topics": [...],
  "preferences": [...]
}}
```

Also output items to KEEP from existing context (still relevant):
```json
{{
  "keep_from_existing": [
    {{"category": "ongoing", "item": "...", "date": "2026-02-10"}}
  ]
}}
```

Be STRICT. If you can't find the exact quote, REFUTE it."""


# ============================================================
# PASS C: COMMITTER
# ============================================================

def format_context_md(
    ongoing: list[dict],
    pending: list[dict],
    topics: list[dict],
    preferences: list[dict]
) -> str:
    """Format context items into CONTEXT.md content."""

    lines = [MANAGED_HEADER]

    if ongoing:
        lines.append("## Ongoing")
        for item in ongoing[:5]:  # Max 5
            lines.append(f"- {item['item']} [{item.get('date', datetime.now().strftime('%Y-%m-%d'))}]")
        lines.append("")

    if pending:
        lines.append("## Pending")
        for item in pending[:5]:  # Max 5
            lines.append(f"- {item['item']}")
        lines.append("")

    if topics:
        lines.append("## Recent Topics")
        for item in topics[:5]:  # Max 5
            lines.append(f"- {item['item']}")
        lines.append("")

    if preferences:
        lines.append("## Preferences")
        for item in preferences[:3]:  # Max 3
            lines.append(f"- {item['item']}")
        lines.append("")

    lines.append("---")
    lines.append(f"*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    content = "\n".join(lines)

    # Enforce max size
    if len(content) > MAX_CONTEXT_SIZE:
        # Truncate topics first, then ongoing
        while len(content) > MAX_CONTEXT_SIZE and topics:
            topics.pop()
            content = format_context_md(ongoing, pending, topics, preferences)
        while len(content) > MAX_CONTEXT_SIZE and ongoing:
            ongoing.pop()
            content = format_context_md(ongoing, pending, topics, preferences)

    return content


# ============================================================
# UTILITIES
# ============================================================

def log(message: str):
    """Log to consolidation log file."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"{timestamp} | {message}\n")


def get_transcript_dir(chat_id: str) -> Optional[Path]:
    """Find the transcript directory for a chat_id."""
    # Check both iMessage and Signal backends
    for backend in ["imessage", "signal"]:
        # Sanitize chat_id (+ becomes _)
        sanitized = chat_id.replace("+", "_")
        path = TRANSCRIPTS_DIR / backend / sanitized
        if path.exists():
            return path
    return None


def get_existing_context(transcript_dir: Path) -> str:
    """Read existing CONTEXT.md if it exists."""
    context_file = transcript_dir / "CONTEXT.md"
    if context_file.exists():
        return context_file.read_text()
    return ""


def parse_existing_context(content: str) -> dict:
    """Parse existing CONTEXT.md into structured data."""
    result = {"ongoing": [], "pending": [], "topics": [], "preferences": []}

    if not content:
        return result

    current_section = None
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("## Ongoing"):
            current_section = "ongoing"
        elif line.startswith("## Pending"):
            current_section = "pending"
        elif line.startswith("## Recent Topics"):
            current_section = "topics"
        elif line.startswith("## Preferences"):
            current_section = "preferences"
        elif line.startswith("- ") and current_section:
            item_text = line[2:]
            # Extract date if present
            date_match = re.search(r'\[(\d{4}-\d{2}-\d{2})\]', item_text)
            date = date_match.group(1) if date_match else None
            item = re.sub(r'\s*\[\d{4}-\d{2}-\d{2}\]', '', item_text)
            result[current_section].append({"item": item, "date": date})

    return result


def prune_stale_items(items: list[dict], stale_days: int = STALE_DAYS) -> list[dict]:
    """Remove items not mentioned in stale_days."""
    cutoff = datetime.now() - timedelta(days=stale_days)
    result = []
    for item in items:
        if item.get("date"):
            try:
                item_date = datetime.strptime(item["date"], "%Y-%m-%d")
                if item_date >= cutoff:
                    result.append(item)
            except ValueError:
                result.append(item)  # Keep if date parsing fails
        else:
            result.append(item)  # Keep if no date
    return result


def call_claude_agent(system_prompt: str, user_prompt: str, verbose: bool = False, pass_name: str = "") -> str:
    """Call Claude via CLI with tool access."""

    # Clear CLAUDECODE to allow spawning from SDK session
    clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    cmd = [
        "claude",
        "-p",
        "--tools", "Bash,Read",
        "--allowed-tools", 'Bash(*/.claude/skills/sms-assistant/scripts/read-sms*)',
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
            preview_lines = output.split('\n')[:5]
            print(f"  [{pass_name}] Output preview:")
            for line in preview_lines:
                print(f"    {line[:100]}")
            if len(output.split('\n')) > 5:
                print(f"    ... ({len(output.split(chr(10)))} total lines)")

        return output

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{pass_name} timed out after 15min")


def extract_json_from_output(output: str) -> dict:
    """Extract JSON object from agent output."""
    # Try to find JSON in markdown code blocks
    json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', output)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON object
    obj_match = re.search(r'\{[\s\S]*\}', output)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            pass

    return {}


def get_contact_name(chat_id: str) -> str:
    """Get contact name for a chat_id."""
    # Try phone lookup
    if chat_id.startswith("+") or chat_id.startswith("_"):
        phone = chat_id.replace("_", "+")
        result = subprocess.run(
            [str(CONTACTS_CLI), "lookup", phone],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|")
            if parts:
                return parts[0].strip()

    # For group chats, just use the chat_id
    return f"Group {chat_id[:8]}"


def is_group_chat(chat_id: str) -> bool:
    """Check if a chat_id is a group chat (hex UUID vs phone number)."""
    # Phone numbers start with + or _ (sanitized +)
    if chat_id.startswith("+") or chat_id.startswith("_"):
        return False
    # Hex UUIDs are 32 chars
    if len(chat_id) == 32 and all(c in "0123456789abcdef" for c in chat_id):
        return True
    return False


# ============================================================
# MAIN CONSOLIDATION FLOW
# ============================================================

def consolidate_chat(chat_id: str, dry_run: bool = False, verbose: bool = False) -> dict:
    """Run 3-pass context consolidation for a single chat."""

    result = {
        "chat_id": chat_id,
        "status": "unknown",
        "ongoing": 0,
        "pending": 0,
        "topics": 0,
        "preferences": 0,
        "error": None,
    }

    # Find transcript directory
    transcript_dir = get_transcript_dir(chat_id)
    if not transcript_dir:
        result["status"] = "skipped"
        result["error"] = "No transcript directory found"
        return result

    # Skip chats with no new messages since last consolidation
    if not has_new_messages_since_last_consolidation(chat_id, transcript_dir):
        result["status"] = "skipped"
        result["error"] = "No new messages since last consolidation"
        log(f"Skipped {chat_id}: no new messages since last consolidation")
        return result

    contact_name = get_contact_name(chat_id)
    is_group = is_group_chat(chat_id)

    log(f"Starting context consolidation for {contact_name} ({chat_id})")

    if verbose:
        print(f"  Chat: ({'group' if is_group else 'individual'})")
        print(f"  Transcript dir: (redacted)")

    # Get existing context
    existing_content = get_existing_context(transcript_dir)
    existing_context = parse_existing_context(existing_content)

    # ========== PASS A: SUGGESTER ==========
    if verbose:
        print(f"\n  === PASS A: SUGGESTER ===")

    suggester_system = get_suggester_prompt(chat_id, contact_name, is_group)
    suggester_user = f"Extract conversation context for {contact_name}. Start by reading recent messages."

    try:
        suggester_output = call_claude_agent(suggester_system, suggester_user, verbose, "PASS A")
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Pass A error: {e}"
        log(f"Pass A error for {chat_id}: {e}")
        return result

    candidates = extract_json_from_output(suggester_output)

    if not candidates or not any(candidates.get(k) for k in ["ongoing", "pending", "topics", "preferences"]):
        result["status"] = "skipped"
        result["error"] = "No context candidates found"
        log(f"Skipped {chat_id}: no candidates from pass A")
        return result

    if verbose:
        for category in ["ongoing", "pending", "topics", "preferences"]:
            items = candidates.get(category, [])
            if items:
                print(f"  [PASS A] {category}: {len(items)} candidates")

    # ========== PASS B: REVIEWER ==========
    if verbose:
        print(f"\n  === PASS B: REVIEWER ===")

    reviewer_system = get_reviewer_prompt(chat_id, contact_name, existing_content)
    reviewer_user = f"""Review these context candidates for {contact_name}:

{json.dumps(candidates, indent=2)}

Verify quotes and merge with existing context."""

    try:
        reviewer_output = call_claude_agent(reviewer_system, reviewer_user, verbose, "PASS B")
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Pass B error: {e}"
        log(f"Pass B error for {chat_id}: {e}")
        return result

    decisions = extract_json_from_output(reviewer_output)

    # Collect accepted items
    final_ongoing = []
    final_pending = []
    final_topics = []
    final_preferences = []

    for category, final_list in [
        ("ongoing", final_ongoing),
        ("pending", final_pending),
        ("topics", final_topics),
        ("preferences", final_preferences)
    ]:
        for item in decisions.get(category, []):
            if item.get("decision") in ["ACCEPT", "MERGE"]:
                final_list.append({
                    "item": item.get("item", ""),
                    "date": item.get("date", datetime.now().strftime("%Y-%m-%d"))
                })

    # Add kept items from existing context
    for kept in decisions.get("keep_from_existing", []):
        category = kept.get("category")
        if category == "ongoing":
            final_ongoing.append(kept)
        elif category == "pending":
            final_pending.append(kept)
        elif category == "topics":
            final_topics.append(kept)
        elif category == "preferences":
            final_preferences.append(kept)

    # Prune stale items
    final_ongoing = prune_stale_items(final_ongoing)

    # CRITICAL: Filter out proposal-related content if this is Caroline's chat
    if is_caroline_chat(contact_name, chat_id):
        log(f"⚠️ Caroline's chat - filtering proposal-related content")
        for category_list in [final_ongoing, final_pending, final_topics, final_preferences]:
            original_len = len(category_list)
            category_list[:] = [item for item in category_list if not is_proposal_leak_risk(item.get("item", ""))]
            filtered = original_len - len(category_list)
            if filtered > 0:
                log(f"⚠️ FILTERED {filtered} proposal-related item(s) from Caroline's context")

    if verbose:
        print(f"  [PASS B] Final: {len(final_ongoing)} ongoing, {len(final_pending)} pending, {len(final_topics)} topics, {len(final_preferences)} preferences")

    result["ongoing"] = len(final_ongoing)
    result["pending"] = len(final_pending)
    result["topics"] = len(final_topics)
    result["preferences"] = len(final_preferences)

    if not any([final_ongoing, final_pending, final_topics, final_preferences]):
        result["status"] = "skipped"
        result["error"] = "No context items after review"
        return result

    # ========== PASS C: COMMITTER ==========
    if verbose:
        print(f"\n  === PASS C: COMMITTER ===")

    context_content = format_context_md(final_ongoing, final_pending, final_topics, final_preferences)

    if dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN - Would write CONTEXT.md:")
        print(f"{'='*60}")
        print(context_content)
        print(f"{'='*60}\n")
        result["status"] = "dry_run"
        return result

    # Write atomically
    context_file = transcript_dir / "CONTEXT.md"
    try:
        # Write to temp file first
        with tempfile.NamedTemporaryFile(mode='w', dir=transcript_dir, delete=False, suffix='.tmp') as f:
            f.write(context_content)
            temp_path = f.name

        # Atomic rename
        os.rename(temp_path, context_file)

        result["status"] = "updated"
        log(f"Updated context for {chat_id}: {result['ongoing']} ongoing, {result['pending']} pending, {result['topics']} topics")

    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Write failed: {e}"
        log(f"Write error for {chat_id}: {e}")

    return result


def has_new_messages_since_last_consolidation(chat_id: str, transcript_dir: Path) -> bool:
    """Check if there are new messages since the last CONTEXT.md update.

    Returns True if there are new messages or if we can't determine (erring on side of processing).
    """
    context_file = transcript_dir / "CONTEXT.md"
    if not context_file.exists():
        return True  # No existing context = needs consolidation

    # Get CONTEXT.md last modified time
    context_mtime = context_file.stat().st_mtime
    context_date = datetime.fromtimestamp(context_mtime)

    # Check for recent messages using read-sms CLI
    try:
        result = subprocess.run(
            [str(READ_SMS_CLI), "--chat", chat_id, "--limit", "1"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0 or not result.stdout.strip():
            return True  # Can't determine, process it

        # Parse the most recent message timestamp
        # Format: "2026-03-13 07:35:39 | +16175969496 | IN | message text"
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(" | ", 3)
            if len(parts) >= 3:
                try:
                    msg_date = datetime.strptime(parts[0].strip(), "%Y-%m-%d %H:%M:%S")
                    return msg_date > context_date
                except ValueError:
                    continue

        return True  # Can't parse, process it
    except (subprocess.TimeoutExpired, OSError):
        return True  # Can't determine, process it


def get_active_chats() -> list[str]:
    """Get list of active chat IDs from sessions registry."""
    if not SESSIONS_FILE.exists():
        return []

    try:
        sessions = json.loads(SESSIONS_FILE.read_text())
        return list(sessions.keys())
    except (json.JSONDecodeError, OSError):
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Per-chat context consolidation"
    )
    parser.add_argument("chat_id", nargs="?", help="Chat ID to consolidate")
    parser.add_argument("--all", action="store_true", help="Run for all active chats")
    parser.add_argument("--dry-run", action="store_true", help="Show without writing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.all:
        chat_ids = get_active_chats()
        print(f"Consolidating context for {len(chat_ids)} active chats...")
        log(f"Starting batch context consolidation for {len(chat_ids)} chats")

        results = []
        for i, chat_id in enumerate(chat_ids):
            print(f"\n[{i+1}/{len(chat_ids)}] chat")
            result = consolidate_chat(chat_id, dry_run=args.dry_run, verbose=args.verbose)
            results.append(result)
            print(f"  Status: {result['status']}")

            if not args.dry_run and i < len(chat_ids) - 1:
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

    elif args.chat_id:
        print(f"Consolidating context for: (redacted)")
        result = consolidate_chat(args.chat_id, dry_run=args.dry_run, verbose=args.verbose)
        print(f"\nStatus: {result['status']}")
        print(f"  Ongoing: {result['ongoing']}")
        print(f"  Pending: {result['pending']}")
        print(f"  Topics: {result['topics']}")
        print(f"  Preferences: {result['preferences']}")
        if result["error"]:
            print(f"  Error: {result['error']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
