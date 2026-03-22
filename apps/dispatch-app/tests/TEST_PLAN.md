# Dispatch App E2E Test Plan

## Critical User Journeys (CUJs)

### Tab 1: Admin Agents (Chat List)

| # | CUJ | Description | Testable |
|---|-----|-------------|----------|
| C1 | View chat list | App loads, shows all chats with title, preview, timestamp, unread dots | E2E |
| ~~C2~~ | ~~Search chats~~ | ~~REMOVED: search bar does not exist on chat list~~ | N/A |
| C3 | Create new chat | Tap FAB (+), new chat created, navigates to detail | E2E |
| C4 | Open chat | Tap a chat row, navigates to chat detail screen | E2E |
| ~~C5~~ | ~~Delete chat (swipe)~~ | ~~Swipe left on chat, tap delete~~ | **Manual only** (gesture) |
| C6 | Delete chat (long-press) | Long-press chat, confirm deletion, chat removed | E2E |
| C7 | Unread indicator | Chat with new messages shows blue dot and bold styling | E2E |
| C8 | Thinking indicator | Chat with is_thinking shows animated dots in list row | E2E |
| ~~C9~~ | ~~Pull to refresh~~ | ~~Pull down on list, data refreshes~~ | **Manual only** (gesture) |
| C4-empty | Empty chat list | No chats shows "No conversations yet" message | E2E |
| C4-error | Chat list error | API failure shows error banner | E2E |

### Tab 1 Detail: Chat Conversation

| # | CUJ | Description | Testable |
|---|-----|-------------|----------|
| C10 | View messages | Open chat, see message history (user right, assistant left) | E2E |
| C11 | Send text message | Type text, tap send, message appears as pending then delivered | E2E |
| C12 | Send message with image | Pick image, add text, send, both appear in chat | **Manual only** (file picker) |
| C13 | Paste clipboard image | Focus input with image in clipboard, paste bar appears, tap to paste | **Manual only** (clipboard) |
| ~~C14~~ | ~~Voice dictation~~ | ~~Tap mic, speak, see live transcript~~ | **Manual only** (native API) |
| C15 | Expand/collapse long messages | Messages >840 chars show truncated with "Show more" | E2E |
| C16 | View message timestamp | Tap message bubble, timestamp appears/disappears | E2E |
| C17 | Retry failed message | Failed message shows "Not Delivered" + retry button, tap to retry | E2E |
| C18 | Play audio (TTS) | Tap play button on assistant message, audio generates and plays | **Manual only** (audio) |
| C19 | View inline image | Assistant message with image shows inline, tappable | E2E (presence only) |
| C20 | Open image viewer | Tap inline image, full-screen modal opens | E2E (navigation) |
| ~~C21~~ | ~~Save image~~ | ~~In image viewer, tap Save to Photos~~ | **Manual only** (native) |
| ~~C22~~ | ~~Share image~~ | ~~In image viewer, tap Share~~ | **Manual only** (native) |
| C23 | Rename chat | Tap rename button in header, enter new name, title updates | E2E |
| C24 | Thinking indicator in chat | While assistant processes, animated dots appear | E2E (DOM presence) |
| C25 | Empty chat state | New chat shows "No messages yet" empty state | E2E |
| C-image-remove | Image removal | Selected image preview shows X button, tap to remove | **Manual only** (image picker) |
| C-thinking-expand | ThinkingIndicator expand | Tap thinking dots to expand SDK event list | E2E (DOM presence) |

### Tab 2: Sessions

| # | CUJ | Description | Testable |
|---|-----|-------------|----------|
| S1 | View session list | See all sessions with name, status dot, tier/source badges | E2E |
| S2 | Search sessions | Type in search, list filters by session name | E2E |
| S3 | Filter by source | Tap filter pills (All, iMessage, Signal, Discord, Dispatch-API) | E2E |
| S4 | Create new session | Tap FAB (+), enter name, session created | E2E |
| S5 | Open session | Tap session row, navigates to session detail | E2E |
| S6 | Session status colors | Green (active), gray (idle), red (error) | E2E (DOM presence) |
| ~~S7~~ | ~~Pull to refresh~~ | ~~Pull down, data refreshes~~ | **Manual only** (gesture) |
| S-empty | Empty sessions | No sessions shows "No agent sessions" message | E2E |

### Tab 2 Detail: Session Conversation

| # | CUJ | Description | Testable |
|---|-----|-------------|----------|
| S8 | View session messages | Open session, see message history | E2E |
| S9 | Send message to session | Type text, send (dispatch-api sessions only) | E2E |
| S10 | Toggle Messages/SDK Events | Tap toggle, view changes between modes | E2E |
| S11 | View SDK events | See event list with type badges, tool names, durations, payloads | E2E |
| S12 | Expand SDK event payload | Tap long payload, expands to full content | E2E |
| S13 | SDK event timestamps | Tap event, timestamp + turn number shown | E2E (presence) |
| S14 | Rename session | Tap rename button (dispatch-api only), enter name | E2E |
| S15 | Delete session | Tap delete button (dispatch-api only), confirm | E2E |
| S16 | Thinking indicator | While session processes, animated dots appear | E2E (DOM presence) |
| S17 | Error events | Error SDK events show red highlighting | E2E |
| S-inputbar | InputBar visibility | InputBar only shown for dispatch-api session type | E2E |
| S-rename-hidden | Rename/Delete hidden | Rename/Delete buttons hidden for contact sessions | E2E |

### Tab 3: Dashboard

| # | CUJ | Description | Testable |
|---|-----|-------------|----------|
| D1 | Dashboard fallback on web | WebView not available in web build, shows fallback UI with "Open in Browser" | E2E |

### Tab 4: Settings

| # | CUJ | Description | Testable |
|---|-----|-------------|----------|
| ST1 | View settings | See connection status, API URL, device token, debug options | E2E |
| ST2 | Change API URL | Tap server URL, enter new URL, connection re-checks | E2E |
| ST3 | Connection status | Shows Connected/Disconnected with colored dot | E2E |
| ST4 | Copy device token | Tap device token, shows "Copied!" feedback | E2E |
| ST5 | View logs | Tap Logs, navigates to logs screen | E2E (via Logs tests) |
| ST6 | Restart session | Tap restart, confirm, session restarts | E2E |
| ST7 | Clear notifications | Tap clear, notifications and badge cleared | E2E |
| ST8 | Reset to default URL | Tap reset button, URL reverts to default | E2E |

### Logs Screen

| # | CUJ | Description | Testable |
|---|-----|-------------|----------|
| L1 | View logs | See log lines with line numbers | E2E |
| L2 | Switch log files | Tap file tabs (manager, dispatch-api, client, signal, watchdog) | E2E |
| L3 | Auto-scroll | Toggle auto-scroll on/off, new lines auto-scroll when on | **Manual only** (timing) |
| L4 | Color-coded lines | ERROR lines red, WARNING yellow, INFO normal | E2E (content presence) |
| L-empty | Empty logs | No logs shows "No logs found" | E2E |

### Cross-cutting

| # | CUJ | Description | Testable |
|---|-----|-------------|----------|
| X1 | Tab navigation | Switch between all 4 tabs, content persists correctly | E2E |
| X2 | Deep navigation + tab switch | Enter chat detail, switch tab, switch back | E2E |
| X3 | Error handling | API failure shows error banner/message | E2E |
| X4 | Empty states | Screens with no data show appropriate empty messages | E2E |
| X5 | Mobile viewport | App renders correctly at iPhone dimensions (390x844) | E2E |
| X6 | Desktop viewport | App renders correctly at desktop dimensions (1280x800) | E2E |

---

## Mock Strategy

**All tests use a mock API server** via Playwright `page.route()` that intercepts ALL requests to the API. No real sessions, databases, or Claude sessions are touched.

### Mock Server Setup (`tests/fixtures/mock-server.ts`)

A Playwright route handler intercepts all API requests and returns canned responses:

- `GET /chats` - Returns 3 mock chats (one with unread, one thinking, one normal)
- `POST /chats` - Returns a new chat with provided title
- `PATCH /chats/:id` - Returns updated chat
- `DELETE /chats/:id` - Returns `{ ok: true }`
- `GET /messages` - Returns mock messages (user + assistant, one with image, one long)
- `POST /prompt` - Returns `{ status: "ok", message: "queued", request_id: "mock-123" }`
- `POST /prompt-with-image` - Returns same as above (handles FormData)
- `POST /chats/:id/open` - Returns `{ status: "ok" }`
- `DELETE /messages` - Returns `{ status: "ok", message: "cleared" }`
- `POST /restart-session` - Returns `{ status: "ok", message: "restarted" }`
- `GET /api/agents/sessions` - Returns mock sessions (various tiers, sources, statuses)
- `POST /api/agents/sessions` - Returns new session
- `PATCH /api/agents/sessions/:id` - Returns renamed session
- `DELETE /api/agents/sessions/:id` - Returns `{ ok: true }`
- `GET /api/agents/messages` - Returns mock agent messages
- `POST /api/agents/messages` - Returns `{ ok: true }`
- `GET /api/agents/sdk-events` - Returns mock SDK events (tool_use, tool_result, error)
- `GET /api/dashboard/logs` - Returns mock log lines
- `GET /health` - Returns `{ status: "ok" }`
- `GET /audio/*` - Returns a minimal WAV file (44 bytes)
- `GET /images/*` - Returns a 1x1 transparent PNG

### Scenario Support

Each mock data category can be set to one of: `normal`, `empty`, `error`, `thinking`.

```typescript
const server = await setupMockServer(page);
server.state.chats = "empty";      // Empty state
server.state.messages = "error";   // Error state
server.setError("/prompt");        // Force specific endpoint to 500
```

### Key Mock Data

**Mock Chats:**
1. "Test Chat Alpha" - has unread messages (last_message_at > last_opened_at, role=assistant)
2. "Test Chat Beta" - is_thinking: true, last message from user
3. "Test Chat Gamma" - normal, read (last_opened_at > last_message_at)

**Mock Messages (for Chat Alpha):**
1. User: "Hello, can you help me?" (text only)
2. Assistant: "Of course! How can I assist you today?" (text + audio_url)
3. User: "Check this image" (text + image)
4. Assistant: 900-char message to test expand/collapse (> 840 char threshold)
5. Assistant: Message with image_url for inline image testing

**Mock Sessions:**
1. "Alice Johnson" - contact, iMessage, **active**, admin tier
2. "Bob Smith" - contact, Signal, **idle**, family tier
3. "My Test Agent" - dispatch-api, **active**, admin tier
4. "Discord Bot Channel" - contact, Discord, **error**, favorite tier

**Mock SDK Events:**
1. tool_use: "Bash" with payload, tool_use_id "tu-1"
2. tool_result: "Bash" with output payload, 1500ms duration
3. tool_use: "Read" with short payload, 200ms duration
4. tool_result: "Read" with output
5. result: final response (turn complete)
6. tool_use: "Write" with is_error: true (error event)

**Mock Logs:**
Lines with mixed INFO, WARNING, ERROR levels for color testing.

### Dialog Handling

On web, `showPrompt()`, `showDestructiveConfirm()`, and `showAlert()` use native `window.prompt`, `window.confirm`, and `window.alert`. Tests handle these via `page.on('dialog')`.
