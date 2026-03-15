"""
Tests for the messaging backend system.

Covers:
- Backend configuration correctness
- get_backend() routing and defaults
- normalize_chat_id with all backend prefixes
- is_group_chat_id with prefixed IDs
- Session name generation per backend
- wrap_sms / wrap_group_message per backend
- Backend isolation (test vs signal vs imessage)
"""
import pytest
from assistant.backends import BACKENDS, BackendConfig, get_backend
from assistant.common import (
    normalize_chat_id,
    is_group_chat_id,
    get_session_name,
    wrap_sms,
    wrap_group_message,
    format_message_body,
)


class TestBackendConfig:
    """Test backend configuration correctness."""

    def test_all_backends_defined(self):
        assert "imessage" in BACKENDS
        assert "signal" in BACKENDS
        assert "test" in BACKENDS

    def test_imessage_has_no_prefix(self):
        b = BACKENDS["imessage"]
        assert b.registry_prefix == ""
        assert b.session_suffix == ""

    def test_signal_has_signal_prefix(self):
        b = BACKENDS["signal"]
        assert b.registry_prefix == "signal:"
        assert b.session_suffix == "-signal"

    def test_test_has_test_prefix(self):
        b = BACKENDS["test"]
        assert b.registry_prefix == "test:"
        assert b.session_suffix == "-test"

    def test_all_backends_have_send_cmd(self):
        for name, b in BACKENDS.items():
            assert b.send_cmd, f"{name} missing send_cmd"
            assert b.send_group_cmd, f"{name} missing send_group_cmd"
            assert "{chat_id}" in b.send_cmd, f"{name} send_cmd missing {{chat_id}} placeholder"

    def test_send_cmd_has_no_message_placeholder(self):
        """Verify 'message' was removed from send_cmd templates (fix #4)."""
        for name, b in BACKENDS.items():
            assert '"message"' not in b.send_cmd, f"{name} send_cmd still has message placeholder"
            assert '"message"' not in b.send_group_cmd, f"{name} send_group_cmd still has message placeholder"

    def test_backend_config_is_frozen(self):
        b = BACKENDS["imessage"]
        with pytest.raises(Exception):  # pydantic frozen model
            b.name = "changed"

    def test_all_backends_have_unique_names(self):
        names = [b.name for b in BACKENDS.values()]
        assert len(names) == len(set(names))

    def test_all_backends_have_unique_prefixes(self):
        """Non-empty prefixes must be unique."""
        prefixes = [b.registry_prefix for b in BACKENDS.values() if b.registry_prefix]
        assert len(prefixes) == len(set(prefixes))


class TestGetBackend:
    """Test get_backend() routing."""

    def test_get_imessage(self):
        b = get_backend("imessage")
        assert b.name == "imessage"

    def test_get_signal(self):
        b = get_backend("signal")
        assert b.name == "signal"

    def test_get_test(self):
        b = get_backend("test")
        assert b.name == "test"

    def test_unknown_defaults_to_imessage(self):
        b = get_backend("unknown_backend")
        assert b.name == "imessage"

    def test_empty_defaults_to_imessage(self):
        b = get_backend("")
        assert b.name == "imessage"


class TestNormalizeChatId:
    """Test normalize_chat_id with backend prefixes."""

    def test_plain_phone(self):
        assert normalize_chat_id("+16175551234") == "+16175551234"

    def test_10_digit_phone(self):
        assert normalize_chat_id("6175551234") == "+16175551234"

    def test_11_digit_phone(self):
        assert normalize_chat_id("16175551234") == "+116175551234" or normalize_chat_id("16175551234") == "+16175551234"
        # Should normalize 11-digit starting with 1
        result = normalize_chat_id("16175551234")
        assert result == "+16175551234"

    def test_signal_prefixed_phone(self):
        result = normalize_chat_id("signal:+16175551234")
        assert result == "signal:+16175551234"

    def test_test_prefixed_phone(self):
        result = normalize_chat_id("test:+15555551234")
        assert result == "test:+15555551234"

    def test_signal_prefix_preserved_for_10digit(self):
        result = normalize_chat_id("signal:6175551234")
        assert result == "signal:+16175551234"

    def test_test_prefix_preserved_for_10digit(self):
        result = normalize_chat_id("test:5555551234")
        assert result == "test:+15555551234"

    def test_group_uuid_lowercase(self):
        result = normalize_chat_id("B3D258B9A4DE447CA412EB335C82A077")
        assert result == "b3d258b9a4de447ca412eb335c82a077"

    def test_signal_group_uuid_preserved(self):
        """Signal group IDs are base64, not hex - should be returned as-is."""
        result = normalize_chat_id("signal:AbCdEf1234567890AbCdEf12")
        # This has non-hex chars so won't match hex pattern
        assert result.startswith("signal:")

    def test_unknown_format_returned_as_is(self):
        assert normalize_chat_id("weird-id") == "weird-id"


class TestIsGroupChatId:
    """Test is_group_chat_id with backend prefixes."""

    def test_phone_is_not_group(self):
        assert is_group_chat_id("+16175551234") is False

    def test_signal_phone_is_not_group(self):
        """signal:+phone should not be a group (fix #3)."""
        assert is_group_chat_id("signal:+16175551234") is False

    def test_test_phone_is_not_group(self):
        assert is_group_chat_id("test:+15555551234") is False

    def test_hex_uuid_is_group(self):
        assert is_group_chat_id("b3d258b9a4de447ca412eb335c82a077") is True

    def test_base64_is_group(self):
        # 44-char base64 Signal group ID
        assert is_group_chat_id("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop1234") is True

    def test_signal_prefixed_base64_is_group(self):
        """signal: prefixed group ID should still be detected as group (fix for bare_id bug)."""
        assert is_group_chat_id("signal:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop1234") is True

    def test_signal_prefixed_hex_is_group(self):
        """signal: prefixed hex group ID should still be detected as group."""
        assert is_group_chat_id("signal:b3d258b9a4de447ca412eb335c82a077") is True


class TestSessionName:
    """Test session name generation per backend (chat_id-based)."""

    def test_imessage_phone(self):
        assert get_session_name("+15555551234", "imessage") == "imessage/_15555551234"

    def test_signal_phone(self):
        assert get_session_name("signal:+15555551234", "signal") == "signal/_15555551234"

    def test_test_phone(self):
        assert get_session_name("test:+15555551234", "test") == "test/_15555551234"

    def test_default_is_imessage(self):
        assert get_session_name("+15555551234") == "imessage/_15555551234"

    def test_group_chat_id(self):
        assert get_session_name("abc123def456", "imessage") == "imessage/abc123def456"


class TestWrapSms:
    """Test wrap_sms uses correct backend labels and commands."""

    def test_imessage_wrap(self):
        result = wrap_sms("hello", "Test User", "admin", "+15555551234", source="imessage")
        assert "SMS FROM" in result
        assert "reply" in result
        assert "+15555551234" in result

    def test_signal_wrap(self):
        result = wrap_sms("hello", "Test User", "admin", "+15555551234", source="signal")
        assert "SIGNAL FROM" in result
        assert "reply" in result

    def test_test_wrap(self):
        result = wrap_sms("hello", "Test User", "admin", "+15555551234", source="test")
        assert "TEST FROM" in result
        assert "reply" in result

    def test_wrap_includes_message_placeholder(self):
        """After fix #4, 'message' placeholder is appended at display time."""
        result = wrap_sms("hello", "Test User", "admin", "+15555551234", source="imessage")
        assert '"message"' in result

    def test_wrap_includes_tier(self):
        result = wrap_sms("hello", "Test User", "family", "+15555551234")
        assert "family" in result


class TestWrapGroupMessage:
    """Test wrap_group_message uses correct backend labels."""

    def test_imessage_group(self):
        result = wrap_group_message(
            "abc123def456abc123def456abc123de",
            "Family Chat", "Mom", "family", "dinner?",
            source="imessage",
        )
        assert "GROUP SMS" in result
        assert "reply" in result

    def test_signal_group(self):
        result = wrap_group_message(
            "abc123", "Signal Group", "Friend", "favorite", "hey",
            source="signal",
        )
        assert "GROUP SIGNAL" in result
        assert "reply" in result

    def test_group_wrap_includes_message_placeholder(self):
        result = wrap_group_message(
            "abc123", "Group", "User", "admin", "hi",
            source="test",
        )
        assert '"message"' in result


class TestFormatMessageBody:
    """Test message body formatting."""

    def test_plain_text(self):
        assert format_message_body("hello") == "hello"

    def test_empty_text(self):
        assert format_message_body("") == "(no text)"

    def test_none_text(self):
        assert format_message_body(None) == "(no text)"

    def test_audio_transcription(self):
        result = format_message_body("", audio_transcription="test audio")
        assert "Audio message transcription" in result
        assert "test audio" in result

    def test_attachments(self):
        attachments = [{"name": "photo.jpg", "mime_type": "image/jpeg", "size": 2048, "path": "/tmp/photo.jpg"}]
        result = format_message_body("check this", attachments=attachments)
        assert "ATTACHMENTS" in result
        assert "photo.jpg" in result
        assert "/tmp/photo.jpg" in result
