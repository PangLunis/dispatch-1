"""
Messaging backend configurations.

Each backend defines the source-specific strings (CLI commands, labels, suffixes)
needed throughout the codebase. Adding a new messaging backend = adding one entry here.
"""
from __future__ import annotations

from pydantic import BaseModel


class BackendConfig(BaseModel, frozen=True):
    """Configuration for a messaging backend. All source-specific strings in one place."""

    name: str              # "imessage", "signal", "test"
    label: str             # "SMS", "SIGNAL", "TEST" (for wrap headers)
    session_suffix: str    # "" for iMessage, "-signal" for Signal, "-test" for Test
    registry_prefix: str   # "" for iMessage, "signal:" for Signal, "test:" for Test

    # CLI command templates. {chat_id} is replaced at call site.
    send_cmd: str          # '~/.claude/skills/sms-assistant/scripts/send-sms "{chat_id}"'
    send_group_cmd: str    # same or different for groups
    history_cmd: str       # CLI template or "" if unavailable

    # Reply hint shown to the LLM in message wrapping.
    # Tells the session how to send responses for this backend.
    reply_hint: str = '~/.claude/skills/sms-assistant/scripts/reply "message" [--image PATH] [--file PATH]'

    # Whether this backend supports image context for Gemini vision analysis.
    # If True, a MessageReader implementation must exist for this backend.
    supports_image_context: bool = False


BACKENDS: dict[str, BackendConfig] = {
    "imessage": BackendConfig(
        name="imessage",
        label="SMS",
        session_suffix="",
        registry_prefix="",
        send_cmd='~/.claude/skills/sms-assistant/scripts/send-sms "{chat_id}"',
        send_group_cmd='~/.claude/skills/sms-assistant/scripts/send-sms "{chat_id}"',
        history_cmd='~/.claude/skills/sms-assistant/scripts/read-sms --chat "{chat_id}" --limit {limit}',
        supports_image_context=True,
    ),
    "signal": BackendConfig(
        name="signal",
        label="SIGNAL",
        session_suffix="-signal",
        registry_prefix="signal:",
        send_cmd='~/.claude/skills/signal/scripts/send-signal "{chat_id}"',
        send_group_cmd='~/.claude/skills/signal/scripts/send-signal-group "{chat_id}"',
        history_cmd='~/.claude/skills/signal/scripts/read-signal --chat "{chat_id}" --limit {limit}',
        supports_image_context=True,
    ),
    "test": BackendConfig(
        name="test",
        label="TEST",
        session_suffix="-test",
        registry_prefix="test:",
        send_cmd='~/dispatch/tools/test-send "{chat_id}"',
        send_group_cmd='~/dispatch/tools/test-send "{chat_id}"',
        history_cmd='~/dispatch/tools/test-read --chat "{chat_id}" --limit {limit}',
        supports_image_context=False,
    ),
    "discord": BackendConfig(
        name="discord",
        label="DISCORD",
        session_suffix="-discord",
        registry_prefix="discord:",
        send_cmd='~/.claude/skills/discord/scripts/send-discord "{chat_id}"',
        send_group_cmd='~/.claude/skills/discord/scripts/send-discord "{chat_id}"',
        history_cmd="",  # No history CLI yet (could add later via Discord REST API)
        supports_image_context=False,  # Discord CDN URLs, not local files
    ),
    "dispatch-app": BackendConfig(
        name="dispatch-app",
        label="DISPATCH_APP",
        session_suffix="-dispatch-app",
        registry_prefix="dispatch-app:",
        send_cmd='~/.claude/skills/dispatch-app/scripts/reply-app "{chat_id}"',
        send_group_cmd='~/.claude/skills/dispatch-app/scripts/reply-app "{chat_id}"',
        reply_hint='~/.claude/skills/dispatch-app/scripts/reply-app "{chat_id}" "message"',
        history_cmd="",
        supports_image_context=True,
    ),
    "dispatch-api": BackendConfig(
        name="dispatch-api",
        label="DISPATCH-API",
        session_suffix="-dispatch-api",
        registry_prefix="dispatch-api:",
        send_cmd='~/.claude/skills/dispatch-app/scripts/reply-dispatch-api "{chat_id}"',
        send_group_cmd='~/.claude/skills/dispatch-app/scripts/reply-dispatch-api "{chat_id}"',
        reply_hint='~/.claude/skills/dispatch-app/scripts/reply-dispatch-api "{chat_id}" "message"',
        history_cmd="",
        supports_image_context=True,
    ),
}

# Backward compatibility: "sven-app" was the old name for "dispatch-app".
# Needs its own config with "sven-app:" prefix so sanitize_chat_id/normalize_chat_id
# can strip the prefix from existing sessions.json entries.
# DEPRECATED: "sven-app" was the old name for "dispatch-app".
# Kept for backward compatibility with existing sessions.json entries.
# TODO: Remove after running migration script to rewrite sven-app: → dispatch-app: prefixes.
BACKENDS["sven-app"] = BackendConfig(
    name="dispatch-app",  # canonical name
    label="DISPATCH_APP",
    session_suffix="-dispatch-app",
    registry_prefix="sven-app:",  # preserve old prefix for existing sessions
    send_cmd='~/.claude/skills/dispatch-app/scripts/reply-app "{chat_id}"',
    send_group_cmd='~/.claude/skills/dispatch-app/scripts/reply-app "{chat_id}"',
    reply_hint='~/.claude/skills/dispatch-app/scripts/reply-app "{chat_id}" "message"',
    history_cmd="",
    supports_image_context=True,
)


def get_backend(source: str) -> BackendConfig:
    """Get backend config by source name. Defaults to imessage with warning."""
    if source and source not in BACKENDS:
        import logging
        logging.getLogger(__name__).warning(f"Unknown backend source '{source}', falling back to imessage")
    return BACKENDS.get(source, BACKENDS["imessage"])
