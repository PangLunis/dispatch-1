# Sven API Server

Backend HTTP server for the Sven iOS voice assistant app. Receives voice transcripts and optional images, injects them into a dedicated Claude SDK session, and serves responses with TTS audio.

## Endpoints

### `POST /prompt`
Receive voice transcript (JSON body).

```json
{
  "transcript": "What's the weather like?",
  "token": "device-auth-token"
}
```

### `POST /prompt-with-image`
Receive voice transcript with optional image (multipart/form-data).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| transcript | string | yes | Voice transcript text |
| token | string | yes | Device auth token |
| image | file | no | Photo attachment (JPEG/PNG) |

Images are saved to `~/dispatch/state/sven-images/` and passed to the Claude session via `--attachment` flag for Gemini vision analysis.

### `GET /messages`
Poll for new messages.

| Param | Type | Description |
|-------|------|-------------|
| since | string | ISO timestamp to get messages after |
| token | string | Device auth token (optional) |

### `GET /audio/{message_id}`
Download TTS audio file (WAV format).

### `DELETE /messages`
Clear all messages (for testing/reset).

### `POST /restart-session`
Restart the Claude SDK session.

## Database

SQLite database at `~/dispatch/state/sven-messages.db`:

```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    image_path TEXT,     -- path to uploaded image
    audio_path TEXT,     -- path to TTS audio file
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## Running

```bash
# Start server (listens on 0.0.0.0:9091)
uv run server.py

# Or as executable
./server.py
```

## Configuration

- `allowed_tokens.json` - Authorized device tokens
- Logs written to `~/dispatch/logs/dispatch-api.log`
- Rate limit: 30 requests per 60 seconds per token
