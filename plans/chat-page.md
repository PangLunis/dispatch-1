# /chat Page — ChatGPT-Style Conversation Viewer

## Overview

Add a `/chat` page to dispatch-api that provides a ChatGPT-style interface for browsing and reading all dispatch conversations (iMessage + Signal). Users see a sidebar of conversations sorted by recency, click one to read the full message thread. **Read-only** — no message composition.

## Design Intent

- **Who**: Admin user reviewing conversations with contacts across iMessage and Signal on his laptop
- **What**: Browse conversations, read message history, see who said what
- **Feel**: Like a native messaging app — familiar, fast, information-dense. Dark terminal aesthetic matching the existing dashboard, but warmer in the message area to feel conversational rather than monitoring-like.

### Design Decisions

- **Single HTML file** (`chat.html`) — same pattern as `dashboard.html`, served at `GET /chat`
- **Dark theme** — matches dashboard's `#000/#0a0a0a/#111/#1a1a1a` surface scale
- **Fira Code + Fira Sans** — consistent with dashboard typography (Fira Sans for message body text to aid readability of long messages, Fira Code for metadata/timestamps/names)
- **Sharp corners** — `border-radius: 0` throughout (matches dashboard)
- **Signature element**: Message bubbles with a left-border accent instead of rounded bubbles. Incoming = subtle blue-tinted left border, outgoing = subtle green-tinted left border. Sender name in monospace above each message group.
- **One accent**: Blue (`#2563eb`) for selected state, active indicators — same as dashboard
- **Tier badges**: Reuse dashboard's tier badge styles in conversation list
- **Desktop only** — no mobile responsive layout (admin tool, always accessed on laptop)

### Rejected Defaults
1. ❌ Rounded chat bubbles (too iMessage-clone, not our aesthetic)
2. ❌ White/light theme (inconsistent with dashboard)
3. ❌ Separate React app (we want single-file simplicity like dashboard.html)
4. ❌ Mobile responsive (admin tool, unnecessary complexity)
5. ❌ WebSockets/SSE (polling is simpler and sufficient for a read-only viewer)
6. ❌ Pure monospace for message body (hurts readability for long messages)

## Data Layer — bus.db Audit Results

### Event Types (topic='messages')

| Type | Count | Purpose | Render? |
|------|-------|---------|---------|
| `message.received` | 73,356 | **Primary inbound messages** | ✅ Yes (is_from_me=false) |
| `message.delivered` | 3,380 | Delivery confirmations | ❌ No |
| `message.queued` | 3,256 | Internal queue events | ❌ No |
| `message.sent` | 1,578 | **Outbound messages** | ✅ Yes (is_from_me=true) |
| `message.in` | 90 | Legacy inbound (tiny subset) | ❌ Skip (superseded by message.received) |
| `message.ignored` | 7 | Ignored messages | ❌ No |
| `reaction.received` | 1 | Reactions | ❌ No (v2) |

### Sources & Deduplication

| Source | Count | Notes |
|--------|-------|-------|
| `consumer-retry` | 69,254 | **Redelivered copies** of message.received — MUST deduplicate |
| `sdk_session` | 7,917 | SDK tool calls (message.sent, message.delivered, message.queued) |
| `imessage` | 2,693 | Native iMessage events |
| `signal` | 1,415 | Native Signal events |
| `discord` | 265 | Discord events |

**Deduplication strategy for `message.received`**: The `consumer-retry` source creates ~17x duplicate records. Deduplicate by `json_extract(payload, '$.chat_id')` + `json_extract(payload, '$.timestamp_ms')` + `json_extract(payload, '$.phone')`, keeping the earliest `timestamp` (first delivery).

### Key Column Inconsistency

The `key` column has 5+ different formats for the same chat_id:
- `bare_id` (e.g., `f3106ee9...`) — most common
- `imessage/f3106ee9...` — prefixed with backend
- `imessage:f3106ee9...` — colon-separated
- `+16175969496` — raw phone number
- `signal/xMuT...` — signal prefixed

**Resolution**: NEVER filter by `key`. Always use `json_extract(payload, '$.chat_id')` which is consistently present (99.8% of records) and always contains the canonical chat_id.

### Payload Schema by Type+Source

**`message.received` / imessage,signal,discord** (the main inbound events):
```json
{
  "chat_id": "f3106ee9...",        // ✅ always present
  "phone": "+16175969496",          // sender phone/UUID
  "text": "message content",       // ✅ present in 99.7% of records
  "is_group": true,
  "group_name": "admin-user1-user2",
  "has_attachments": false,
  "source": "imessage",
  "timestamp_ms": 1773445935913
}
```

**`message.sent` / imessage** (173 records — confirmed sends with text):
```json
{
  "chat_id": "f3106ee9...",
  "text": "we have two claude binaries...",  // ✅ text present
  "is_group": true,
  "success": true
}
```

**`message.sent` / sdk_session** (1,405 records — NO text field):
```json
{
  "chat_id": "f3106ee9...",
  "command": "send-sms \"f3106ee9...\" \"$(cat <<'ENDMSG'\nmessage here\nENDMSG\n)\"",  // text buried in heredoc
  "duration_ms": 198.84
}
```
**Text extraction**: Parse the heredoc from `command` field: extract content between `ENDMSG\n` and `\nENDMSG`. Fall back to `[message sent]` if parsing fails.

### Sender Name Resolution

Build a contact lookup map from sessions.json:
- For each session, map `chat_id → contact_name`
- For group chats, also map individual phone numbers to names using `participants` data
- Signal uses UUIDs for `phone` field (e.g., `a7d4eb2b-bb28-4cb5-ad7b-...`), not phone numbers — need to resolve via sessions.json

## Architecture

### New Files
- `~/dispatch/services/dispatch-api/chat.html` — Single-page chat UI

### Modified Files
- `~/dispatch/services/dispatch-api/server.py` — Add 3 new endpoints + 1 route
- `~/dispatch/services/dispatch-api/dashboard.html` — Add nav link to `/chat`

### API Endpoints (New)

#### 1. `GET /chat` — Serve the HTML page
```python
@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    html_path = Path(__file__).parent / "chat.html"
    return HTMLResponse(content=html_path.read_text())
```

#### 2. `GET /api/chat/conversations` — List all conversations
Returns all active sessions with last message preview, sorted by recency.

**Data source**: `sessions.json` merged with bus.db for last-message previews.

**Response**:
```json
{
  "conversations": [
    {
      "chat_id": "+16175969496",
      "display_name": "Admin User",
      "tier": "admin",
      "source": "imessage",
      "type": "individual",
      "participants": ["Admin User"],
      "last_message": "okay switching gears for a sec",
      "last_message_time": "2026-03-20T21:39:46Z",
      "last_message_is_from_me": false
    }
  ]
}
```

**Efficient query** — single query using `json_extract` for chat_id, deduplicated:
```sql
-- Get most recent message per chat_id in one pass
-- Filter to non-retry sources to avoid duplicates
SELECT json_extract(payload, '$.chat_id') as chat_id,
       payload, timestamp, type, source
FROM (
  SELECT payload, timestamp, type, source,
         ROW_NUMBER() OVER (
           PARTITION BY json_extract(payload, '$.chat_id')
           ORDER BY timestamp DESC
         ) as rn
  FROM records
  WHERE topic = 'messages'
    AND type IN ('message.received', 'message.sent')
    AND source != 'consumer-retry'
) sub
WHERE rn = 1
```

Then merge with sessions.json in Python to attach display_name, tier, source, type, participants. Sort by `last_message_time` descending.

**Reuse**: Factor out session-loading logic from existing `dashboard_sessions()` into a shared `_load_sessions()` helper, used by both endpoints.

#### 3. `GET /api/chat/messages?chat_id={id}&limit=100&before_ts={timestamp}&before_offset={offset}` — Get messages for a conversation
Returns message history for a specific chat, with compound cursor pagination.

**Data source**: bus.db (unified across iMessage + Signal)

**Event types rendered**:
- `message.received` from sources `imessage`, `signal`, `discord` → is_from_me=false
- `message.sent` from sources `imessage`, `sdk_session` → is_from_me=true

**Filtered out by query**: `consumer-retry` source (deduplication), `message.delivered`, `message.queued`, `message.in`, `message.ignored`, `reaction.received`.

**Response**:
```json
{
  "messages": [
    {
      "id": "123",
      "text": "hello!",
      "sender": "Admin User",
      "sender_phone": "+16175969496",
      "is_from_me": false,
      "timestamp": "2026-03-20T21:39:46Z",
      "timestamp_ms": 1773441586000,
      "source": "imessage",
      "has_attachment": false
    }
  ],
  "has_more": true,
  "next_cursor": { "ts": 1773441586000, "offset": 123 }
}
```

**Query**:
```sql
SELECT "offset", type, source, payload, timestamp
FROM records
WHERE topic = 'messages'
  AND json_extract(payload, '$.chat_id') = ?
  AND type IN ('message.received', 'message.sent')
  AND source != 'consumer-retry'
  AND (? IS NULL OR (timestamp < ? OR (timestamp = ? AND "offset" < ?)))
ORDER BY timestamp DESC, "offset" DESC
LIMIT ?
```

**Text extraction logic** (Python):
```python
def extract_text(payload: dict, source: str, type_: str) -> str | None:
    # message.received — text is directly in payload
    if type_ == 'message.received':
        return payload.get('text')

    # message.sent from imessage — text is directly in payload
    if type_ == 'message.sent' and source == 'imessage':
        return payload.get('text')

    # message.sent from sdk_session — text is in heredoc inside command
    if type_ == 'message.sent' and source == 'sdk_session':
        command = payload.get('command', '')
        # Extract between ENDMSG\n and \nENDMSG
        match = re.search(r"ENDMSG\n(.*?)\nENDMSG", command, re.DOTALL)
        if match:
            return match.group(1)
        # Fallback: try simpler quote extraction
        match = re.search(r'"([^"]+)"$', command)
        if match:
            return match.group(1)
        return '[message sent]'

    return None
```

**Sender resolution**:
- `message.received`: Use `payload.phone` → look up in contact map. Signal uses UUIDs, iMessage uses phone numbers.
- `message.sent`: Sender is always "sven" (the assistant).

**Non-text content**:
- If text is None/empty but `payload.has_attachments` is true: render as `[attachment]`
- If text is None/empty and no attachments: skip

**New message polling**: The endpoint also accepts `after_ts` parameter for polling for new messages:
```sql
-- For polling new messages (append to bottom)
SELECT "offset", type, source, payload, timestamp
FROM records
WHERE topic = 'messages'
  AND json_extract(payload, '$.chat_id') = ?
  AND type IN ('message.received', 'message.sent')
  AND source != 'consumer-retry'
  AND timestamp > ?
ORDER BY timestamp ASC, "offset" ASC
LIMIT 50
```

### Performance Note

`json_extract(payload, '$.chat_id')` on 81K records may be slow without an index. Two options:
1. **Create an index**: `CREATE INDEX IF NOT EXISTS idx_records_chat_id ON records(topic, json_extract(payload, '$.chat_id'))` — fastest but requires write access
2. **Filter by key patterns**: Pre-filter using `key LIKE '%{chat_id}%'` to narrow the scan, then verify with `json_extract` — no index needed

Recommend option 1 at startup. The bus.db is ours and we can add indexes.

### Frontend (chat.html)

#### Layout
```
┌─────────────────────────────────────────────────┐
│ DISPATCH / CHAT                    [← Dashboard]│
├──────────────┬──────────────────────────────────┤
│              │                                  │
│  Conversation│    Message Thread                │
│  List        │                                  │
│              │    ┌─ sender name ─────────────┐ │
│  🔍 Search   │    │ message text              │ │
│              │    │ timestamp                 │ │
│  ┌─────────┐ │    └───────────────────────────┘ │
│  │ Admin   │ │                                  │
│  │ last... │ │    ┌─ me ──────────────────────┐ │
│  ├─────────┤ │    │ response text             │ │
│  │ Ryan    │ │    │ timestamp                 │ │
│  │ last... │ │    └───────────────────────────┘ │
│  ├─────────┤ │                                  │
│  │ Group.. │ │                                  │
│  │ last... │ │                                  │
│  └─────────┘ │                                  │
│              │                                  │
└──────────────┴──────────────────────────────────┘
```

- **Sidebar** (300px fixed): Conversation list, filterable by search
- **Main area**: Message thread for selected conversation
- **No input box**: This is read-only (messages are sent via SMS sessions, not this UI)
- **Header**: "DISPATCH / CHAT" with link back to `/dashboard`

#### Sidebar Conversation Items
Each item shows:
- Contact name (bold, Fira Sans) with tier badge (small, inline)
- Source label: `iMessage` or `Signal` in small monospace
- Last message preview (truncated via CSS `text-overflow: ellipsis`, 1 line, secondary text color)
- Relative timestamp ("5m ago", "2h ago", "yesterday")
- Selected conversation: blue left border (4px)
- Group chats show participant count from sessions.json `participants` array

#### Message Thread

**Scroll Architecture** (critical — this is the hardest part):

1. **Container uses `flex-direction: column-reverse`** — browser natively anchors to the bottom. Messages array is rendered in reverse order. This gives us auto-scroll-to-bottom for free.

2. **Infinite scroll up (loading older messages)**:
   - `IntersectionObserver` on a sentinel element at the top of the message list
   - When sentinel becomes visible → fetch older messages using `before_ts`/`before_offset` cursor
   - **Scroll position preservation on prepend**: With `column-reverse`, prepending older messages to the DOM end naturally preserves scroll position — no manual scrollTop adjustment needed.
   - Show a loading spinner while fetching
   - Set `has_more = false` to stop observing when no more messages

3. **New message polling (5s interval)**:
   - Track the most recent message `timestamp`
   - Poll with `after_ts` parameter to get only new messages
   - Prepend new messages to DOM start (visual bottom with column-reverse)
   - Only auto-scroll to new messages if user is already at the bottom
   - **"At bottom" detection**: `container.scrollTop >= -50` (with column-reverse, scrollTop 0 = bottom)

**Message rendering**:
- Messages grouped by sender (consecutive messages from same sender collapse under one name header)
- **Incoming messages**: Left-aligned, subtle blue left-border (3px `rgba(37, 99, 235, 0.4)`), sender name in Fira Code above group
- **Outgoing messages (me/Sven)**: Left-aligned, green left-border (3px `rgba(34, 197, 94, 0.4)`), "sven" label
- Message body in Fira Sans (14px) for readability
- Timestamps per-message in Fira Code (11px, tertiary color)
- Whitespace preserved (`white-space: pre-wrap`)
- **URLs linkified**: Regex to detect URLs and wrap in `<a>` tags (open in new tab)
- **Group chats**: Color-code sender names using a deterministic hash → hue rotation
- **Attachments**: Show `[attachment]` in italic, tertiary color

#### Search
- Text input at top of sidebar
- Filters conversation list by contact name (client-side filter)
- No full-text message search (v1)

#### Cross-Navigation
- Header has `← Dashboard` link to `/dashboard`
- Dashboard nav sidebar gets a new "Chat" nav item linking to `/chat`

### Polling

- **Conversation list**: Poll every 10 seconds
- **Active message thread**: Poll every 5 seconds for new messages via `after_ts`
- **Visibility-aware**: Use `document.visibilitychange` listener to pause all polling when tab is hidden, resume when tab becomes visible again
- **Error handling**: On fetch failure, show a subtle warning banner (like dashboard's connection-loss banner), retry on next interval

### Error & Loading States

- **Loading conversations**: Show skeleton/placeholder items in sidebar
- **Loading messages**: Show centered spinner in message area
- **API error**: Subtle red banner at top "Connection lost — retrying..." (auto-dismiss on recovery)
- **Empty conversation**: "No messages yet" centered in message area
- **No conversations**: "No active conversations" centered in sidebar

## Implementation Order

1. Audit bus.db: create `json_extract` index on chat_id for performance ✅ (documented above)
2. Add shared `_load_sessions()` helper (refactor from `dashboard_sessions()`)
3. Add `/api/chat/conversations` endpoint with deduplication
4. Add `/api/chat/messages` endpoint with text extraction + `after_ts` support
5. Build `chat.html` with embedded CSS + JS
6. Add `GET /chat` route to serve the page
7. Add "Chat" nav link to `dashboard.html`
8. Test in Chrome

## Edge Cases

- **Empty conversations**: Show "No messages yet" in thread area
- **No conversations**: Show "No active conversations" in sidebar
- **Long messages**: Word-wrap via `white-space: pre-wrap`, preserve newlines
- **Group chats**: Show all participant names, color-code by sender via hash
- **Mixed sources**: A contact might have both iMessage and Signal sessions — show as separate conversations (they have different chat_ids)
- **Bus.db missing messages**: Early conversations might not be in bus.db if it was added later. Show what's available.
- **Attachments**: Show `[attachment]` placeholder for messages with attachments but no text
- **Blank messages**: Skip messages with no text and no attachments
- **URLs in messages**: Auto-linkify with regex, open in new tab
- **Concurrent timestamps**: Compound cursor `(timestamp, offset)` prevents message skipping
- **consumer-retry duplicates**: Excluded by `source != 'consumer-retry'` filter
- **sdk_session sent messages**: Text extracted from heredoc in `command` field; falls back to `[message sent]`
- **Signal UUIDs**: `phone` field contains UUIDs not phone numbers — resolved via sessions.json contact map
- **Sessions without bus.db data**: Show in sidebar (from sessions.json) but display "No messages in bus" in thread
- **Timezone**: All timestamps stored as Unix ms in bus.db, converted to ISO8601 in API response, displayed as relative time in UI
