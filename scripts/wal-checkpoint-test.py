#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
WAL checkpoint test script for chat.db polling.
Tests different checkpoint strategies under real message load.

Usage:
  ./wal-checkpoint-test.py truncate  # Test TRUNCATE checkpoint
  ./wal-checkpoint-test.py passive   # Test PASSIVE checkpoint
  ./wal-checkpoint-test.py none      # No checkpoint (baseline)
"""

import sqlite3
import time
import sys
from pathlib import Path

CHAT_DB = Path.home() / "Library/Messages/chat.db"
POLL_INTERVAL = 0.1  # 100ms like daemon
DURATION = 180  # 3 minutes

def poll_messages(mode: str, start_rowid: int) -> tuple[int, list]:
    """Poll for new messages with specified checkpoint mode."""
    conn = sqlite3.connect(str(CHAT_DB))
    cursor = conn.cursor()

    # Apply checkpoint based on mode
    if mode == "truncate":
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    elif mode == "passive":
        cursor.execute("PRAGMA wal_checkpoint(PASSIVE)")
    # else: none - no checkpoint

    cursor.execute("""
        SELECT ROWID, datetime(date/1000000000 + 978307200, 'unixepoch', 'localtime') as ts, text
        FROM message
        WHERE ROWID > ?
        ORDER BY ROWID
    """, (start_rowid,))

    messages = cursor.fetchall()
    new_rowid = start_rowid
    if messages:
        new_rowid = max(m[0] for m in messages)

    conn.close()
    return new_rowid, messages

def get_latest_rowid() -> int:
    conn = sqlite3.connect(str(CHAT_DB))
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(ROWID) FROM message")
    result = cursor.fetchone()[0]
    conn.close()
    return result

def main():
    if len(sys.argv) < 2:
        print("Usage: ./wal-checkpoint-test.py [truncate|passive|none]")
        sys.exit(1)

    mode = sys.argv[1]
    if mode not in ("truncate", "passive", "none"):
        print(f"Invalid mode: {mode}")
        sys.exit(1)

    print(f"Testing WAL checkpoint mode: {mode}")
    print(f"Duration: {DURATION}s, Poll interval: {POLL_INTERVAL}s")
    print("-" * 50)

    start_rowid = get_latest_rowid()
    print(f"Starting from rowid: {start_rowid}")

    start_time = time.time()
    poll_count = 0
    error_count = 0
    messages_seen = []

    while time.time() - start_time < DURATION:
        try:
            poll_start = time.time()
            start_rowid, new_msgs = poll_messages(mode, start_rowid)
            poll_duration = (time.time() - poll_start) * 1000

            poll_count += 1

            for m in new_msgs:
                rowid, ts, text = m
                staleness = (time.time() - (time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S")))) * 1000
                messages_seen.append({
                    "rowid": rowid,
                    "ts": ts,
                    "staleness_ms": staleness,
                    "poll_ms": poll_duration
                })
                preview = (text or "")[:50].replace("\n", " ")
                print(f"MSG | rowid={rowid} | staleness={staleness:.0f}ms | poll={poll_duration:.1f}ms | {preview}")

            if poll_count % 100 == 0:
                elapsed = time.time() - start_time
                print(f"STATUS | polls={poll_count} | errors={error_count} | msgs={len(messages_seen)} | elapsed={elapsed:.0f}s")

        except Exception as e:
            error_count += 1
            print(f"ERROR | {type(e).__name__}: {e}")

        time.sleep(POLL_INTERVAL)

    # Summary
    print("-" * 50)
    print(f"SUMMARY | mode={mode}")
    print(f"  polls: {poll_count}")
    print(f"  errors: {error_count}")
    print(f"  messages: {len(messages_seen)}")
    if messages_seen:
        avg_staleness = sum(m["staleness_ms"] for m in messages_seen) / len(messages_seen)
        max_staleness = max(m["staleness_ms"] for m in messages_seen)
        print(f"  avg staleness: {avg_staleness:.0f}ms")
        print(f"  max staleness: {max_staleness:.0f}ms")

if __name__ == "__main__":
    main()
