# /agents — Agent Command Center

## Overview

A web-based agent command center at `/agents` on dispatch-api. Two modes in one UI:

1. **Monitor** — See all active SDK sessions (contact sessions, group chats, custom agents). Click into any to view the SMS-level conversation. Inject messages into any session.

2. **Workspace** — Create new named agent sessions from the UI. Each gets a full SDK session with all tools. Type messages, upload files/images, see responses. Like a web-based Claude Code chat.

**Read + Write** — input box for both injecting into existing sessions and chatting with new agent sessions.

## Phasing

**Phase 1 (this plan)**: Core agent command center
- Session sidebar with all sessions (contact + agent)
- Message view for both session types (plain text, `white-space: pre-wrap`)
- Create new agent sessions
- Send messages / inject into sessions
- No tool call rendering, no markdown rendering, no file upload
- Contact sessions show SMS-level messages, agent sessions show user/assistant messages

**Phase 1.5 (next)**: Rich rendering + file upload
- Markdown rendering via marked.js for agent session responses
- Code block syntax highlighting via highlight.js
- File/image upload UI (drag-and-drop, preview strip)
- Upload endpoint + attachment passing to SDK

**Phase 2 (future)**: Tool call rendering
- Integrate `sdk_events` table to show tool calls inline
- Expandable tool call blocks with input/output
- Thinking block rendering

This phasing lets us ship a useful agent management UI quickly. Each phase adds richness without blocking the core.

## Design Intent

- **Who**: Admin user at their laptop, managing and auditing AI agent sessions
- **What**: Monitor agent activity, audit conversations, create task-specific agent workspaces
- **Feel**: Like a command center — dense, information-rich, fast. Not a casual chat app. More like Linear meets Claude.ai. Clean, tight, minimal padding. Dark and focused.

### Domain Exploration

**Domain concepts**: Command center, dispatch, agents, sessions, transcripts, injection, orchestration, fleet management

**Color world**: Terminal green on black, amber warning lights, blue data streams, the glow of multiple screens in a dark room, status LEDs (green/amber/red)

**Signature element**: The session sidebar — a real-time fleet view of all running AI agents with status indicators, tier badges, and source labels. Each session is a living entity you can observe and interact with.

**Rejected defaults**:
1. ❌ Rounded chat bubbles → flat left-border messages (terminal aesthetic)
2. ❌ Card-heavy layout → borderless flowing content with subtle separators
3. ❌ Colorful tier badges → monochrome text labels with a single accent dot

### Design Decisions

- **Single HTML file** (`agents.html`) — same pattern as `dashboard.html`
- **Dark theme** — matches dashboard's surface scale but with its own token names
- **Typography**: Fira Code for metadata/labels/timestamps, Fira Sans for message body text
- **Sharp corners** — `border-radius: 0` throughout
- **Accent**: Blue (`#2563eb`) for selected/active states — single accent color
- **Depth**: Borders-only, no shadows (technical/dense feel)
- **Spacing**: Tight — 8px base unit. Dense information display, not spacious.
- **Desktop only**
- **Auth**: None — Tailscale network-level access only (matches dashboard)

### CSS Token Architecture

```css
/* Surfaces — whisper-quiet elevation shifts */
--surface-base: #09090b;      /* zinc-950 */
--surface-raised: #0f0f11;    /* sidebar, panels */
--surface-overlay: #18181b;   /* dropdowns, tool call blocks */
--surface-input: #0c0c0e;     /* input fields (inset feel) */

/* Text hierarchy */
--text-primary: #e4e4e7;      /* main content */
--text-secondary: #a1a1aa;    /* supporting text, previews */
--text-tertiary: #52525b;     /* timestamps, metadata */
--text-muted: #3f3f46;        /* disabled, placeholder */

/* Borders — low opacity, disappear when not needed */
--border-standard: rgba(255,255,255,0.06);
--border-soft: rgba(255,255,255,0.03);
--border-emphasis: rgba(255,255,255,0.12);

/* Accent — single blue */
--accent: #2563eb;
--accent-muted: rgba(37,99,235,0.15);

/* Semantic */
--success: #22c55e;
--warning: #f59e0b;
--error: #ef4444;

/* Message borders */
--msg-incoming: rgba(37,99,235,0.3);   /* blue tint */
--msg-outgoing: rgba(34,197,94,0.3);   /* green tint */
--msg-sven: rgba(168,85,247,0.3);      /* purple tint for Sven's responses */
```

## Architecture

### Two Session Types

**1. Contact Sessions** (existing — from dispatch daemon)
- Already running SDK sessions for iMessage/Signal contacts
- Data: messages in bus.db, session metadata in sessions.json
- Interaction: inject messages via `inject-prompt` CLI
- View: SMS-level conversation (who said what, when)

**2. Agent Sessions** (new — created from /agents UI)
- New SDK sessions created on demand via daemon IPC
- Data: messages stored in sven-messages.db (reuse existing schema)
- Interaction: POST /api/agents/messages → store in sven-messages.db → inject via IPC → session responds via `reply-agent` CLI → stored in sven-messages.db → frontend polls
- View: User/assistant conversation (plain text in Phase 1)
- Named by user (e.g., "debug signal", "build hue skill")
- Registered in sessions.json with `source: "agent"` to distinguish from contact sessions
- Survive daemon restarts via `was_active` flag (same as contact sessions)
- System prompt: default Claude Code system prompt (no sms-assistant injection, no tier rules)

### Daemon IPC Contract

**Socket**: `/tmp/claude-assistant.sock` (Unix domain socket, `chmod 0600`)
**Protocol**: Single JSON object + newline per request/response, connection closes after response

**Supported commands relevant to /agents**:

| Command | Purpose | Payload |
|---------|---------|---------|
| `inject` | Send message to any session | `{"cmd": "inject", "chat_id": "...", "prompt": "...", "admin": true, "source": "agent"}` |
| `kill_session` | Terminate a session | `{"cmd": "kill_session", "chat_id": "..."}` |
| `status` | List active sessions | `{"cmd": "status"}` |
| `restart_session` | Restart a session | `{"cmd": "restart_session", "chat_id": "..."}` |

**Response format**: `{"ok": true, "message": "..."}` or `{"ok": false, "error": "..."}`

**Agent session creation**: Sessions are created lazily on first inject. When `inject-prompt` receives a chat_id with prefix `agent:`, the daemon:
1. Detects no existing session for this chat_id
2. Creates transcript dir: `~/transcripts/agent/{slug}/`
3. Creates `.claude` symlink: `~/transcripts/agent/{slug}/.claude -> ~/.claude`
4. Registers in sessions.json with `source: "agent"`, `tier: "admin"`
5. Spawns Claude SDK session with full tool access
6. Queues the injected message

### Agent Reply Mechanism

**New CLI**: `~/.claude/skills/sven-app/scripts/reply-agent` — lightweight version of `reply-sven`

The agent session's SDK process runs in `~/transcripts/agent/{slug}/`. When Claude needs to respond, it calls `reply-agent "{chat_id}" "response text"`.

**`reply-agent` behavior**:
1. Stores message in sven-messages.db: `INSERT INTO messages (id, role, content, chat_id) VALUES (uuid, 'assistant', text, chat_id)`
2. Updates `chats.updated_at`
3. No TTS generation (unlike `reply-sven`)
4. No push notification (unlike `reply-sven`)
5. Exit 0 on success

**How the session knows to use `reply-agent`**: The `agent` backend config in `backends.py` specifies `send_cmd: "~/.claude/skills/sven-app/scripts/reply-agent \"{chat_id}\""`. This template is injected into the session's system prompt as the reply instruction.

### New Backend Config

Add to `~/dispatch/assistant/backends.py`:
```python
BackendConfig(
    name="agent",
    label="Agent",
    session_suffix="-agent",
    registry_prefix="agent:",
    send_cmd='~/.claude/skills/sven-app/scripts/reply-agent "{chat_id}"',
    send_group_cmd='~/.claude/skills/sven-app/scripts/reply-agent "{chat_id}"',  # same as individual
    history_cmd='',  # no external history source — messages in sven-messages.db
    supports_image_context=True,
)
```

**IMPORTANT**: This must be registered in the `BACKENDS` dict before any agent inject calls. The `get_backend("agent")` function needs to find it, otherwise it falls back to imessage. Add to prerequisites.

**Reply instruction delivery**: The backend's `send_cmd` is injected into the session's system prompt by `_inject_system_prompt_if_needed()` in `sdk_backend.py`. This function reads the backend config to build the reply instruction (e.g., "To respond, call: `reply-agent '{chat_id}' 'message'`"). This works the same for agent sessions as for contact sessions — it's part of the SDK session setup, not the sms-assistant prompt.

**Tier rules suffix**: The daemon's `_cmd_inject` appends a tier-rules reminder from `~/.claude/skills/sms-assistant/{tier}-rules.md`. For agent sessions with `source="agent"`, this should be suppressed since agent sessions don't use sms-assistant rules. Add a check: `if source != "agent": append tier rules`. This is a one-line change in `manager.py`.

### Files

**New**:
- `~/dispatch/services/dispatch-api/agents.html` — Agent command center UI

**Modified**:
- `~/dispatch/services/dispatch-api/server.py` — New endpoints
- `~/dispatch/services/dispatch-api/dashboard.html` — Add nav link to `/agents`

### API Endpoints

#### 1. `GET /agents` — Serve the HTML page
```python
@app.get("/agents", response_class=HTMLResponse)
async def agents_page():
    html_path = Path(__file__).parent / "agents.html"
    return HTMLResponse(content=html_path.read_text())
```

#### 2. `GET /api/agents/sessions` — List all sessions (both types)

Merges contact sessions (from sessions.json) and agent sessions (from sven-messages.db chats table with `agent:` prefix IDs).

**Response**:
```json
{
  "sessions": [
    {
      "id": "+16175969496",
      "type": "contact",
      "name": "Admin User",
      "tier": "admin",
      "source": "imessage",
      "chat_type": "individual",
      "participants": ["Admin User"],
      "last_message": "okay switching gears",
      "last_message_time": "2026-03-20T21:39:46Z",
      "last_message_is_from_me": false,
      "status": "active"
    },
    {
      "id": "agent:debug-signal",
      "type": "agent",
      "name": "debug signal",
      "tier": "admin",
      "source": "agent",
      "chat_type": "agent",
      "participants": null,
      "last_message": "Found the issue...",
      "last_message_time": "2026-03-20T22:00:00Z",
      "last_message_is_from_me": false,
      "status": "active"
    }
  ]
}
```

**Implementation**:

```python
async def get_agent_sessions():
    sessions = []

    # 1. Load contact sessions from sessions.json (reuse _load_sessions() helper)
    registry = _load_sessions()

    # 2. Get last message per chat_id from bus.db (single efficient query)
    bus_db = get_bus_db()
    cursor = bus_db.execute("""
        SELECT chat_id, payload, timestamp, type, source FROM (
            SELECT json_extract(payload, '$.chat_id') as chat_id,
                   payload, timestamp, type, source,
                   ROW_NUMBER() OVER (
                       PARTITION BY json_extract(payload, '$.chat_id')
                       ORDER BY timestamp DESC
                   ) as rn
            FROM records
            WHERE topic = 'messages'
              AND type IN ('message.received', 'message.sent')
              AND source NOT IN ('consumer-retry', 'sdk_backend.replay')
        ) sub WHERE rn = 1
    """)
    last_messages = {row[0]: row for row in cursor.fetchall()}

    # 3. Merge: for each registry entry, attach last message info
    for chat_id, session_info in registry.items():
        if chat_id.startswith('agent:'):
            continue  # agent sessions come from sven-messages.db
        last = last_messages.get(chat_id)
        sessions.append({
            "id": chat_id,
            "type": "contact",
            "name": session_info.get("contact_name", chat_id),
            "tier": session_info.get("tier", "unknown"),
            "source": session_info.get("source", "unknown"),
            "chat_type": session_info.get("type", "individual"),
            "participants": session_info.get("participants"),
            "last_message": extract_text_from_payload(last) if last else None,
            "last_message_time": iso_from_ts(last[2]) if last else session_info.get("last_message_time"),
            "last_message_is_from_me": last[3] == 'message.sent' if last else False,
            "status": "active" if session_info.get("was_active") else "idle"
        })

    # 4. Load agent sessions from sven-messages.db
    msg_db = get_messages_db()
    agent_cursor = msg_db.execute("""
        SELECT c.id, c.title, c.updated_at,
               m.content, m.role, m.created_at
        FROM chats c
        LEFT JOIN (
            SELECT chat_id, content, role, created_at,
                   ROW_NUMBER() OVER (PARTITION BY chat_id ORDER BY created_at DESC) as rn
            FROM messages
        ) m ON m.chat_id = c.id AND m.rn = 1
        WHERE c.id LIKE 'agent:%'
        ORDER BY COALESCE(m.created_at, c.updated_at) DESC
    """)
    for row in agent_cursor.fetchall():
        chat_id = row[0]
        # Check session health via sessions.json registry
        reg_entry = registry.get(chat_id, {})
        is_active = reg_entry.get("was_active", False)
        sessions.append({
            "id": chat_id,
            "type": "agent",
            "name": row[1],  # chat title
            "tier": "admin",
            "source": "agent",
            "chat_type": "agent",
            "participants": None,
            "last_message": row[3],
            "last_message_time": row[5] or row[2],
            "last_message_is_from_me": row[4] == 'user' if row[4] else False,
            "status": "active" if is_active else "idle"
        })

    # 5. Sort all sessions by last_message_time descending
    sessions.sort(key=lambda s: s["last_message_time"] or "", reverse=True)
    return {"sessions": sessions}
```

#### 3. `GET /api/agents/messages` — Get messages for a session

**Parameters**: `session_id` (required), `limit` (default 100), `before_ts` (cursor, epoch ms), `after_ts` (for polling new messages)

**For contact sessions** (session_id does NOT start with `agent:`):

```sql
-- Historical load (before_ts set)
SELECT "offset", type, source, payload, timestamp
FROM records
WHERE topic = 'messages'
  AND json_extract(payload, '$.chat_id') = :chat_id
  AND type IN ('message.received', 'message.sent')
  AND source NOT IN ('consumer-retry', 'sdk_backend.replay')
  AND (:before_ts IS NULL OR timestamp < :before_ts)
ORDER BY timestamp DESC
LIMIT :limit

-- Polling for new messages (after_ts set)
SELECT "offset", type, source, payload, timestamp
FROM records
WHERE topic = 'messages'
  AND json_extract(payload, '$.chat_id') = :chat_id
  AND type IN ('message.received', 'message.sent')
  AND source NOT IN ('consumer-retry', 'sdk_backend.replay')
  AND timestamp > :after_ts
ORDER BY timestamp ASC
LIMIT 50
```

**Text extraction** (Python):
```python
import re

def extract_text_from_record(payload_str: str, source: str, type_: str) -> str | None:
    payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str

    # message.received — text directly in payload
    if type_ == 'message.received':
        return payload.get('text')

    # message.sent from imessage — text directly in payload
    if type_ == 'message.sent' and source == 'imessage':
        return payload.get('text')

    # message.sent from sdk_session — text in heredoc or quoted arg
    if type_ == 'message.sent' and source == 'sdk_session':
        command = payload.get('command', '')
        # Try heredoc with any delimiter (ENDMSG, EOF, etc.)
        match = re.search(r"<<'(\w+)'\n(.*?)\n\1", command, re.DOTALL)
        if match:
            return match.group(2)
        # Fallback: last quoted argument
        match = re.search(r'"([^"]*)"$', command)
        if match and len(match.group(1)) > 0:
            return match.group(1)
        return '[message sent]'

    return None
```

**Sender resolution**: Use the `build_sender_map()` dict (defined in Performance section) once per request. For each message:
```python
def resolve_sender(payload: dict, type_: str, sender_map: dict) -> str:
    if type_ == 'message.sent':
        return 'sven'
    phone = payload.get('phone') or payload.get('sender_phone', '')
    return sender_map.get(phone, phone)  # fallback to raw phone/UUID
```

**For agent sessions** (session_id starts with `agent:`):

```sql
-- Historical load
SELECT id, role, content, audio_path, created_at
FROM messages
WHERE chat_id = :chat_id
  AND (:before_ts IS NULL OR created_at < datetime(:before_ts / 1000, 'unixepoch'))
ORDER BY created_at DESC
LIMIT :limit

-- Polling for new messages
SELECT id, role, content, audio_path, created_at
FROM messages
WHERE chat_id = :chat_id
  AND created_at > datetime(:after_ts / 1000, 'unixepoch')
ORDER BY created_at ASC
LIMIT 50
```

**Unified response** (both types normalized to same format):
```json
{
  "messages": [
    {
      "id": "123",
      "role": "user",
      "text": "check the signal socket",
      "sender": "Admin User",
      "is_from_me": false,
      "timestamp_ms": 1773441586000,
      "source": "imessage",
      "has_attachment": false
    }
  ],
  "has_more": true
}
```

**Timestamp normalization**:
- bus.db `timestamp`: already epoch milliseconds → use directly as `timestamp_ms`
- sven-messages.db `created_at`: ISO datetime string → convert to epoch ms in Python: `int(datetime.fromisoformat(created_at).timestamp() * 1000)`

#### 4. `POST /api/agents/sessions` — Create new agent session

**Request**:
```json
{
  "name": "debug signal"
}
```

**Flow**:
1. Validate: name required, max 50 chars, non-empty text. Return 400 on failure.
2. Slugify name: `"debug signal"` → `"debug-signal"`
3. Generate chat_id: `agent:debug-signal`
4. Check for conflicts: if slug exists in sven-messages.db chats, append `-2`, `-3`, etc.
5. Create chat in sven-messages.db: `INSERT INTO chats (id, title) VALUES (:chat_id, :name)`
6. Create SDK session via lazy inject: send `{"cmd": "inject", "chat_id": "agent:debug-signal", "prompt": "Session started. Ready for tasks.", "admin": true, "source": "agent"}` to daemon IPC socket. The daemon auto-creates the session on first inject (no separate `create_agent` command needed).
7. Return session info

**Error handling**: If IPC socket is unavailable (daemon down), return 503 with `{"error": "Daemon unavailable"}`. If IPC returns `{"ok": false}`, forward the error message.

**Response**:
```json
{
  "id": "agent:debug-signal",
  "name": "debug signal",
  "status": "active"
}
```

**Daemon IPC for agent sessions**: The daemon registers the session in sessions.json with `source: "agent"`, `type: "agent"`, `tier: "admin"`. The session gets a full SDK process with all tools, transcript dir at `~/transcripts/agent/debug-signal/`.

#### 5. `POST /api/agents/messages` — Send message to any session

**Request**:
```json
{
  "session_id": "agent:debug-signal",
  "text": "check the signal socket"
}
```

**Input validation**: `text` required and non-empty, `session_id` must exist. Return 400/404 on failure.

**For agent sessions**:
1. Store user message in sven-messages.db: `INSERT INTO messages (id, role, content, chat_id) VALUES (:id, 'user', :text, :chat_id)`
2. Inject into SDK session via IPC: `{"cmd": "inject", "chat_id": "agent:debug-signal", "prompt": :text, "admin": true, "source": "agent"}`
3. SDK session processes and responds via `reply-agent` CLI → stores assistant response in sven-messages.db
4. Frontend polls `GET /api/agents/messages?after_ts=...` to pick up response

**For contact sessions**:
1. Inject via `inject-prompt :chat_id --admin :text`
2. Message appears in bus.db as `message.sent` when the session sends via `send-sms`/`send-signal`
3. Frontend polls to pick up the response

**File uploads**: Deferred to Phase 1.5.

#### 6. `PATCH /api/agents/sessions/{id}` — Rename agent session
Updates `chats.title` in sven-messages.db. Only works for agent sessions.

#### 7. `DELETE /api/agents/sessions/{id}` — Kill agent session
1. Kill SDK session via IPC: `{"cmd": "kill_session", "chat_id": "agent:debug-signal"}`
2. Mark as inactive in sessions.json
3. If `?delete_messages=true`: delete messages + chat entry from sven-messages.db, remove transcript dir `~/transcripts/agent/{slug}/`
4. If no `delete_messages` param: keep data for historical reference, mark as ended

### Performance

**Expression index on bus.db** — must be created separately (bus.db is opened read-only by dispatch-api):

Create via a one-time setup script or at daemon startup (daemon has write access):
```sql
CREATE INDEX IF NOT EXISTS idx_records_chat_id
ON records(topic, json_extract(payload, '$.chat_id'))
WHERE topic = 'messages';
```

This makes the `json_extract(payload, '$.chat_id') = ?` filter use an index scan instead of full table scan. SQLite 3.9+ supports expression indexes.

**Sender lookup optimization**: Build a phone→name lookup dict once per request from sessions.json, not per-message iteration.

Note: `participants` in sessions.json contains display names (strings like "Admin User"), not phone numbers. For individual chats, the `chat_id` IS the phone number. For group chats, sender resolution uses the `phone` field from the bus.db payload, which is a phone number (iMessage) or UUID (Signal). We map these by scanning all individual sessions in the registry:

```python
def build_sender_map(registry: dict) -> dict:
    sender_map = {}
    for chat_id, session in registry.items():
        name = session.get("contact_name", chat_id)
        # Map the chat_id (phone number for individuals) to contact name
        sender_map[chat_id] = name
        # For individual sessions, chat_id is the phone number
        # This handles group chat sender resolution too — when a group
        # message has phone="+16175969496", we find "Admin User"
        # from his individual session entry
    return sender_map
```

### Frontend (agents.html)

#### Layout

```
┌────────────────────────────────────────────────────────┐
│ ← DISPATCH    AGENTS                    [+ New Agent]  │
├──────────────┬─────────────────────────────────────────┤
│              │                                         │
│  🔍 Search   │   Session Name              tier · src  │
│              │   ─────────────────────────────────────  │
│  [Filters ▼] │                                         │
│              │   ┌ sender ───────────────────────────┐  │
│  ┌─────────┐ │   │ message text                     │  │
│  │●Admin   │ │   │ 10:14pm                          │  │
│  │ last... │ │   └──────────────────────────────────┘  │
│  ├─────────┤ │                                         │
│  │●debug.. │ │   ┌ sven ────────────────────────────┐  │
│  │ Found.. │ │   │ Here's what I found...           │  │
│  ├─────────┤ │   │ 10:15pm                          │  │
│  │●Ryan    │ │   └──────────────────────────────────┘  │
│  │ hey c.. │ │                                         │
│  └─────────┘ │                                         │
│              │  ┌──────────────────────────────┐ [📎]  │
│              │  │ Type a message...             │ [↑]   │
│              │  └──────────────────────────────┘       │
└──────────────┴─────────────────────────────────────────┘
```

- **Sidebar** (280px): Session list with search + filters
- **Main area**: Conversation view + input box
- **Header**: Back to dashboard + "AGENTS" title + "New Agent" button

#### Sidebar

**Session items**:
- Status dot (green=active, amber=idle, red=error) — 6px circle
- Session name (bold, Fira Sans 13px, truncated)
- Type indicator: small monospace label — `iMessage`, `Signal`, `Agent` in tertiary color
- Last message preview (1 line, ellipsis, secondary color, Fira Sans 12px)
- Relative timestamp (tertiary color, Fira Code 11px)
- Selected: blue left border (3px), accent-muted background

**Filters** (collapsible row below search):
- Pill-style toggle buttons: Type (All | Contact | Agent), Source (All | iMessage | Signal | Agent)
- Active filter: accent background, primary text
- Inactive filter: transparent, tertiary text

**Search**: Text input, Fira Sans 13px, surface-input background, filters client-side by name

**Sort**: By last_message_time descending (most recent first)

#### Conversation View

**Header bar**:
- Session name (Fira Sans 16px, bold) — click to edit for agent sessions: replaces text with an `<input>` field, Enter to save (PATCH API), Escape to cancel. Simpler and more reliable than contenteditable.
- Tier label (monospace, tertiary) + source label + status dot
- Right side: session age ("created 2h ago")

**Messages**:
- `flex-direction: column-reverse` for bottom-anchoring
- `IntersectionObserver` sentinel at DOM end (visual top) for infinite scroll up
- Prepending older messages to DOM end naturally preserves scroll position
- New messages via `after_ts` polling prepended to DOM start (visual bottom)
- Auto-scroll only if user is at bottom (`scrollTop >= -50` with column-reverse)

**Message rendering**:
- Messages grouped by consecutive sender
- Left-border accent per sender type:
  - Incoming (contact): `--msg-incoming` blue
  - Admin injection: `--msg-outgoing` green
  - Sven responses: `--msg-sven` purple
- Sender name header: Fira Code 12px, accent-colored for first occurrence, subsequent messages in group omit name
- Message body: Fira Sans 14px, `white-space: pre-wrap`, `word-break: break-word`
- Timestamps: Fira Code 11px, tertiary, shown per-message
- URLs: Auto-linkified via regex, `color: var(--accent)`, `target="_blank"`
- Phase 1: plain text only (no markdown rendering). Markdown + code highlighting deferred to Phase 1.5

**Group chat messages**: Color-code sender names using deterministic hue from name hash:
```javascript
function senderColor(name) {
    let hash = 0;
    for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
    const hue = Math.abs(hash) % 360;
    return `hsl(${hue}, 60%, 65%)`;
}
```

#### Input Area

- Container: surface-raised background, border-standard top border
- Textarea: auto-resize (min 1 row, max 8 rows), Fira Sans 14px, surface-input background
- Send button: `↑` in small circle, accent background when text is non-empty, muted when empty
- Submit: Enter to send, Shift+Enter for newline
- Disabled state: muted text "Select a session" when no session is selected
- **Processing indicator**: After sending a message to an agent session, show a pulsing "thinking..." label below the sent message until the next assistant response arrives. Uses CSS animation on opacity. Disappears when polling picks up the response.
- File upload: deferred to Phase 1.5
- **Context label for contact sessions**: Show "Injecting as admin — message goes to {name}'s AI session, not directly to the contact" above input in warning color. This clarifies that injection sends a prompt to the SDK session, which then processes it and may respond via send-sms/send-signal. The injected text is NOT sent directly as an SMS.

#### Create New Agent

- "+" button in header → reveals inline form at top of sidebar (pushes session list down)
- Form: Name input (required, Fira Sans 14px, surface-input background, auto-focus)
- Enter to create, Escape to cancel
- On create: API call → session appears at top of sidebar → auto-selected → input focused
- Validation: name required, max 50 chars
- Error: inline red text below input

#### Delete Session

- Only for agent sessions (contact sessions managed by daemon, not deletable from UI)
- Small `✕` button in conversation header (tertiary color, visible on hover)
- On click: show inline confirmation bar replacing header: "Delete '{name}'? [Delete] [Cancel]"
- Delete button: error color background
- On confirm: API call with `?delete_messages=true` → return to no-session-selected state

#### Keyboard Shortcuts

- `Ctrl+N` / `Cmd+N`: Create new agent
- `Escape`: Deselect session / close create form
- `↑` / `↓` in sidebar: Navigate sessions (when sidebar focused)
- `Enter` on sidebar item: Select session
- Focus textarea: auto when session selected

### Polling Strategy

- **Session list**: Every 10s
- **Active conversation**: Every 5s via `after_ts`
- **Visibility-aware**: `document.addEventListener('visibilitychange', ...)` — pause all intervals when `hidden`, resume when `visible`
- **Error handling**: On fetch failure, show warning banner, retry on next interval, auto-dismiss on recovery

### CDN Dependencies

**Phase 1**: None — all vanilla JS/CSS, no external dependencies.

**Phase 1.5** (when markdown rendering is added):
```html
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
```

### Error & Loading States

- **Loading sessions**: 5 skeleton items in sidebar (pulsing surface-overlay rectangles)
- **Loading messages**: Centered spinner (CSS-only, 20px)
- **Sending message**: Optimistic UI — show message immediately with muted opacity, full opacity on confirmed delivery
- **Connection lost**: Red banner at top "Connection lost — retrying..." with pulse animation
- **Empty session**: Centered text "No messages yet" in tertiary color
- **No session selected**: Centered text "Select a conversation" with keyboard hint
- **Create failed**: Inline red error text below create input
- **Session dead**: If session registry shows `was_active: false`, show "Session ended" badge in header, disable input

## Implementation Order

### Prerequisites (one-time setup, must be done before backend work)
0a. Create json_extract expression index on bus.db (run via `sqlite3` CLI, not dispatch-api)
0b. Add `agent` BackendConfig to `~/dispatch/assistant/backends.py` AND register in `BACKENDS` dict — must be done before any agent inject calls
0c. Create `reply-agent` CLI script at `~/.claude/skills/sven-app/scripts/reply-agent`
0d. Add `source != "agent"` check in daemon's `_cmd_inject` to skip tier-rules suffix for agent sessions

### Backend (server.py)
1. Refactor `_load_sessions()` helper from existing `dashboard_sessions()`
2. Add `GET /agents` route to serve HTML
3. Add `GET /api/agents/sessions` endpoint
4. Add `GET /api/agents/messages` endpoint (dual data source: bus.db + sven-messages.db)
5. Add `POST /api/agents/sessions` endpoint (create chat in sven-messages.db + IPC inject to spawn)
6. Add `POST /api/agents/messages` endpoint (store user msg + IPC inject)
7. Add `PATCH /api/agents/sessions/{id}` (rename) + `DELETE` (kill + delete)

### Frontend (agents.html)
8. Build HTML shell + CSS tokens + layout structure
9. Build sidebar: session list, search, filters
10. Build conversation view: message rendering, scroll architecture
11. Build input area: textarea, send button, context label
12. Build create-agent form: inline in sidebar
13. Build delete confirmation inline bar
14. Wire up polling (10s sessions, 5s messages, visibility-aware)

### Integration
15. Add "Agents" nav link to dashboard.html
16. Test in Chrome — subagent visual review

## Edge Cases

- **Contact sessions with no bus.db data**: Show in sidebar from sessions.json, display "No transcript available"
- **Agent sessions**: Full message history always available (sven-messages.db)
- **sdk_session heredoc parsing**: Generic `<<'DELIM'\n...\nDELIM` regex handles ENDMSG, EOF, etc.; fallback to last quoted arg; ultimate fallback to `[message sent]`
- **consumer-retry dedup**: `source NOT IN ('consumer-retry', 'sdk_backend.replay')` filter
- **Signal UUID phone fields**: Resolve via sessions.json contact map
- **Long messages**: `white-space: pre-wrap`, `word-break: break-word`
- **Timestamp normalization**: bus.db (epoch ms) and sven-messages.db (ISO datetime) both converted to epoch ms in API response
- **Session name conflicts**: Append `-2`, `-3` suffix if slug exists in chats table
- **File uploads**: Deferred to Phase 1.5
- **Session killed externally**: Detect via `was_active` flag in sessions.json, show "Session ended" badge, disable input
- **Agent session restarts**: Registered in sessions.json with `was_active: true`, auto-recreated by daemon on restart (same lifecycle as contact sessions)
- **Auth**: No authentication — Tailscale network-level access only (same as dashboard). Single admin user.
- **Concurrent creates**: Slug conflict check + append suffix is atomic per request (SQLite serializes writes)
- **Injecting into contact sessions**: Admin injection sends a prompt to the AI session (not directly to the contact). The session processes it and may respond via send-sms/send-signal. Show explicit warning label in UI.
- **Delete confirmation**: Inline confirmation bar (not modal) before deleting agent sessions
- **Multiple browser tabs**: Each tab polls independently. Visibility API pauses hidden tabs but not unfocused ones. Acceptable for single-admin tool.
- **Group chat rendering**: Sender names resolved via sessions.json contact map. Group chat `participants` field provides name list. Color-coded via deterministic hash.
- **Agent session system prompt**: Uses default Claude Code system prompt with full tool access. No sms-assistant rules injected. The transcript dir has `.claude` symlink so all skills are available.
