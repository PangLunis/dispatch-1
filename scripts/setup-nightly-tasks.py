#!/usr/bin/env -S uv run --script
"""
Set up nightly ephemeral tasks via the reminder/scheduler system.

Creates six cron reminders that fire task.requested events:
1. Vacation house scraper (agent mode, 1:45am) - runs nightly-scraper + builds HTML report
2. Memory consolidation (script mode, 2:00am) - runs consolidate_3pass + consolidate_chat
3. Skillify analysis (agent mode, 2:10am) - runs /skillify --nightly
4. Bug finder scan (agent mode, 2:20am) - runs /bug-finder --nightly
5. Latency finder scan (agent mode, 2:30am) - runs /latency-finder --nightly
6. Sven Times gazette (agent mode, 2:40am) - generates daily gazette from system activity

These replace the hardcoded 2am consolidation in manager.py.

Usage:
    setup-nightly-tasks.py           # Add all reminders
    setup-nightly-tasks.py --list    # Show existing nightly task reminders
    setup-nightly-tasks.py --remove  # Remove existing nightly task reminders
"""
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import sys
from pathlib import Path

# Add dispatch to path
sys.path.insert(0, str(Path.home() / "dispatch"))

from assistant import config
from assistant.reminders import (
    create_reminder, load_reminders, save_reminders, reminders_lock,
)


def _get_admin_phone() -> str:
    """Look up admin phone from config (never hardcode)."""
    return config.require("owner.phone")


# Task IDs are stable so we can detect duplicates
VACATION_SCRAPER_TASK_ID = "nightly-vacation-scraper"
CONSOLIDATION_TASK_ID = "nightly-consolidation"
SKILLIFY_TASK_ID = "nightly-skillify"
BUGFINDER_TASK_ID = "nightly-bugfinder"
LATENCYFINDER_TASK_ID = "nightly-latencyfinder"
SVENTIMES_TASK_ID = "nightly-sventimes"

NIGHTLY_TASK_IDS = {VACATION_SCRAPER_TASK_ID, CONSOLIDATION_TASK_ID, SKILLIFY_TASK_ID, BUGFINDER_TASK_ID, LATENCYFINDER_TASK_ID, SVENTIMES_TASK_ID}

# Vacation house scraper prompt
VACATION_SCRAPER_PROMPT = (
    "Run the nightly vacation house scraper: "
    "~/.claude/skills/vacation-house/scripts/nightly-scraper --notify "
    "Then build a beautiful HTML report from the results using the bus dashboard "
    "design pattern (Space Grotesk + warm papery palette) with photo carousels, "
    "exec summary, and score badges. Publish to sven-pages as vacation-scraper-YYYY-MM-DD. "
    "Send a short SMS summary + link to the group chat 95fa934b84bc4f9aa4dfe22ac9d72afb."
)

# Bug finder prompt
BUGFINDER_PROMPT = (
    "Run /bug-finder --nightly to scan ~/dispatch/ for bugs. "
    "Focus on code changed in the last 24 hours but scan the whole codebase. "
    "Use the full 3-phase pipeline: parallel discovery explorers, "
    "parallel refinement reviewers (ACCEPT/REFINE/REFUTE), then compile report. "
    "All subagents must use opus. "
    "Send the bug report to admin via SMS only if there are ACCEPT or REFINE verdicts. "
    "If clean scan, log silently."
)

LATENCYFINDER_PROMPT = (
    "Run /latency-finder --nightly to scan for performance bottlenecks. "
    "Analyze perf JSONL, bus.db sdk_events, bus.db records, and system resources "
    "for slow queries, tool executions, and processing delays. "
    "Use the full discovery→refinement pipeline with opus subagents. "
    "Send the report to admin via SMS only if there are ACCEPT or REFINE verdicts. "
    "If clean scan (all metrics within baselines), log silently."
)

# Sven Times daily gazette prompt
SVENTIMES_PROMPT = (
    "Generate today's edition of The Sven Times — a daily gazette of system activity.\n\n"
    "TONE & STYLE: Professional newspaper voice with understated wit. Third-person perspective. "
    "Write as if reporting on a complex technical system for an audience of engineers. "
    "Example lead: 'The messaging subsystem processed 400 inbound messages across eight active sessions "
    "yesterday, while a nightly consolidation pass merged conversation context for all contacts.'\n\n"
    "Steps:\n"
    "1. GATHER DATA: Run: uv run ~/code/svenflow.ai/scripts/gather-daily-data (defaults to today). "
    "This script already applies OPSEC filtering (blocklist, PII regex, IP/UUID redaction).\n\n"
    "2. READ TEMPLATE: Read ~/code/svenflow.ai/pages/times/index.html — replicate its exact HTML structure, CSS, and class names. "
    "Do NOT invent new structure; match what exists.\n\n"
    "3. READ BLOCKLIST: Read ~/code/svenflow.ai/scripts/opsec-blocklist.txt — this is the AUTHORITATIVE source of blocked terms. "
    "In addition to those terms, these CATEGORIES are always denied:\n"
    "   - Infrastructure identifiers: IP addresses, ports, hostnames, API keys, session IDs, commit SHAs\n"
    "   - Media services: streaming, downloading, media automation, media management\n"
    "   - Real estate: property searches, listings, addresses, house hunting\n"
    "   - PII: phone numbers, email addresses, real names of ANY contacts or people (except the system builder in the about section)\n"
    "   - Contact info: chat IDs, group IDs, phone numbers\n"
    "   When in doubt, OMIT. Never mention what was filtered — just skip it entirely.\n\n"
    "4. PLAN CONTENT: Before writing HTML, plan the gazette as structured notes:\n"
    "   Lead article: kicker, headline, 1-sentence summary, 150-250 word body with a pull-quote\n"
    "   2 dispatch articles: kicker, headline, 60-100 word summary\n"
    "   3-4 briefing items: headline + 1-2 sentence description\n"
    "   Editor's desk: 2-3 sentences, 50-80 words\n"
    "   Valid kickers: INFRASTRUCTURE, MESSAGING, SESSION MANAGEMENT, HEALTH, DEVELOPMENT, AUTOMATION, OPERATIONS\n"
    "   SPARSE DATA: If total messages.received < 10 AND tasks list is empty AND git_commits is empty, "
    "generate a 'quiet day' edition — focus on uptime/stability themes, system health metrics, shorter content.\n"
    "   ERROR: If gather-daily-data exits non-zero or returns {\"error\": ...}, generate a minimal edition "
    "noting data was unavailable with a brief system status.\n\n"
    "5. WRITE HTML: Fill the template structure with the planned content.\n"
    "   Dateline format: 'Vol. 1 · [Full weekday], [Month] [Day], [Year]' (e.g., 'Vol. 1 · Friday, March 21, 2026')\n"
    "   Use drop-cap class on the lead article's first paragraph.\n"
    "   Include a pull-quote in the lead article.\n"
    "   Use ABSOLUTE font paths: /pages/times/fonts/source-serif-4.woff2\n\n"
    "6. OPSEC VERIFICATION (MANDATORY): Run the deterministic verifier:\n"
    "   uv run ~/code/svenflow.ai/scripts/verify-opsec ~/code/svenflow.ai/pages/times/index.html\n"
    "   This checks ALL blocklist terms PLUS pattern-based detection (phone, email, IP, UUID, git SHA).\n"
    "   If it reports violations, fix them in the HTML and re-run verify-opsec until it prints CLEAN.\n"
    "   Do NOT proceed to deploy until verify-opsec exits with code 0.\n\n"
    "7. ARCHIVE: Run: uv run ~/code/svenflow.ai/scripts/archive-edition\n"
    "   This deterministic script archives yesterday's edition and updates editions.json. Do not do this manually.\n\n"
    "8. DEPLOY: cd ~/code/svenflow.ai && npm run build && bash deploy.sh\n"
    "   If deploy fails, do NOT retry. Log the error and exit.\n\n"
    "9. Do NOT send any SMS notification — this runs silently."
)

# Skillify prompt (single source of truth, used in both instructions and execution.prompt)
SKILLIFY_PROMPT = (
    "Run /skillify --nightly to analyze today's conversations for "
    "new skill opportunities and improvements to existing skills. "
    "This runs the full discovery→refinement pipeline. "
    "When done, send a concise summary of findings to the admin via SMS."
)


def _build_vacation_scraper_reminder(admin_phone: str) -> dict:
    """Build the vacation house scraper reminder config."""
    return {
        "title": "Nightly vacation house scraper",
        "schedule_type": "cron",
        "schedule_value": "45 1 * * *",  # 1:45am daily (before consolidation)
        "tz_name": "America/New_York",
        "event": {
            "topic": "tasks",
            "type": "task.requested",
            "key": admin_phone,
            "payload": {
                "task_id": VACATION_SCRAPER_TASK_ID,
                "title": "Nightly vacation house scraper",
                "requested_by": admin_phone,
                "instructions": VACATION_SCRAPER_PROMPT,
                "notify": True,
                "timeout_minutes": 120,
                "execution": {
                    "mode": "agent",
                    "prompt": VACATION_SCRAPER_PROMPT,
                },
            },
        },
    }


def _build_consolidation_reminder(admin_phone: str) -> dict:
    """Build the consolidation reminder config."""
    return {
        "title": "Nightly memory consolidation",
        "schedule_type": "cron",
        "schedule_value": "0 2 * * *",  # 2am daily
        "tz_name": "America/New_York",
        "event": {
            "topic": "tasks",
            "type": "task.requested",
            "key": admin_phone,
            "payload": {
                "task_id": CONSOLIDATION_TASK_ID,
                "title": "Nightly memory consolidation",
                "requested_by": admin_phone,
                "instructions": "Run the nightly memory consolidation scripts",
                "notify": True,
                "timeout_minutes": 60,
                "execution": {
                    "mode": "script",
                    # Store $HOME-relative path; bash expands $HOME at runtime
                    "command": [
                        "bash", "-c",
                        "$HOME/dispatch/scripts/nightly-consolidation.sh",
                    ],
                },
            },
        },
    }


def _build_skillify_reminder(admin_phone: str) -> dict:
    """Build the skillify reminder config."""
    return {
        "title": "Nightly skillify analysis",
        "schedule_type": "cron",
        "schedule_value": "10 2 * * *",  # 2:10am daily (staggered)
        "tz_name": "America/New_York",
        "event": {
            "topic": "tasks",
            "type": "task.requested",
            "key": admin_phone,
            "payload": {
                "task_id": SKILLIFY_TASK_ID,
                "title": "Nightly skillify analysis",
                "requested_by": admin_phone,
                "instructions": SKILLIFY_PROMPT,
                "notify": True,
                "timeout_minutes": 90,
                "execution": {
                    "mode": "agent",
                    "prompt": SKILLIFY_PROMPT,
                },
            },
        },
    }


def _build_bugfinder_reminder(admin_phone: str) -> dict:
    """Build the bug finder reminder config."""
    return {
        "title": "Nightly bug finder scan",
        "schedule_type": "cron",
        "schedule_value": "20 2 * * *",  # 2:20am daily (staggered)
        "tz_name": "America/New_York",
        "event": {
            "topic": "tasks",
            "type": "task.requested",
            "key": admin_phone,
            "payload": {
                "task_id": BUGFINDER_TASK_ID,
                "title": "Nightly bug finder scan",
                "requested_by": admin_phone,
                "instructions": BUGFINDER_PROMPT,
                "notify": True,
                "timeout_minutes": 90,
                "execution": {
                    "mode": "agent",
                    "prompt": BUGFINDER_PROMPT,
                },
            },
        },
    }


def _build_latencyfinder_reminder(admin_phone: str) -> dict:
    """Build the latency finder reminder config."""
    return {
        "title": "Nightly latency finder scan",
        "schedule_type": "cron",
        "schedule_value": "30 2 * * *",  # 2:30am daily (staggered)
        "tz_name": "America/New_York",
        "event": {
            "topic": "tasks",
            "type": "task.requested",
            "key": admin_phone,
            "payload": {
                "task_id": LATENCYFINDER_TASK_ID,
                "title": "Nightly latency finder scan",
                "requested_by": admin_phone,
                "instructions": LATENCYFINDER_PROMPT,
                "notify": True,
                "timeout_minutes": 90,
                "execution": {
                    "mode": "agent",
                    "prompt": LATENCYFINDER_PROMPT,
                },
            },
        },
    }


def _build_sventimes_reminder(admin_phone: str) -> dict:
    """Build the Sven Times daily gazette reminder config."""
    return {
        "title": "Nightly Sven Times gazette",
        "schedule_type": "cron",
        "schedule_value": "40 2 * * *",  # 2:40am daily (after other agents)
        "tz_name": "America/New_York",
        "event": {
            "topic": "tasks",
            "type": "task.requested",
            "key": admin_phone,
            "payload": {
                "task_id": SVENTIMES_TASK_ID,
                "title": "Nightly Sven Times gazette",
                "requested_by": admin_phone,
                "instructions": SVENTIMES_PROMPT,
                "notify": False,
                "timeout_minutes": 60,
                "execution": {
                    "mode": "agent",
                    "prompt": SVENTIMES_PROMPT,
                },
            },
        },
    }


def find_existing(reminders: list) -> list:
    """Find existing nightly task reminders by task_id in event payload."""
    found = []
    for r in reminders:
        event = r.get("event", {})
        payload = event.get("payload", {})
        if payload.get("task_id") in NIGHTLY_TASK_IDS:
            found.append(r)
    return found


def cmd_list():
    with reminders_lock():
        data = load_reminders()
    existing = find_existing(data["reminders"])
    if not existing:
        print("No nightly task reminders found.")
        return
    for r in existing:
        task_id = r.get("event", {}).get("payload", {}).get("task_id", "?")
        cron = r.get("schedule", {}).get("value", "?")
        print(f"  [{r['id']}] {r['title']} (cron: {cron}, task: {task_id})")


def cmd_remove():
    with reminders_lock():
        data = load_reminders()
        existing = find_existing(data["reminders"])
        if not existing:
            print("No nightly task reminders to remove.")
            return
        ids_to_remove = {r["id"] for r in existing}
        data["reminders"] = [r for r in data["reminders"] if r["id"] not in ids_to_remove]
        save_reminders(data)
    for r in existing:
        print(f"  Removed: {r['title']} ({r['id']})")


def cmd_add():
    admin_phone = _get_admin_phone()

    with reminders_lock():
        data = load_reminders()

        # Check for existing
        existing = find_existing(data["reminders"])
        if existing:
            print("Nightly task reminders already exist:")
            for r in existing:
                print(f"  [{r['id']}] {r['title']}")
            print("\nUse --remove first to replace them.")
            return

        # Create vacation scraper reminder
        r0 = create_reminder(**_build_vacation_scraper_reminder(admin_phone))
        data["reminders"].append(r0)
        print(f"  Added: {r0['title']} (id={r0['id']}, cron=45 1 * * *, mode=agent)")

        # Create consolidation reminder
        r1 = create_reminder(**_build_consolidation_reminder(admin_phone))
        data["reminders"].append(r1)
        print(f"  Added: {r1['title']} (id={r1['id']}, cron=0 2 * * *, mode=script)")

        # Create skillify reminder
        r2 = create_reminder(**_build_skillify_reminder(admin_phone))
        data["reminders"].append(r2)
        print(f"  Added: {r2['title']} (id={r2['id']}, cron=0 2 * * *, mode=agent)")

        # Create bug finder reminder
        r3 = create_reminder(**_build_bugfinder_reminder(admin_phone))
        data["reminders"].append(r3)
        print(f"  Added: {r3['title']} (id={r3['id']}, cron=20 2 * * *, mode=agent)")

        # Create latency finder reminder
        r4 = create_reminder(**_build_latencyfinder_reminder(admin_phone))
        data["reminders"].append(r4)
        print(f"  Added: {r4['title']} (id={r4['id']}, cron=30 2 * * *, mode=agent)")

        # Create Sven Times gazette reminder
        r5 = create_reminder(**_build_sventimes_reminder(admin_phone))
        data["reminders"].append(r5)
        print(f"  Added: {r5['title']} (id={r5['id']}, cron=40 2 * * *, mode=agent)")

        save_reminders(data)

    print("\n✅ All nightly tasks scheduled (staggered, ET):")
    print("  1:45am - Vacation house scraper (120min timeout, agent mode)")
    print("  2:00am - Memory consolidation (60min timeout, script mode)")
    print("  2:10am - Skillify analysis (90min timeout, agent mode)")
    print("  2:20am - Bug finder scan (90min timeout, agent mode)")
    print("  2:30am - Latency finder scan (90min timeout, agent mode)")
    print("  2:40am - Sven Times gazette (60min timeout, agent mode)")


def main():
    if "--list" in sys.argv:
        cmd_list()
    elif "--remove" in sys.argv:
        cmd_remove()
    else:
        cmd_add()


if __name__ == "__main__":
    main()
