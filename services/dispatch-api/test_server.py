#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["fastapi", "uvicorn", "pydantic", "python-multipart", "pyyaml", "httpx", "pytest", "anyio", "pytest-anyio"]
# ///
"""
Comprehensive tests for dispatch-api server.py

Run with:
    cd ~/dispatch/services/dispatch-api && uv run pytest test_server.py -v
"""

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import server


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_TOKEN = "test-token-abc123"


@pytest.fixture(autouse=True)
def isolated_server(tmp_path, monkeypatch):
    """Isolate every test from the real filesystem and external processes."""
    db_path = tmp_path / "dispatch-messages.db"
    tokens_file = tmp_path / "allowed_tokens.json"
    apns_file = tmp_path / "dispatch-apns-tokens.json"
    image_dir = tmp_path / "dispatch-images"
    audio_dir = tmp_path / "dispatch-audio"
    image_dir.mkdir()
    audio_dir.mkdir()

    # Write a token so auth passes by default
    tokens_file.write_text(json.dumps({"tokens": [TEST_TOKEN]}))

    monkeypatch.setattr(server, "DB_PATH", db_path)
    monkeypatch.setattr(server, "ALLOWED_TOKENS_FILE", tokens_file)
    monkeypatch.setattr(server, "APNS_TOKENS_FILE", apns_file)
    monkeypatch.setattr(server, "IMAGE_DIR", image_dir)
    monkeypatch.setattr(server, "AUDIO_DIR", audio_dir)

    # Mock inject_prompt_to_app_session to avoid real subprocess calls
    async def _fake_inject(transcript, chat_id="voice", image_path=None):
        return True

    monkeypatch.setattr(server, "inject_prompt_to_app_session", _fake_inject)

    # Mock _check_is_thinking so it doesn't hit bus.db
    monkeypatch.setattr(server, "_check_is_thinking", lambda session_name: False)

    # Clear in-memory rate limit state between tests
    server.request_counts.clear()

    # Initialize the DB once so tables exist
    server.init_db()


@pytest.fixture
def client():
    """Yield an httpx AsyncClient wired to the FastAPI app."""
    transport = ASGITransport(app=server.app)
    return AsyncClient(transport=transport, base_url="http://testserver")


# ---------------------------------------------------------------------------
# Helper to create a chat via DB (avoids HTTP round-trips in unrelated tests)
# ---------------------------------------------------------------------------

def _create_chat_in_db(chat_id: str, title: str = "New Chat"):
    conn = sqlite3.connect(server.DB_PATH)
    conn.execute("INSERT INTO chats (id, title) VALUES (?, ?)", (chat_id, title))
    conn.commit()
    conn.close()


def _insert_message(msg_id: str, role: str, content: str, chat_id: str = "voice",
                     image_path: str | None = None, audio_path: str | None = None):
    conn = sqlite3.connect(server.DB_PATH)
    conn.execute(
        "INSERT INTO messages (id, role, content, chat_id, image_path, audio_path) VALUES (?,?,?,?,?,?)",
        (msg_id, role, content, chat_id, image_path, audio_path),
    )
    conn.commit()
    conn.close()


# ===========================================================================
# Utility function tests (non-async, plain pytest)
# ===========================================================================

class TestSqliteToIso:
    def test_none_input(self):
        assert server._sqlite_to_iso(None) is None

    def test_already_iso(self):
        # If there's no space it is returned as-is
        assert server._sqlite_to_iso("2024-01-15T10:30:00Z") == "2024-01-15T10:30:00Z"

    def test_sqlite_format_conversion(self):
        assert server._sqlite_to_iso("2024-01-15 10:30:00") == "2024-01-15T10:30:00Z"


class TestIsValidImage:
    def test_jpeg(self):
        data = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        assert server._is_valid_image(data) is True

    def test_png(self):
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        assert server._is_valid_image(data) is True

    def test_gif(self):
        data = b"GIF89a" + b"\x00" * 100
        assert server._is_valid_image(data) is True

    def test_webp(self):
        data = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 100
        assert server._is_valid_image(data) is True

    def test_heic_ftyp(self):
        # ftyp at offset 4
        data = b"\x00\x00\x00\x18ftyp" + b"heic" + b"\x00" * 100
        assert server._is_valid_image(data) is True

    def test_invalid_data(self):
        data = b"this is not an image at all" + b"\x00" * 100
        assert server._is_valid_image(data) is False

    def test_too_short(self):
        assert server._is_valid_image(b"\xff\xd8") is False
        assert server._is_valid_image(b"") is False


class TestIsRateLimited:
    def test_under_limit(self):
        server.request_counts.clear()
        assert server.is_rate_limited("tok") is False

    def test_at_limit(self):
        server.request_counts.clear()
        token = "rl-tok"
        for _ in range(server.RATE_LIMIT_MAX):
            server.is_rate_limited(token)
        # Next call should be limited
        assert server.is_rate_limited(token) is True

    def test_window_expiry(self):
        server.request_counts.clear()
        token = "expire-tok"
        # Fill with timestamps in the past
        old = time.time() - server.RATE_LIMIT_WINDOW - 1
        server.request_counts[token] = [old] * server.RATE_LIMIT_MAX
        # Should NOT be limited because all entries are expired
        assert server.is_rate_limited(token) is False


# ===========================================================================
# Endpoint tests (async)
# ===========================================================================

@pytest.mark.anyio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


@pytest.mark.anyio
async def test_root_returns_html(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Dispatch" in resp.text


# ---------------------------------------------------------------------------
# POST /register & GET /tokens
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_register_token(client):
    resp = await client.post("/register", params={"token": "new-tok-12345678"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify it shows in /tokens
    resp2 = await client.get("/tokens")
    assert resp2.status_code == 200
    truncated = resp2.json()["tokens"]
    assert any("new-tok-" in t for t in truncated)


@pytest.mark.anyio
async def test_list_tokens_truncated(client):
    resp = await client.get("/tokens")
    assert resp.status_code == 200
    for t in resp.json()["tokens"]:
        assert t.endswith("...")
        # 8 chars + "..."
        assert len(t) == 11


# ---------------------------------------------------------------------------
# POST /chats
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_chat_default_title(client):
    resp = await client.post(
        "/chats",
        params={"token": TEST_TOKEN},
        json={"token": TEST_TOKEN},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New Chat"
    assert "id" in data


@pytest.mark.anyio
async def test_create_chat_custom_title(client):
    resp = await client.post(
        "/chats",
        params={"token": TEST_TOKEN},
        json={"token": TEST_TOKEN, "title": "My Custom Chat"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "My Custom Chat"


# ---------------------------------------------------------------------------
# GET /chats
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_list_chats_empty(client):
    resp = await client.get("/chats")
    assert resp.status_code == 200
    assert resp.json()["chats"] == []


@pytest.mark.anyio
async def test_list_chats_iso_timestamps(client):
    _create_chat_in_db("chat-ts-1", "Timestamp Chat")
    resp = await client.get("/chats")
    assert resp.status_code == 200
    chat = resp.json()["chats"][0]
    # SQLite CURRENT_TIMESTAMP produces "YYYY-MM-DD HH:MM:SS" which gets converted
    assert "T" in chat["created_at"]
    assert chat["created_at"].endswith("Z")


@pytest.mark.anyio
async def test_list_chats_last_opened_at_default_none(client):
    _create_chat_in_db("chat-lo-1", "Opened Chat")
    resp = await client.get("/chats")
    chat = resp.json()["chats"][0]
    assert chat["last_opened_at"] is None


@pytest.mark.anyio
async def test_list_chats_ordering_by_recency(client):
    """Chats with more recent messages should come first."""
    # Create chats with explicit timestamps to control ordering
    conn = sqlite3.connect(server.DB_PATH)
    conn.execute(
        "INSERT INTO chats (id, title, created_at) VALUES (?, ?, ?)",
        ("old-chat", "Old", "2024-01-01 00:00:00"),
    )
    conn.execute(
        "INSERT INTO chats (id, title, created_at) VALUES (?, ?, ?)",
        ("new-chat", "New", "2024-01-02 00:00:00"),
    )
    # Insert a message into "new-chat" with a later timestamp
    conn.execute(
        "INSERT INTO messages (id, role, content, chat_id, created_at) VALUES (?,?,?,?,?)",
        ("m1", "user", "hello", "new-chat", "2025-06-01 00:00:00"),
    )
    conn.commit()
    conn.close()

    resp = await client.get("/chats")
    chats = resp.json()["chats"]
    assert len(chats) == 2
    assert chats[0]["id"] == "new-chat"


# ---------------------------------------------------------------------------
# POST /chats/{id}/open
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_mark_chat_opened(client):
    _create_chat_in_db("open-chat", "Open Me")
    resp = await client.post(
        "/chats/open-chat/open",
        params={"token": TEST_TOKEN},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify last_opened_at is now set
    chats_resp = await client.get("/chats")
    chat = [c for c in chats_resp.json()["chats"] if c["id"] == "open-chat"][0]
    assert chat["last_opened_at"] is not None


# ---------------------------------------------------------------------------
# PATCH /chats/{id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_rename_chat(client):
    _create_chat_in_db("rename-chat", "Old Title")
    resp = await client.patch(
        "/chats/rename-chat",
        params={"token": TEST_TOKEN},
        json={"title": "New Title", "token": TEST_TOKEN},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "New Title"


@pytest.mark.anyio
async def test_rename_nonexistent_chat_404(client):
    resp = await client.patch(
        "/chats/does-not-exist",
        params={"token": TEST_TOKEN},
        json={"title": "Whatever", "token": TEST_TOKEN},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /chats/{id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_delete_chat(client, monkeypatch):
    _create_chat_in_db("del-chat", "Delete Me")
    _insert_message("dm1", "user", "to be deleted", chat_id="del-chat")

    # Mock subprocess.Popen so kill-session doesn't run
    mock_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", mock_popen)

    resp = await client.delete("/chats/del-chat", params={"token": TEST_TOKEN})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify chat and messages are gone
    conn = sqlite3.connect(server.DB_PATH)
    assert conn.execute("SELECT COUNT(*) FROM chats WHERE id='del-chat'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE chat_id='del-chat'").fetchone()[0] == 0
    conn.close()

    # Verify kill-session was called
    mock_popen.assert_called_once()


# ---------------------------------------------------------------------------
# POST /prompt
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_prompt_happy_path(client):
    _create_chat_in_db("voice", "Voice Chat")
    resp = await client.post("/prompt", json={
        "transcript": "Hello world",
        "token": TEST_TOKEN,
        "chat_id": "voice",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "request_id" in data

    # Verify message was stored
    conn = sqlite3.connect(server.DB_PATH)
    row = conn.execute("SELECT content, role FROM messages WHERE id=?", (data["request_id"],)).fetchone()
    conn.close()
    assert row[0] == "Hello world"
    assert row[1] == "user"


@pytest.mark.anyio
async def test_prompt_empty_transcript_400(client):
    resp = await client.post("/prompt", json={
        "transcript": "   ",
        "token": TEST_TOKEN,
    })
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_prompt_invalid_token_401(client):
    resp = await client.post("/prompt", json={
        "transcript": "hello",
        "token": "bad-token-not-registered",
    })
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_prompt_rate_limiting_429(client):
    _create_chat_in_db("voice", "Voice")
    # Exhaust the rate limit
    for i in range(server.RATE_LIMIT_MAX):
        resp = await client.post("/prompt", json={
            "transcript": f"msg {i}",
            "token": TEST_TOKEN,
            "chat_id": "voice",
        })
        assert resp.status_code == 200, f"Request {i} failed unexpectedly"

    # Next request should be rate limited
    resp = await client.post("/prompt", json={
        "transcript": "one too many",
        "token": TEST_TOKEN,
        "chat_id": "voice",
    })
    assert resp.status_code == 429


@pytest.mark.anyio
async def test_prompt_auto_title_on_first_message(client):
    """When a chat has title 'New Chat', the first message should set the title."""
    _create_chat_in_db("auto-title-chat", "New Chat")
    resp = await client.post("/prompt", json={
        "transcript": "What is the weather like today in San Francisco?",
        "token": TEST_TOKEN,
        "chat_id": "auto-title-chat",
    })
    assert resp.status_code == 200

    # Check the title was updated
    conn = sqlite3.connect(server.DB_PATH)
    row = conn.execute("SELECT title FROM chats WHERE id='auto-title-chat'").fetchone()
    conn.close()
    assert row[0] != "New Chat"
    assert "weather" in row[0].lower() or "What" in row[0]


@pytest.mark.anyio
async def test_prompt_auto_title_truncation(client):
    """Long transcripts get truncated to ~40 chars with ellipsis."""
    _create_chat_in_db("long-title-chat", "New Chat")
    long_text = "This is a very long message that should be truncated appropriately when used as a chat title"
    resp = await client.post("/prompt", json={
        "transcript": long_text,
        "token": TEST_TOKEN,
        "chat_id": "long-title-chat",
    })
    assert resp.status_code == 200

    conn = sqlite3.connect(server.DB_PATH)
    row = conn.execute("SELECT title FROM chats WHERE id='long-title-chat'").fetchone()
    conn.close()
    title = row[0]
    assert title.endswith("...")
    # Title stem (before ...) should be <= 40 chars
    assert len(title) <= 44  # 40 + "..."


@pytest.mark.anyio
async def test_prompt_first_token_auto_registers(client, tmp_path, monkeypatch):
    """When no tokens exist, the first token is auto-registered."""
    empty_tokens = tmp_path / "empty_tokens.json"
    # No file = no tokens
    monkeypatch.setattr(server, "ALLOWED_TOKENS_FILE", empty_tokens)
    _create_chat_in_db("voice", "Voice")

    resp = await client.post("/prompt", json={
        "transcript": "first ever message",
        "token": "brand-new-token-xyz",
        "chat_id": "voice",
    })
    assert resp.status_code == 200

    # Verify the token was saved
    saved = json.loads(empty_tokens.read_text())
    assert "brand-new-token-xyz" in saved["tokens"]


# ---------------------------------------------------------------------------
# POST /prompt-with-image
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_prompt_with_image_happy_path(client):
    _create_chat_in_db("img-chat", "Image Chat")
    jpeg_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100

    resp = await client.post(
        "/prompt-with-image",
        data={"transcript": "Look at this", "token": TEST_TOKEN, "chat_id": "img-chat"},
        files={"image": ("photo.jpg", jpeg_data, "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"

    # Verify image was saved to disk
    conn = sqlite3.connect(server.DB_PATH)
    row = conn.execute("SELECT image_path FROM messages WHERE id=?", (data["request_id"],)).fetchone()
    conn.close()
    assert row[0] is not None
    assert Path(row[0]).exists()


@pytest.mark.anyio
async def test_prompt_with_image_oversized_413(client):
    _create_chat_in_db("img-chat-big", "Big Image Chat")
    jpeg_header = b"\xff\xd8\xff\xe0"
    oversized = jpeg_header + b"\x00" * 10_000_001

    resp = await client.post(
        "/prompt-with-image",
        data={"transcript": "Too big", "token": TEST_TOKEN, "chat_id": "img-chat-big"},
        files={"image": ("big.jpg", oversized, "image/jpeg")},
    )
    assert resp.status_code == 413


@pytest.mark.anyio
async def test_prompt_with_image_invalid_format_400(client):
    _create_chat_in_db("img-chat-bad", "Bad Image Chat")
    bad_data = b"not-an-image-at-all" + b"\x00" * 100

    resp = await client.post(
        "/prompt-with-image",
        data={"transcript": "Bad image", "token": TEST_TOKEN, "chat_id": "img-chat-bad"},
        files={"image": ("bad.txt", bad_data, "application/octet-stream")},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_prompt_with_image_no_image(client):
    """Endpoint works without an image too."""
    _create_chat_in_db("img-chat-none", "No Image Chat")
    resp = await client.post(
        "/prompt-with-image",
        data={"transcript": "No image here", "token": TEST_TOKEN, "chat_id": "img-chat-none"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /messages
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_messages_empty(client):
    resp = await client.get("/messages", params={"chat_id": "voice"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["messages"] == []
    assert data["is_thinking"] is False


@pytest.mark.anyio
async def test_get_messages_returns_stored(client):
    _insert_message("msg-1", "user", "Hello", chat_id="voice")
    _insert_message("msg-2", "assistant", "Hi there", chat_id="voice")

    resp = await client.get("/messages", params={"chat_id": "voice"})
    assert resp.status_code == 200
    msgs = resp.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


@pytest.mark.anyio
async def test_get_messages_filter_by_since(client):
    conn = sqlite3.connect(server.DB_PATH)
    conn.execute(
        "INSERT INTO messages (id, role, content, chat_id, created_at) VALUES (?,?,?,?,?)",
        ("old-msg", "user", "old", "voice", "2020-01-01 00:00:00"),
    )
    conn.execute(
        "INSERT INTO messages (id, role, content, chat_id, created_at) VALUES (?,?,?,?,?)",
        ("new-msg", "assistant", "new", "voice", "2025-06-01 12:00:00"),
    )
    conn.commit()
    conn.close()

    resp = await client.get("/messages", params={
        "chat_id": "voice",
        "since": "2024-01-01T00:00:00Z",
    })
    msgs = resp.json()["messages"]
    assert len(msgs) == 1
    assert msgs[0]["id"] == "new-msg"


@pytest.mark.anyio
async def test_get_messages_iso_timestamps(client):
    _insert_message("iso-msg", "user", "test", chat_id="voice")
    resp = await client.get("/messages", params={"chat_id": "voice"})
    msg = resp.json()["messages"][0]
    assert "T" in msg["created_at"]
    assert msg["created_at"].endswith("Z")


@pytest.mark.anyio
async def test_get_messages_is_thinking_field(client):
    resp = await client.get("/messages", params={"chat_id": "voice"})
    data = resp.json()
    assert "is_thinking" in data
    assert isinstance(data["is_thinking"], bool)


@pytest.mark.anyio
async def test_get_messages_image_url_present(client):
    """When a message has an image_path pointing to an existing file, image_url is set."""
    # Create a real image file
    image_file = server.IMAGE_DIR / "img-msg.jpg"
    image_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)
    _insert_message("img-msg", "user", "pic", chat_id="voice", image_path=str(image_file))

    resp = await client.get("/messages", params={"chat_id": "voice"})
    msg = resp.json()["messages"][0]
    assert msg["image_url"] == "/image/img-msg"


# ---------------------------------------------------------------------------
# GET /image/{id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_image_serves_file(client):
    image_file = server.IMAGE_DIR / "serve-img.jpg"
    image_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
    _insert_message("serve-img", "user", "pic", chat_id="voice", image_path=str(image_file))

    resp = await client.get("/image/serve-img")
    assert resp.status_code == 200
    assert len(resp.content) > 0


@pytest.mark.anyio
async def test_get_image_404_missing_message(client):
    resp = await client.get("/image/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_image_404_no_image_path(client):
    _insert_message("no-img", "user", "text only", chat_id="voice")
    resp = await client.get("/image/no-img")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_image_403_path_traversal(client):
    """Image path outside IMAGE_DIR should be rejected."""
    outside_path = "/tmp/evil-image.jpg"
    Path(outside_path).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)
    _insert_message("traversal-msg", "user", "hack", chat_id="voice", image_path=outside_path)

    resp = await client.get("/image/traversal-msg")
    assert resp.status_code == 403

    # Clean up
    Path(outside_path).unlink(missing_ok=True)


@pytest.mark.anyio
async def test_get_image_404_file_missing_on_disk(client):
    """image_path in DB points to a file that doesn't exist on disk."""
    missing = str(server.IMAGE_DIR / "gone.jpg")
    _insert_message("gone-img", "user", "missing file", chat_id="voice", image_path=missing)

    resp = await client.get("/image/gone-img")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /messages
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_clear_messages(client):
    _insert_message("clr-1", "user", "bye", chat_id="voice")
    _insert_message("clr-2", "assistant", "goodbye", chat_id="voice")

    resp = await client.delete("/messages", params={"chat_id": "voice"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify empty
    conn = sqlite3.connect(server.DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM messages WHERE chat_id='voice'").fetchone()[0]
    conn.close()
    assert count == 0


@pytest.mark.anyio
async def test_clear_messages_cleans_up_media_files(client):
    """Audio and image files on disk should be deleted."""
    audio_file = server.AUDIO_DIR / "media-msg.wav"
    audio_file.write_bytes(b"fake-audio")
    image_file = server.IMAGE_DIR / "media-msg.jpg"
    image_file.write_bytes(b"fake-image")

    _insert_message("media-msg", "user", "media", chat_id="voice",
                     audio_path=str(audio_file), image_path=str(image_file))

    resp = await client.delete("/messages", params={"chat_id": "voice"})
    assert resp.status_code == 200
    assert not audio_file.exists()
    assert not image_file.exists()


@pytest.mark.anyio
async def test_clear_messages_unauthorized(client):
    resp = await client.delete("/messages", params={"chat_id": "voice", "token": "bad-token"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /register-apns
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_register_apns_token(client):
    resp = await client.post("/register-apns", json={
        "device_token": "device-abc123",
        "apns_token": "apns-xyz789",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify APNs token file was written
    data = json.loads(server.APNS_TOKENS_FILE.read_text())
    assert data["device-abc123"] == "apns-xyz789"


@pytest.mark.anyio
async def test_register_apns_auto_registers_device_token(client):
    """Registering APNs should also auto-register the device token for auth."""
    new_device = "brand-new-device-token"
    resp = await client.post("/register-apns", json={
        "device_token": new_device,
        "apns_token": "apns-for-new",
    })
    assert resp.status_code == 200

    # The device token should now be in allowed_tokens
    tokens = json.loads(server.ALLOWED_TOKENS_FILE.read_text())
    assert new_device in tokens["tokens"]


# ---------------------------------------------------------------------------
# POST /restart-session
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_restart_session_success(client, monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "restarted"
    mock_result.stderr = ""
    mock_run = MagicMock(return_value=mock_result)
    monkeypatch.setattr("subprocess.run", mock_run)

    resp = await client.post("/restart-session", params={
        "token": TEST_TOKEN,
        "chat_id": "voice",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    mock_run.assert_called_once()


@pytest.mark.anyio
async def test_restart_session_failure(client, monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "error"
    mock_run = MagicMock(return_value=mock_result)
    monkeypatch.setattr("subprocess.run", mock_run)

    resp = await client.post("/restart-session", params={
        "token": TEST_TOKEN,
        "chat_id": "voice",
    })
    assert resp.status_code == 500


@pytest.mark.anyio
async def test_restart_session_unauthorized(client):
    resp = await client.post("/restart-session", params={
        "token": "invalid-token",
        "chat_id": "voice",
    })
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Auth edge cases
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_validate_token_allows_when_no_tokens_file(client, tmp_path, monkeypatch):
    """validate_token() allows access when no tokens file exists (empty set)."""
    monkeypatch.setattr(server, "ALLOWED_TOKENS_FILE", tmp_path / "nonexistent.json")
    # This should not raise - create_chat uses validate_token
    resp = await client.post(
        "/chats",
        params={"token": "any-token"},
        json={"token": "any-token"},
    )
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_get_messages_unauthorized(client):
    resp = await client.get("/messages", params={
        "chat_id": "voice",
        "token": "bad-token",
    })
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Migration: last_opened_at column
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_list_chats_migration_adds_last_opened_at(client):
    """GET /chats should work even if last_opened_at column is missing (migration)."""
    # Drop the column by recreating the table without it
    conn = sqlite3.connect(server.DB_PATH)
    conn.execute("DROP TABLE IF EXISTS chats")
    conn.execute("""
        CREATE TABLE chats (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New Chat',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("INSERT INTO chats (id, title) VALUES ('migr-chat', 'Migration Test')")
    conn.commit()
    conn.close()

    resp = await client.get("/chats")
    assert resp.status_code == 200
    chats = resp.json()["chats"]
    assert len(chats) == 1
    assert "last_opened_at" in chats[0]


# ---------------------------------------------------------------------------
# POST /prompt - inject failure
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_prompt_inject_failure_500(client, monkeypatch):
    _create_chat_in_db("voice", "Voice")

    async def _fail_inject(transcript, chat_id="voice", image_path=None):
        return False

    monkeypatch.setattr(server, "inject_prompt_to_app_session", _fail_inject)

    resp = await client.post("/prompt", json={
        "transcript": "will fail",
        "token": TEST_TOKEN,
        "chat_id": "voice",
    })
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /prompt-with-image - auth and rate limit
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_prompt_with_image_unauthorized(client):
    resp = await client.post(
        "/prompt-with-image",
        data={"transcript": "hello", "token": "bad-token", "chat_id": "voice"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_prompt_with_image_empty_transcript(client):
    resp = await client.post(
        "/prompt-with-image",
        data={"transcript": "  ", "token": TEST_TOKEN, "chat_id": "voice"},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_prompt_with_image_rate_limited(client):
    _create_chat_in_db("voice", "Voice")
    # Exhaust rate limit
    server.request_counts[TEST_TOKEN] = [time.time()] * server.RATE_LIMIT_MAX

    resp = await client.post(
        "/prompt-with-image",
        data={"transcript": "limited", "token": TEST_TOKEN, "chat_id": "voice"},
    )
    assert resp.status_code == 429
