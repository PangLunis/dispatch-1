"""
Discord listener — threading.Thread that runs discord.py in its own event loop.

Follows the same pattern as SignalListener:
  - Runs in a daemon thread
  - Pushes normalized messages to a queue.Queue
  - Main poll loop drains the queue and produces to bus

Key threading note: discord.py is async-native. We run it in a dedicated thread
with its own asyncio event loop (asyncio.new_event_loop + run_until_complete),
not asyncio.run() which tries to set signal handlers (main thread only).
Only primitive data (dicts) cross the thread boundary via queue — never discord.py
objects, which are not thread-safe.
"""

import asyncio
import logging
import queue
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Guard import — discord.py may not be installed
try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False


class DiscordListener:
    """Listens to Discord messages and queues them for processing.

    Follows Sven's listener interface:
      - Runs as a daemon thread (call .start())
      - Pushes messages to a queue.Queue
      - Main poll loop drains queue → produces to bus
    """

    def __init__(self, message_queue: queue.Queue, channel_ids: list[str], bot_token: str):
        if not DISCORD_AVAILABLE:
            raise ImportError("discord.py is not installed. Run: uv add 'discord.py>=2.3.0'")

        import threading
        self._thread = threading.Thread(target=self._run, daemon=True, name="DiscordListener")
        self.message_queue = message_queue
        self.channel_ids = set(int(c) for c in channel_ids)
        self.bot_token = bot_token
        self.running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: discord.Client | None = None

    def start(self):
        """Start the listener thread."""
        self._thread.start()

    def is_alive(self) -> bool:
        """Check if the listener thread is alive."""
        return self._thread.is_alive()

    def _run(self):
        """Start discord.py client in a new event loop (runs in thread)."""
        self.running = True
        while self.running:
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._loop.run_until_complete(self._connect())
            except Exception as e:
                log.error(f"DiscordListener error: {e}")
            finally:
                if self._loop and not self._loop.is_closed():
                    self._loop.close()
                self._loop = None
                self._client = None

            if self.running:
                log.info("[discord] Reconnecting in 5s...")
                time.sleep(5)  # Backoff before reconnect

    async def _connect(self):
        """Connect to Discord Gateway and listen for messages."""
        intents = discord.Intents.default()
        intents.message_content = True  # Privileged intent — required for message.content

        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready():
            log.info(f"DiscordListener connected as {client.user} (channels: {self.channel_ids})")

        @client.event
        async def on_message(message):
            # Ignore own messages
            if message.author == client.user:
                return

            # Ignore DMs — bot only responds in guild channels
            if not message.guild:
                return

            # Defense-in-depth channel filter (Discord permissions are primary gate)
            if message.channel.id not in self.channel_ids:
                return

            text = message.content
            if not text:
                if message.attachments:
                    text = "(attachment)"
                else:
                    return

            sender_id = str(message.author.id)
            sender_name = message.author.display_name or message.author.name
            channel_id = str(message.channel.id)

            # Normalize to match SignalListener message format exactly
            # NOTE: No "date" field — SignalListener doesn't have it either.
            # Only "timestamp" (datetime) is used by process_message().
            msg = {
                "rowid": message.id,  # Discord message snowflake as unique ID
                "phone": sender_id,  # Discord user ID as "phone" field
                "is_from_me": 0,
                "text": text,
                "is_group": True,  # Discord channels are always group-like
                "is_audio_message": False,  # Discord doesn't have audio messages
                "group_name": message.channel.name,
                "chat_identifier": channel_id,
                "attachments": [
                    {
                        "mime_type": a.content_type or "application/octet-stream",
                        "name": a.filename,
                        "size": a.size,
                        "path": a.url,  # Discord CDN URL
                    }
                    for a in message.attachments
                ],
                "audio_transcription": None,
                "thread_originator_guid": None,
                "source": "discord",
                "sender_name": sender_name,  # Display name for group message wrapping
                "timestamp": message.created_at.astimezone(timezone.utc),  # datetime for Gemini vision context
            }

            log.info(f"DiscordListener: queued message from {sender_name} ({sender_id}) in #{message.channel.name}: {text[:80]}...")
            self.message_queue.put(msg)

        @client.event
        async def on_disconnect():
            log.warning("[discord] Disconnected from Gateway — discord.py will auto-reconnect")

        @client.event
        async def on_resumed():
            log.info("[discord] Resumed Gateway connection")

        try:
            await client.start(self.bot_token)
        except Exception as e:
            log.error(f"[discord] Fatal connection error: {e}")
            raise
        finally:
            if not client.is_closed():
                await client.close()
            self._client = None

    def stop(self):
        """Gracefully stop the listener.

        1. Close the Discord client (async, via threadsafe call)
        2. Stop the event loop
        3. The _run() while loop exits because self.running is False
        """
        self.running = False
        # Gracefully close the Discord client before stopping the loop
        if self._client and self._loop and self._loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
                future.result(timeout=5)  # Wait for graceful close
            except Exception as e:
                log.warning(f"[discord] Error during graceful close: {e}")
            # Loop should exit naturally after client.close()
        elif self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    @property
    def is_ready(self) -> bool:
        """Check if the Discord client is connected and ready."""
        return self._client is not None and self._client.is_ready()

    @property
    def latency(self) -> float | None:
        """Get the Discord Gateway latency in seconds, or None if not connected."""
        if self._client and self._client.is_ready():
            return self._client.latency
        return None
