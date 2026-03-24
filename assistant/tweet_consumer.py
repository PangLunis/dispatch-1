"""
Tweet Consumer: watches tweets topic for scheduled tweets and posts them at the right time.

When a tweet.scheduled event arrives, this consumer checks if it's time to post.
If the scheduled time has passed, it posts immediately. If it's in the future,
it re-produces the event with a delay (via a simple sleep-and-retry approach).

Since the ConsumerRunner polls continuously, we use a simple approach:
- On each poll, check if scheduled_for <= now → post it
- If scheduled_for > now → skip (don't commit), it'll come back next poll

Actually, the bus consumer commits after processing, so we need a different approach.
We'll post immediately if it's time, or sleep until the scheduled time in the action handler.
Since each tweet is independent and rare (1/day max), sleeping in the handler is fine.
"""

import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

TWITTER_CLI = Path.home() / ".claude" / "skills" / "twitter" / "scripts" / "twitter"


def handle_tweet_scheduled(records: list) -> None:
    """Handle tweet.scheduled events — wait for scheduled time, then post."""
    for record in records:
        payload = record.payload
        text = payload.get("text", "")
        scheduled_for = payload.get("scheduled_for", "")

        if not text:
            log.warning("tweet.scheduled event with empty text, skipping")
            continue

        # Parse scheduled time
        if scheduled_for:
            try:
                post_at = datetime.fromisoformat(scheduled_for)
                # Make sure it's timezone-aware
                if post_at.tzinfo is None:
                    from zoneinfo import ZoneInfo
                    post_at = post_at.replace(tzinfo=ZoneInfo("America/New_York"))

                now = datetime.now(timezone.utc)
                wait_seconds = (post_at - now).total_seconds()

                if wait_seconds > 0:
                    log.info(
                        "Tweet scheduled for %s — waiting %.0f seconds (%.1f hours)",
                        scheduled_for, wait_seconds, wait_seconds / 3600,
                    )
                    # Cap at 24 hours — if somehow scheduled for far future, don't block forever
                    if wait_seconds > 86400:
                        log.warning("Tweet scheduled >24h in future, posting now anyway")
                    else:
                        time.sleep(wait_seconds)
            except (ValueError, TypeError) as e:
                log.warning("Could not parse scheduled_for '%s': %s — posting now", scheduled_for, e)

        # Post the tweet
        log.info("Posting tweet: %s", text[:80])
        try:
            result = subprocess.run(
                ["uv", "run", str(TWITTER_CLI), "post", text],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(Path.home()),
            )
            if result.returncode == 0:
                log.info("Tweet posted successfully: %s", result.stdout.strip()[:200])
            else:
                log.error("Tweet post failed (rc=%d): %s", result.returncode, result.stderr[:500])
        except subprocess.TimeoutExpired:
            log.error("Tweet post timed out after 60s")
        except Exception as e:
            log.error("Tweet post error: %s", e)
