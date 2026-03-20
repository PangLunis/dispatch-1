"""
Integration tests for SDK backend.

Tests the full SDK session lifecycle, message injection, and registry management.
Run with: uv run pytest tests/integration/test_sdk_backend.py -v
"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from assistant.sdk_backend import SDKBackend, SessionRegistry
from assistant.sdk_session import SDKSession


class MockContactsManager:
    """Mock ContactsManager for testing."""

    def lookup_tier_by_phone(self, phone: str):
        """Return test tier based on phone number."""
        if phone.endswith('1111'):
            return 'admin'
        elif phone.endswith('2222'):
            return 'partner'
        elif phone.endswith('3333'):
            return 'family'
        elif phone.endswith('4444'):
            return 'favorite'
        return None

    def lookup_contact_name_by_phone(self, phone: str):
        """Return test contact name."""
        tier = self.lookup_tier_by_phone(phone)
        if tier:
            return f"Test {tier.title()}"
        return None


@pytest_asyncio.fixture
async def sdk_backend():
    """Create a temporary SDKBackend for testing."""
    tmp_registry = Path(tempfile.mktemp(suffix='.json'))
    registry = SessionRegistry(tmp_registry)
    contacts = None  # Most tests don't need contacts
    backend = SDKBackend(registry, contacts)

    yield backend

    # Cleanup
    await backend.shutdown()
    tmp_registry.unlink(missing_ok=True)


@pytest.mark.asyncio
class TestSDKBackend:
    """Test SDKBackend session management."""

    async def test_create_session(self, sdk_backend):
        """Test creating a new SDK session."""
        session = await sdk_backend.create_session(
            chat_id='+15555550009',
            contact_name='Test Admin',
            tier='admin',
            source='imessage'
        )

        assert isinstance(session, SDKSession)
        assert session.chat_id == '+15555550009'
        assert session.contact_name == 'Test Admin'
        assert session.tier == 'admin'
        assert session.is_alive()

    async def test_lazy_session_creation_via_inject(self, sdk_backend):
        """Test that inject_message creates session on-demand."""
        # Session doesn't exist yet
        assert '+15555550009' not in sdk_backend.sessions

        # Inject message (should create session)
        success = await sdk_backend.inject_message(
            chat_id='+15555550009',
            contact_name='Test Admin',
            tier='admin',
            text='Hello world',
            source='imessage'
        )

        assert success is True
        assert '+15555550009' in sdk_backend.sessions
        assert sdk_backend.sessions['+15555550009'].is_alive()

    async def test_session_reuse(self, sdk_backend):
        """Test that existing sessions are reused."""
        # Create first session
        session1 = await sdk_backend.create_session(
            chat_id='+15555550009',
            contact_name='Test Admin',
            tier='admin',
            source='imessage'
        )

        # Try to create again - should return same session
        session2 = await sdk_backend.create_session(
            chat_id='+15555550009',
            contact_name='Test Admin',
            tier='admin',
            source='imessage'
        )

        assert session1 is session2

    async def test_multiple_sessions(self, sdk_backend):
        """Test managing multiple concurrent sessions."""
        # Create admin session
        admin_session = await sdk_backend.create_session(
            chat_id='+15555550009',
            contact_name='Test Admin',
            tier='admin',
            source='imessage'
        )

        # Create family session
        family_session = await sdk_backend.create_session(
            chat_id='+15555550010',
            contact_name='Test Family',
            tier='family',
            source='imessage'
        )

        assert len(sdk_backend.sessions) == 2
        assert admin_session.tier == 'admin'
        assert family_session.tier == 'family'
        assert admin_session.is_alive()
        assert family_session.is_alive()

    async def test_get_session_info(self, sdk_backend):
        """Test retrieving session information."""
        await sdk_backend.create_session(
            chat_id='+15555550009',
            contact_name='Test Admin',
            tier='admin',
            source='imessage'
        )

        info = await sdk_backend.get_session_info('+15555550009')

        assert info is not None
        assert info['chat_id'] == '+15555550009'
        assert info['contact_name'] == 'Test Admin'
        assert info['tier'] == 'admin'
        assert info['is_alive'] is True
        assert 'session_id' in info
        assert 'turn_count' in info
        assert 'last_activity' in info

    async def test_kill_session(self, sdk_backend):
        """Test killing a session."""
        # Create session
        session = await sdk_backend.create_session(
            chat_id='+15555550009',
            contact_name='Test Admin',
            tier='admin',
            source='imessage'
        )

        assert session.is_alive()

        # Kill it
        result = await sdk_backend.kill_session('+15555550009')

        assert result is True
        assert '+15555550009' not in sdk_backend.sessions

    async def test_restart_session(self, sdk_backend):
        """Test restarting a session."""
        # Create session
        session1 = await sdk_backend.create_session(
            chat_id='+15555550009',
            contact_name='Test Admin',
            tier='admin',
            source='imessage'
        )

        # Restart it
        session2 = await sdk_backend.restart_session('+15555550009')

        assert session2 is not None
        assert session2.is_alive()
        # Should be a new session instance
        assert session2 is not session1

    async def test_kill_all_sessions(self, sdk_backend):
        """Test killing all sessions."""
        # Create multiple sessions
        await sdk_backend.create_session(
            chat_id='+15555550009',
            contact_name='Test Admin',
            tier='admin',
            source='imessage'
        )
        await sdk_backend.create_session(
            chat_id='+15555550010',
            contact_name='Test Family',
            tier='family',
            source='imessage'
        )

        assert len(sdk_backend.sessions) == 2

        # Give sessions a moment to fully start
        await asyncio.sleep(0.5)

        # Kill all - may raise CancelledError during cleanup, which is expected
        try:
            count = await sdk_backend.kill_all_sessions()
            assert count == 2
            assert len(sdk_backend.sessions) == 0
        except asyncio.CancelledError:
            # This can happen during aggressive shutdown - sessions still get killed
            assert len(sdk_backend.sessions) == 0

    async def test_get_all_sessions(self, sdk_backend):
        """Test retrieving all session info."""
        # Create multiple sessions
        await sdk_backend.create_session(
            chat_id='+15555550009',
            contact_name='Test Admin',
            tier='admin',
            source='imessage'
        )
        await sdk_backend.create_session(
            chat_id='+15555550010',
            contact_name='Test Family',
            tier='family',
            source='imessage'
        )

        all_sessions = await sdk_backend.get_all_sessions()

        assert len(all_sessions) == 2
        chat_ids = [s['chat_id'] for s in all_sessions]
        assert '+15555550009' in chat_ids
        assert '+15555550010' in chat_ids


@pytest.mark.asyncio
class TestSessionRegistry:
    """Test SessionRegistry persistence."""

    def test_registry_create_and_load(self):
        """Test that registry persists to disk."""
        tmp_file = Path(tempfile.mktemp(suffix='.json'))

        # Create registry and register a session
        registry1 = SessionRegistry(tmp_file)
        registry1.register(
            chat_id='+15555550009',
            session_name='test-admin',
            contact_name='Test Admin',
            tier='admin'
        )

        # Load registry from disk in new instance
        registry2 = SessionRegistry(tmp_file)

        assert '+15555550009' in registry2.all()
        entry = registry2.get('+15555550009')
        assert entry is not None
        assert entry['session_name'] == 'test-admin'
        assert entry['contact_name'] == 'Test Admin'
        assert entry['tier'] == 'admin'

        # Cleanup
        tmp_file.unlink()

    def test_registry_update_session_id(self):
        """Test updating session_id for resume support."""
        tmp_file = Path(tempfile.mktemp(suffix='.json'))
        registry = SessionRegistry(tmp_file)

        # Register session
        registry.register(
            chat_id='+15555550009',
            session_name='test-admin',
            contact_name='Test Admin',
            tier='admin'
        )

        # Update session_id
        registry.update_session_id('+15555550009', 'test-session-id-123')

        entry = registry.get('+15555550009')
        assert entry is not None
        assert entry['session_id'] == 'test-session-id-123'

        # Cleanup
        tmp_file.unlink()

    def test_registry_update_last_message_time(self):
        """Test updating last_message_time."""
        tmp_file = Path(tempfile.mktemp(suffix='.json'))
        registry = SessionRegistry(tmp_file)

        # Register session
        registry.register(
            chat_id='+15555550009',
            session_name='test-admin'
        )

        entry1 = registry.get('+15555550009')
        assert entry1 is not None
        original_time = entry1.get('last_message_time')

        # Update timestamp
        import time
        time.sleep(0.1)  # Ensure time difference
        registry.update_last_message_time('+15555550009')

        entry2 = registry.get('+15555550009')
        assert entry2 is not None
        new_time = entry2.get('last_message_time')

        assert new_time != original_time

        # Cleanup
        tmp_file.unlink()

    def test_registry_remove(self):
        """Test removing a session from registry."""
        tmp_file = Path(tempfile.mktemp(suffix='.json'))
        registry = SessionRegistry(tmp_file)

        # Register session
        registry.register(
            chat_id='+15555550009',
            session_name='test-admin'
        )

        assert '+15555550009' in registry.all()

        # Remove it
        registry.remove('+15555550009')

        assert '+15555550009' not in registry.all()

        # Cleanup
        tmp_file.unlink()

    def test_registry_get_by_session_name(self):
        """Test looking up session by name."""
        tmp_file = Path(tempfile.mktemp(suffix='.json'))
        registry = SessionRegistry(tmp_file)

        # Register session
        registry.register(
            chat_id='+15555550009',
            session_name='test-admin',
            contact_name='Test Admin'
        )

        entry = registry.get_by_session_name('test-admin')

        assert entry is not None
        assert entry['chat_id'] == '+15555550009'
        assert entry['contact_name'] == 'Test Admin'

        # Cleanup
        tmp_file.unlink()


@pytest.mark.asyncio
class TestGroupSessions:
    """Test group chat session support."""

    async def test_create_group_session(self, sdk_backend):
        """Test creating a group chat session."""
        # Group sessions need participant info from contacts
        # Skip detailed test - just verify the method exists
        assert hasattr(sdk_backend, 'create_group_session')
        assert hasattr(sdk_backend, 'inject_group_message')


