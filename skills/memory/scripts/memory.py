#!/usr/bin/env -S uv run --script
"""
Memory CLI - Store and retrieve persistent memories about contacts.

Uses jsmith-search HTTP API at localhost:7890 as the backend.

Usage:
    memory.py save <contact> <text> [--type TYPE] [--importance N]
    memory.py load <contact> [--type TYPE] [--limit N]
    memory.py search <query> [--contact CONTACT]
    memory.py sync <contact>
    memory.py stats
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Optional

# Server URL
SEARCH_API = "http://localhost:7890"
REGISTRY_PATH = Path.home() / "dispatch/state/sessions.json"


def _load_registry() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {}


def get_session_by_contact(contact_name: str) -> Optional[dict]:
    registry = _load_registry()
    contact_lower = contact_name.lower().replace(" ", "-")
    for entry in registry.values():
        entry_contact = entry.get("contact_name", "").lower().replace(" ", "-")
        if entry_contact == contact_lower:
            return entry
        entry_display = entry.get("display_name", "").lower().replace(" ", "-")
        if entry_display == contact_lower:
            return entry
    return None


TRANSCRIPTS_DIR = Path.home() / "transcripts"
LOG_PATH = Path.home() / ".claude" / "logs" / "memory.log"


def log_operation(operation: str, contact: str, details: str):
    """Log memory operations to file for auditing."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a") as f:
        f.write(f"{timestamp} | {operation} | {contact} | {details}\n")


def normalize_contact(identifier: str) -> str:
    """Normalize contact identifier to session-name format.

    Accepts:
    - Phone number (+1234567890) -> looks up contact, returns session name
    - Contact name (Jane Doe) -> converts to session name (jane-doe)
    - Session name (jane-doe) -> returns as-is
    """
    identifier = identifier.strip()

    # If it looks like a phone number, do a contact lookup
    if identifier.startswith("+") or identifier.replace("-", "").replace(" ", "").isdigit():
        import subprocess
        result = subprocess.run(
            [str(Path.home() / ".claude/skills/contacts/scripts/contacts"), "lookup", identifier],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            # Parse the contact lookup output to get the name
            # Format: "Name | tier | phone"
            parts = result.stdout.strip().split("|")
            if parts:
                name = parts[0].strip()
                return name.lower().replace(" ", "-")
        # If lookup fails, return as-is (will likely find no memories)
        return identifier

    # Already looks like a session name (lowercase with hyphens)
    if identifier == identifier.lower() and "-" in identifier:
        return identifier

    # Convert display name to session name
    return identifier.lower().replace(" ", "-")


def api_request(method: str, path: str, data: dict | None = None) -> dict:
    """Make an API request to jsmith-search."""
    url = f"{SEARCH_API}{path}"

    if method == "GET" and data:
        # Encode query params
        params = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in data.items() if v is not None)
        url = f"{url}?{params}"
        data = None

    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")

    if data:
        req.data = json.dumps(data).encode("utf-8")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else str(e)
        print(f"ERROR|API error {e.code}: {error_body}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR|Cannot connect to search daemon at {SEARCH_API}: {e.reason}")
        print("Make sure memory-search is running: cd ~/dispatch/services/memory-search && bun run src/daemon.ts")
        sys.exit(1)


def save_memory(contact: str, text: str, type_: str | None = None, importance: int = 3, tags: list | None = None):
    """Save a memory to the database."""
    contact = normalize_contact(contact)

    result = api_request("POST", "/memory/save", {
        "contact": contact,
        "memory_text": text,
        "type": type_ or "fact",
        "importance": importance,
        "tags": tags or [],
    })

    if result.get("success"):
        memory_id = result.get("id")
        log_operation("SAVE", contact, f"id={memory_id} type={type_ or 'fact'} text={text[:100]}")
        print(f"SAVED|{contact}|{type_ or 'fact'}|id={memory_id}|{text}")
    else:
        print(f"ERROR|{result.get('error', 'Unknown error')}")


def load_memories(contact: str, type_: str | None = None, limit: int = 20):
    """Load memories for a contact."""
    contact = normalize_contact(contact)

    params = {"contact": contact, "limit": limit}
    if type_:
        params["type"] = type_

    result = api_request("GET", "/memory/load", params)
    memories = result.get("memories", [])

    if not memories:
        print(f"EMPTY|{contact}|No memories found")
        return

    print(f"MEMORIES|{contact}|{len(memories)} found")
    for mem in memories:
        ts_str = mem.get("created_at", "")[:10] if mem.get("created_at") else "unknown"
        importance = mem.get("importance", 3)
        type_name = mem.get("type", "untyped")
        text = mem.get("memory_text", "")
        mem_id = mem.get("id", "?")
        print(f"  [{mem_id}] {ts_str} ({type_name}, imp={importance}): {text}")


def search_memories(query: str, contact: str | None = None):
    """Search memories by text."""
    params = {"q": query, "limit": 50}
    if contact:
        params["contact"] = normalize_contact(contact)

    result = api_request("GET", "/memory/search", params)
    memories = result.get("memories", [])

    if not memories:
        print(f"SEARCH|{query}|No results")
        return

    print(f"SEARCH|{query}|{len(memories)} results")
    for mem in memories:
        contact_ = mem.get("contact", "?")
        ts_str = mem.get("created_at", "")[:10] if mem.get("created_at") else "unknown"
        type_name = mem.get("type", "untyped")
        text = mem.get("memory_text", "")
        print(f"  [{contact_}] {ts_str} ({type_name}): {text}")


def delete_memory(memory_id: int):
    """Delete a memory by ID."""
    result = api_request("POST", "/memory/delete", {"id": memory_id})

    if result.get("success"):
        log_operation("DELETE", "?", f"id={memory_id}")
        print(f"DELETED|{memory_id}")
    else:
        print(f"ERROR|{result.get('error', 'Unknown error')}")


def get_stats():
    """Get memory statistics."""
    result = api_request("GET", "/memory/stats", {})

    print(f"STATS|{result.get('total', 0)} total memories")
    print("\nBy contact:")
    for contact, count in result.get("byContact", {}).items():
        print(f"  {contact}: {count}")
    print("\nBy type:")
    for type_, count in result.get("byType", {}).items():
        print(f"  {type_}: {count}")


def summary_for_session(contact: str):
    """Generate a human-like summary for session injection."""
    contact = normalize_contact(contact)

    result = api_request("GET", "/memory/load", {"contact": contact, "limit": 15})
    memories = result.get("memories", [])

    if not memories:
        print(f"SUMMARY|{contact}|No memories")
        return

    name = contact.replace('-', ' ').title()

    print(f"## About {name}")
    print("")
    print("What I know about them:")
    for mem in memories:
        print(f"- {mem.get('memory_text', '')}")
    print("")
    print("(Write and speak about them as a friend would, not as a database.)")


def sync_claude_md(contact: str):
    """Regenerate CLAUDE.md for a contact as a human-readable note."""
    entry = get_session_by_contact(contact)
    if not entry:
        print(f"No session found for contact: {contact}")
        return
    transcript_dir = Path(entry["transcript_dir"])
    claude_md_path = transcript_dir / "CLAUDE.md"

    contact = normalize_contact(contact)

    result = api_request("GET", "/memory/load", {"contact": contact, "limit": 100})
    memories = result.get("memories", [])

    if not memories:
        print(f"SYNC|{contact}|No memories to sync")
        return

    name = contact.replace('-', ' ').title()

    # Generate CLAUDE.md as a natural note
    lines = [
        f"# {name}",
        "",
        "What I know about them:",
        "",
    ]

    for mem in memories[:15]:  # Limit to keep it scannable
        lines.append(f"- {mem.get('memory_text', '')}")

    lines.extend([
        "",
        "---",
        f"*{len(memories)} memories · Last synced: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
    ])

    if not claude_md_path.parent.exists():
        print(f"ERROR|Transcript folder not found: {claude_md_path.parent}")
        return

    claude_md_path.write_text("\n".join(lines))
    log_operation("SYNC", contact, f"path={claude_md_path} memories={len(memories)}")
    print(f"SYNCED|{contact}|{claude_md_path}|{len(memories)} memories")


def ask_memories(contact: str, prompt: str):
    """Query memories based on a natural language prompt."""
    contact = normalize_contact(contact)

    # Search memories using FTS
    result = api_request("GET", "/memory/search", {"q": prompt, "contact": contact, "limit": 20})
    memories = result.get("memories", [])

    if not memories:
        # Fall back to loading all memories
        result = api_request("GET", "/memory/load", {"contact": contact, "limit": 20})
        memories = result.get("memories", [])

    if not memories:
        print(f"ASK|{contact}|No relevant memories found for: {prompt}")
        return

    # Format for Claude to interpret
    print(f"ASK|{contact}|{len(memories)} relevant memories")
    print(f"Question: {prompt}")
    print("---")
    for mem in memories:
        type_ = mem.get("type", "note")
        text = mem.get("memory_text", "")
        print(f"[{type_}] {text}")
    print("---")
    print("(Use these memories to answer the question)")


def consolidate_memories(contact: str):
    """Review today's transcript and output content for memory extraction."""
    entry = get_session_by_contact(contact)
    if not entry:
        print(f"No session found for contact: {contact}")
        return []
    session_name = entry["session_name"]
    sanitized = session_name.replace("/", "-")

    contact = normalize_contact(contact)
    from datetime import date

    # Find transcript files for this contact
    projects_dir = Path.home() / ".claude" / "projects"
    username = Path.home().name
    contact_project = projects_dir / f"-Users-{username}-transcripts-{sanitized}"

    if not contact_project.exists():
        print(f"CONSOLIDATE|{contact}|No transcript folder found")
        return

    # Get today's date
    today = date.today().isoformat()

    # Find JSONL files modified today
    jsonl_files = list(contact_project.glob("*.jsonl"))
    if not jsonl_files:
        print(f"CONSOLIDATE|{contact}|No transcript files found")
        return

    # Sort by modification time, get most recent
    jsonl_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    # Read messages from recent transcripts
    messages = []
    for jsonl_file in jsonl_files[:3]:  # Check last 3 transcript files
        try:
            with open(jsonl_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        # Get timestamp
                        ts = entry.get("timestamp", "")
                        if not ts.startswith(today):
                            continue  # Skip messages not from today

                        # Extract user messages (SMS content)
                        if entry.get("type") == "user":
                            msg = entry.get("message", {})
                            content = msg.get("content", "")
                            if isinstance(content, str) and "---SMS FROM" in content:
                                messages.append({
                                    "timestamp": ts,
                                    "content": content,
                                    "file": jsonl_file.name
                                })
                            elif isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        text = item.get("text", "")
                                        if "---SMS FROM" in text:
                                            messages.append({
                                                "timestamp": ts,
                                                "content": text,
                                                "file": jsonl_file.name
                                            })
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            continue

    if not messages:
        print(f"CONSOLIDATE|{contact}|No messages from today to consolidate")
        return

    # Output for Claude to review
    print(f"CONSOLIDATE|{contact}|{len(messages)} messages from today")
    print("=" * 60)
    print("REMEMBER LIKE A FRIEND, NOT A DATABASE")
    print("")
    print("Ask yourself: What would I tell someone about this person?")
    print("")
    print("Good memories sound like:")
    print('  - "He loves building systems and seeing them come to life"')
    print('  - "We designed the podcast system together over text"')
    print('  - "She thinks through problems out loud"')
    print("")
    print("Bad memories sound like:")
    print('  - "prefers concise text responses" (too mechanical)')
    print('  - "uses X email for Spotify" (config, not memory)')
    print('  - "admin tier - full access" (system data, not personal)')
    print("")
    print("Vibe check: Would you say this out loud to a mutual friend?")
    print("")
    print(f"Save with: memory save '{contact}' 'memory text'")
    print("(Types are optional - natural language is better)")
    print("=" * 60)
    print("")

    for msg in messages[:20]:  # Limit to 20 messages
        print(f"[{msg['timestamp'][:16]}]")
        # Clean up the content for display
        content = msg['content']
        # Remove the SMS wrapper if present
        if "---SMS FROM" in content:
            lines = content.split('\n')
            for line in lines:
                if line.strip() and not line.startswith('---'):
                    print(f"  {line}")
        else:
            print(f"  {content}")
        print("")

    print("=" * 60)
    print(f"After reviewing, run: memory sync {contact}")
    print("=" * 60)


def main():
    # Need urllib.parse for encoding
    import urllib.parse

    parser = argparse.ArgumentParser(description="Memory CLI - backed by jsmith-search")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # save
    save_parser = subparsers.add_parser("save", help="Save a memory")
    save_parser.add_argument("contact", help="Contact name (e.g., jane-doe)")
    save_parser.add_argument("text", help="Memory text")
    save_parser.add_argument("--type", "-t", dest="type_", help="Memory type")
    save_parser.add_argument("--importance", "-i", type=int, default=3, help="Importance 1-5")

    # load
    load_parser = subparsers.add_parser("load", help="Load memories for contact")
    load_parser.add_argument("contact", help="Contact name")
    load_parser.add_argument("--type", "-t", dest="type_", help="Filter by type")
    load_parser.add_argument("--limit", "-n", type=int, default=20, help="Max results")

    # delete
    delete_parser = subparsers.add_parser("delete", help="Delete a memory")
    delete_parser.add_argument("id", type=int, help="Memory ID to delete")

    # search
    search_parser = subparsers.add_parser("search", help="Search memories")
    search_parser.add_argument("query", help="Search text")
    search_parser.add_argument("--contact", "-c", help="Filter by contact")

    # stats
    subparsers.add_parser("stats", help="Show memory statistics")

    # sync
    sync_parser = subparsers.add_parser("sync", help="Sync CLAUDE.md for contact")
    sync_parser.add_argument("contact", help="Contact name")

    # ask
    ask_parser = subparsers.add_parser("ask", help="Query memories with natural language")
    ask_parser.add_argument("contact", help="Contact name")
    ask_parser.add_argument("prompt", help="Question or topic to explore")

    # summary
    summary_parser = subparsers.add_parser("summary", help="Generate compact summary for session")
    summary_parser.add_argument("contact", help="Contact name")

    # consolidate (old: review transcripts, new: extract to Contacts.app)
    consolidate_parser = subparsers.add_parser("consolidate", help="Extract memories to Contacts.app notes")
    consolidate_parser.add_argument("contact", nargs="?", help="Contact name (omit with --all)")
    consolidate_parser.add_argument("--all", action="store_true", help="Run for all contacts")
    consolidate_parser.add_argument("--dry-run", action="store_true", help="Show without writing")
    consolidate_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.command == "save":
        save_memory(args.contact, args.text, args.type_, args.importance)
    elif args.command == "load":
        load_memories(args.contact, args.type_, args.limit)
    elif args.command == "delete":
        delete_memory(args.id)
    elif args.command == "search":
        search_memories(args.query, args.contact)
    elif args.command == "stats":
        get_stats()
    elif args.command == "sync":
        sync_claude_md(args.contact)
    elif args.command == "ask":
        ask_memories(args.contact, args.prompt)
    elif args.command == "summary":
        summary_for_session(args.contact)
    elif args.command == "consolidate":
        # Call the new consolidation prototype
        import subprocess
        cmd = [str(Path.home() / "dispatch/prototypes/memory-consolidation/consolidate.py")]
        if args.all:
            cmd.append("--all")
        elif args.contact:
            cmd.append(args.contact)
        else:
            print("ERROR: specify a contact name or use --all")
            sys.exit(1)
        if getattr(args, 'dry_run', False):
            cmd.append("--dry-run")
        if getattr(args, 'verbose', False):
            cmd.append("--verbose")
        subprocess.run(cmd)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
