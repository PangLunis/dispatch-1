---
name: sven-app
description: Backend for Sven iOS voice assistant app. Handles message storage and TTS generation for in-app responses.
---

# Sven App Backend

This skill provides the backend infrastructure for the Sven iOS voice assistant app.

## Architecture

```
iOS App → POST /prompt → dispatch-api → inject-prompt → SDK Session
                                                        ↓
                                              Claude generates response
                                                        ↓
                                              calls reply-sven CLI
                                                        ↓
                                    reply-sven stores message + generates TTS
                                                        ↓
iOS App ← GET /messages ← dispatch-api ← reads from SQLite message bus
iOS App ← GET /audio/{id} ← serves TTS audio files
```

## Components

### Message Bus (SQLite)
Location: `~/dispatch/state/sven-messages.db`

```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    audio_path TEXT,     -- path to TTS audio file (assistant only)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### reply-sven CLI
Location: `~/.claude/skills/sven-app/scripts/reply-sven`

Called by Claude to send responses. Stores message in SQLite and generates TTS audio.

```bash
~/.claude/skills/sven-app/scripts/reply-sven "voice" "Your response text here"
```

### Session
- Transcript directory: `~/transcripts/sven-app/voice/`
- Session name: `sven-app/voice`
- Tier: admin (full access)

## API Endpoints (dispatch-api)

- `POST /prompt` - Receive transcript, inject into session (JSON body)
- `POST /prompt-with-image` - Receive transcript + image via multipart/form-data
- `GET /messages?since=<timestamp>` - Poll for new messages
- `GET /audio/<id>` - Download TTS audio file
- `DELETE /messages` - Clear all messages (reset)
- `POST /restart-session` - Restart the Claude session

## Image Support

The iOS app can send images along with voice transcripts:

1. **Upload**: `POST /prompt-with-image` with multipart form-data
   - `transcript` (string) - Voice transcript
   - `token` (string) - Device auth token
   - `image` (file, optional) - Photo attachment

2. **Storage**: Images saved to `~/dispatch/state/sven-images/`

3. **Vision**: Gemini analyzes images with conversation context via `DispatchAppReader`

4. **Schema**: Messages table includes `image_path TEXT` column
