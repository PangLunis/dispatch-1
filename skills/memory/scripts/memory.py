#!/usr/bin/env -S uv run --script
"""
Memory CLI - Consolidation and bus search.

The old memory-search daemon (localhost:7890) has been retired.
Curated memories now live in CLAUDE.md + Contacts.app notes.
Conversation search uses bus FTS5: cd ~/dispatch && uv run -m bus.cli search "query"

Usage:
    memory.py consolidate <contact> [--dry-run] [--verbose]
    memory.py consolidate --all [--dry-run] [--verbose]
    memory.py search <query>  (delegates to bus FTS5)
"""

import argparse
import subprocess
import sys
from pathlib import Path


DISPATCH_DIR = Path.home() / "dispatch"


def cmd_consolidate(args):
    """Run nightly consolidation to extract memories to Contacts.app notes."""
    cmd = [str(DISPATCH_DIR / "prototypes/memory-consolidation/consolidate.py")]
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


def cmd_search(args):
    """Delegate search to bus FTS5."""
    cmd = ["uv", "run", "-m", "bus.cli", "search", args.query]
    if args.topic:
        cmd.extend(["--topic", args.topic])
    if args.key:
        cmd.extend(["--key", args.key])
    if args.since:
        cmd.extend(["--since", str(args.since)])
    if args.limit:
        cmd.extend(["--limit", str(args.limit)])
    subprocess.run(cmd, cwd=str(DISPATCH_DIR))


def cmd_retired(command_name):
    """Print retirement message for old daemon-backed commands."""
    print(f"The '{command_name}' command has been retired.")
    print()
    print("The memory-search daemon (localhost:7890) is no longer running.")
    print("Memories now live in:")
    print("  - CLAUDE.md (per-contact context, auto-loaded)")
    print("  - Contacts.app notes (populated by nightly consolidation)")
    print()
    print("To search conversation history:")
    print("  cd ~/dispatch && uv run -m bus.cli search \"query\" --topic messages")
    print()
    print("To run consolidation:")
    print("  uv run ~/.claude/skills/memory/scripts/memory.py consolidate --all")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Memory CLI - consolidation and bus search")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # consolidate
    consolidate_parser = subparsers.add_parser("consolidate", help="Extract memories to Contacts.app notes")
    consolidate_parser.add_argument("contact", nargs="?", help="Contact name (omit with --all)")
    consolidate_parser.add_argument("--all", action="store_true", help="Run for all contacts")
    consolidate_parser.add_argument("--dry-run", action="store_true", help="Show without writing")
    consolidate_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # search (delegates to bus FTS5)
    search_parser = subparsers.add_parser("search", help="Search conversation history (via bus FTS5)")
    search_parser.add_argument("query", help="Search text")
    search_parser.add_argument("--topic", help="Filter by topic (messages, sessions, system, tasks)")
    search_parser.add_argument("--key", help="Filter by chat_id/phone number")
    search_parser.add_argument("--since", type=int, help="Only last N days")
    search_parser.add_argument("--limit", type=int, help="Max results")

    args = parser.parse_args()

    if args.command == "consolidate":
        cmd_consolidate(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command in ("save", "load", "delete", "stats", "sync", "ask", "summary"):
        cmd_retired(args.command)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
