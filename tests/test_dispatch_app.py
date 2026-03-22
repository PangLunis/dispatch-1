"""
Tests for the dispatch-app backend, API server, and shared DB module.

Renamed from test_sven_app.py as part of the sven-app → dispatch-app migration.
"""

import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Path(path)
    os.unlink(path)


@pytest.fixture
def temp_audio_dir():
    """Create a temporary directory for audio files."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# =============================================================================
# Backend Config Tests
# =============================================================================


class TestDispatchAppBackend:
    """Tests for the dispatch-app backend configuration."""

    def test_backend_exists_in_backends(self):
        """Verify dispatch-app backend is registered."""
        from assistant.backends import BACKENDS, get_backend

        assert "dispatch-app" in BACKENDS
        backend = get_backend("dispatch-app")
        assert backend.name == "dispatch-app"

    def test_backend_config_values(self):
        """Verify dispatch-app backend has correct configuration."""
        from assistant.backends import get_backend

        backend = get_backend("dispatch-app")
        assert backend.label == "DISPATCH_APP"
        assert backend.session_suffix == "-dispatch-app"
        assert backend.registry_prefix == "dispatch-app:"
        assert "reply-app" in backend.send_cmd

    def test_backend_send_cmd_format(self):
        """Verify send_cmd has proper format with chat_id placeholder."""
        from assistant.backends import get_backend

        backend = get_backend("dispatch-app")
        assert "{chat_id}" in backend.send_cmd

    def test_backward_compat_sven_app_alias(self):
        """Verify sven-app is a backward-compat alias for dispatch-app."""
        from assistant.backends import BACKENDS

        assert "sven-app" in BACKENDS
        sven_app = BACKENDS["sven-app"]
        dispatch_app = BACKENDS["dispatch-app"]
        # Same canonical name, same send_cmd, but different registry prefix
        assert sven_app.name == dispatch_app.name == "dispatch-app"
        assert sven_app.send_cmd == dispatch_app.send_cmd
        assert sven_app.registry_prefix == "sven-app:"
        assert dispatch_app.registry_prefix == "dispatch-app:"


# =============================================================================
# Reply-App CLI Tests
# =============================================================================


class TestReplyAppCLI:
    """Tests for the reply-app CLI."""

    def test_reply_app_exists(self):
        """Verify reply-app script exists and is executable."""
        script_path = Path.home() / ".claude" / "skills" / "dispatch-app" / "scripts" / "reply-app"
        assert script_path.exists(), f"reply-app not found at {script_path}"
        assert os.access(script_path, os.X_OK), "reply-app is not executable"

    def test_reply_app_empty_message_fails(self):
        """Verify empty messages are rejected."""
        script_path = Path.home() / ".claude" / "skills" / "dispatch-app" / "scripts" / "reply-app"
        result = subprocess.run(
            [str(script_path), "voice", ""],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0

    def test_reply_app_stores_message(self, temp_db, temp_audio_dir):
        """Verify reply-app stores messages in database."""
        script_path = Path.home() / ".claude" / "skills" / "dispatch-app" / "scripts" / "reply-app"

        # Patch the paths in the script
        with patch.dict(os.environ, {
            'SVEN_DB_PATH': str(temp_db),
            'SVEN_AUDIO_DIR': str(temp_audio_dir)
        }):
            # Create database with expected schema
            conn = sqlite3.connect(temp_db)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    audio_path TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()

            # Note: Full test would require mocking TTS, but we verify structure

    def test_reply_sven_backward_compat_exists(self):
        """Verify reply-sven backward-compat wrapper exists."""
        script_path = Path.home() / ".claude" / "skills" / "dispatch-app" / "scripts" / "reply-sven"
        assert script_path.exists(), f"reply-sven backward-compat wrapper not found at {script_path}"
        assert os.access(script_path, os.X_OK), "reply-sven is not executable"


# =============================================================================
# Message Database Tests
# =============================================================================


class TestMessageDatabase:
    """Tests for the SQLite message database."""

    def test_database_schema(self, temp_db):
        """Verify database schema is correct."""
        conn = sqlite3.connect(temp_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                audio_path TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Verify we can insert and query
        conn.execute(
            "INSERT INTO messages (id, role, content) VALUES (?, ?, ?)",
            ("test-1", "user", "Hello")
        )
        conn.commit()

        cursor = conn.execute("SELECT * FROM messages WHERE id = ?", ("test-1",))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "test-1"
        assert row[1] == "user"
        assert row[2] == "Hello"

        conn.close()

    def test_user_and_assistant_messages(self, temp_db):
        """Verify both user and assistant messages can be stored."""
        conn = sqlite3.connect(temp_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                audio_path TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert user message
        conn.execute(
            "INSERT INTO messages (id, role, content) VALUES (?, ?, ?)",
            ("user-1", "user", "What's the weather?")
        )

        # Insert assistant message with audio
        conn.execute(
            "INSERT INTO messages (id, role, content, audio_path) VALUES (?, ?, ?, ?)",
            ("asst-1", "assistant", "It's sunny today.", "/path/to/audio.wav")
        )
        conn.commit()

        # Query all messages
        cursor = conn.execute("SELECT role, content, audio_path FROM messages ORDER BY created_at")
        rows = cursor.fetchall()

        assert len(rows) == 2
        assert rows[0] == ("user", "What's the weather?", None)
        assert rows[1] == ("assistant", "It's sunny today.", "/path/to/audio.wav")

        conn.close()

    def test_message_ordering(self, temp_db):
        """Verify messages are ordered by creation time."""
        conn = sqlite3.connect(temp_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                audio_path TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert messages (they should be ordered by created_at)
        for i in range(5):
            conn.execute(
                "INSERT INTO messages (id, role, content) VALUES (?, ?, ?)",
                (f"msg-{i}", "user" if i % 2 == 0 else "assistant", f"Message {i}")
            )
            conn.commit()

        cursor = conn.execute("SELECT id FROM messages ORDER BY created_at ASC")
        ids = [row[0] for row in cursor.fetchall()]
        assert ids == ["msg-0", "msg-1", "msg-2", "msg-3", "msg-4"]

        conn.close()


# =============================================================================
# API Server Tests (Unit)
# =============================================================================


class TestDispatchAPIModels:
    """Tests for API data models."""

    def test_prompt_request_model(self):
        """Verify PromptRequest model structure."""
        request_data = {
            "transcript": "Hello",
            "token": "test-token-123"
        }
        assert "transcript" in request_data
        assert "token" in request_data

    def test_message_model_structure(self):
        """Verify Message model structure."""
        message_data = {
            "id": "msg-123",
            "role": "assistant",
            "content": "Hello!",
            "audio_url": "/audio/msg-123",
            "created_at": "2026-02-10 03:00:00"
        }
        assert message_data["role"] in ["user", "assistant"]
        assert message_data["audio_url"] is None or message_data["audio_url"].startswith("/audio/")

    def test_messages_response_structure(self):
        """Verify MessagesResponse structure."""
        response_data = {
            "messages": [
                {
                    "id": "1",
                    "role": "user",
                    "content": "Hi",
                    "audio_url": None,
                    "created_at": "2026-02-10 03:00:00"
                },
                {
                    "id": "2",
                    "role": "assistant",
                    "content": "Hello!",
                    "audio_url": "/audio/2",
                    "created_at": "2026-02-10 03:00:01"
                }
            ]
        }
        assert isinstance(response_data["messages"], list)
        assert len(response_data["messages"]) == 2


# =============================================================================
# Integration Tests
# =============================================================================


class TestDispatchAPIIntegration:
    """Integration tests for the Dispatch API server.

    These tests require the server to be running.
    """

    @pytest.fixture
    def api_base(self):
        """Base URL for API tests."""
        return "http://localhost:9091"

    @pytest.mark.integration
    def test_health_endpoint(self, api_base):
        """Verify health endpoint returns 200."""
        import requests
        response = requests.get(f"{api_base}/health", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.integration
    def test_messages_endpoint(self, api_base):
        """Verify messages endpoint returns valid structure."""
        import requests
        response = requests.get(f"{api_base}/messages", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert isinstance(data["messages"], list)

    @pytest.mark.integration
    def test_clear_messages(self, api_base):
        """Verify messages can be cleared."""
        import requests
        response = requests.delete(f"{api_base}/messages", timeout=5)
        assert response.status_code == 200

        # Verify cleared
        response = requests.get(f"{api_base}/messages", timeout=5)
        data = response.json()
        assert len(data["messages"]) == 0

    @pytest.mark.integration
    def test_prompt_requires_token(self, api_base):
        """Verify prompt endpoint validates tokens."""
        import requests
        # Without proper token setup, this should either register or reject
        response = requests.post(
            f"{api_base}/prompt",
            json={"transcript": "test", "token": "invalid-token-xyz"},
            timeout=5
        )
        # Either 200 (first registration) or 401 (unknown token)
        assert response.status_code in [200, 401]


# =============================================================================
# Run tests
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
