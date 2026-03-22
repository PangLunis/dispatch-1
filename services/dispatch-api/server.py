#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastapi",
#     "uvicorn",
#     "pydantic",
#     "python-multipart",
#     "pyyaml",
# ]
# ///
"""
Dispatch API Server - receives voice transcripts from the mobile app via Tailscale
and provides in-app responses with TTS audio.

Run with: uv run server.py
Or: ./server.py (if executable)

Listens on: http://0.0.0.0:9091

Endpoints:
- POST /prompt - Receive transcript, inject into app session
- GET /messages - Poll for new messages
- GET /audio/{message_id} - Download TTS audio file
"""

import json
import logging
import mimetypes
import os
import re
import socket as sock_module
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, File, UploadFile, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import yaml


def _load_dispatch_config() -> dict:
    """Load assistant config from ~/dispatch/config.local.yaml."""
    config_path = Path.home() / "dispatch" / "config.local.yaml"
    if config_path.exists():
        try:
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}


_DISPATCH_CONFIG = _load_dispatch_config()
ASSISTANT_NAME = (_DISPATCH_CONFIG.get("assistant", {}) or {}).get("name", "Dispatch")
APP_SESSION_PREFIX = "dispatch-app"  # Always "dispatch-app" regardless of assistant name


def log_perf(metric: str, value: float, **labels) -> None:
    """Log a perf metric to the shared JSONL file."""
    try:
        perf_dir = Path.home() / "dispatch" / "logs"
        perf_dir.mkdir(parents=True, exist_ok=True)
        path = perf_dir / f"perf-{datetime.now():%Y-%m-%d}.jsonl"
        entry = {"v": 1, "ts": datetime.now().isoformat(), "metric": metric, "value": value, "component": "dispatch-api", **labels}
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never fail on perf logging

# Configure logging
LOG_DIR = Path.home() / "dispatch" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "dispatch-api.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("dispatch-api")

app = FastAPI(title="Dispatch API", description="Voice assistant backend for Dispatch mobile app")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests and responses."""
    start_time = time.time()

    # Log incoming request
    logger.info(f"→ {request.method} {request.url.path} from {request.client.host if request.client else 'unknown'}")

    # Process request
    response = await call_next(request)

    # Log response
    duration_ms = (time.time() - start_time) * 1000
    logger.info(f"← {request.method} {request.url.path} → {response.status_code} ({duration_ms:.1f}ms)")

    # Perf logging
    log_perf("request_ms", duration_ms, endpoint=request.url.path, method=request.method, status=response.status_code)

    return response


# Config
ALLOWED_TOKENS_FILE = Path(__file__).parent / "allowed_tokens.json"
_STATE_DIR = Path.home() / "dispatch" / "state"
APNS_TOKENS_FILE = _STATE_DIR / "dispatch-apns-tokens.json"
DB_PATH = _STATE_DIR / "dispatch-messages.db"
AUDIO_DIR = _STATE_DIR / "dispatch-audio"
IMAGE_DIR = _STATE_DIR / "dispatch-images"

# Backward compatibility: migrate old sven-* file names to dispatch-*
_LEGACY_RENAMES = {
    _STATE_DIR / "sven-apns-tokens.json": APNS_TOKENS_FILE,
    _STATE_DIR / "sven-messages.db": DB_PATH,
    _STATE_DIR / "sven-audio": AUDIO_DIR,
    _STATE_DIR / "sven-images": IMAGE_DIR,
}
for old_path, new_path in _LEGACY_RENAMES.items():
    if old_path.exists() and not new_path.exists():
        try:
            old_path.rename(new_path)
        except OSError:
            pass  # Best-effort migration
CLAUDE_ASSISTANT_CLI = str(Path.home() / "dispatch" / "bin" / "claude-assistant")
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 30  # requests per window

# Image format signatures for upload validation
_IMAGE_SIGNATURES = [
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG",       # PNG
    b"GIF8",          # GIF
    b"RIFF",          # WebP
]

def _is_valid_image(data: bytes) -> bool:
    """Check magic bytes to verify data is a recognized image format."""
    if len(data) < 8:
        return False
    header = data[:12]
    if any(header.startswith(sig) for sig in _IMAGE_SIGNATURES):
        return True
    # HEIC/HEIF/AVIF: ISO BMFF container has 'ftyp' at byte offset 4
    if header[4:8] == b"ftyp":
        return True
    return False

# In-memory rate limiting (reset on restart)
request_counts: dict[str, list[float]] = {}


class PromptRequest(BaseModel):
    """Request from Dispatch mobile app"""
    transcript: str
    token: str
    chat_id: str = "voice"
    message_id: Optional[str] = None  # Client-generated idempotency key to prevent duplicates
    attestation: Optional[str] = None
    assertion: Optional[str] = None


class APNsRegisterRequest(BaseModel):
    """Request to register APNs device token"""
    device_token: str
    apns_token: str


class CreateChatRequest(BaseModel):
    token: str = ""
    title: str = None


class UpdateChatRequest(BaseModel):
    token: str = ""
    title: str


class PromptResponse(BaseModel):
    """Response to iOS app"""
    status: str
    message: str
    request_id: str


class Message(BaseModel):
    """A message in the conversation"""
    id: str
    role: str
    content: str
    audio_url: Optional[str]
    created_at: str


class MessagesResponse(BaseModel):
    """Response for GET /messages"""
    messages: list[Message]


def init_db():
    """Initialize the SQLite database if it doesn't exist.

    NOTE: Schema mirrors dispatch_db.py (the single source of truth).
    If adding migrations, update dispatch_db.py too.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")  # Enable WAL for concurrent readers/writers
    conn.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s on lock contention
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            image_path TEXT,
            audio_path TEXT,
            chat_id TEXT NOT NULL DEFAULT 'voice',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migration: add chat_id column if table already exists without it
    columns = [row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()]
    if "chat_id" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN chat_id TEXT NOT NULL DEFAULT 'voice'")
    # Migration: add image_path column if missing
    if "image_path" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN image_path TEXT")
    # Create indexes for chat_id queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_created ON messages(chat_id, created_at)")
    # Create chats table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New Chat',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Note: no default "voice" chat is auto-created. Chats are created on demand.
    # Migration: add last_opened_at column if missing
    chat_columns = [row[1] for row in conn.execute("PRAGMA table_info(chats)").fetchall()]
    if "last_opened_at" not in chat_columns:
        try:
            conn.execute("ALTER TABLE chats ADD COLUMN last_opened_at DATETIME")
        except sqlite3.OperationalError:
            pass  # Column already exists (race condition)
    # Chat notes table — keep in sync with dispatch_db.py CHAT_NOTES_SCHEMA
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_notes (
            chat_id TEXT PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,
            content TEXT NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def load_allowed_tokens() -> set[str]:
    """Load allowed device tokens from file"""
    if ALLOWED_TOKENS_FILE.exists():
        with open(ALLOWED_TOKENS_FILE) as f:
            data = json.load(f)
            return set(data.get("tokens", []))
    return set()


def save_allowed_tokens(tokens: set[str]):
    """Save allowed device tokens to file"""
    with open(ALLOWED_TOKENS_FILE, "w") as f:
        json.dump({"tokens": list(tokens)}, f, indent=2)


def is_rate_limited(token: str) -> bool:
    """Check if token has exceeded rate limit"""
    now = time.time()
    if token not in request_counts:
        request_counts[token] = []

    # Remove old entries outside window
    request_counts[token] = [t for t in request_counts[token] if now - t < RATE_LIMIT_WINDOW]

    if len(request_counts[token]) >= RATE_LIMIT_MAX:
        return True

    request_counts[token].append(now)
    return False


def validate_token(token: str):
    """Validate device token against allowed tokens list. Raises HTTPException on failure."""
    allowed = load_allowed_tokens()
    if allowed and token not in allowed:
        raise HTTPException(status_code=403, detail="Invalid token")


def get_db():
    """Get a WAL-mode database connection."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def store_user_message(message_id: str, content: str, chat_id: str = "voice", image_path: str | None = None):
    """Store user message in SQLite database."""
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (id, role, content, chat_id, image_path) VALUES (?, ?, ?, ?, ?)",
        (message_id, "user", content, chat_id, image_path)
    )
    conn.execute(
        "UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (chat_id,)
    )
    conn.commit()
    conn.close()


async def inject_prompt_to_app_session(transcript: str, chat_id: str = "voice", image_path: str | None = None) -> bool:
    """Inject the transcript into the dedicated app session.

    Uses async subprocess to avoid blocking the FastAPI event loop.
    """
    import asyncio

    try:
        logger.info(f"inject_prompt: calling inject-prompt CLI...")
        # Use inject-prompt to send to the app session
        # The session will respond via reply CLI which stores in message bus
        cmd = [
            CLAUDE_ASSISTANT_CLI, "inject-prompt",
            f"{APP_SESSION_PREFIX}:{chat_id}",  # Dedicated app session
            "--sms",  # Wrap with SMS format (includes tier in prompt)
            "--app",  # Format for mobile app (adds 🎤 prefix and echo instruction)
            "--admin",  # Admin tier access
        ]

        # Add image attachment if present
        if image_path:
            cmd.extend(["--attachment", image_path])

        # For image-only messages, use a placeholder prompt (image is the content)
        cmd.append(transcript if transcript else "[Sent an image]")

        # Use async subprocess to avoid blocking the event loop
        # Clear VIRTUAL_ENV to prevent uv's venv from leaking into subprocess
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.error("inject_prompt: timed out after 30s")
            return False

        if proc.returncode != 0:
            logger.error(f"inject_prompt: failed with code {proc.returncode}")
            logger.error(f"inject_prompt: stderr={stderr.decode()}")
            logger.error(f"inject_prompt: stdout={stdout.decode()}")
            return False

        logger.info(f"inject_prompt: success - {transcript[:50]}...")
        return True

    except Exception as e:
        logger.error(f"inject_prompt: exception: {type(e).__name__}: {e}")
        return False



@app.get("/")
async def root():
    """Landing page with links to app pages"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse("""<!DOCTYPE html>
<html><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dispatch</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #000; color: #fff;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .container { text-align: center; }
  h1 { font-size: 2rem; margin-bottom: 2rem; font-weight: 600; }
  .links { display: flex; gap: 1rem; flex-wrap: wrap; justify-content: center; }
  a { display: block; padding: 1rem 2rem; background: #1a1a1a; border: 1px solid #333;
      border-radius: 12px; color: #fff; text-decoration: none; font-size: 1.1rem;
      transition: background 0.2s, border-color 0.2s; min-width: 160px; }
  a:hover { background: #2a2a2a; border-color: #555; }
  .label { font-weight: 500; }
  .sub { color: #888; font-size: 0.85rem; margin-top: 4px; }
</style>
</head><body>
<div class="container">
  <h1>Dispatch</h1>
  <div class="links">
    <a href="/app/"><div class="label">App</div><div class="sub">Messages &amp; Settings</div></a>
    <a href="/agents"><div class="label">Agents</div><div class="sub">Session Management</div></a>
  </div>
</div>
</body></html>""")


@app.get("/health")
async def health():
    """Health check for monitoring"""
    return {"status": "healthy"}


def _build_server_identity() -> dict:
    """Build server identity once at import time. Cached — IPs are stable."""
    import socket as _sock
    import subprocess as _sp

    hostname = _sock.gethostname()

    # Local IP (en0)
    local_ip = None
    try:
        result = _sp.run(["ipconfig", "getifaddr", "en0"],
                         capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            local_ip = result.stdout.strip()
    except Exception:
        pass

    # Tailscale IP
    tailscale_ip = None
    try:
        result = _sp.run(
            ["/opt/homebrew/opt/tailscale/bin/tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            tailscale_ip = result.stdout.strip()
        else:
            result = _sp.run(
                ["/opt/homebrew/opt/tailscale/bin/tailscale",
                 "--socket=/tmp/tailscale.sock", "ip", "-4"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                tailscale_ip = result.stdout.strip()
    except Exception:
        pass

    return {
        "name": ASSISTANT_NAME,
        "hostname": hostname,
        "local_ip": local_ip,
        "tailscale_ip": tailscale_ip,
        "port": 9091,
    }


_SERVER_IDENTITY = _build_server_identity()


@app.get("/discover")
async def discover():
    """Return cached server identity for auto-discovery by the mobile app.

    Response is computed once at startup (IPs are stable).
    Called by the mobile app's subnet scanner — must be fast.
    """
    return _SERVER_IDENTITY


@app.post("/prompt", response_model=PromptResponse)
async def receive_prompt(request: PromptRequest):
    """
    Receive voice transcript from Dispatch mobile app.

    Stores user message and injects into app session.
    Response will appear via GET /messages polling.
    """
    token_short = request.token[:8] if request.token else "none"
    logger.info(f"POST /prompt: token={token_short}... transcript={request.transcript[:100] if request.transcript else 'empty'}...")

    # Validate transcript
    if not request.transcript or not request.transcript.strip():
        logger.warning(f"POST /prompt: empty transcript from token={token_short}")
        raise HTTPException(status_code=400, detail="Empty transcript")

    transcript = request.transcript.strip()

    # Token validation
    allowed_tokens = load_allowed_tokens()
    logger.debug(f"Allowed tokens: {len(allowed_tokens)} registered")

    # If no tokens registered yet, accept any token and register it (first-time setup)
    if not allowed_tokens:
        logger.info(f"First token registration: {token_short}...")
        allowed_tokens.add(request.token)
        save_allowed_tokens(allowed_tokens)
    elif request.token not in allowed_tokens:
        logger.warning(f"POST /prompt: unauthorized token={token_short}")
        raise HTTPException(status_code=401, detail="Unknown device token")

    # Rate limiting
    if is_rate_limited(request.token):
        logger.warning(f"POST /prompt: rate limited token={token_short}")
        raise HTTPException(status_code=429, detail="Too many requests")

    # Use client-provided message_id for idempotency, or generate one
    request_id = request.message_id or str(uuid.uuid4())
    logger.info(f"POST /prompt: request_id={request_id[:8]}... for transcript")

    # Deduplicate: if a client-provided message_id already exists, return success
    # without re-storing or re-injecting (idempotent retry)
    if request.message_id:
        try:
            conn = get_db()
            existing = conn.execute(
                "SELECT id FROM messages WHERE id = ?", (request.message_id,)
            ).fetchone()
            conn.close()
            if existing:
                logger.info(f"POST /prompt: duplicate message_id={request_id[:8]}... — returning existing (idempotent)")
                return PromptResponse(
                    status="ok",
                    message="Prompt already received (deduplicated).",
                    request_id=request_id,
                )
        except Exception as e:
            logger.warning(f"POST /prompt: dedup check failed: {e} — proceeding normally")

    # Store user message in message bus
    try:
        store_user_message(request_id, transcript, chat_id=request.chat_id)
        logger.info(f"POST /prompt: stored user message {request_id[:8]}...")
    except Exception as e:
        logger.error(f"POST /prompt: failed to store message: {e}")
        raise HTTPException(status_code=500, detail="Failed to store message")

    # Auto-title: on first message to a "New Chat", set title from transcript
    try:
        conn = get_db()
        row = conn.execute("SELECT title FROM chats WHERE id = ?", (request.chat_id,)).fetchone()
        if row and row[0] == "New Chat":
            title = transcript[:40].strip()
            if len(transcript) > 40:
                title = title.rsplit(" ", 1)[0] + "..." if " " in title else title + "..."
            conn.execute("UPDATE chats SET title = ? WHERE id = ?", (title, request.chat_id))
            conn.commit()
        conn.close()
    except Exception:
        pass  # Don't fail the request on auto-title error

    # Inject into app session
    logger.info(f"POST /prompt: injecting into {APP_SESSION_PREFIX} session...")
    success = await inject_prompt_to_app_session(transcript, chat_id=request.chat_id)

    if not success:
        logger.error(f"POST /prompt: failed to inject prompt for request_id={request_id[:8]}")
        raise HTTPException(status_code=500, detail="Failed to inject prompt")

    logger.info(f"POST /prompt: success! request_id={request_id[:8]}...")
    return PromptResponse(
        status="ok",
        message="Prompt received. Poll /messages for response.",
        request_id=request_id
    )


@app.post("/prompt-with-image", response_model=PromptResponse)
async def receive_prompt_with_image(
    request: Request,
    transcript: str = Form(""),
    token: str = Form(""),
    chat_id: str = Form("voice"),
    message_id: str = Form(None),  # Client-generated idempotency key to prevent duplicates
    image: UploadFile | None = File(None),
):
    """
    Receive voice transcript with optional image from Dispatch mobile app.

    Uses multipart/form-data to support file uploads.
    Stores user message and injects into app session with image attachment.
    Response will appear via GET /messages polling.
    """
    # Accept token from either form data or query param (apiRequest sends it as query param)
    token = token or request.query_params.get("token", "")
    token_short = token[:8] if token else "none"
    has_image = image is not None and image.filename
    logger.info(f"POST /prompt-with-image: token={token_short}... transcript={transcript[:100] if transcript else 'empty'}... has_image={has_image}")

    # Validate: need either transcript or image
    transcript = (transcript or "").strip()
    if not transcript and not has_image:
        logger.warning(f"POST /prompt-with-image: empty transcript and no image from token={token_short}")
        raise HTTPException(status_code=400, detail="Empty transcript and no image")

    # Token validation
    allowed_tokens = load_allowed_tokens()
    logger.debug(f"Allowed tokens: {len(allowed_tokens)} registered")

    if not allowed_tokens:
        logger.info(f"First token registration: {token_short}...")
        allowed_tokens.add(token)
        save_allowed_tokens(allowed_tokens)
    elif token not in allowed_tokens:
        logger.warning(f"POST /prompt-with-image: unauthorized token={token_short}")
        raise HTTPException(status_code=401, detail="Unknown device token")

    # Rate limiting
    if is_rate_limited(token):
        logger.warning(f"POST /prompt-with-image: rate limited token={token_short}")
        raise HTTPException(status_code=429, detail="Too many requests")

    # Use client-provided message_id for idempotency, or generate one
    request_id = message_id or str(uuid.uuid4())
    logger.info(f"POST /prompt-with-image: request_id={request_id[:8]}...")

    # Deduplicate: if a client-provided message_id already exists, return success
    if message_id:
        try:
            conn = get_db()
            existing = conn.execute(
                "SELECT id FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
            conn.close()
            if existing:
                logger.info(f"POST /prompt-with-image: duplicate message_id={request_id[:8]}... — returning existing (idempotent)")
                return PromptResponse(
                    status="ok",
                    message="Prompt already received (deduplicated).",
                    request_id=request_id,
                )
        except Exception as e:
            logger.warning(f"POST /prompt-with-image: dedup check failed: {e} — proceeding normally")

    # Handle image upload
    image_path = None
    if image and image.filename:
        try:
            IMAGE_DIR.mkdir(parents=True, exist_ok=True)
            # Preserve file extension
            ext = Path(image.filename).suffix.lower() or ".jpg"
            image_path = str(IMAGE_DIR / f"{request_id}{ext}")

            # Read and save image (file-first, DB-second for crash safety)
            image_data = await image.read()

            # Size validation: reject uploads over 10MB
            if len(image_data) > 10_000_000:
                raise HTTPException(status_code=413, detail="Image too large (max 10MB)")

            # Magic bytes validation: verify this is actually an image
            if not _is_valid_image(image_data):
                raise HTTPException(status_code=400, detail="Invalid image format")

            with open(image_path, "wb") as f:
                f.write(image_data)

            logger.info(f"POST /prompt-with-image: saved image to {image_path} ({len(image_data)} bytes)")
        except HTTPException:
            raise  # Re-raise validation errors (413, 400) — don't swallow them
        except Exception as e:
            logger.error(f"POST /prompt-with-image: failed to save image: {e}")
            # Continue without image - don't fail the whole request

    # Store user message in message bus
    try:
        store_user_message(request_id, transcript, chat_id=chat_id, image_path=image_path)
        logger.info(f"POST /prompt-with-image: stored user message {request_id[:8]}...")
    except Exception as e:
        logger.error(f"POST /prompt-with-image: failed to store message: {e}")
        raise HTTPException(status_code=500, detail="Failed to store message")

    # Inject into app session
    logger.info(f"POST /prompt-with-image: injecting into {APP_SESSION_PREFIX} session...")
    success = await inject_prompt_to_app_session(transcript, chat_id=chat_id, image_path=image_path)

    if not success:
        logger.error(f"POST /prompt-with-image: failed to inject prompt for request_id={request_id[:8]}")
        raise HTTPException(status_code=500, detail="Failed to inject prompt")

    logger.info(f"POST /prompt-with-image: success! request_id={request_id[:8]}...")
    return PromptResponse(
        status="ok",
        message="Prompt received with image. Poll /messages for response.",
        request_id=request_id
    )


@app.get("/messages")
async def get_messages(since: Optional[str] = None, token: Optional[str] = None, chat_id: str = "voice"):
    """Get messages from the conversation, filtered by chat."""
    token_short = token[:8] if token else "none"
    logger.debug(f"GET /messages: since={since}, token={token_short}..., chat_id={chat_id}")

    if token:
        allowed_tokens = load_allowed_tokens()
        if allowed_tokens and token not in allowed_tokens:
            logger.warning(f"GET /messages: unauthorized token={token_short}")
            raise HTTPException(status_code=401, detail="Unknown device token")

    try:
        conn = get_db()
        if since:
            # Convert ISO 8601 back to SQLite format for comparison
            since_sqlite = since.replace("T", " ").replace("Z", "") if since else since
            cursor = conn.execute(
                "SELECT id, role, content, image_path, audio_path, created_at FROM messages "
                "WHERE chat_id = ? AND created_at > ? ORDER BY created_at ASC LIMIT 500",
                (chat_id, since_sqlite)
            )
        else:
            # Subquery gets newest 200 messages, outer query re-orders ASC for display
            cursor = conn.execute(
                "SELECT * FROM ("
                "  SELECT id, role, content, image_path, audio_path, created_at FROM messages "
                "  WHERE chat_id = ? ORDER BY created_at DESC LIMIT 200"
                ") ORDER BY created_at ASC",
                (chat_id,)
            )
        columns = [desc[0] for desc in cursor.description]
        messages = []
        for row in cursor.fetchall():
            msg = dict(zip(columns, row))
            if msg.get("audio_path"):
                msg["audio_url"] = f"/audio/{msg['id']}"
            else:
                msg["audio_url"] = None
            del msg["audio_path"]
            # Expose image_url if image exists on disk
            image_path = msg.get("image_path")
            if image_path and Path(image_path).exists():
                msg["image_url"] = f"/image/{msg['id']}"
            else:
                msg["image_url"] = None
            del msg["image_path"]
            # Convert SQLite timestamp to ISO 8601 for JavaScript
            msg["created_at"] = _sqlite_to_iso(msg.get("created_at"))
            messages.append(msg)
        conn.close()
    except Exception as e:
        logger.error(f"GET /messages: database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

    # Check if the agent is currently thinking for this chat
    is_thinking = _check_is_thinking(f"{APP_SESSION_PREFIX}/{chat_id}")

    logger.debug(f"GET /messages: returning {len(messages)} messages, is_thinking={is_thinking}")
    return {"messages": messages, "is_thinking": is_thinking}


@app.get("/audio/{message_id}")
async def get_audio(message_id: str, token: Optional[str] = None):
    """
    Download TTS audio file for a message.

    Lazy TTS: if the audio file doesn't exist yet, generates it on-demand
    from the message content using Kokoro TTS, then caches and serves it.

    Args:
        message_id: The message ID
        token: Device token for auth (optional)
    """
    token_short = token[:8] if token else "none"
    logger.info(f"GET /audio/{message_id[:8]}...: token={token_short}...")

    # Optional token validation
    if token:
        allowed_tokens = load_allowed_tokens()
        if allowed_tokens and token not in allowed_tokens:
            logger.warning(f"GET /audio: unauthorized token={token_short}")
            raise HTTPException(status_code=401, detail="Unknown device token")

    audio_path = AUDIO_DIR / f"{message_id}.wav"

    if not audio_path.exists():
        # Lazy TTS: generate audio on-demand from message content
        logger.info(f"GET /audio: generating TTS on-demand for {message_id[:8]}...")

        # Look up message content from DB
        conn = get_db()
        row = conn.execute(
            "SELECT content FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        conn.close()

        if not row:
            logger.warning(f"GET /audio: message not found: {message_id[:8]}")
            raise HTTPException(status_code=404, detail="Message not found")

        content = row[0]
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

        # Generate TTS using Kokoro
        tts_script = Path.home() / ".claude" / "skills" / "tts" / "scripts" / "speak"
        if not tts_script.exists():
            logger.error(f"GET /audio: TTS script not found at {tts_script}")
            raise HTTPException(status_code=503, detail="TTS service unavailable")

        import asyncio
        try:
            proc = await asyncio.create_subprocess_exec(
                str(tts_script), content, "-o", str(audio_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0 or not audio_path.exists():
                logger.error(f"GET /audio: TTS failed: {stderr.decode()[:200]}")
                raise HTTPException(status_code=503, detail="TTS generation failed")

            # Update the message record with the audio path
            conn = get_db()
            conn.execute(
                "UPDATE messages SET audio_path = ? WHERE id = ?",
                (str(audio_path), message_id),
            )
            conn.commit()
            conn.close()

            logger.info(f"GET /audio: TTS generated and cached for {message_id[:8]}")

        except asyncio.TimeoutError:
            logger.error(f"GET /audio: TTS timed out for {message_id[:8]}")
            raise HTTPException(status_code=503, detail="TTS generation timed out")

    logger.info(f"GET /audio: serving {audio_path.name} ({audio_path.stat().st_size} bytes)")
    return FileResponse(
        path=audio_path,
        media_type="audio/wav",
        filename=f"{message_id}.wav"
    )


@app.get("/image/{message_id}")
async def get_image(message_id: str, token: Optional[str] = None):
    """Serve an image attachment for a message.

    Looks up image_path from the messages DB and serves the file.
    Mirrors the GET /audio/{message_id} pattern.

    Args:
        message_id: The message ID
        token: Device token for auth (optional)
    """
    token_short = token[:8] if token else "none"
    logger.info(f"GET /image/{message_id[:8]}...: token={token_short}...")

    # Token validation (same as audio endpoint)
    if token:
        allowed_tokens = load_allowed_tokens()
        if allowed_tokens and token not in allowed_tokens:
            logger.warning(f"GET /image: unauthorized token={token_short}")
            raise HTTPException(status_code=401, detail="Unknown device token")

    # Look up image_path from DB
    conn = get_db()
    row = conn.execute(
        "SELECT image_path FROM messages WHERE id = ?", (message_id,)
    ).fetchone()
    conn.close()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Image not found")

    image_path = Path(row[0]).resolve()

    # Security: ensure path is under expected images directory
    if not image_path.is_relative_to(IMAGE_DIR.resolve()):
        logger.warning(f"GET /image: path traversal attempt: {image_path}")
        raise HTTPException(status_code=403, detail="Access denied")

    if not image_path.exists():
        logger.warning(f"GET /image: file missing on disk: {image_path}")
        raise HTTPException(status_code=404, detail="Image file not found")

    # Detect MIME type from extension
    mime_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"

    logger.info(f"GET /image: serving {image_path.name} ({image_path.stat().st_size} bytes, {mime_type})")
    return FileResponse(
        path=image_path,
        media_type=mime_type,
        filename=image_path.name,
        headers={"Cache-Control": "max-age=86400"},
    )


@app.delete("/messages")
async def clear_messages(token: Optional[str] = None, chat_id: str = "voice"):
    """Clear messages for a specific chat."""
    if token:
        allowed_tokens = load_allowed_tokens()
        if allowed_tokens and token not in allowed_tokens:
            raise HTTPException(status_code=401, detail="Unknown device token")

    conn = get_db()
    # Get media paths before deleting
    media_rows = conn.execute(
        "SELECT audio_path, image_path FROM messages WHERE chat_id = ?",
        (chat_id,)
    ).fetchall()
    conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

    # Clean up audio and image files for this chat
    for audio_path, image_path in media_rows:
        for media_path in (audio_path, image_path):
            if media_path:
                p = Path(media_path)
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass

    return {"status": "ok", "message": "Messages cleared"}


@app.post("/register")
async def register_token(token: str):
    """
    Register a new device token (admin endpoint).
    """
    allowed_tokens = load_allowed_tokens()
    allowed_tokens.add(token)
    save_allowed_tokens(allowed_tokens)
    return {"status": "ok", "message": "Token registered"}


@app.post("/register-apns")
async def register_apns(request: APNsRegisterRequest):
    """
    Register APNs device token for push notifications.

    The iOS app calls this on launch to register/update its APNs token.
    Maps device_token (app-level ID) to apns_token (Apple push token).
    """
    device_short = request.device_token[:8] if request.device_token else "none"
    apns_short = request.apns_token[:8] if request.apns_token else "none"
    logger.info(f"POST /register-apns: device={device_short}... apns={apns_short}...")

    # Auto-register device token if not already registered
    allowed_tokens = load_allowed_tokens()
    if request.device_token not in allowed_tokens:
        allowed_tokens.add(request.device_token)
        save_allowed_tokens(allowed_tokens)
        logger.info(f"POST /register-apns: auto-registered device={device_short}...")

    # Load existing APNs tokens
    try:
        apns_tokens = json.loads(APNS_TOKENS_FILE.read_text()) if APNS_TOKENS_FILE.exists() else {}
    except Exception as e:
        logger.error(f"POST /register-apns: failed to load tokens: {e}")
        apns_tokens = {}

    # Store mapping: device_token -> apns_token
    apns_tokens[request.device_token] = request.apns_token

    # Save
    try:
        APNS_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
        APNS_TOKENS_FILE.write_text(json.dumps(apns_tokens, indent=2))
        logger.info(f"POST /register-apns: saved APNs token for device={device_short}...")
    except Exception as e:
        logger.error(f"POST /register-apns: failed to save tokens: {e}")
        raise HTTPException(status_code=500, detail="Failed to save APNs token")

    return {"status": "ok", "message": "APNs token registered"}


@app.get("/tokens")
async def list_tokens():
    """List registered tokens (admin endpoint, shows truncated tokens)"""
    allowed_tokens = load_allowed_tokens()
    return {"tokens": [t[:8] + "..." for t in allowed_tokens]}


@app.post("/restart-session")
async def restart_session(token: Optional[str] = None, chat_id: str = "voice"):
    """
    Restart the app Claude session.
    Useful when the session gets stuck or needs a fresh context.
    """
    token_short = token[:8] if token else "none"
    logger.info(f"POST /restart-session: token={token_short}...")

    # Optional token validation
    if token:
        allowed_tokens = load_allowed_tokens()
        if allowed_tokens and token not in allowed_tokens:
            logger.warning(f"POST /restart-session: unauthorized token={token_short}")
            raise HTTPException(status_code=401, detail="Unknown device token")

    try:
        result = subprocess.run(
            [
                CLAUDE_ASSISTANT_CLI, "restart-session",
                f"{APP_SESSION_PREFIX}:{chat_id}"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.error(f"restart-session: failed with code {result.returncode}")
            logger.error(f"restart-session: stderr={result.stderr}")
            raise HTTPException(status_code=500, detail="Failed to restart session")

        logger.info("restart-session: success")
        return {"status": "ok", "message": "Session restarted"}

    except subprocess.TimeoutExpired:
        logger.error("restart-session: timed out after 30s")
        raise HTTPException(status_code=500, detail="Timeout restarting session")
    except Exception as e:
        logger.error(f"restart-session: exception: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chats")
async def create_chat(request: CreateChatRequest, token: str = None):
    """Create a new chat."""
    # Use query param token (sent by apiRequest), fall back to body token
    effective_token = token or request.token
    validate_token(effective_token)
    chat_id = str(uuid.uuid4())
    display_title = request.title or "New Chat"
    conn = get_db()
    conn.execute(
        "INSERT INTO chats (id, title) VALUES (?, ?)",
        (chat_id, display_title)
    )
    conn.commit()
    row = conn.execute("SELECT id, title, created_at, updated_at, last_opened_at FROM chats WHERE id = ?", (chat_id,)).fetchone()
    conn.close()
    return {
        "id": row[0], "title": row[1],
        "created_at": _sqlite_to_iso(row[2]), "updated_at": _sqlite_to_iso(row[3]),
        "last_message": None, "last_message_at": None, "last_message_role": None,
        "last_opened_at": _sqlite_to_iso(row[4]),
    }


def _sqlite_to_iso(ts: str | None) -> str | None:
    """Convert SQLite DATETIME string to ISO 8601 format for JavaScript."""
    if not ts:
        return None
    # SQLite CURRENT_TIMESTAMP gives "YYYY-MM-DD HH:MM:SS" (UTC)
    # JavaScript needs "YYYY-MM-DDTHH:MM:SSZ" for reliable parsing
    return ts.replace(" ", "T") + "Z" if " " in ts else ts


@app.get("/chats")
async def list_chats(token: str = None):
    """List all chats with last message previews."""
    conn = get_db()
    cursor = conn.execute("""
        SELECT c.id, c.title, c.created_at, c.updated_at,
               m.content AS last_message,
               m.created_at AS last_message_at,
               m.role AS last_message_role,
               c.last_opened_at,
               EXISTS(SELECT 1 FROM chat_notes cn WHERE cn.chat_id = c.id AND cn.content != '') AS has_notes
        FROM chats c
        LEFT JOIN (
            SELECT chat_id, content, created_at, role,
                   ROW_NUMBER() OVER (PARTITION BY chat_id ORDER BY created_at DESC) AS rn
            FROM messages
        ) m ON m.chat_id = c.id AND m.rn = 1
        ORDER BY COALESCE(m.created_at, c.created_at) DESC
    """)
    chats = []
    for row in cursor.fetchall():
        chat_id = row[0]
        chats.append({
            "id": chat_id,
            "title": row[1],
            "created_at": _sqlite_to_iso(row[2]),
            "updated_at": _sqlite_to_iso(row[3]),
            "last_message": row[4],
            "last_message_at": _sqlite_to_iso(row[5]),
            "last_message_role": row[6],
            "last_opened_at": _sqlite_to_iso(row[7]),
            "has_notes": bool(row[8]),
            "is_thinking": _check_is_thinking(f"{APP_SESSION_PREFIX}/{chat_id}"),
        })
    conn.close()
    return {"chats": chats}


@app.post("/chats/{chat_id}/open")
async def mark_chat_opened(chat_id: str, token: str = None):
    """Mark a chat as opened (updates last_opened_at for unread tracking)."""
    validate_token(token)
    conn = get_db()
    cursor = conn.execute(
        "UPDATE chats SET last_opened_at = CURRENT_TIMESTAMP WHERE id = ?",
        (chat_id,),
    )
    conn.commit()
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Chat not found")
    conn.close()
    return {"ok": True}


@app.patch("/chats/{chat_id}")
async def update_chat(chat_id: str, request: UpdateChatRequest, token: str = None):
    """Rename a chat."""
    effective_token = token or request.token
    validate_token(effective_token)
    conn = get_db()
    conn.execute(
        "UPDATE chats SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (request.title, chat_id)
    )
    conn.commit()
    row = conn.execute("SELECT id, title, created_at, updated_at, last_opened_at FROM chats WHERE id = ?", (chat_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {
        "id": row[0], "title": row[1],
        "created_at": _sqlite_to_iso(row[2]), "updated_at": _sqlite_to_iso(row[3]),
        "last_message": None, "last_message_at": None, "last_message_role": None,
        "last_opened_at": _sqlite_to_iso(row[4]),
    }


MAX_NOTES_LENGTH = 50_000


class UpdateNotesRequest(BaseModel):
    token: str = ""
    content: str


@app.get("/chats/{chat_id}/notes")
async def get_chat_notes(chat_id: str, token: str = None):
    """Get notes for a chat."""
    validate_token(token)
    conn = get_db()
    row = conn.execute(
        "SELECT content, updated_at FROM chat_notes WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    conn.close()
    return {
        "chat_id": chat_id,
        "content": row[0] if row else "",
        "updated_at": _sqlite_to_iso(row[1]) if row else None,
    }


@app.put("/chats/{chat_id}/notes")
async def update_chat_notes(chat_id: str, request: UpdateNotesRequest, token: str = None):
    """Create or update notes for a chat (upsert)."""
    effective_token = token or request.token
    validate_token(effective_token)
    if len(request.content) > MAX_NOTES_LENGTH:
        raise HTTPException(status_code=400, detail=f"Notes exceed maximum length of {MAX_NOTES_LENGTH} characters")
    conn = get_db()
    conn.execute("""
        INSERT INTO chat_notes (chat_id, content, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(chat_id) DO UPDATE SET
            content = excluded.content,
            updated_at = CURRENT_TIMESTAMP
    """, (chat_id, request.content))
    conn.commit()
    row = conn.execute(
        "SELECT content, updated_at FROM chat_notes WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    conn.close()
    return {
        "chat_id": chat_id,
        "content": row[0],
        "updated_at": _sqlite_to_iso(row[1]),
    }


@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, token: str = None):
    """Delete a chat and its messages."""
    validate_token(token)
    conn = get_db()
    # Clean up media files for this chat
    media_rows = conn.execute(
        "SELECT audio_path, image_path FROM messages WHERE chat_id = ?",
        (chat_id,)
    ).fetchall()
    conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    conn.commit()
    conn.close()
    for audio_path, image_path in media_rows:
        for media_path in (audio_path, image_path):
            if media_path:
                p = Path(media_path)
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass
    # Kill the dispatch session (fire and forget)
    session_id = f"{APP_SESSION_PREFIX}:{chat_id}"
    subprocess.Popen(
        [CLAUDE_ASSISTANT_CLI, "kill-session", session_id],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# Dashboard API endpoints
# ─────────────────────────────────────────────────────────────

BUS_DB_PATH = Path.home() / "dispatch" / "state" / "bus.db"
IPC_SOCKET = Path("/tmp/claude-assistant.sock")
SESSIONS_JSON = Path.home() / "dispatch" / "state" / "sessions.json"
REMINDERS_JSON = Path.home() / "dispatch" / "state" / "reminders.json"
DAEMON_PID_FILE = Path.home() / "dispatch" / "state" / "daemon.pid"
PERF_LOG_DIR = Path.home() / "dispatch" / "logs"
SKILLS_DIR = Path.home() / ".claude" / "skills"
DISPATCH_LOGS_DIR = Path.home() / "dispatch" / "logs"

ALLOWED_LOG_FILES = {
    "manager.log", "session_lifecycle.log", "watchdog.log",
    "dispatch-api.log", "signal-daemon.log", "compactions.log",
    "memory-consolidation.log", "nightly-scraper.log",
    "launchd.log", "watchdog-launchd.log", "search-daemon.log",
    "embed-rerank.log", "memory-search.log", "chat-context-consolidation.log",
    "client.log",
}

# Client log file for remote app logging
CLIENT_LOG_PATH = DISPATCH_LOGS_DIR / "client.log"


def get_bus_db():
    """Get a read-only connection to bus.db with WAL mode."""
    conn = sqlite3.connect(f"file:{BUS_DB_PATH}?mode=ro", uri=True)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    html_path = Path(__file__).parent / "dashboard.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return HTMLResponse(content=html_path.read_text())


@app.get("/api/dashboard/health")
async def dashboard_health():
    """System health snapshot."""
    result = {
        "daemon_pid": None,
        "daemon_running": False,
        "uptime_seconds": 0,
        "active_sessions": 0,
        "total_sessions": 0,
        "total_bus_events": 0,
        "total_sdk_events": 0,
        "events_last_hour": 0,
        "sdk_events_last_hour": 0,
        "last_event_age_seconds": None,
        "health_status": "unknown",
        "active_reminders": 0,
        "facts_count": 0,
        "skills_count": 0,
    }

    # Daemon PID and running status
    try:
        if DAEMON_PID_FILE.exists():
            pid = int(DAEMON_PID_FILE.read_text().strip())
            result["daemon_pid"] = pid
            # Check if process is running
            try:
                os.kill(pid, 0)
                result["daemon_running"] = True
                # Estimate uptime from pid file mtime
                mtime = DAEMON_PID_FILE.stat().st_mtime
                result["uptime_seconds"] = int(time.time() - mtime)
            except OSError:
                result["daemon_running"] = False
    except Exception:
        pass

    # Sessions
    try:
        sessions = _load_sessions()
        if sessions:
            result["total_sessions"] = len(sessions)
            now_ts = time.time()
            active = 0
            for s in sessions.values():
                lmt = s.get("last_message_time") or s.get("updated_at")
                if lmt:
                    try:
                        from datetime import timezone
                        dt = datetime.fromisoformat(lmt.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            age = now_ts - dt.timestamp()
                        else:
                            age = now_ts - dt.timestamp()
                        if age < 3600:
                            active += 1
                    except Exception:
                        pass
            result["active_sessions"] = active
    except Exception:
        pass

    # Bus events
    try:
        conn = get_bus_db()
        now_ms = int(time.time() * 1000)
        hour_ago_ms = now_ms - 3600_000

        row = conn.execute("SELECT COUNT(*) FROM records").fetchone()
        result["total_bus_events"] = row[0]

        row = conn.execute("SELECT COUNT(*) FROM records WHERE timestamp > ?", (hour_ago_ms,)).fetchone()
        result["events_last_hour"] = row[0]

        row = conn.execute("SELECT MAX(timestamp) FROM records").fetchone()
        if row[0]:
            result["last_event_age_seconds"] = round((now_ms - row[0]) / 1000, 1)

        row = conn.execute("SELECT COUNT(*) FROM sdk_events").fetchone()
        result["total_sdk_events"] = row[0]

        row = conn.execute("SELECT COUNT(*) FROM sdk_events WHERE timestamp > ?", (hour_ago_ms,)).fetchone()
        result["sdk_events_last_hour"] = row[0]

        row = conn.execute("SELECT COUNT(*) FROM facts WHERE active = 1").fetchone()
        result["facts_count"] = row[0]

        conn.close()
    except Exception:
        pass

    # Reminders
    try:
        if REMINDERS_JSON.exists():
            data = json.loads(REMINDERS_JSON.read_text())
            result["active_reminders"] = len(data.get("reminders", []))
    except Exception:
        pass

    # Skills count
    try:
        import glob as globmod
        skill_files = globmod.glob(str(SKILLS_DIR / "*" / "SKILL.md"))
        result["skills_count"] = len(skill_files)
    except Exception:
        pass

    # Health status
    if result["daemon_running"] and result["last_event_age_seconds"] is not None and result["last_event_age_seconds"] < 300:
        result["health_status"] = "healthy"
    elif result["daemon_running"]:
        result["health_status"] = "degraded"
    else:
        result["health_status"] = "down"

    return result


@app.get("/api/dashboard/events")
async def dashboard_events(
    limit: int = 100,
    since_offset: Optional[int] = None,
    type: Optional[str] = None,
    source: Optional[str] = None,
    topic: Optional[str] = None,
    search: Optional[str] = None,
):
    """Bus events with filtering."""
    limit = min(limit, 500)
    try:
        conn = get_bus_db()
        now_ms = int(time.time() * 1000)

        conditions = []
        params = []

        if since_offset is not None:
            conditions.append("offset > ?")
            params.append(since_offset)
        if type:
            conditions.append("type = ?")
            params.append(type)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if topic:
            conditions.append("topic = ?")
            params.append(topic)
        if search:
            conditions.append("payload LIKE ?")
            params.append(f"%{search}%")

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        query = f"SELECT topic, partition, offset, timestamp, type, source, key, substr(payload, 1, 2000) as payload_preview FROM records {where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        events = []
        for r in rows:
            events.append({
                "topic": r["topic"],
                "partition": r["partition"],
                "offset": r["offset"],
                "timestamp": r["timestamp"],
                "type": r["type"],
                "source": r["source"],
                "key": r["key"],
                "payload_preview": r["payload_preview"],
                "age_seconds": round((now_ms - r["timestamp"]) / 1000, 1),
            })

        total_row = conn.execute("SELECT COUNT(*) FROM records").fetchone()
        max_offset_row = conn.execute("SELECT MAX(offset) FROM records").fetchone()

        conn.close()

        return {
            "events": events,
            "total_count": total_row[0],
            "max_offset": max_offset_row[0] or 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/events/stats")
async def dashboard_events_stats():
    """Event type distribution."""
    try:
        conn = get_bus_db()

        by_type = [
            {"type": r["type"], "count": r["cnt"]}
            for r in conn.execute("SELECT type, COUNT(*) as cnt FROM records GROUP BY type ORDER BY cnt DESC").fetchall()
        ]

        by_source = [
            {"source": r["source"], "count": r["cnt"]}
            for r in conn.execute("SELECT source, COUNT(*) as cnt FROM records GROUP BY source ORDER BY cnt DESC").fetchall()
        ]

        # Events by 15-min bucket (last 24h), broken down by source
        now_ms = int(time.time() * 1000)
        day_ago_ms = now_ms - 86400_000
        bucket_ms = 900_000  # 15 minutes
        by_hour = []
        rows = conn.execute(
            "SELECT (timestamp / ?) * ? as bucket_ms, source, COUNT(*) as cnt "
            "FROM records WHERE timestamp > ? GROUP BY bucket_ms, source ORDER BY bucket_ms",
            (bucket_ms, bucket_ms, day_ago_ms)
        ).fetchall()
        hour_map = {}
        all_sources = set()
        for r in rows:
            ts = datetime.fromtimestamp(r["bucket_ms"] / 1000).strftime("%Y-%m-%dT%H:%M:%S")
            src = r["source"] or "system"
            all_sources.add(src)
            if ts not in hour_map:
                hour_map[ts] = {"hour": ts, "total": 0}
            hour_map[ts][src] = r["cnt"]
            hour_map[ts]["total"] += r["cnt"]
        by_hour = list(hour_map.values())
        all_sources_list = sorted(all_sources)

        # Events by 15-min bucket, broken down by type
        type_rows = conn.execute(
            "SELECT (timestamp / ?) * ? as bucket_ms, type, COUNT(*) as cnt "
            "FROM records WHERE timestamp > ? GROUP BY bucket_ms, type ORDER BY bucket_ms",
            (bucket_ms, bucket_ms, day_ago_ms)
        ).fetchall()
        type_time_map = {}
        all_types_time = set()
        for r in type_rows:
            ts = datetime.fromtimestamp(r["bucket_ms"] / 1000).strftime("%Y-%m-%dT%H:%M:%S")
            t = r["type"] or "unknown"
            all_types_time.add(t)
            if ts not in type_time_map:
                type_time_map[ts] = {"hour": ts, "total": 0}
            type_time_map[ts][t] = r["cnt"]
            type_time_map[ts]["total"] += r["cnt"]
        by_type_time = list(type_time_map.values())
        all_types_time_list = sorted(all_types_time)

        types_list = [r["type"] for r in by_type if r["type"]]
        sources_list = [r["source"] for r in by_source if r["source"]]

        # Topics list for filter dropdown
        topics_rows = conn.execute(
            "SELECT DISTINCT topic FROM records WHERE topic IS NOT NULL AND topic != '' ORDER BY topic"
        ).fetchall()
        topics_list = [r["topic"] for r in topics_rows]

        # Chat activity by 15-min bucket, broken down by key (chat)
        chat_rows = conn.execute(
            "SELECT (timestamp / ?) * ? as bucket_ms, key, COUNT(*) as cnt "
            "FROM records WHERE timestamp > ? AND type = 'message.received' "
            "GROUP BY bucket_ms, key ORDER BY bucket_ms",
            (bucket_ms, bucket_ms, day_ago_ms)
        ).fetchall()
        chat_map = {}
        all_chats = set()
        for r in chat_rows:
            ts = datetime.fromtimestamp(r["bucket_ms"] / 1000).strftime("%Y-%m-%dT%H:%M:%S")
            # Extract contact name from key (e.g. "imessage/+16175969496" -> short form)
            chat_key = r["key"] or "unknown"
            all_chats.add(chat_key)
            if ts not in chat_map:
                chat_map[ts] = {"hour": ts, "total": 0}
            chat_map[ts][chat_key] = r["cnt"]
            chat_map[ts]["total"] += r["cnt"]
        by_chat = list(chat_map.values())
        all_chats_list = sorted(all_chats)

        # Build chat_id -> contact_name mapping from sessions registry
        registry = _load_sessions()
        chat_names = {}
        for chat_key in all_chats_list:
            # chat_key is like "imessage/+16175969496" or "discord/1234"
            parts = chat_key.split("/", 1)
            if len(parts) == 2:
                backend, chat_id = parts
                if chat_id in registry:
                    entry = registry[chat_id]
                    name = entry.get("contact_name", "")
                    # Fall back to display_name for groups
                    if not name or name == "?":
                        name = entry.get("display_name", chat_id)
                    chat_names[chat_key] = f"[{backend}] {name}"
                else:
                    chat_names[chat_key] = f"[{backend}] {chat_id}"
            else:
                chat_names[chat_key] = chat_key

        # Activity by person (sender) — 15-min buckets
        # For message.received, extract phone from payload; for message.sent, attribute to assistant
        sender_map = _build_sender_map(registry)
        person_rows = conn.execute(
            "SELECT (timestamp / ?) * ? as bucket_ms, type, json_extract(payload, '$.phone') as phone, COUNT(*) as cnt "
            "FROM records WHERE timestamp > ? AND type IN ('message.received', 'message.sent') "
            "GROUP BY bucket_ms, type, phone ORDER BY bucket_ms",
            (bucket_ms, bucket_ms, day_ago_ms)
        ).fetchall()
        person_map = {}
        all_persons = set()
        for r in person_rows:
            ts = datetime.fromtimestamp(r["bucket_ms"] / 1000).strftime("%Y-%m-%dT%H:%M:%S")
            if r["type"] == "message.sent":
                person = ASSISTANT_NAME
            else:
                raw_phone = r["phone"] or "unknown"
                person = sender_map.get(raw_phone, raw_phone)
            all_persons.add(person)
            if ts not in person_map:
                person_map[ts] = {"hour": ts, "total": 0}
            person_map[ts][person] = person_map[ts].get(person, 0) + r["cnt"]
            person_map[ts]["total"] += r["cnt"]
        by_person = list(person_map.values())
        all_persons_list = sorted(all_persons)

        conn.close()

        return {
            "by_type": by_type,
            "by_source": by_source,
            "by_hour": by_hour,
            "all_sources": all_sources_list,
            "by_type_time": by_type_time,
            "all_types_time": all_types_time_list,
            "by_chat": by_chat,
            "all_chats": all_chats_list,
            "chat_names": chat_names,
            "by_person": by_person,
            "all_persons": all_persons_list,
            "types_list": types_list,
            "sources_list": sources_list,
            "topics_list": topics_list,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/sessions")
async def dashboard_sessions():
    """All sessions with metadata."""
    try:
        sessions_data = _load_sessions()

        now_ts = time.time()
        sessions = []
        by_tier = {}

        for chat_id, s in sessions_data.items():
            tier = s.get("tier", "unknown")
            by_tier[tier] = by_tier.get(tier, 0) + 1

            lmt = s.get("last_message_time") or s.get("updated_at")
            age_seconds = None
            if lmt:
                try:
                    dt = datetime.fromisoformat(lmt.replace("Z", "+00:00"))
                    age_seconds = round(now_ts - dt.timestamp(), 1)
                except Exception:
                    pass

            sessions.append({
                "chat_id": chat_id,
                "session_name": s.get("session_name"),
                "contact_name": s.get("contact_name") or s.get("display_name", "Unknown"),
                "tier": tier,
                "type": s.get("type", "individual"),
                "source": s.get("source", "unknown"),
                "model": s.get("model", "opus"),
                "created_at": s.get("created_at"),
                "updated_at": s.get("updated_at"),
                "last_message_time": lmt,
                "age_seconds": age_seconds,
            })

        # Sort by most recent
        sessions.sort(key=lambda x: x.get("age_seconds") or 999999999)

        return {
            "sessions": sessions,
            "total": len(sessions),
            "by_tier": by_tier,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/sdk")
async def dashboard_sdk(
    limit: int = 100,
    since_id: Optional[int] = None,
    tool_name: Optional[str] = None,
    session_name: Optional[str] = None,
    is_error: Optional[int] = None,
    search: Optional[str] = None,
):
    """SDK tool call events with filtering."""
    limit = min(limit, 500)
    try:
        conn = get_bus_db()

        conditions = []
        params = []

        if since_id is not None:
            conditions.append("id > ?")
            params.append(since_id)
        if tool_name:
            conditions.append("tool_name = ?")
            params.append(tool_name)
        if session_name:
            conditions.append("session_name = ?")
            params.append(session_name)
        if is_error is not None:
            conditions.append("is_error = ?")
            params.append(is_error)
        if search:
            conditions.append("payload LIKE ?")
            params.append(f"%{search}%")

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        query = f"SELECT id, timestamp, session_name, chat_id, event_type, tool_name, duration_ms, is_error, substr(payload, 1, 2000) as payload_preview FROM sdk_events {where} ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        events = []
        for r in rows:
            events.append({
                "id": r["id"],
                "timestamp": r["timestamp"],
                "session_name": r["session_name"],
                "chat_id": r["chat_id"],
                "event_type": r["event_type"],
                "tool_name": r["tool_name"],
                "duration_ms": r["duration_ms"],
                "is_error": bool(r["is_error"]),
                "payload_preview": r["payload_preview"],
            })

        max_id_row = conn.execute("SELECT MAX(id) FROM sdk_events").fetchone()
        conn.close()

        return {
            "events": events,
            "max_id": max_id_row[0] or 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/sdk/stats")
async def dashboard_sdk_stats():
    """Tool usage analytics."""
    try:
        conn = get_bus_db()

        by_tool = []
        rows = conn.execute(
            "SELECT tool_name, COUNT(*) as cnt, AVG(duration_ms) as avg_ms, "
            "SUM(CASE WHEN is_error = 1 THEN 1 ELSE 0 END) as errors "
            "FROM sdk_events WHERE tool_name IS NOT NULL "
            "GROUP BY tool_name ORDER BY cnt DESC"
        ).fetchall()
        for r in rows:
            error_rate = round(r["errors"] / r["cnt"], 4) if r["cnt"] > 0 else 0
            by_tool.append({
                "tool": r["tool_name"],
                "count": r["cnt"],
                "avg_ms": round(r["avg_ms"] or 0, 1),
                "error_rate": error_rate,
            })

        by_session = [
            {"session": r["session_name"], "count": r["cnt"]}
            for r in conn.execute(
                "SELECT session_name, COUNT(*) as cnt FROM sdk_events "
                "GROUP BY session_name ORDER BY cnt DESC LIMIT 50"
            ).fetchall()
        ]

        now_ms = int(time.time() * 1000)
        day_ago_ms = now_ms - 86400_000
        bucket_ms = 900_000  # 15 minutes

        # SDK calls by 15-min bucket, broken down by event_type
        by_hour = []
        rows = conn.execute(
            "SELECT (timestamp / ?) * ? as bucket_ms, event_type, COUNT(*) as cnt "
            "FROM sdk_events WHERE timestamp > ? GROUP BY bucket_ms, event_type ORDER BY bucket_ms",
            (bucket_ms, bucket_ms, day_ago_ms)
        ).fetchall()
        hour_map = {}
        all_event_types = set()
        for r in rows:
            ts = datetime.fromtimestamp(r["bucket_ms"] / 1000).strftime("%Y-%m-%dT%H:%M:%S")
            et = r["event_type"] or "unknown"
            all_event_types.add(et)
            if ts not in hour_map:
                hour_map[ts] = {"hour": ts, "total": 0}
            hour_map[ts][et] = r["cnt"]
            hour_map[ts]["total"] += r["cnt"]
        by_hour = list(hour_map.values())
        all_event_types_list = sorted(all_event_types)

        total_row = conn.execute("SELECT COUNT(*) FROM sdk_events").fetchone()
        error_row = conn.execute("SELECT COUNT(*) FROM sdk_events WHERE is_error = 1").fetchone()

        conn.close()

        return {
            "by_tool": by_tool,
            "by_session": by_session,
            "by_hour": by_hour,
            "all_event_types": all_event_types_list,
            "error_count": error_row[0],
            "total": total_row[0],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/perf")
async def dashboard_perf(hours: int = 24, metric: Optional[str] = None):
    """Performance metrics from perf JSONL files."""
    hours = min(hours, 168)
    try:
        from collections import defaultdict

        now = datetime.now()
        cutoff = now.timestamp() - (hours * 3600)

        # Collect perf entries from relevant files
        entries_by_metric = defaultdict(list)
        timeseries_buckets = defaultdict(lambda: defaultdict(list))

        # Determine which files to read
        dates_to_check = set()
        for h in range(hours + 24):
            d = datetime.fromtimestamp(now.timestamp() - h * 3600)
            dates_to_check.add(d.strftime("%Y-%m-%d"))

        for date_str in sorted(dates_to_check):
            perf_file = PERF_LOG_DIR / f"perf-{date_str}.jsonl"
            if not perf_file.exists():
                continue
            try:
                with open(perf_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        ts_str = entry.get("ts", "")
                        try:
                            ts = datetime.fromisoformat(ts_str).timestamp()
                        except Exception:
                            continue
                        if ts < cutoff:
                            continue
                        m = entry.get("metric", "")
                        v = entry.get("value")
                        if v is None:
                            continue
                        if metric and m != metric:
                            continue
                        entries_by_metric[m].append(v)
                        # 5-minute bucket
                        bucket = int(ts // 300) * 300
                        timeseries_buckets[m][bucket].append(v)
            except Exception:
                continue

        def percentile(values, p):
            if not values:
                return 0
            sorted_v = sorted(values)
            idx = int(len(sorted_v) * p / 100)
            idx = min(idx, len(sorted_v) - 1)
            return round(sorted_v[idx], 2)

        metrics = {}
        for m, values in entries_by_metric.items():
            metrics[m] = {
                "p50": percentile(values, 50),
                "p95": percentile(values, 95),
                "p99": percentile(values, 99),
                "avg": round(sum(values) / len(values), 2) if values else 0,
                "count": len(values),
            }

        timeseries = []
        for m, buckets in timeseries_buckets.items():
            for bucket_ts, values in sorted(buckets.items()):
                timeseries.append({
                    "ts": datetime.fromtimestamp(bucket_ts).strftime("%Y-%m-%dT%H:%M"),
                    "metric": m,
                    "avg": round(sum(values) / len(values), 2),
                    "p95": percentile(values, 95),
                    "count": len(values),
                })

        timeseries.sort(key=lambda x: x["ts"])

        return {
            "metrics": metrics,
            "timeseries": timeseries,
            "available_metrics": sorted(entries_by_metric.keys()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/skills")
async def dashboard_skills():
    """All skills with frontmatter."""
    import glob as globmod
    import re

    skills = []
    skill_files = sorted(globmod.glob(str(SKILLS_DIR / "*" / "SKILL.md")))

    for sf in skill_files:
        sf_path = Path(sf)
        skill_dir = sf_path.parent
        skill_name = skill_dir.name

        name = skill_name
        description = ""

        # Parse YAML frontmatter
        try:
            with open(sf) as f:
                content = f.read(2000)  # Read first 2KB for frontmatter
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    frontmatter = content[3:end].strip()
                    for line in frontmatter.split("\n"):
                        line = line.strip()
                        if line.startswith("name:"):
                            name = line[5:].strip().strip("\"'")
                        elif line.startswith("description:"):
                            description = line[12:].strip().strip("\"'")
        except Exception:
            pass

        # Count scripts
        scripts_dir = skill_dir / "scripts"
        script_names = []
        if scripts_dir.is_dir():
            script_names = [f.name for f in scripts_dir.iterdir() if f.is_file() and not f.name.startswith(".")]

        # Count total files
        file_count = sum(1 for _ in skill_dir.rglob("*") if _.is_file())

        skills.append({
            "name": name,
            "description": description,
            "path": str(skill_dir).replace(str(Path.home()), "~"),
            "has_scripts": len(script_names) > 0,
            "script_count": len(script_names),
            "scripts": sorted(script_names),
            "file_count": file_count,
        })

    return {"skills": skills, "total": len(skills)}


@app.get("/api/dashboard/tasks")
async def dashboard_tasks():
    """Reminders + recent task events."""
    reminders = []
    try:
        if REMINDERS_JSON.exists():
            data = json.loads(REMINDERS_JSON.read_text())
            for r in data.get("reminders", []):
                status = "healthy"
                if r.get("last_error"):
                    status = "error"
                elif r.get("retry_count", 0) > 0:
                    status = "retrying"
                reminders.append({
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "schedule": r.get("schedule", {}).get("value", ""),
                    "timezone": r.get("schedule", {}).get("timezone", "UTC"),
                    "next_fire": r.get("next_fire"),
                    "last_fired": r.get("last_fired"),
                    "fired_count": r.get("fired_count", 0),
                    "last_error": r.get("last_error"),
                    "status": status,
                })
    except Exception:
        pass

    recent_task_events = []
    try:
        conn = get_bus_db()
        rows = conn.execute(
            "SELECT type, timestamp, key, substr(payload, 1, 500) as payload "
            "FROM records WHERE type LIKE 'task.%' ORDER BY timestamp DESC LIMIT 50"
        ).fetchall()
        for r in rows:
            payload = {}
            try:
                payload = json.loads(r["payload"]) if r["payload"] else {}
            except Exception:
                pass
            recent_task_events.append({
                "type": r["type"],
                "timestamp": r["timestamp"],
                "key": r["key"],
                "task_id": payload.get("task_id"),
                "title": payload.get("title"),
            })
        conn.close()
    except Exception:
        pass

    return {"reminders": reminders, "recent_task_events": recent_task_events}


@app.get("/api/dashboard/logs")
async def dashboard_logs(
    file: str = "manager.log",
    lines: int = 100,
    since_line: Optional[int] = None,
):
    """Tail log files (with allowlist)."""
    lines = min(lines, 500)

    # Security: validate filename
    if file not in ALLOWED_LOG_FILES:
        raise HTTPException(status_code=400, detail=f"File not in allowlist. Allowed: {sorted(ALLOWED_LOG_FILES)}")

    log_path = DISPATCH_LOGS_DIR / file
    if not log_path.exists():
        return {
            "file": file,
            "lines": [],
            "total_lines": 0,
            "returned_from_line": 0,
            "available_files": sorted(f for f in ALLOWED_LOG_FILES if (DISPATCH_LOGS_DIR / f).exists()),
        }

    try:
        # Get total line count efficiently via wc -l (avoids reading entire file)
        wc_result = subprocess.run(
            ["wc", "-l", str(log_path)],
            capture_output=True, text=True, timeout=5,
        )
        total = int(wc_result.stdout.strip().split()[0]) if wc_result.returncode == 0 else 0

        if since_line is not None and since_line > 0:
            # Cursor-based tailing: return lines after since_line
            tail_result = subprocess.run(
                ["tail", "-n", f"+{since_line + 1}", str(log_path)],
                capture_output=True, text=True, timeout=10, errors="replace",
            )
            all_tail_lines = tail_result.stdout.splitlines() if tail_result.returncode == 0 else []
            result_lines = all_tail_lines[:lines]
            returned_from = since_line
        else:
            # Return last N lines via tail (never reads entire file into memory)
            tail_result = subprocess.run(
                ["tail", "-n", str(lines), str(log_path)],
                capture_output=True, text=True, timeout=10, errors="replace",
            )
            result_lines = tail_result.stdout.splitlines() if tail_result.returncode == 0 else []
            returned_from = max(0, total - len(result_lines))

        return {
            "file": file,
            "lines": result_lines,
            "total_lines": total,
            "returned_from_line": returned_from,
            "available_files": sorted(f for f in ALLOWED_LOG_FILES if (DISPATCH_LOGS_DIR / f).exists()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/client-logs")
async def client_logs(request: Request):
    """Receive client-side logs from the iOS/web app.

    Body: { "logs": [{"level": "error", "message": "...", "timestamp": "..."}] }
    """
    try:
        body = await request.json()
        logs = body.get("logs", [])
        if not logs:
            return {"status": "ok", "received": 0}

        # Ensure logs dir exists
        CLIENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(CLIENT_LOG_PATH, "a") as f:
            for entry in logs:
                level = entry.get("level", "info").upper()
                msg = entry.get("message", "")
                ts = entry.get("timestamp", datetime.now().isoformat())
                device = entry.get("device", "unknown")
                f.write(f"[{ts}] [{level}] [{device}] {msg}\n")

        logger.info(f"POST /api/client-logs: received {len(logs)} entries")
        return {"status": "ok", "received": len(logs)}
    except Exception as e:
        logger.error(f"POST /api/client-logs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/facts")
async def dashboard_facts():
    """Structured contact facts."""
    try:
        conn = get_bus_db()
        rows = conn.execute(
            "SELECT id, contact, fact_type, summary, details, confidence, "
            "starts_at, ends_at, active, created_at, updated_at, source "
            "FROM facts ORDER BY created_at DESC"
        ).fetchall()

        facts = []
        for r in rows:
            facts.append({
                "id": r["id"],
                "contact": r["contact"],
                "fact_type": r["fact_type"],
                "summary": r["summary"],
                "details": r["details"],
                "confidence": r["confidence"],
                "starts_at": r["starts_at"],
                "ends_at": r["ends_at"],
                "active": bool(r["active"]),
                "created_at": r["created_at"],
                "source": r["source"],
            })

        conn.close()
        return {"facts": facts, "total": len(facts)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────
# Agents API endpoints
# ─────────────────────────────────────────────────────────────

def _load_sessions() -> dict:
    """Load session registry from sessions.json. Returns chat_id -> session dict."""
    if SESSIONS_JSON.exists():
        try:
            return json.loads(SESSIONS_JSON.read_text())
        except Exception:
            return {}
    return {}


def _get_messages_db():
    """Get a connection to dispatch-messages.db (read-write)."""
    init_db()
    return sqlite3.connect(DB_PATH)


def _ipc_command(cmd: dict, timeout: float = 30) -> dict:
    """Send a command to the daemon via Unix socket IPC.

    Returns the JSON response dict. Raises HTTPException on failure.
    """
    if not IPC_SOCKET.exists():
        raise HTTPException(status_code=503, detail="Daemon unavailable (IPC socket not found)")

    try:
        s = sock_module.socket(sock_module.AF_UNIX, sock_module.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(str(IPC_SOCKET))
        s.sendall((json.dumps(cmd) + "\n").encode())

        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        s.close()

        return json.loads(data.decode().strip())
    except ConnectionRefusedError:
        raise HTTPException(status_code=503, detail="Daemon not responding")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"IPC error: {e}")


def _check_is_thinking(session_name: str) -> bool:
    """Check if a session is actively thinking via the session_states table.

    The daemon writes is_busy=1 when a query starts and is_busy=0 when it
    completes (ResultMessage). This is more reliable than the old 30-second
    sdk_events window which had false negatives during long operations.
    """
    if not session_name:
        return False
    try:
        conn = get_bus_db()
        # Try multiple session_name formats — the daemon writes with
        # {source}/{chat_id} but chat_id may or may not include the registry prefix.
        # Generate all plausible variants for the lookup.
        names_to_try = [session_name]
        if session_name.startswith(f"{APP_SESSION_PREFIX}/"):
            chat_id_part = session_name[len(f"{APP_SESSION_PREFIX}/"):]
            # If chat_id_part has prefix like "dispatch-app:UUID", also try bare "UUID"
            if ":" in chat_id_part:
                bare_uuid = chat_id_part.split(":", 1)[1]
                names_to_try.append(f"{APP_SESSION_PREFIX}/{bare_uuid}")
            else:
                # If bare UUID, also try with prefix
                names_to_try.append(f"{APP_SESSION_PREFIX}/{APP_SESSION_PREFIX}:{chat_id_part}")
            # Legacy sven-app format
            names_to_try.append(f"sven-app/sven-app:{chat_id_part}")
        placeholders = ",".join("?" * len(names_to_try))
        row = conn.execute(
            f"SELECT is_busy, updated_at FROM session_states WHERE session_name IN ({placeholders}) ORDER BY updated_at DESC LIMIT 1",
            names_to_try,
        ).fetchone()
        conn.close()
        if row is None:
            return False
        is_busy, updated_at = row["is_busy"], row["updated_at"]
        # Staleness guard: if the daemon hasn't updated in 10 minutes,
        # assume it crashed or the session ended without clearing the flag.
        # Sessions can legitimately be busy for 10+ minutes during long
        # subagent calls, so this needs to be generous.
        now_ms = int(time.time() * 1000)
        if now_ms - updated_at > 600_000:
            return False
        return bool(is_busy)
    except Exception:
        return False


def _extract_text_from_record(payload_str: str, source: str, type_: str) -> str | None:
    """Extract human-readable text from a bus.db record payload.

    Handles three cases:
    - message.received: text directly in payload
    - message.sent from imessage/signal: text directly in payload
    - message.sent from sdk_session: text in heredoc or quoted arg of command
    """
    payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str

    if type_ == "message.received":
        return payload.get("text")

    if type_ == "message.sent" and source == "imessage":
        return payload.get("text")

    if type_ == "message.sent" and source in ("sdk_session", "signal"):
        if source == "signal":
            return payload.get("text")
        command = payload.get("command", "")
        # Try heredoc with any delimiter (ENDMSG, EOF, etc.)
        match = re.search(r"<<'(\w+)'\n(.*?)\n\1", command, re.DOTALL)
        if match:
            return match.group(2)
        # Fallback: single-quoted argument (reply 'message text')
        match = re.search(r"(?:reply|send-sms|send-signal)\s+'(.*)'$", command, re.DOTALL)
        if match and len(match.group(1)) > 0:
            return match.group(1)
        # Fallback: last double-quoted argument
        match = re.search(r'"([^"]*)"$', command)
        if match and len(match.group(1)) > 0:
            return match.group(1)
        return "[message sent]"

    return None


def _build_sender_map(registry: dict) -> dict:
    """Build phone/UUID -> contact name lookup dict from session registry.

    Used to resolve sender names in group chat messages. For individual sessions,
    chat_id IS the phone number, so we map it to the contact name.
    """
    sender_map = {}
    for chat_id, session in registry.items():
        name = session.get("contact_name", chat_id)
        sender_map[chat_id] = name
    return sender_map


def _resolve_sender(payload: dict, type_: str, sender_map: dict) -> str:
    """Resolve sender name for a bus.db message record."""
    if type_ == "message.sent":
        return ASSISTANT_NAME.lower()
    phone = payload.get("phone") or payload.get("sender_phone", "")
    return sender_map.get(phone, phone)


def _iso_from_ts(ts_ms: int | float) -> str:
    """Convert epoch milliseconds to ISO 8601 string."""
    return datetime.fromtimestamp(ts_ms / 1000).isoformat()


def _slugify(name: str) -> str:
    """Convert a session name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "session"


# --- Pydantic models for agent endpoints ---

class CreateAgentRequest(BaseModel):
    name: str


class SendAgentMessageRequest(BaseModel):
    session_id: str
    text: str
    message_id: Optional[str] = None  # Client-generated idempotency key to prevent duplicates


class RenameAgentRequest(BaseModel):
    name: str


# --- Agent endpoints ---

@app.get("/agents", response_class=HTMLResponse)
async def agents_page():
    """Serve the agents command center HTML page."""
    html_path = Path(__file__).parent / "agents.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Agents page not found")
    return HTMLResponse(content=html_path.read_text())


@app.get("/api/agents/sessions")
async def agents_sessions():
    """List all sessions — contact sessions from sessions.json + agent sessions from dispatch-messages.db.

    Merges both session types, attaches last message info, and sorts by recency.
    """
    try:
        sessions = []
        registry = _load_sessions()

        # --- Contact sessions: get last message per chat_id from bus.db ---
        last_messages = {}
        try:
            conn = get_bus_db()
            cursor = conn.execute("""
                SELECT chat_id, payload, timestamp, type, source FROM (
                    SELECT json_extract(payload, '$.chat_id') as chat_id,
                           payload, timestamp, type, source,
                           ROW_NUMBER() OVER (
                               PARTITION BY json_extract(payload, '$.chat_id')
                               ORDER BY timestamp DESC
                           ) as rn
                    FROM records
                    WHERE topic = 'messages'
                      AND type IN ('message.received', 'message.sent', 'message.admin_inject')
                      AND source NOT IN ('consumer-retry', 'sdk_backend.replay')
                ) sub WHERE rn = 1
            """)
            for row in cursor.fetchall():
                last_messages[row[0]] = row
            conn.close()
        except Exception as e:
            logger.warning(f"agents_sessions: failed to query bus.db: {e}")

        # --- iMessage group display names from chat.db ---
        imessage_group_names: dict[str, str] = {}
        try:
            chat_db_path = Path.home() / "Library" / "Messages" / "chat.db"
            if chat_db_path.exists():
                import sqlite3 as _sqlite3
                chat_conn = _sqlite3.connect(f"file:{chat_db_path}?mode=ro", uri=True)
                for row in chat_conn.execute(
                    "SELECT guid, display_name FROM chat WHERE display_name IS NOT NULL AND display_name != ''"
                ).fetchall():
                    # guid format: "any;+;{hex_chat_id}"
                    parts = row[0].split(";")
                    if len(parts) >= 3:
                        imessage_group_names[parts[-1]] = row[1]
                chat_conn.close()
        except Exception as e:
            logger.warning(f"agents_sessions: failed to query chat.db for group names: {e}")

        # --- Signal group names via JSON-RPC socket ---
        signal_group_names: dict[str, str] = {}
        try:
            import socket as _socket
            sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            sock.connect("/tmp/signal-cli.sock")
            sock.settimeout(5)
            req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "listGroups"}) + "\n"
            sock.sendall(req.encode())
            data = b""
            while True:
                try:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break
                except _socket.timeout:
                    break
            sock.close()
            result = json.loads(data.decode().strip())
            for g in result.get("result", []):
                gid = g.get("id", "")
                gname = g.get("name", "")
                if gid and gname:
                    signal_group_names[gid] = gname
        except Exception as e:
            logger.warning(f"agents_sessions: failed to load signal group names: {e}")

        # Build contact sessions from registry
        # Track seen chat_ids to deduplicate prefixed variants (e.g. "signal:xxx" vs "xxx")
        seen_chat_ids: set[str] = set()

        for chat_id, session_info in registry.items():
            if chat_id.startswith("dispatch-api:"):
                continue  # dispatch-api sessions come from dispatch-messages.db
            if chat_id.startswith("dispatch-app:") or chat_id.startswith("sven-app:"):
                continue  # dispatch-app sessions come from dispatch-messages.db below

            # Deduplicate: strip source prefix to get canonical id
            canonical_id = chat_id
            for prefix in ("signal:", "imessage:", "discord:"):
                if chat_id.startswith(prefix):
                    canonical_id = chat_id[len(prefix):]
                    break
            if canonical_id in seen_chat_ids:
                continue  # already have this session from its unprefixed entry
            seen_chat_ids.add(canonical_id)

            last = last_messages.get(chat_id)
            last_text = None
            last_time = None
            last_is_from_me = False

            if last:
                try:
                    last_text = _extract_text_from_record(last[1], last[4], last[3])
                except Exception:
                    last_text = None
                last_time = _iso_from_ts(last[2])
                last_is_from_me = last[3] == "message.sent"
            else:
                last_time = session_info.get("last_message_time")

            # Resolve display name: contact_name > display_name > group display name > participant list > chat_id
            display_name = session_info.get("contact_name") or session_info.get("display_name") or ""
            if not display_name and session_info.get("type") == "group":
                source = session_info.get("source", "")
                # Try platform-specific group name first (try both raw chat_id and canonical_id)
                if source == "imessage":
                    display_name = imessage_group_names.get(chat_id, "") or imessage_group_names.get(canonical_id, "")
                elif source == "signal":
                    display_name = signal_group_names.get(chat_id, "") or signal_group_names.get(canonical_id, "")
                # Fall back to participant list
                if not display_name:
                    participants = session_info.get("participants") or []
                    names = [p for p in participants if not p.startswith("+") and "@" not in p]
                    if names:
                        if len(names) <= 3:
                            display_name = ", ".join(names)
                        else:
                            display_name = ", ".join(names[:2]) + f" +{len(names)-2}"
            if not display_name:
                display_name = chat_id

            # Deduplicate signal groups that appear under different chat_ids
            # (e.g. phone-based "signal:+207..." and base64 group ID for same group)
            if session_info.get("source") == "signal" and session_info.get("type") == "group":
                name_key = f"signal_group:{display_name}"
                if name_key in seen_chat_ids:
                    continue
                seen_chat_ids.add(name_key)

            sessions.append({
                "id": chat_id,
                "type": "contact",
                "name": display_name,
                "tier": session_info.get("tier", "unknown"),
                "source": session_info.get("source", "unknown"),
                "chat_type": session_info.get("type", "individual"),
                "participants": session_info.get("participants"),
                "last_message": last_text,
                "last_message_time": last_time,
                "last_message_is_from_me": last_is_from_me,
                "status": "active" if session_info.get("was_active") else "idle",
            })

        # --- Agent / dispatch-app sessions from dispatch-messages.db ---
        # Fetch ALL chats (not just dispatch-api: prefixed) so dispatch-app
        # chats with plain UUID ids also get their title from the DB instead
        # of showing "Unknown (uuid)" from the sessions registry.
        try:
            msg_db = _get_messages_db()
            agent_cursor = msg_db.execute("""
                SELECT c.id, c.title, c.updated_at,
                       m.content, m.role, m.created_at
                FROM chats c
                LEFT JOIN (
                    SELECT chat_id, content, role, created_at,
                           ROW_NUMBER() OVER (PARTITION BY chat_id ORDER BY created_at DESC) as rn
                    FROM messages
                ) m ON m.chat_id = c.id AND m.rn = 1
                ORDER BY COALESCE(m.created_at, c.updated_at) DESC
            """)
            for row in agent_cursor.fetchall():
                agent_chat_id = row[0]
                # Check registry under multiple key formats
                reg_entry = (
                    registry.get(agent_chat_id, {})
                    or registry.get(f"dispatch-app:{agent_chat_id}", {})
                    or registry.get(f"sven-app:{agent_chat_id}", {})
                )
                is_active = reg_entry.get("was_active", False)
                sessions.append({
                    "id": agent_chat_id,
                    "type": "dispatch-api",
                    "name": row[1],  # chat title from DB
                    "tier": "admin",
                    "source": "dispatch-api",
                    "chat_type": "dispatch-api",
                    "participants": None,
                    "last_message": row[3],
                    "last_message_time": row[5] or row[2],
                    "last_message_is_from_me": row[4] == "user" if row[4] else False,
                    "status": "active" if is_active else "idle",
                })
            msg_db.close()
        except Exception as e:
            logger.warning(f"agents_sessions: failed to query dispatch-messages.db: {e}")

        # Sort all sessions by last_message_time descending (most recent first)
        sessions.sort(key=lambda s: s["last_message_time"] or "", reverse=True)

        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agents/sdk-events")
async def agents_sdk_events(
    session_id: str,
    limit: int = 100,
    since_id: Optional[int] = None,
    since_ts: Optional[int] = None,
):
    """Get SDK events (tool calls, thinking, errors) for a session."""
    limit = min(limit, 500)
    try:
        # Map session_id to session_name for sdk_events lookup
        # Try registry first (most reliable), then construct from prefix
        registry = _load_sessions()
        session_info = registry.get(session_id, {})
        # Also try with sven-app: prefix for backward compat (frontend sends dispatch-app: but registry may have sven-app:)
        if not session_info and session_id.startswith(f"{APP_SESSION_PREFIX}:"):
            legacy_id = "sven-app:" + session_id.split(":", 1)[1]
            session_info = registry.get(legacy_id, {})
        session_name = session_info.get("session_name")

        if not session_name:
            if session_id.startswith("dispatch-api:") or session_id.startswith(f"{APP_SESSION_PREFIX}:"):
                chat_id_part = session_id.split(":", 1)[1] if ":" in session_id else session_id
                session_name = f"{APP_SESSION_PREFIX}/{chat_id_part}"
            else:
                session_name = session_id

        conn = get_bus_db()

        # Query with the session_name, but also try legacy double-nested format
        # (old bug stored "sven-app/sven-app:chat_id" instead of "sven-app/chat_id")
        conditions = ["(session_name = ? OR session_name = ?)"]
        legacy_session_name = session_name.replace(f"{APP_SESSION_PREFIX}/", "sven-app/sven-app:") if session_name.startswith(f"{APP_SESSION_PREFIX}/") else f"sven-app/{session_id}"
        params = [session_name, legacy_session_name]

        if since_id is not None:
            conditions.append("id > ?")
            params.append(since_id)

        if since_ts is not None:
            conditions.append("timestamp > ?")
            params.append(since_ts)

        where = "WHERE " + " AND ".join(conditions)
        query = f"SELECT id, timestamp, session_name, chat_id, event_type, tool_name, tool_use_id, duration_ms, is_error, payload, num_turns FROM sdk_events {where} ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        conn.close()

        events = []
        for r in rows:
            events.append({
                "id": r["id"],
                "timestamp": r["timestamp"],
                "session_name": r["session_name"],
                "chat_id": r["chat_id"],
                "event_type": r["event_type"],
                "tool_name": r["tool_name"],
                "tool_use_id": r["tool_use_id"],
                "duration_ms": r["duration_ms"],
                "is_error": bool(r["is_error"]),
                "payload": r["payload"],
                "num_turns": r["num_turns"],
            })

        return {"events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agents/messages")
async def agents_messages(
    session_id: str,
    limit: int = 100,
    before_ts: Optional[int] = None,
    after_ts: Optional[int] = None,
):
    """Get messages for a session.

    Dual data source:
    - Contact sessions (no 'dispatch-api:' prefix): read from bus.db
    - Dispatch-API sessions ('dispatch-api:' prefix): read from dispatch-messages.db

    Supports cursor-based pagination via before_ts (historical load)
    and after_ts (polling for new messages).
    """
    limit = min(limit, 500)

    try:
        if session_id.startswith("dispatch-api:"):
            # --- Agent session: read from dispatch-messages.db ---
            msg_db = _get_messages_db()

            if after_ts is not None:
                # Polling for new messages
                after_dt = datetime.fromtimestamp(after_ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
                cursor = msg_db.execute(
                    "SELECT id, role, content, audio_path, created_at "
                    "FROM messages WHERE chat_id = ? AND created_at > ? "
                    "ORDER BY created_at ASC LIMIT 50",
                    (session_id, after_dt),
                )
            elif before_ts is not None:
                # Historical load (scrolling up)
                before_dt = datetime.fromtimestamp(before_ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
                cursor = msg_db.execute(
                    "SELECT id, role, content, audio_path, created_at "
                    "FROM messages WHERE chat_id = ? AND created_at < ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (session_id, before_dt, limit),
                )
            else:
                # Initial load (most recent messages)
                cursor = msg_db.execute(
                    "SELECT id, role, content, audio_path, created_at "
                    "FROM messages WHERE chat_id = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (session_id, limit),
                )

            rows = cursor.fetchall()
            msg_db.close()

            messages = []
            for row in rows:
                msg_id, role, content, audio_path, created_at = row
                # Convert ISO datetime to epoch ms
                try:
                    ts_ms = int(datetime.fromisoformat(created_at).timestamp() * 1000)
                except Exception:
                    ts_ms = 0
                messages.append({
                    "id": msg_id,
                    "role": role,
                    "text": content,
                    "sender": "you" if role == "user" else ASSISTANT_NAME.lower(),
                    "is_from_me": role == "user",
                    "timestamp_ms": ts_ms,
                    "source": "dispatch-api",
                    "has_attachment": bool(audio_path),
                })

            # Check if there are more messages beyond this page
            has_more = len(rows) >= limit if before_ts is None and after_ts is None else len(rows) >= limit

            # Check thinking status from sdk_events
            # session_id is "dispatch-app:voice" -> extract "voice" for session_name lookup
            session_chat_id = session_id.split(":", 1)[1] if ":" in session_id else session_id
            is_thinking = _check_is_thinking(f"{APP_SESSION_PREFIX}/{session_chat_id}")

            return {"messages": messages, "has_more": has_more, "is_thinking": is_thinking}

        else:
            # --- Contact session: read from bus.db ---
            registry = _load_sessions()
            sender_map = _build_sender_map(registry)

            conn = get_bus_db()

            if after_ts is not None:
                # Polling for new messages
                cursor = conn.execute(
                    'SELECT "offset", type, source, payload, timestamp '
                    "FROM records "
                    "WHERE topic = 'messages' "
                    "  AND json_extract(payload, '$.chat_id') = ? "
                    "  AND type IN ('message.received', 'message.sent', 'message.admin_inject') "
                    "  AND source NOT IN ('consumer-retry', 'sdk_backend.replay') "
                    "  AND timestamp > ? "
                    "ORDER BY timestamp ASC LIMIT 50",
                    (session_id, after_ts),
                )
            elif before_ts is not None:
                # Historical load (scrolling up)
                cursor = conn.execute(
                    'SELECT "offset", type, source, payload, timestamp '
                    "FROM records "
                    "WHERE topic = 'messages' "
                    "  AND json_extract(payload, '$.chat_id') = ? "
                    "  AND type IN ('message.received', 'message.sent', 'message.admin_inject') "
                    "  AND source NOT IN ('consumer-retry', 'sdk_backend.replay') "
                    "  AND timestamp < ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (session_id, before_ts, limit),
                )
            else:
                # Initial load (most recent messages)
                cursor = conn.execute(
                    'SELECT "offset", type, source, payload, timestamp '
                    "FROM records "
                    "WHERE topic = 'messages' "
                    "  AND json_extract(payload, '$.chat_id') = ? "
                    "  AND type IN ('message.received', 'message.sent', 'message.admin_inject') "
                    "  AND source NOT IN ('consumer-retry', 'sdk_backend.replay') "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (session_id, limit),
                )

            rows = cursor.fetchall()
            conn.close()

            messages = []
            for row in rows:
                offset, type_, source, payload_str, timestamp = row
                try:
                    payload = json.loads(payload_str)
                except Exception:
                    payload = {}

                if type_ == "message.admin_inject":
                    text = payload.get("text", "")
                    sender = "admin"
                else:
                    text = _extract_text_from_record(payload_str, source, type_)
                    sender = _resolve_sender(payload, type_, sender_map)

                messages.append({
                    "id": str(offset),
                    "role": "admin" if type_ == "message.admin_inject" else ("assistant" if type_ == "message.sent" else "user"),
                    "text": text,
                    "sender": sender,
                    "is_from_me": type_ == "message.sent" or type_ == "message.admin_inject",
                    "timestamp_ms": timestamp,
                    "source": source,
                    "has_attachment": bool(payload.get("image_path") or payload.get("attachment")),
                    "is_admin": type_ == "message.admin_inject",
                })

            has_more = len(rows) >= limit if before_ts is None and after_ts is None else len(rows) >= limit

            # Check thinking status from sdk_events
            session_info = registry.get(session_id, {})
            session_name = session_info.get("session_name", "")
            is_thinking = _check_is_thinking(session_name) if session_name else False

            return {"messages": messages, "has_more": has_more, "is_thinking": is_thinking}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/sessions")
async def create_agent_session(request: CreateAgentRequest):
    """Create a new agent session.

    1. Validate name (required, max 50 chars)
    2. Slugify name and generate chat_id (dispatch-api:<slug>)
    3. Deduplicate slug if conflict exists
    4. Create chat entry in dispatch-messages.db
    5. Inject initial prompt via daemon IPC (lazy session creation)
    """
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if len(name) > 50:
        raise HTTPException(status_code=400, detail="Name must be 50 characters or less")

    # Slugify and generate chat_id
    slug = _slugify(name)
    chat_id = f"dispatch-api:{slug}"

    # Check for slug conflicts and deduplicate
    msg_db = _get_messages_db()
    existing = msg_db.execute("SELECT id FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if existing:
        suffix = 2
        while True:
            candidate = f"dispatch-api:{slug}-{suffix}"
            if not msg_db.execute("SELECT id FROM chats WHERE id = ?", (candidate,)).fetchone():
                chat_id = candidate
                break
            suffix += 1

    # Create chat entry
    msg_db.execute(
        "INSERT INTO chats (id, title) VALUES (?, ?)",
        (chat_id, name),
    )
    msg_db.commit()
    msg_db.close()

    # Inject initial prompt via IPC to spawn the SDK session
    try:
        result = _ipc_command({
            "cmd": "inject",
            "chat_id": chat_id,
            "prompt": "Session started. Ready for tasks.",
            "admin": True,
            "source": "dispatch-api",
        })
        if not result.get("ok"):
            logger.error(f"create_agent_session: IPC inject failed: {result.get('error')}")
            # Session was created in DB but IPC failed — still return success
            # so the UI can show the session. It will become active on next inject.
    except HTTPException:
        # IPC unavailable — session created in DB, will be activated on first message
        logger.warning(f"create_agent_session: daemon unavailable, session {chat_id} created in DB only")

    return {"id": chat_id, "name": name, "status": "active"}


@app.post("/api/agents/messages")
async def send_agent_message(request: SendAgentMessageRequest):
    """Send a message to any session (agent or contact).

    For agent sessions: stores user message in dispatch-messages.db, then injects via IPC.
    For contact sessions: injects via IPC only (message appears in bus.db when session responds).
    """
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    session_id = request.session_id

    if session_id.startswith("dispatch-api:"):
        # --- Agent session: store user message + inject ---
        message_id = request.message_id or str(uuid.uuid4())
        msg_db = _get_messages_db()

        # Verify chat exists
        chat = msg_db.execute("SELECT id FROM chats WHERE id = ?", (session_id,)).fetchone()
        if not chat:
            msg_db.close()
            raise HTTPException(status_code=404, detail="Session not found")

        # Deduplicate: if client-provided message_id already exists, return success
        if request.message_id:
            existing = msg_db.execute(
                "SELECT id FROM messages WHERE id = ?", (request.message_id,)
            ).fetchone()
            if existing:
                msg_db.close()
                logger.info(f"send_agent_message: duplicate message_id={message_id[:8]}... — returning existing (idempotent)")
                return {"ok": True, "message_id": message_id}

        # Store user message
        msg_db.execute(
            "INSERT INTO messages (id, role, content, chat_id) VALUES (?, 'user', ?, ?)",
            (message_id, text, session_id),
        )
        msg_db.execute(
            "UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        msg_db.commit()
        msg_db.close()

        # Inject into SDK session via IPC
        result = _ipc_command({
            "cmd": "inject",
            "chat_id": session_id,
            "prompt": text,
            "admin": True,
            "source": "dispatch-api",
        })
        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error", "Injection failed"))

        return {"ok": True, "message_id": message_id}

    else:
        # --- Contact session: messaging disabled from agents tab ---
        raise HTTPException(status_code=403, detail="Messaging contact sessions from agents tab is disabled")


@app.patch("/api/agents/sessions/{session_id:path}")
async def rename_agent_session(session_id: str, request: RenameAgentRequest):
    """Rename an agent session. Only works for dispatch-api sessions (dispatch-api: prefix)."""
    if not session_id.startswith("dispatch-api:"):
        raise HTTPException(status_code=400, detail="Only dispatch-api sessions can be renamed")

    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if len(name) > 50:
        raise HTTPException(status_code=400, detail="Name must be 50 characters or less")

    msg_db = _get_messages_db()
    row = msg_db.execute("SELECT id FROM chats WHERE id = ?", (session_id,)).fetchone()
    if not row:
        msg_db.close()
        raise HTTPException(status_code=404, detail="Session not found")

    msg_db.execute(
        "UPDATE chats SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (name, session_id),
    )
    msg_db.commit()
    msg_db.close()

    return {"ok": True, "id": session_id, "name": name}


@app.delete("/api/agents/sessions/{session_id:path}")
async def delete_agent_session(session_id: str, delete_messages: bool = False):
    """Kill and optionally delete an agent session.

    1. Kill SDK session via daemon IPC
    2. If delete_messages=true: remove messages, chat entry, and transcript dir
    3. Otherwise: keep data for historical reference
    """
    if not session_id.startswith("dispatch-api:"):
        raise HTTPException(status_code=400, detail="Only dispatch-api sessions can be deleted")

    # Kill the SDK session via IPC (best-effort)
    try:
        _ipc_command({"cmd": "kill_session", "chat_id": session_id})
    except HTTPException:
        # Daemon may be down — continue with cleanup
        logger.warning(f"delete_agent_session: daemon unavailable for kill_session {session_id}")

    if delete_messages:
        # Delete messages and chat entry from dispatch-messages.db
        msg_db = _get_messages_db()
        msg_db.execute("DELETE FROM messages WHERE chat_id = ?", (session_id,))
        msg_db.execute("DELETE FROM chats WHERE id = ?", (session_id,))
        msg_db.commit()
        msg_db.close()

        # Remove transcript directory
        slug = session_id.removeprefix("dispatch-api:")
        transcript_dir = Path.home() / "transcripts" / "dispatch-api" / slug
        if transcript_dir.exists():
            import shutil
            try:
                shutil.rmtree(transcript_dir)
            except Exception as e:
                logger.warning(f"delete_agent_session: failed to remove transcript dir: {e}")

    return {"ok": True}


# ---------------------------------------------------------------------------
# Serve dispatch-app web build at /app (static files)
# ---------------------------------------------------------------------------

DISPATCH_APP_DIST = Path(__file__).parent.parent.parent / "apps" / "dispatch-app" / "dist"

if DISPATCH_APP_DIST.is_dir():
    from starlette.staticfiles import StaticFiles
    from starlette.responses import FileResponse as StarletteFileResponse

    @app.get("/app")
    async def app_index():
        """Serve dispatch-app index.html for root route"""
        return StarletteFileResponse(DISPATCH_APP_DIST / "index.html")

    @app.get("/app/{path:path}")
    async def app_catchall(path: str):
        """Catch-all for client-side routing — serve index.html for all /app/* routes"""
        # Try to serve a static file first (e.g. favicon.ico)
        static_path = DISPATCH_APP_DIST / path
        if static_path.is_file():
            return StarletteFileResponse(static_path)
        # Otherwise serve index.html for client-side routing
        return StarletteFileResponse(DISPATCH_APP_DIST / "index.html")

    # Mount _expo static assets under /app/_expo (Expo baseUrl="/app")
    app.mount("/app/_expo", StaticFiles(directory=str(DISPATCH_APP_DIST / "_expo")), name="dispatch-app-expo")

    # Mount other static assets
    if (DISPATCH_APP_DIST / "assets").is_dir():
        app.mount("/app/assets", StaticFiles(directory=str(DISPATCH_APP_DIST / "assets")), name="dispatch-app-assets")

    logger.info(f"Serving dispatch-app from {DISPATCH_APP_DIST}")
else:
    logger.info(f"dispatch-app dist not found at {DISPATCH_APP_DIST} — skipping static mount")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Starting Dispatch API server...")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info(f"Allowed tokens file: {ALLOWED_TOKENS_FILE}")
    logger.info(f"Database: {DB_PATH}")
    logger.info(f"Audio directory: {AUDIO_DIR}")
    logger.info("Listening on http://0.0.0.0:9091")
    logger.info("Tailscale IP: 100.127.42.15:9091")
    logger.info("=" * 60)

    # Initialize database on startup
    init_db()

    # Configure uvicorn with socket reuse to prevent "address already in use" crashes
    # when the daemon restarts and the old process hasn't fully released the port.
    # Uses uvicorn internal (config.loaded) — tested with uvicorn 0.32+.
    # Falls back to plain uvicorn.run() if the internal API has changed.
    config = uvicorn.Config(app, host="0.0.0.0", port=9091, log_level="warning")

    if hasattr(config, "loaded"):
        server = uvicorn.Server(config)

        # Enable SO_REUSEADDR on the socket before binding
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", 9091))
        sock.listen(128)
        sock.set_inheritable(True)

        # Pass pre-bound socket to uvicorn
        config.load()  # Initialize lifespan_class and other internals
        server.servers = []  # Will be populated by serve()

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve(sockets=[sock]))
    else:
        # Fallback: uvicorn manages its own socket (no SO_REUSEADDR guarantee)
        logger.warning("uvicorn missing config.loaded — falling back to plain uvicorn.run()")
        uvicorn.run(app, host="0.0.0.0", port=9091, log_level="warning")
