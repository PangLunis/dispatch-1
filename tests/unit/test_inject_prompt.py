"""
Tests for inject-prompt CLI command.

These tests verify that the inject-prompt command properly handles
tier overrides, particularly the --admin flag.
"""

import argparse
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_registry():
    """Create a temporary registry file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({
            "sven-app:voice": {
                "chat_id": "sven-app:voice",
                "session_name": "sven-app/voice",
                "tier": "favorite",  # Intentionally wrong - should be overridden
                "contact_name": "Unknown (voice)",
                "source": "sven-app",
            },
            "+16175550100": {
                "chat_id": "+16175550100",
                "session_name": "imessage/_16175550100",
                "tier": "admin",
                "contact_name": "Test Admin",
                "source": "imessage",
            },
        }, f)
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def mock_args_admin():
    """Create mock args with --admin flag set."""
    args = argparse.Namespace(
        chat_id="sven-app:voice",
        prompt="test prompt",
        file=None,
        sms=True,
        admin=True,
        sven_app=True,
        bg=False,
        reply_to=None,
    )
    return args


@pytest.fixture
def mock_args_no_admin():
    """Create mock args without --admin flag."""
    args = argparse.Namespace(
        chat_id="sven-app:voice",
        prompt="test prompt",
        file=None,
        sms=True,
        admin=False,
        sven_app=True,
        bg=False,
        reply_to=None,
    )
    return args


# =============================================================================
# Admin Flag Override Tests
# =============================================================================


class TestAdminFlagOverride:
    """Tests for the --admin flag tier override behavior."""

    def test_admin_flag_overrides_favorite_tier(self, temp_registry, mock_args_admin):
        """Verify --admin flag overrides tier from registry.

        This is the bug fix test: when --admin is passed, the tier should
        be "admin" regardless of what's in the registry.
        """
        # Mock the IPC command to capture what gets sent
        captured_request = {}

        def mock_ipc(req):
            captured_request.update(req)
            return {"ok": True, "message": "Injected"}

        # Create a mock SessionRegistry that returns our test data
        mock_registry = MagicMock()
        mock_registry.get.return_value = {
            "chat_id": "sven-app:voice",
            "session_name": "sven-app/voice",
            "tier": "favorite",  # Registry has wrong tier
            "contact_name": "Unknown (voice)",
            "source": "sven-app",
        }

        with patch('assistant.cli._ipc_command', side_effect=mock_ipc), \
             patch('assistant.cli._session_name_to_chat_id', return_value=None), \
             patch('assistant.sdk_backend.SessionRegistry', return_value=mock_registry):

            from assistant.cli import cmd_inject_prompt
            result = cmd_inject_prompt(mock_args_admin)

            # Verify the tier was overridden to admin
            assert captured_request.get("tier") == "admin", \
                f"Expected tier='admin' but got tier='{captured_request.get('tier')}'"
            assert result == 0

    def test_no_admin_flag_uses_registry_tier(self, temp_registry, mock_args_no_admin):
        """Verify without --admin flag, tier comes from registry."""
        captured_request = {}

        def mock_ipc(req):
            captured_request.update(req)
            return {"ok": True, "message": "Injected"}

        mock_registry = MagicMock()
        mock_registry.get.return_value = {
            "chat_id": "sven-app:voice",
            "session_name": "sven-app/voice",
            "tier": "favorite",
            "contact_name": "Unknown (voice)",
            "source": "sven-app",
        }

        with patch('assistant.cli._ipc_command', side_effect=mock_ipc), \
             patch('assistant.cli._session_name_to_chat_id', return_value=None), \
             patch('assistant.sdk_backend.SessionRegistry', return_value=mock_registry):

            from assistant.cli import cmd_inject_prompt
            result = cmd_inject_prompt(mock_args_no_admin)

            # Verify the tier comes from registry (favorite)
            assert captured_request.get("tier") == "favorite", \
                f"Expected tier='favorite' but got tier='{captured_request.get('tier')}'"
            assert result == 0

    def test_admin_flag_works_for_existing_admin_session(self, temp_registry):
        """Verify --admin flag doesn't break already-admin sessions."""
        args = argparse.Namespace(
            chat_id="+16175550100",
            prompt="test prompt",
            file=None,
            sms=True,
            admin=True,
            sven_app=False,
            bg=False,
            reply_to=None,
        )

        captured_request = {}

        def mock_ipc(req):
            captured_request.update(req)
            return {"ok": True, "message": "Injected"}

        mock_registry = MagicMock()
        mock_registry.get.return_value = {
            "chat_id": "+16175550100",
            "session_name": "imessage/_16175550100",
            "tier": "admin",  # Already admin
            "contact_name": "Test Admin",
            "source": "imessage",
        }

        with patch('assistant.cli._ipc_command', side_effect=mock_ipc), \
             patch('assistant.cli._session_name_to_chat_id', return_value=None), \
             patch('assistant.sdk_backend.SessionRegistry', return_value=mock_registry):

            from assistant.cli import cmd_inject_prompt
            result = cmd_inject_prompt(args)

            # Should still be admin
            assert captured_request.get("tier") == "admin"
            assert result == 0


class TestSvenAppInjectIntegration:
    """Integration tests for sven-app inject workflow."""

    def test_sven_app_inject_includes_admin_flag(self):
        """Verify dispatch-api server passes --admin flag correctly.

        The server.py should include both --sms and --admin flags
        when calling inject-prompt.
        """
        server_path = Path.home() / "dispatch/services/dispatch-api/server.py"
        if not server_path.exists():
            pytest.skip("dispatch-api server.py not found")

        content = server_path.read_text()

        # Verify inject call includes --admin
        assert '--admin' in content, \
            "dispatch-api server should pass --admin flag to inject-prompt"

        # Verify inject call includes --sms (needed for tier to be used)
        assert '--sms' in content, \
            "dispatch-api server should pass --sms flag to inject-prompt"

    def test_sven_app_session_claude_md_shows_admin(self):
        """Verify CLAUDE.md for sven-app states admin tier."""
        claude_md = Path.home() / "transcripts/sven-app/voice/CLAUDE.md"
        if not claude_md.exists():
            pytest.skip("sven-app CLAUDE.md not found")

        content = claude_md.read_text()

        # Should indicate admin tier
        assert 'ADMIN' in content.upper() or 'admin' in content.lower(), \
            "sven-app CLAUDE.md should indicate admin tier"


# =============================================================================
# Run tests
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
