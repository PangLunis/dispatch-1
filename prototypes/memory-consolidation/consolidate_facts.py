#!/usr/bin/env -S uv run --script
"""
Nightly Fact Extraction — Structured Facts from Daily Conversations

Extracts structured facts (travel, events, preferences) from each contact's
daily messages and writes them to the facts table in bus.db.

Runs as part of the nightly consolidation cron.

Usage:
    consolidate_facts.py --all                # Run for all contacts
    consolidate_facts.py <contact>            # Run for one contact (by name)
    consolidate_facts.py --dry-run --all      # Extract but don't write to DB
    consolidate_facts.py --verbose --all      # Show LLM input/output
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
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────
HOME = Path.home()
DISPATCH_DIR = HOME / "dispatch"
DB_PATH = DISPATCH_DIR / "state" / "bus.db"
LOGS_DIR = DISPATCH_DIR / "logs"
EXTRACTION_LOG = LOGS_DIR / "fact-extraction.jsonl"
CONTACTS_CLI = HOME / ".claude/skills/contacts/scripts/contacts"
READ_SMS_CLI = HOME / ".claude/skills/sms-assistant/scripts/read-sms"
SEND_SMS_CLI = HOME / ".claude/skills/sms-assistant/scripts/send-sms"
FACT_CLI = DISPATCH_DIR / "scripts" / "fact"

sys.path.insert(0, str(DISPATCH_DIR))

# ── Feature flag ──────────────────────────────────────────────
FACTS_ENABLED = os.environ.get("FACTS_ENABLED", "0") == "1"

# ── Circuit breaker thresholds ────────────────────────────────
MAX_NEW_FACTS_PER_CONTACT = 20
MAX_NEW_FACTS_TOTAL = 50

# ── Phase 1 fact types ───────────────────────────────────────
VALID_FACT_TYPES = {"travel", "event", "preference"}

REQUIRED_DETAIL_KEYS = {
    "travel": {"destination"},
    "event": set(),
    "preference": {"domain"},
}


# ── Extraction Prompt ─────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are extracting structured facts from today's conversations. You will be given:
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

IMPORTANT:
- Output ONLY valid JSON. No markdown fences, no explanation text.
- fact_type must be one of: travel, event, preference
- For travel: details MUST include "destination" (string)
- For preference: details MUST include "domain" (string)
- All dates in details should be ISO 8601 (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)
- starts_at/ends_at should be ISO 8601 UTC datetime strings
- If no facts to extract, output: {"new_facts": [], "updated_facts": [], "expired_fact_ids": []}"""


def build_extraction_user_prompt(
    contact_name: str,
    messages_text: str,
    existing_facts: list[dict],
) -> str:
    """Build the user prompt for the extraction LLM call."""
    facts_str = json.dumps(existing_facts, indent=2) if existing_facts else "[]"
    return f"""Contact: {contact_name}

Today's messages:
{messages_text}

Existing active facts for this contact:
{facts_str}

Extract structured facts from today's messages. Output ONLY valid JSON."""


# ── Utilities ─────────────────────────────────────────────────

def log_info(msg: str, verbose: bool = False):
    """Print to stderr for logging."""
    if verbose:
        print(f"  [INFO] {msg}", file=sys.stderr)


def log_warn(msg: str):
    """Print warning to stderr."""
    print(f"  [WARN] {msg}", file=sys.stderr)


def log_error(msg: str):
    """Print error to stderr."""
    print(f"  [ERROR] {msg}", file=sys.stderr)


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_all_contacts() -> list[dict]:
    """Get all contacts with phone numbers and tiers (same pattern as consolidate_3pass.py)."""
    result = subprocess.run(
        [str(CONTACTS_CLI), "list"],
        capture_output=True, text=True, timeout=30,
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


def get_todays_messages(phone: str, verbose: bool = False) -> str:
    """Read today's messages for a contact using read-sms CLI.

    Returns formatted messages with timestamps for the extraction prompt.
    """
    # Get messages from the last ~24 hours
    since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    result = subprocess.run(
        [str(READ_SMS_CLI), "--chat", phone, "--since", since, "--limit", "500"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        log_warn(f"read-sms failed for {phone}: {result.stderr[:200]}")
        return ""

    return result.stdout.strip()


def get_existing_facts(contact: str, max_facts: int = 30) -> list[dict]:
    """Load active facts for a contact from the fact CLI.

    Context window management: prioritize temporal facts with upcoming dates,
    then most recently created/updated non-temporal facts. Max 30 per contact.
    """
    result = subprocess.run(
        [str(FACT_CLI), "list", "--contact", contact, "--active", "--json"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        all_facts = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        log_warn(f"Failed to parse existing facts JSON for {contact}")
        return []

    if not all_facts:
        return []

    # Prioritize: temporal facts with upcoming dates first (within 30 days),
    # then most recently created/updated non-temporal facts
    now = datetime.now(timezone.utc)
    cutoff = (now + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    temporal = []
    non_temporal = []

    for fact in all_facts:
        starts_at = fact.get("starts_at")
        if starts_at and starts_at <= cutoff:
            temporal.append(fact)
        else:
            non_temporal.append(fact)

    # Sort temporal by starts_at ascending
    temporal.sort(key=lambda f: f.get("starts_at", ""))

    # Sort non-temporal by most recently created/updated
    def sort_key(f):
        return f.get("updated_at") or f.get("created_at") or ""
    non_temporal.sort(key=sort_key, reverse=True)

    # Combine, respecting max_facts limit
    prioritized = temporal + non_temporal
    return prioritized[:max_facts]


def call_claude_extraction(
    contact_name: str,
    messages_text: str,
    existing_facts: list[dict],
    verbose: bool = False,
) -> dict:
    """Call Claude via CLI with structured output for fact extraction.

    Returns parsed JSON dict with new_facts, updated_facts, expired_fact_ids.
    """
    # Strip existing facts down to id, fact_type, summary, details for prompt
    # (no need to send internal metadata to the LLM)
    slim_facts = []
    for f in existing_facts:
        slim = {
            "id": f.get("id"),
            "fact_type": f.get("fact_type"),
            "summary": f.get("summary"),
        }
        if f.get("details"):
            slim["details"] = f["details"]
        if f.get("starts_at"):
            slim["starts_at"] = f["starts_at"]
        if f.get("ends_at"):
            slim["ends_at"] = f["ends_at"]
        slim_facts.append(slim)

    user_prompt = build_extraction_user_prompt(contact_name, messages_text, slim_facts)

    if verbose:
        print(f"  [EXTRACTION] System prompt length: {len(EXTRACTION_SYSTEM_PROMPT)}", file=sys.stderr)
        print(f"  [EXTRACTION] User prompt length: {len(user_prompt)}", file=sys.stderr)
        print(f"  [EXTRACTION] User prompt:\n{user_prompt[:500]}...", file=sys.stderr)

    # Clear CLAUDECODE env var to allow spawning from SDK session
    clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--model", "opus",
        "--system-prompt", EXTRACTION_SYSTEM_PROMPT,
    ]

    try:
        result = subprocess.run(
            cmd,
            input=user_prompt,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes per contact
            env=clean_env,
        )

        if result.returncode != 0:
            raise RuntimeError(f"claude CLI failed (code {result.returncode}): {result.stderr[:500]}")

        raw_output = result.stdout.strip()
        if not raw_output:
            raise RuntimeError("claude CLI returned empty output")

        if verbose:
            print(f"  [EXTRACTION] Raw output:\n{raw_output[:500]}", file=sys.stderr)

        # Parse the response — claude -p --output-format json wraps in {"result": "..."}
        try:
            wrapper = json.loads(raw_output)
            if isinstance(wrapper, dict) and "result" in wrapper:
                inner = wrapper["result"]
                if isinstance(inner, str):
                    # The actual extraction JSON is inside the result string
                    extraction = json.loads(inner)
                elif isinstance(inner, dict):
                    extraction = inner
                else:
                    raise RuntimeError(f"Unexpected result type: {type(inner)}")
            elif isinstance(wrapper, dict) and "new_facts" in wrapper:
                # Direct JSON output (no wrapper)
                extraction = wrapper
            else:
                raise RuntimeError(f"Unexpected output structure: {list(wrapper.keys()) if isinstance(wrapper, dict) else type(wrapper)}")
        except json.JSONDecodeError:
            # Try extracting JSON from raw output (fallback)
            extraction = _extract_json_from_text(raw_output)

        return extraction

    except subprocess.TimeoutExpired:
        raise RuntimeError("Extraction timed out after 5 minutes")


def _extract_json_from_text(text: str) -> dict:
    """Fallback: extract JSON object from text that may contain markdown fences."""
    # Try ```json ... ``` blocks
    json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding a JSON object using raw_decode (handles nested braces correctly)
    decoder = json.JSONDecoder()
    # Find first '{' and try to parse from there
    for i, ch in enumerate(text):
        if ch == '{':
            try:
                obj, _ = decoder.raw_decode(text, i)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue

    raise RuntimeError(f"Could not parse extraction JSON from output: {text[:200]}")


# ── Validation & Coercion ─────────────────────────────────────

def validate_new_fact(fact: dict) -> tuple[bool, str, dict]:
    """Validate and coerce a new fact from the extraction output.

    Returns (ok, error_message, coerced_fact).
    """
    # Check required top-level keys
    required = {"fact_type", "summary", "confidence", "details"}
    missing = required - set(fact.keys())
    if missing:
        return False, f"Missing keys: {missing}", fact

    fact_type = fact.get("fact_type", "")
    if fact_type not in VALID_FACT_TYPES:
        return False, f"Invalid fact_type: {fact_type}", fact

    confidence = fact.get("confidence", "")
    if confidence not in ("high", "medium", "low"):
        return False, f"Invalid confidence: {confidence}", fact

    # Validate details schema
    details = fact.get("details") or {}
    if not isinstance(details, dict):
        return False, f"details must be a dict, got {type(details).__name__}", fact

    required_keys = REQUIRED_DETAIL_KEYS.get(fact_type, set())
    missing_keys = required_keys - set(details.keys())
    if missing_keys:
        return False, f"Missing required detail keys for {fact_type}: {missing_keys}", fact

    # Coerce date fields in details
    for key in ("depart", "return"):
        if key in details and isinstance(details[key], str):
            details[key] = _coerce_date(details[key])

    # Coerce starts_at/ends_at
    if fact.get("starts_at") and isinstance(fact["starts_at"], str):
        fact["starts_at"] = _coerce_date(fact["starts_at"])
    if fact.get("ends_at") and isinstance(fact["ends_at"], str):
        fact["ends_at"] = _coerce_date(fact["ends_at"])

    fact["details"] = details
    return True, "", fact


def validate_updated_fact(fact: dict) -> tuple[bool, str, dict]:
    """Validate an updated fact from the extraction output.

    Returns (ok, error_message, coerced_fact).
    """
    if "existing_fact_id" not in fact:
        return False, "Missing existing_fact_id for updated fact", fact

    # Coerce date fields if present
    details = fact.get("details") or {}
    if isinstance(details, dict):
        for key in ("depart", "return"):
            if key in details and isinstance(details[key], str):
                details[key] = _coerce_date(details[key])
        fact["details"] = details

    if fact.get("starts_at") and isinstance(fact["starts_at"], str):
        fact["starts_at"] = _coerce_date(fact["starts_at"])
    if fact.get("ends_at") and isinstance(fact["ends_at"], str):
        fact["ends_at"] = _coerce_date(fact["ends_at"])

    return True, "", fact


def _coerce_date(value: str) -> str:
    """Coerce a date string to ISO 8601 format."""
    if not value:
        return value

    # Already valid ISO formats
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            datetime.strptime(value, fmt)
            return value
        except ValueError:
            continue

    # Try common natural formats
    current_year = datetime.now().year
    formats_with_year = [
        "%B %d, %Y", "%b %d %Y", "%m/%d/%Y", "%d %B %Y", "%d %b %Y",
    ]
    for fmt in formats_with_year:
        try:
            dt = datetime.strptime(value.strip(), fmt)
            result = dt.strftime("%Y-%m-%d")
            log_warn(f"Coerced date '{value}' -> '{result}'")
            return result
        except ValueError:
            continue

    # Formats without year — add current year
    no_year = [("%B %d", "%B %d %Y"), ("%b %d", "%b %d %Y")]
    for _, parse_fmt in no_year:
        try:
            dt = datetime.strptime(f"{value.strip()} {current_year}", parse_fmt)
            result = dt.strftime("%Y-%m-%d")
            log_warn(f"Coerced date '{value}' -> '{result}'")
            return result
        except ValueError:
            continue

    return value


# ── Fact Writing (via fact CLI) ───────────────────────────────

def save_fact(
    contact: str,
    fact: dict,
    source: str = "sms",
    source_ref: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> int | None:
    """Save a new fact using the fact CLI. Returns fact ID or None on failure."""
    cmd = [
        str(FACT_CLI), "save",
        "--contact", contact,
        "--type", fact["fact_type"],
        "--summary", fact["summary"],
        "--confidence", fact.get("confidence", "high"),
        "--source", source,
        "--json",
    ]

    if fact.get("details"):
        cmd.extend(["--details", json.dumps(fact["details"])])
    if fact.get("starts_at"):
        cmd.extend(["--starts", fact["starts_at"]])
    if fact.get("ends_at"):
        cmd.extend(["--ends", fact["ends_at"]])
    if source_ref:
        cmd.extend(["--source-ref", source_ref])

    if dry_run:
        print(f"  [DRY RUN] Would save: {fact['summary']} ({fact['fact_type']}, {fact.get('confidence', '?')})")
        return None

    if verbose:
        print(f"  [SAVE] {' '.join(cmd)}", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        log_error(f"fact save failed: {result.stderr[:200]}")
        return None

    try:
        saved = json.loads(result.stdout.strip())
        return saved.get("id")
    except (json.JSONDecodeError, AttributeError):
        # Parse ID from non-JSON output as fallback
        match = re.search(r'#(\d+)', result.stdout)
        return int(match.group(1)) if match else None


def update_fact(
    fact_id: int,
    updates: dict,
    dry_run: bool = False,
    verbose: bool = False,
) -> bool:
    """Update an existing fact using the fact CLI. Returns True on success."""
    cmd = [str(FACT_CLI), "update", str(fact_id), "--json"]

    if updates.get("summary"):
        cmd.extend(["--summary", updates["summary"]])
    if updates.get("details"):
        cmd.extend(["--details", json.dumps(updates["details"])])
    if updates.get("starts_at"):
        cmd.extend(["--starts", updates["starts_at"]])
    if updates.get("ends_at"):
        cmd.extend(["--ends", updates["ends_at"]])
    if updates.get("confidence"):
        cmd.extend(["--confidence", updates["confidence"]])

    if dry_run:
        print(f"  [DRY RUN] Would update fact #{fact_id}: {updates.get('summary', '(no summary change)')}")
        return True

    if verbose:
        print(f"  [UPDATE] {' '.join(cmd)}", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        log_error(f"fact update #{fact_id} failed: {result.stderr[:200]}")
        return False

    return True


def expire_fact_ids(fact_ids: list[int], dry_run: bool = False, verbose: bool = False) -> int:
    """Expire specific facts by ID. Returns count of expired facts."""
    expired = 0
    for fid in fact_ids:
        if dry_run:
            print(f"  [DRY RUN] Would expire fact #{fid}")
            expired += 1
            continue

        result = subprocess.run(
            [str(FACT_CLI), "deactivate", str(fid)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            expired += 1
            if verbose:
                print(f"  [EXPIRE] Deactivated fact #{fid}", file=sys.stderr)
        else:
            log_error(f"fact deactivate #{fid} failed: {result.stderr[:200]}")

    return expired


def run_temporal_expiration(dry_run: bool = False, verbose: bool = False):
    """Run temporal expiration pass (expire facts past their end date)."""
    if dry_run:
        print("  [DRY RUN] Would run temporal expiration")
        return

    result = subprocess.run(
        [str(FACT_CLI), "expire"],
        capture_output=True, text=True, timeout=60,
    )
    if verbose and result.stdout.strip():
        print(f"  [EXPIRE] {result.stdout.strip()}", file=sys.stderr)


def run_garbage_collection(dry_run: bool = False, verbose: bool = False):
    """Run garbage collection on old deactivated facts."""
    if dry_run:
        print("  [DRY RUN] Would run garbage collection")
        return

    result = subprocess.run(
        [str(FACT_CLI), "gc"],
        capture_output=True, text=True, timeout=60,
    )
    if verbose and result.stdout.strip():
        print(f"  [GC] {result.stdout.strip()}", file=sys.stderr)


def inject_facts_into_claude_md(contact: str, dry_run: bool = False, verbose: bool = False):
    """Inject active facts into contact's CLAUDE.md."""
    if dry_run:
        print(f"  [DRY RUN] Would inject facts into CLAUDE.md for {contact}")
        return

    result = subprocess.run(
        [str(FACT_CLI), "inject", "--contact", contact],
        capture_output=True, text=True, timeout=60,
    )
    if verbose and result.stdout.strip():
        print(f"  [INJECT] {result.stdout.strip()}", file=sys.stderr)


def update_last_confirmed(contact: str, existing_facts: list[dict], dry_run: bool = False):
    """Update last_confirmed for all active facts of a contact who had conversation activity today.

    Uses direct SQLite since the fact CLI doesn't expose this specific operation.
    """
    if dry_run:
        return

    import sqlite3
    now = utcnow()
    conn = None
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "UPDATE facts SET last_confirmed = ? WHERE contact = ? AND active = 1",
            (now, contact),
        )
        conn.commit()
    except Exception as e:
        log_warn(f"Failed to update last_confirmed for {contact}: {e}")
    finally:
        if conn:
            conn.close()


# ── Logging ───────────────────────────────────────────────────

def log_extraction_run(entry: dict):
    """Append an entry to the fact-extraction JSONL log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(EXTRACTION_LOG, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ── Admin Summary ─────────────────────────────────────────────

def send_admin_summary(
    results: list[dict],
    total_new: int,
    total_updated: int,
    total_expired: int,
    contacts_processed: int,
    circuit_breaker_tripped: bool,
    dry_run: bool = False,
):
    """Send morning summary to admin via SMS."""
    if dry_run:
        print("  [DRY RUN] Would send admin summary SMS")
        return

    if total_new == 0 and total_updated == 0 and total_expired == 0:
        # Skip if zero changes (per plan spec)
        return

    lines = [
        f"Nightly facts: {total_new} new, {total_updated} updated, {total_expired} expired across {contacts_processed} contacts."
    ]

    # List new facts
    new_details = []
    for r in results:
        for nf in r.get("new_facts_saved", []):
            conf_flag = " ⚠️" if nf.get("confidence") == "low" else ""
            new_details.append(f'"{nf["summary"]}" ({nf["fact_type"]}, {nf.get("confidence", "?")}{conf_flag})')

    if new_details:
        lines.append("New: " + ", ".join(new_details))

    if circuit_breaker_tripped:
        lines.append("⚠️ Circuit breaker tripped — review extraction log.")

    # Check for per-contact failures
    failures = [r for r in results if r.get("error")]
    if failures:
        fail_names = [r["contact_name"] for r in failures]
        lines.append(f"Failures: {', '.join(fail_names)}")

    message = "\n".join(lines)

    # Get admin phone from contacts
    admin_phone = _get_admin_phone()
    if not admin_phone:
        log_error("Could not determine admin phone for summary SMS")
        return

    subprocess.run(
        [str(SEND_SMS_CLI), admin_phone, message],
        capture_output=True, text=True, timeout=30,
    )


def _get_admin_phone() -> str | None:
    """Get admin phone number from contacts."""
    result = subprocess.run(
        [str(CONTACTS_CLI), "list"],
        capture_output=True, text=True, timeout=30,
    )
    for line in result.stdout.strip().split('\n'):
        if '|' not in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 3 and parts[2].lower() == "admin":
            return parts[1]
    return None


# ── Per-Contact Extraction ────────────────────────────────────

def extract_contact_facts(
    contact_name: str,
    phone: str,
    tier: str,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Run fact extraction for a single contact with fault isolation.

    Returns a result dict with extraction stats.
    """
    result = {
        "contact_name": contact_name,
        "phone": phone,
        "tier": tier,
        "status": "unknown",
        "wall_clock_ms": 0,
        "sources": {"messages": 0, "emails": 0, "calendar_events": 0},
        "existing_facts_shown": 0,
        "new_facts": 0,
        "updated_facts": 0,
        "expired_facts": 0,
        "low_confidence_facts": 0,
        "rejected_facts": 0,
        "circuit_breaker_tripped": False,
        "new_facts_saved": [],
        "error": None,
    }

    start_time = time.monotonic()

    try:
        # 1. Read today's messages
        messages_text = get_todays_messages(phone, verbose=verbose)
        if not messages_text:
            result["status"] = "skipped"
            result["error"] = "No messages in last 24h"
            result["wall_clock_ms"] = int((time.monotonic() - start_time) * 1000)
            return result

        # Count messages (rough: lines containing timestamp patterns or | separators)
        msg_lines = [l for l in messages_text.split('\n') if l.strip() and ('|' in l or re.match(r'\[\d{4}-', l))]
        result["sources"]["messages"] = len(msg_lines)

        if verbose:
            print(f"  Messages: {len(msg_lines)} lines", file=sys.stderr)

        # 2. Load existing active facts (max 30 for context window management)
        existing_facts = get_existing_facts(phone, max_facts=30)
        result["existing_facts_shown"] = len(existing_facts)

        if verbose:
            print(f"  Existing facts: {len(existing_facts)}", file=sys.stderr)

        # 3. Run LLM extraction pass
        extraction = call_claude_extraction(
            contact_name, messages_text, existing_facts, verbose=verbose,
        )

        new_facts = extraction.get("new_facts", [])
        updated_facts = extraction.get("updated_facts", [])
        expired_fact_ids = extraction.get("expired_fact_ids", [])

        if verbose:
            print(f"  Extraction: {len(new_facts)} new, {len(updated_facts)} updated, {len(expired_fact_ids)} expired", file=sys.stderr)

        # 4. Validate and coerce new facts
        validated_new = []
        for nf in new_facts:
            ok, err, coerced = validate_new_fact(nf)
            if ok:
                validated_new.append(coerced)
            else:
                result["rejected_facts"] += 1
                log_warn(f"Rejected new fact for {contact_name}: {err} — {json.dumps(nf)[:200]}")

        # 4b. Validate updated facts
        validated_updates = []
        for uf in updated_facts:
            ok, err, coerced = validate_updated_fact(uf)
            if ok:
                validated_updates.append(coerced)
            else:
                result["rejected_facts"] += 1
                log_warn(f"Rejected updated fact for {contact_name}: {err} — {json.dumps(uf)[:200]}")

        # 4c. Validate expired fact IDs (must be integers referencing existing facts)
        existing_ids = {f.get("id") for f in existing_facts}
        validated_expired = [eid for eid in expired_fact_ids if isinstance(eid, int) and eid in existing_ids]
        invalid_expired = [eid for eid in expired_fact_ids if eid not in validated_expired]
        if invalid_expired:
            log_warn(f"Ignoring invalid expired_fact_ids for {contact_name}: {invalid_expired}")

        # 5. Circuit breaker check
        new_count = len(validated_new)
        if new_count > MAX_NEW_FACTS_PER_CONTACT:
            result["circuit_breaker_tripped"] = True
            result["status"] = "circuit_breaker"
            result["error"] = f"Circuit breaker: {new_count} new facts exceeds per-contact limit of {MAX_NEW_FACTS_PER_CONTACT}"
            log_error(result["error"])
            # Log but do NOT commit
            result["new_facts"] = new_count
            result["updated_facts"] = len(validated_updates)
            result["expired_facts"] = len(validated_expired)
            result["wall_clock_ms"] = int((time.monotonic() - start_time) * 1000)
            return result

        # 6. Count low-confidence facts
        result["low_confidence_facts"] = sum(
            1 for f in validated_new if f.get("confidence") == "low"
        )

        # 7. Write new facts
        for nf in validated_new:
            fact_id = save_fact(
                phone, nf,
                source="sms",
                source_ref=None,
                dry_run=dry_run,
                verbose=verbose,
            )
            if fact_id is not None or dry_run:
                result["new_facts_saved"].append({
                    "id": fact_id,
                    "fact_type": nf["fact_type"],
                    "summary": nf["summary"],
                    "confidence": nf.get("confidence"),
                })

        result["new_facts"] = len(validated_new)

        # 8. Apply updates
        for uf in validated_updates:
            success = update_fact(
                uf["existing_fact_id"],
                {
                    "summary": uf.get("summary"),
                    "details": uf.get("details"),
                    "starts_at": uf.get("starts_at"),
                    "ends_at": uf.get("ends_at"),
                    "confidence": uf.get("confidence"),
                },
                dry_run=dry_run,
                verbose=verbose,
            )
            if success:
                result["updated_facts"] += 1

        # 9. Expire facts
        result["expired_facts"] = expire_fact_ids(validated_expired, dry_run=dry_run, verbose=verbose)

        # 10. Update last_confirmed for all active facts (contact had activity today)
        update_last_confirmed(phone, existing_facts, dry_run=dry_run)

        result["status"] = "success"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        log_error(f"Extraction failed for {contact_name}: {e}")

    result["wall_clock_ms"] = int((time.monotonic() - start_time) * 1000)
    return result


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Nightly fact extraction from daily conversations"
    )
    parser.add_argument("contact", nargs="?", help="Contact name to extract for")
    parser.add_argument("--all", action="store_true", help="Run for all contacts")
    parser.add_argument("--dry-run", action="store_true", help="Extract but don't write to DB")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show LLM input/output details")

    args = parser.parse_args()

    # Check feature flag
    if not FACTS_ENABLED:
        print("Fact extraction is disabled (FACTS_ENABLED != 1). Skipping.", file=sys.stderr)
        sys.exit(0)

    if not args.all and not args.contact:
        parser.print_help()
        sys.exit(1)

    # ── Determine contacts to process ─────────────────────────
    if args.all:
        contacts = get_all_contacts()
        print(f"Fact extraction for {len(contacts)} contacts...")
    else:
        # Look up single contact
        all_contacts = get_all_contacts()
        contact_info = None
        for c in all_contacts:
            if args.contact.lower() in c["name"].lower():
                contact_info = c
                break
        if not contact_info:
            print(f"Contact not found: {args.contact}", file=sys.stderr)
            sys.exit(1)
        contacts = [contact_info]
        print(f"Fact extraction for {contact_info['name']} ({contact_info['tier']})")

    # ── Process each contact ──────────────────────────────────
    results = []
    total_new_all = 0
    circuit_breaker_global = False

    for i, contact in enumerate(contacts):
        # Global circuit breaker: check BEFORE processing next contact
        if total_new_all > MAX_NEW_FACTS_TOTAL:
            circuit_breaker_global = True
            log_error(f"Global circuit breaker: {total_new_all} total new facts exceeds limit of {MAX_NEW_FACTS_TOTAL}")
            print(f"\n⚠️ Global circuit breaker tripped at {total_new_all} new facts. Skipping remaining contacts.")
            break

        if args.all:
            print(f"\n[{i+1}/{len(contacts)}] {contact['name']} ({contact['tier']})")

        result = extract_contact_facts(
            contact["name"],
            contact["phone"],
            tier=contact["tier"],
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        results.append(result)

        total_new_all += result["new_facts"]

        print(f"  Status: {result['status']} | msgs={result['sources']['messages']} "
              f"new={result['new_facts']} updated={result['updated_facts']} "
              f"expired={result['expired_facts']} rejected={result['rejected_facts']}")

        if result.get("error"):
            print(f"  Error: {result['error']}")

        # Small delay between contacts to avoid rate limiting
        if not args.dry_run and i < len(contacts) - 1:
            time.sleep(2)

    # ── Post-processing ───────────────────────────────────────

    # Run temporal expiration pass
    print("\nRunning temporal expiration...")
    run_temporal_expiration(dry_run=args.dry_run, verbose=args.verbose)

    # Run garbage collection
    print("Running garbage collection...")
    run_garbage_collection(dry_run=args.dry_run, verbose=args.verbose)

    # Inject facts into CLAUDE.md for each contact that had changes
    print("Injecting facts into CLAUDE.md files...")
    for contact in contacts:
        inject_facts_into_claude_md(contact["phone"], dry_run=args.dry_run, verbose=args.verbose)

    # ── Logging ───────────────────────────────────────────────
    total_new = sum(r["new_facts"] for r in results)
    total_updated = sum(r["updated_facts"] for r in results)
    total_expired = sum(r["expired_facts"] for r in results)
    total_rejected = sum(r["rejected_facts"] for r in results)
    contacts_processed = sum(1 for r in results if r["status"] == "success")

    for r in results:
        log_entry = {
            "timestamp": utcnow(),
            "contact": r["phone"],
            "wall_clock_ms": r["wall_clock_ms"],
            "sources": r["sources"],
            "existing_facts_shown": r["existing_facts_shown"],
            "new_facts": r["new_facts"],
            "updated_facts": r["updated_facts"],
            "expired_facts": r["expired_facts"],
            "low_confidence_facts": r["low_confidence_facts"],
            "rejected_facts": r["rejected_facts"],
            "circuit_breaker_tripped": r["circuit_breaker_tripped"],
        }
        if r.get("error"):
            log_entry["error"] = r["error"]
        log_extraction_run(log_entry)

    # ── Summary ───────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("FACT EXTRACTION SUMMARY")
    print(f"{'='*60}")
    print(f"  Contacts processed: {contacts_processed}/{len(contacts)}")
    print(f"  New facts:     {total_new}")
    print(f"  Updated facts: {total_updated}")
    print(f"  Expired facts: {total_expired}")
    print(f"  Rejected:      {total_rejected}")
    if circuit_breaker_global:
        print(f"  ⚠️ Global circuit breaker was tripped")

    by_status = {}
    for r in results:
        s = r["status"]
        by_status[s] = by_status.get(s, 0) + 1
    for status, count in sorted(by_status.items()):
        print(f"  {status}: {count}")

    # ── Admin SMS ─────────────────────────────────────────────
    any_circuit_breaker = circuit_breaker_global or any(r["circuit_breaker_tripped"] for r in results)
    send_admin_summary(
        results,
        total_new,
        total_updated,
        total_expired,
        contacts_processed,
        any_circuit_breaker,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
