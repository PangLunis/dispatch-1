#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastapi",
#     "uvicorn",
#     "pydantic",
#     "python-multipart",
# ]
# ///
"""
Sven API Server - receives voice transcripts from iOS app via Tailscale
and provides in-app responses with TTS audio.

Run with: uv run server.py
Or: ./server.py (if executable)

Listens on: http://0.0.0.0:9091

Endpoints:
- POST /prompt - Receive transcript, inject into sven-app session
- GET /messages - Poll for new messages
- GET /audio/{message_id} - Download TTS audio file
"""

import json
import logging
import os
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn


def log_perf(metric: str, value: float, **labels) -> None:
    """Log a perf metric to the shared JSONL file."""
    try:
        perf_dir = Path.home() / "dispatch" / "logs"
        perf_dir.mkdir(parents=True, exist_ok=True)
        path = perf_dir / f"perf-{datetime.now():%Y-%m-%d}.jsonl"
        entry = {"v": 1, "ts": datetime.now().isoformat(), "metric": metric, "value": value, "component": "sven-api", **labels}
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never fail on perf logging

# Configure logging
LOG_DIR = Path.home() / "dispatch" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "sven-api.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("sven-api")

app = FastAPI(title="Sven API", description="Voice assistant backend for Sven iOS app")

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
APNS_TOKENS_FILE = Path.home() / "dispatch" / "state" / "sven-apns-tokens.json"
DB_PATH = Path.home() / "dispatch" / "state" / "sven-messages.db"
AUDIO_DIR = Path.home() / "dispatch" / "state" / "sven-audio"
IMAGE_DIR = Path.home() / "dispatch" / "state" / "sven-images"
CLAUDE_ASSISTANT_CLI = str(Path.home() / "dispatch" / "bin" / "claude-assistant")
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 30  # requests per window

# In-memory rate limiting (reset on restart)
request_counts: dict[str, list[float]] = {}


class PromptRequest(BaseModel):
    """Request from Sven iOS app"""
    transcript: str
    token: str
    chat_id: str = "voice"
    attestation: Optional[str] = None
    assertion: Optional[str] = None


class APNsRegisterRequest(BaseModel):
    """Request to register APNs device token"""
    device_token: str
    apns_token: str


class CreateChatRequest(BaseModel):
    token: str
    title: str = None


class UpdateChatRequest(BaseModel):
    token: str
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
    """Initialize the SQLite database if it doesn't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
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
    # Ensure default "voice" chat exists
    conn.execute("INSERT OR IGNORE INTO chats (id, title) VALUES ('voice', 'General')")
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
    """Get a database connection."""
    init_db()
    return sqlite3.connect(DB_PATH)


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


async def inject_prompt_to_sven_session(transcript: str, chat_id: str = "voice", image_path: str | None = None) -> bool:
    """Inject the transcript into the dedicated sven-app session.

    Uses async subprocess to avoid blocking the FastAPI event loop.
    """
    import asyncio

    try:
        logger.info(f"inject_prompt: calling inject-prompt CLI...")
        # Use inject-prompt to send to the sven-app session
        # The session will respond via reply-sven CLI which stores in message bus
        cmd = [
            CLAUDE_ASSISTANT_CLI, "inject-prompt",
            f"sven-app:{chat_id}",  # Dedicated sven-app session
            "--sms",  # Wrap with SMS format (includes tier in prompt)
            "--sven-app",  # Format for Sven iOS app (adds 🎤 prefix)
            "--admin",  # Admin tier access (Nikhil is admin)
        ]

        # Add image attachment if present
        if image_path:
            cmd.extend(["--attachment", image_path])

        cmd.append(transcript)

        # Use async subprocess to avoid blocking the event loop
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
    """Health check endpoint"""
    return {"status": "ok", "service": "sven-api", "time": datetime.now().isoformat()}


@app.get("/health")
async def health():
    """Health check for monitoring"""
    return {"status": "healthy"}


@app.post("/prompt", response_model=PromptResponse)
async def receive_prompt(request: PromptRequest):
    """
    Receive voice transcript from Sven iOS app.

    Stores user message and injects into sven-app session.
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

    # Generate request ID
    request_id = str(uuid.uuid4())
    logger.info(f"POST /prompt: created request_id={request_id[:8]}... for transcript")

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

    # Inject into sven-app session
    logger.info(f"POST /prompt: injecting into sven-app session...")
    success = await inject_prompt_to_sven_session(transcript, chat_id=request.chat_id)

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
    transcript: str = Form(...),
    token: str = Form(...),
    chat_id: str = Form("voice"),
    image: UploadFile | None = File(None),
):
    """
    Receive voice transcript with optional image from Sven iOS app.

    Uses multipart/form-data to support file uploads.
    Stores user message and injects into sven-app session with image attachment.
    Response will appear via GET /messages polling.
    """
    token_short = token[:8] if token else "none"
    has_image = image is not None and image.filename
    logger.info(f"POST /prompt-with-image: token={token_short}... transcript={transcript[:100] if transcript else 'empty'}... has_image={has_image}")

    # Validate transcript
    if not transcript or not transcript.strip():
        logger.warning(f"POST /prompt-with-image: empty transcript from token={token_short}")
        raise HTTPException(status_code=400, detail="Empty transcript")

    transcript = transcript.strip()

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

    # Generate request ID
    request_id = str(uuid.uuid4())
    logger.info(f"POST /prompt-with-image: created request_id={request_id[:8]}...")

    # Handle image upload
    image_path = None
    if image and image.filename:
        try:
            IMAGE_DIR.mkdir(parents=True, exist_ok=True)
            # Preserve file extension
            ext = Path(image.filename).suffix.lower() or ".jpg"
            image_path = str(IMAGE_DIR / f"{request_id}{ext}")

            # Read and save image
            image_data = await image.read()
            with open(image_path, "wb") as f:
                f.write(image_data)

            logger.info(f"POST /prompt-with-image: saved image to {image_path} ({len(image_data)} bytes)")
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

    # Inject into sven-app session
    logger.info(f"POST /prompt-with-image: injecting into sven-app session...")
    success = await inject_prompt_to_sven_session(transcript, chat_id=chat_id, image_path=image_path)

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
            cursor = conn.execute(
                "SELECT id, role, content, image_path, audio_path, created_at FROM messages "
                "WHERE chat_id = ? AND created_at > ? ORDER BY created_at ASC",
                (chat_id, since)
            )
        else:
            cursor = conn.execute(
                "SELECT id, role, content, image_path, audio_path, created_at FROM messages "
                "WHERE chat_id = ? ORDER BY created_at ASC LIMIT 200",
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
            del msg["image_path"]
            messages.append(msg)
        conn.close()
    except Exception as e:
        logger.error(f"GET /messages: database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

    logger.debug(f"GET /messages: returning {len(messages)} messages")
    return {"messages": messages}


@app.get("/audio/{message_id}")
async def get_audio(message_id: str, token: Optional[str] = None):
    """
    Download TTS audio file for a message.

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
        logger.warning(f"GET /audio: file not found: {audio_path}")
        raise HTTPException(status_code=404, detail="Audio not found")

    logger.info(f"GET /audio: serving {audio_path.name} ({audio_path.stat().st_size} bytes)")
    return FileResponse(
        path=audio_path,
        media_type="audio/wav",
        filename=f"{message_id}.wav"
    )


@app.delete("/messages")
async def clear_messages(token: Optional[str] = None, chat_id: str = "voice"):
    """Clear messages for a specific chat."""
    if token:
        allowed_tokens = load_allowed_tokens()
        if allowed_tokens and token not in allowed_tokens:
            raise HTTPException(status_code=401, detail="Unknown device token")

    conn = get_db()
    # Get audio paths before deleting
    audio_rows = conn.execute(
        "SELECT audio_path FROM messages WHERE chat_id = ? AND audio_path IS NOT NULL",
        (chat_id,)
    ).fetchall()
    conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

    # Clean up audio files for this chat only
    for (audio_path,) in audio_rows:
        if audio_path:
            p = Path(audio_path)
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

    # Validate device token is registered
    allowed_tokens = load_allowed_tokens()
    if allowed_tokens and request.device_token not in allowed_tokens:
        # Auto-register if no tokens exist yet (first-time setup)
        if not allowed_tokens:
            allowed_tokens.add(request.device_token)
            save_allowed_tokens(allowed_tokens)
            logger.info(f"First device registration: {device_short}...")
        else:
            logger.warning(f"POST /register-apns: unauthorized device={device_short}")
            raise HTTPException(status_code=401, detail="Unknown device token")

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
    Restart the sven-app Claude session.
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
                f"sven-app:{chat_id}"
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
async def create_chat(request: CreateChatRequest):
    """Create a new chat."""
    validate_token(request.token)
    chat_id = str(uuid.uuid4())
    display_title = request.title or "New Chat"
    conn = get_db()
    conn.execute(
        "INSERT INTO chats (id, title) VALUES (?, ?)",
        (chat_id, display_title)
    )
    conn.commit()
    row = conn.execute("SELECT id, title, created_at, updated_at FROM chats WHERE id = ?", (chat_id,)).fetchone()
    conn.close()
    return {"id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]}


@app.get("/chats")
async def list_chats(token: str = None):
    """List all chats with last message previews."""
    conn = get_db()
    cursor = conn.execute("""
        SELECT c.id, c.title, c.created_at, c.updated_at,
               m.content AS last_message,
               m.created_at AS last_message_at,
               m.role AS last_message_role
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
        chats.append({
            "id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3],
            "last_message": row[4], "last_message_at": row[5], "last_message_role": row[6]
        })
    conn.close()
    return {"chats": chats}


@app.patch("/chats/{chat_id}")
async def update_chat(chat_id: str, request: UpdateChatRequest):
    """Rename a chat."""
    validate_token(request.token)
    conn = get_db()
    conn.execute(
        "UPDATE chats SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (request.title, chat_id)
    )
    conn.commit()
    row = conn.execute("SELECT id, title, created_at, updated_at FROM chats WHERE id = ?", (chat_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]}


@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, token: str = None):
    """Delete a chat and its messages."""
    if chat_id == "voice":
        raise HTTPException(status_code=400, detail="Cannot delete default chat")
    conn = get_db()
    # Clean up audio files for this chat
    audio_rows = conn.execute(
        "SELECT audio_path FROM messages WHERE chat_id = ? AND audio_path IS NOT NULL",
        (chat_id,)
    ).fetchall()
    conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    conn.commit()
    conn.close()
    for (audio_path,) in audio_rows:
        if audio_path:
            p = Path(audio_path)
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
    # Kill the dispatch session (fire and forget)
    session_id = f"sven-app:{chat_id}"
    subprocess.Popen(
        [CLAUDE_ASSISTANT_CLI, "kill-session", session_id],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# Dashboard API endpoints
# ─────────────────────────────────────────────────────────────

BUS_DB_PATH = Path.home() / "dispatch" / "state" / "bus.db"
SESSIONS_JSON = Path.home() / "dispatch" / "state" / "sessions.json"
REMINDERS_JSON = Path.home() / "dispatch" / "state" / "reminders.json"
DAEMON_PID_FILE = Path.home() / "dispatch" / "state" / "daemon.pid"
PERF_LOG_DIR = Path.home() / "dispatch" / "logs"
SKILLS_DIR = Path.home() / ".claude" / "skills"
DISPATCH_LOGS_DIR = Path.home() / "dispatch" / "logs"

ALLOWED_LOG_FILES = {
    "manager.log", "session_lifecycle.log", "watchdog.log",
    "sven-api.log", "signal-daemon.log", "compactions.log",
    "memory-consolidation.log", "nightly-scraper.log",
    "launchd.log", "watchdog-launchd.log", "search-daemon.log",
    "embed-rerank.log", "memory-search.log", "chat-context-consolidation.log",
}


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
        if SESSIONS_JSON.exists():
            sessions = json.loads(SESSIONS_JSON.read_text())
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

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        query = f"SELECT topic, partition, offset, timestamp, type, source, key, substr(payload, 1, 200) as payload_preview FROM records {where} ORDER BY timestamp DESC LIMIT ?"
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

        # Events by hour (last 24h)
        now_ms = int(time.time() * 1000)
        day_ago_ms = now_ms - 86400_000
        by_hour = []
        rows = conn.execute(
            "SELECT (timestamp / 3600000) * 3600000 as hour_ms, COUNT(*) as cnt "
            "FROM records WHERE timestamp > ? GROUP BY hour_ms ORDER BY hour_ms",
            (day_ago_ms,)
        ).fetchall()
        for r in rows:
            ts = datetime.fromtimestamp(r["hour_ms"] / 1000).strftime("%Y-%m-%dT%H:%M:%S")
            by_hour.append({"hour": ts, "count": r["cnt"]})

        types_list = [r["type"] for r in by_type if r["type"]]
        sources_list = [r["source"] for r in by_source if r["source"]]

        # Topics list for filter dropdown
        topics_rows = conn.execute(
            "SELECT DISTINCT topic FROM records WHERE topic IS NOT NULL AND topic != '' ORDER BY topic"
        ).fetchall()
        topics_list = [r["topic"] for r in topics_rows]

        conn.close()

        return {
            "by_type": by_type,
            "by_source": by_source,
            "by_hour": by_hour,
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
        sessions_data = {}
        if SESSIONS_JSON.exists():
            sessions_data = json.loads(SESSIONS_JSON.read_text())

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

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        query = f"SELECT id, timestamp, session_name, chat_id, event_type, tool_name, duration_ms, is_error, substr(payload, 1, 200) as payload_preview FROM sdk_events {where} ORDER BY id DESC LIMIT ?"
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
        by_hour = []
        rows = conn.execute(
            "SELECT (timestamp / 3600000) * 3600000 as hour_ms, COUNT(*) as cnt "
            "FROM sdk_events WHERE timestamp > ? GROUP BY hour_ms ORDER BY hour_ms",
            (day_ago_ms,)
        ).fetchall()
        for r in rows:
            ts = datetime.fromtimestamp(r["hour_ms"] / 1000).strftime("%Y-%m-%dT%H:%M:%S")
            by_hour.append({"hour": ts, "count": r["cnt"]})

        total_row = conn.execute("SELECT COUNT(*) FROM sdk_events").fetchone()
        error_row = conn.execute("SELECT COUNT(*) FROM sdk_events WHERE is_error = 1").fetchone()

        conn.close()

        return {
            "by_tool": by_tool,
            "by_session": by_session,
            "by_hour": by_hour,
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


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Starting Sven API server...")
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
