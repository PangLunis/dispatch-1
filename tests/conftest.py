"""
Shared fixtures for claude-assistant integration tests.

Tests exercise the daemon infrastructure without real Claude API connections.
We mock ClaudeSDKClient to avoid hitting the API while testing session lifecycle,
message routing, health checks, and backend isolation.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Mock the Claude Agent SDK before any assistant imports ──────────────

class FakeTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class FakeToolUseBlock:
    def __init__(self, name: str, input_data: dict, tool_id: str = "tool_1"):
        self.type = "tool_use"
        self.name = name
        self.input = input_data
        self.id = tool_id


class FakeAssistantMessage:
    def __init__(self, content=None):
        self.content = content or []
        self.type = "assistant"
        self.model = "claude-opus-4-5-20251101"


class FakeResultMessage:
    def __init__(self, session_id: str = "test-session-123", is_error: bool = False, duration_ms: int = 500):
        self.session_id = session_id
        self.is_error = is_error
        self.duration_ms = duration_ms
        self.duration_api_ms = duration_ms
        self.num_turns = 1
        self.type = "result"
        self.cost_usd = 0.01
        self.usage = {"input_tokens": 100, "output_tokens": 50}


class FakeSystemMessage:
    def __init__(self, subtype: str = "init"):
        self.type = "system"
        self.subtype = subtype


class FakeClaudeSDKClient:
    """Mock ClaudeSDKClient that simulates responses without API calls."""

    def __init__(self, options=None):
        self.options = options
        self.connected = False
        self._queries = []  # All queries ever sent (for test assertions)
        self._pending_queries = []  # Queries not yet consumed by receive_messages
        self._responses = []
        self.session_id = "test-session-123"
        self._connect_delay = 0  # Simulate slow connections
        self._query_delay = 0  # Simulate slow queries
        self._should_error = False  # Simulate errors

    async def connect(self):
        if self._connect_delay:
            await asyncio.sleep(self._connect_delay)
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def query(self, text: str):
        if self._query_delay:
            await asyncio.sleep(self._query_delay)
        if self._should_error:
            raise Exception("Simulated query error")
        self._queries.append(text)
        self._pending_queries.append(text)

    async def receive_response(self):
        if self._responses:
            for msg in self._responses:
                yield msg
            self._responses.clear()
        else:
            yield FakeAssistantMessage([FakeTextBlock("I'll help with that.")])
            yield FakeResultMessage(session_id=self.session_id)

    async def receive_messages(self):
        """Infinite async iterator that yields messages for all turns.

        Waits for queries to arrive, then yields response messages including
        a ResultMessage. Never stops (like the real SDK's receive_messages).
        """
        while True:
            # Wait for a query to be sent
            while not self._pending_queries:
                await asyncio.sleep(0.05)
            # Small delay to simulate processing
            if self._query_delay:
                await asyncio.sleep(self._query_delay)
            # Drain pending (they merge into one turn)
            self._pending_queries.clear()
            if self._responses:
                for msg in self._responses:
                    yield msg
                self._responses.clear()
            else:
                yield FakeAssistantMessage([FakeTextBlock("I'll help with that.")])
                yield FakeResultMessage(session_id=self.session_id)

    async def interrupt(self):
        pass


class FakeClaudeAgentOptions:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeHookMatcher:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeUserMessage:
    def __init__(self, content=None):
        self.type = "human"
        self.content = content or []


class FakeToolResultBlock:
    def __init__(self, tool_use_id: str = "", content: str = "", is_error: bool = False):
        self.type = "tool_result"
        self.tool_use_id = tool_use_id
        self.content = content
        self.is_error = is_error


class FakePermissionResultAllow:
    pass


class FakePermissionResultDeny:
    def __init__(self, reason: str = "denied", message: str = "denied"):
        self.reason = reason or message
        self.message = message or reason


# Wire up the mock module
mock_sdk_module = MagicMock()
mock_sdk_module.ClaudeSDKClient = FakeClaudeSDKClient
mock_sdk_module.ClaudeAgentOptions = FakeClaudeAgentOptions
mock_sdk_module.AssistantMessage = FakeAssistantMessage
mock_sdk_module.ResultMessage = FakeResultMessage
mock_sdk_module.SystemMessage = FakeSystemMessage
mock_sdk_module.TextBlock = FakeTextBlock
mock_sdk_module.ToolUseBlock = FakeToolUseBlock
mock_sdk_module.UserMessage = FakeUserMessage
mock_sdk_module.ToolResultBlock = FakeToolResultBlock
mock_sdk_module.PermissionResultAllow = FakePermissionResultAllow
mock_sdk_module.PermissionResultDeny = FakePermissionResultDeny
mock_sdk_module.HookMatcher = FakeHookMatcher

sys.modules["claude_agent_sdk"] = mock_sdk_module


# ── Now safe to import assistant modules ────────────────────────────────
from assistant.backends import BACKENDS, BackendConfig, get_backend
from assistant.common import (
    normalize_chat_id,
    is_group_chat_id,
    get_session_name,
    wrap_sms,
    wrap_group_message,
    format_message_body,
    ensure_transcript_dir,
)


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_perf_dir(tmp_path):
    """Redirect perf metrics to tmp_path so tests don't pollute production logs."""
    from assistant import perf
    perf.reset_state()
    with patch.object(perf, "PERF_DIR", tmp_path / "perf"):
        yield
        perf.reset_state()


@pytest.fixture
def registry_file(tmp_path):
    """Create a temporary session registry file."""
    reg_file = tmp_path / "sessions.json"
    reg_file.write_text("{}")
    return reg_file


@pytest.fixture
def registry(registry_file):
    """Create a SessionRegistry instance."""
    from assistant.sdk_backend import SessionRegistry
    return SessionRegistry(registry_file)


@pytest_asyncio.fixture
async def sdk_backend(registry):
    """Create an SDKBackend with a temporary registry."""
    from assistant.sdk_backend import SDKBackend
    backend = SDKBackend(registry=registry, contacts_manager=None)
    yield backend
    # Cleanup
    for session in list(backend.sessions.values()):
        try:
            await session.stop()
        except Exception:
            pass


@pytest_asyncio.fixture
async def sdk_session(tmp_path):
    """Create a standalone SDKSession for testing."""
    from assistant.sdk_session import SDKSession
    cwd = str(tmp_path / "test-session")
    os.makedirs(cwd, exist_ok=True)
    session = SDKSession(
        chat_id="test:+15555551234",
        contact_name="Test User",
        tier="admin",
        cwd=cwd,
        session_type="individual",
        source="test",
    )
    yield session
    if session.is_alive():
        await session.stop()


@pytest.fixture
def test_messages_dir(tmp_path):
    """Create a temporary test messages directory."""
    msg_dir = tmp_path / "test-messages"
    msg_dir.mkdir()
    (msg_dir / "inbox").mkdir()
    (msg_dir / "outbox").mkdir()
    (msg_dir / "errors").mkdir()
    return msg_dir


@pytest.fixture
def sample_message():
    """Factory for test messages (as dropped into TestMessageWatcher dir)."""
    def _make(
        from_phone: str = "+15555551234",
        text: str = "Hello from test",
        is_group: bool = False,
        chat_id: str | None = None,
        group_name: str | None = None,
        source: str = "test",
    ) -> dict:
        return {
            "from": from_phone,
            "text": text,
            "is_group": is_group,
            "chat_id": chat_id or from_phone,
            "group_name": group_name,
        }
    return _make


@pytest.fixture
def normalized_message():
    """Factory for normalized messages (as process_message receives them)."""
    def _make(
        phone: str = "+15555551234",
        text: str = "Hello from test",
        is_group: bool = False,
        chat_identifier: str | None = None,
        group_name: str | None = None,
        source: str = "test",
    ) -> dict:
        return {
            "rowid": int(time.time() * 1000),
            "date": int(time.time()),
            "phone": phone,
            "is_from_me": 0,
            "text": text,
            "attachments": [],
            "is_group": is_group,
            "group_name": group_name,
            "chat_identifier": chat_identifier or phone,
            "chat_style": 43 if is_group else 45,
            "reply_to_guid": None,
            "source": source,
        }
    return _make
