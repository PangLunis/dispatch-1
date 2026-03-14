"""
Tests for the SessionRegistry.

Covers:
- Register, get, remove, update operations
- Persistence across loads
- Atomic write with file locking
- Session ID tracking for resume
- Last message time tracking
- Concurrent registry access
- Registry data integrity
"""
import asyncio
import json
import time
from pathlib import Path

import pytest

from assistant.sdk_backend import SessionRegistry


class TestRegistryBasicOps:
    """Test basic registry operations."""

    def test_register_and_get(self, registry):
        registry.register(
            chat_id="test:+15555551234",
            session_name="test-user-test",
            contact_name="Test User",
            tier="admin",
            source="test",
        )
        data = registry.get("test:+15555551234")
        assert data is not None
        assert data["contact_name"] == "Test User"
        assert data["tier"] == "admin"
        assert data["source"] == "test"
        assert data["session_name"] == "test-user-test"

    def test_get_nonexistent(self, registry):
        assert registry.get("nonexistent") is None

    def test_remove(self, registry):
        registry.register(chat_id="test:+15555550006", session_name="user1")
        registry.remove("test:+15555550006")
        assert registry.get("test:+15555550006") is None

    def test_remove_nonexistent_is_safe(self, registry):
        registry.remove("nonexistent")  # Should not raise

    def test_all_returns_copy(self, registry):
        registry.register(chat_id="a", session_name="sa")
        registry.register(chat_id="b", session_name="sb")
        all_data = registry.all()
        assert len(all_data) == 2
        # Modifying the copy shouldn't affect the registry
        all_data["c"] = {"session_name": "sc"}
        assert registry.get("c") is None

    def test_get_by_session_name(self, registry):
        registry.register(chat_id="test:+15555550006", session_name="user-one-test")
        result = registry.get_by_session_name("user-one-test")
        assert result is not None
        assert result["chat_id"] == "test:+15555550006"

    def test_get_by_session_name_not_found(self, registry):
        assert registry.get_by_session_name("nonexistent") is None

    def test_register_empty_chat_id_raises(self, registry):
        with pytest.raises(ValueError):
            registry.register(chat_id="", session_name="test")


class TestRegistryPersistence:
    """Test that registry persists across loads."""

    def test_persists_to_disk(self, registry_file):
        r1 = SessionRegistry(registry_file)
        r1.register(chat_id="test:+15555551234", session_name="user-test")

        # New registry instance should load from same file
        r2 = SessionRegistry(registry_file)
        data = r2.get("test:+15555551234")
        assert data is not None
        assert data["session_name"] == "user-test"

    def test_atomic_write(self, registry_file):
        """Verify file is valid JSON after writes."""
        r = SessionRegistry(registry_file)
        for i in range(10):
            r.register(chat_id=f"test:+1555555{i:04d}", session_name=f"user-{i}")
        r.flush()  # register() uses debounced saves — flush to persist all

        # File should be valid JSON
        content = json.loads(registry_file.read_text())
        assert len(content) == 10

    def test_preserves_created_at_on_update(self, registry):
        registry.register(chat_id="test:+15555550006", session_name="u1")
        created_at = registry.get("test:+15555550006")["created_at"]

        time.sleep(0.01)
        registry.register(chat_id="test:+15555550006", session_name="u1", extra="data")
        assert registry.get("test:+15555550006")["created_at"] == created_at


class TestRegistrySessionTracking:
    """Test session ID and message time tracking."""

    def test_update_session_id(self, registry):
        registry.register(chat_id="test:+15555550006", session_name="u1")
        registry.update_session_id("test:+15555550006", "sdk-session-abc123")
        data = registry.get("test:+15555550006")
        assert data["session_id"] == "sdk-session-abc123"

    def test_update_session_id_nonexistent(self, registry):
        """Should be a no-op for nonexistent chat_id."""
        registry.update_session_id("nonexistent", "abc")
        assert registry.get("nonexistent") is None

    def test_update_last_message_time(self, registry):
        registry.register(chat_id="test:+15555550006", session_name="u1")
        registry.update_last_message_time("test:+15555550006")
        data = registry.get("test:+15555550006")
        assert "last_message_time" in data
        assert "updated_at" in data

    def test_update_last_message_time_nonexistent(self, registry):
        registry.update_last_message_time("nonexistent")  # Should not raise


class TestRegistryWasActive:
    """Test was_active flag for session recreation on startup."""

    def test_mark_was_active(self, registry):
        registry.register(chat_id="test:+15555550006", session_name="u1")
        registry.mark_was_active("test:+15555550006")
        data = registry.get("test:+15555550006")
        assert data["was_active"] is True

    def test_mark_was_active_nonexistent(self, registry):
        """Should be a no-op for nonexistent chat_id."""
        registry.mark_was_active("nonexistent")  # Should not raise

    def test_clear_was_active(self, registry):
        registry.register(chat_id="test:+15555550006", session_name="u1")
        registry.mark_was_active("test:+15555550006")
        assert registry.get("test:+15555550006")["was_active"] is True
        registry.clear_was_active("test:+15555550006")
        data = registry.get("test:+15555550006")
        assert "was_active" not in data

    def test_clear_was_active_nonexistent(self, registry):
        """Should be a no-op for nonexistent chat_id."""
        registry.clear_was_active("nonexistent")  # Should not raise

    def test_mark_persists_to_disk(self, registry_file):
        r1 = SessionRegistry(registry_file)
        r1.register(chat_id="test:+15555550006", session_name="u1")
        r1.mark_was_active("test:+15555550006")

        r2 = SessionRegistry(registry_file)
        data = r2.get("test:+15555550006")
        assert data["was_active"] is True


class TestRegistryConcurrency:
    """Test registry under concurrent access."""

    def test_many_rapid_writes(self, registry):
        """Simulate rapid writes like multiple messages arriving at once."""
        for i in range(50):
            registry.register(chat_id=f"test:+1{i:010d}", session_name=f"user-{i}")
            registry.update_last_message_time(f"test:+1{i:010d}")

        all_data = registry.all()
        assert len(all_data) == 50

    def test_interleaved_register_and_remove(self, registry):
        for i in range(20):
            registry.register(chat_id=f"test:+1{i:010d}", session_name=f"user-{i}")
        for i in range(0, 20, 2):
            registry.remove(f"test:+1{i:010d}")
        all_data = registry.all()
        assert len(all_data) == 10  # Only odd ones remain
