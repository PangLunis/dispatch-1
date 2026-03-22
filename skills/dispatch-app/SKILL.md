---
name: dispatch-app
description: Dispatch mobile app — Expo/React Native frontend, FastAPI backend (dispatch-api), message bus, TTS, push notifications, reply CLIs. Trigger words - dispatch app, sven app, expo, ios app, mobile app, react native, reply-sven, push notification, dispatch-api, api server, dispatch api.
---

# Dispatch App

Full-stack mobile app for the dispatch personal assistant. Frontend (Expo/React Native) + backend API (FastAPI/dispatch-api) + message bus, TTS, and push notifications.

- **Frontend code**: `~/dispatch/apps/dispatch-app/`
- **Backend API code**: `~/dispatch/services/dispatch-api/`
- **Legacy symlink**: `~/.claude/skills/sven-app` → `~/.claude/skills/dispatch-app`
- **Legacy symlink**: `~/.claude/skills/dispatch-api` → `~/.claude/skills/dispatch-app`

---

## Setup for New Instances (e.g. Pang)

To deploy the dispatch-app + dispatch-api on a new machine (e.g. Ryan's Pang), follow these steps:

### 1. Config (Backend)

Create `~/dispatch/config.local.yaml` with your assistant name:

```yaml
assistant:
  name: "Pang"  # Drives session prefix (pang-app:), display name, etc.
  email: "your-assistant@example.com"

owner:
  name: "Ryan"
  phone: "+1XXXXXXXXXX"
  email: "owner@example.com"
```

The dispatch-api server reads `assistant.name` from this config. It derives:
- **Session prefix**: `{name.lower()}-app` (e.g. `pang-app`)
- **Display name**: Used in dashboard and API responses
- **Infrastructure files**: `dispatch-messages.db`, `dispatch-audio/`, etc. (generic, shared across all instances)

### 2. Config (Mobile App)

Create `~/dispatch/apps/dispatch-app/app.yaml` (gitignored):

```yaml
appName: Pang
displayName: Pang
bundleIdentifier: com.yourname.pang
apiHost: YOUR_TAILSCALE_IP:9091
sessionPrefix: pang-app
accentColor: "#3478f7"
scheme: pang
iconPath: ./assets/images/icon.png
adaptiveIconPath: ./assets/images/adaptive-icon.png
splashColor: "#09090b"

speechCorrections:
  pang: Pang
  peng: Pang
```

Key fields:
- **`sessionPrefix`**: Must match what `config.local.yaml`'s `assistant.name` produces (`{name.lower()}-app`)
- **`apiHost`**: Your Tailscale IP + port (e.g. `100.x.x.x:9091`)
- **`bundleIdentifier`**: Unique per device/app

### 3. Backend Setup

The app backend must be registered in `~/dispatch/assistant/backends.py`. For a new assistant name, add a backend entry:

```python
"pang-app": BackendConfig(
    name="pang-app",
    label="PANG_APP",
    session_suffix="-pang-app",
    registry_prefix="pang-app:",
    send_cmd='~/.claude/skills/dispatch-app/scripts/reply-sven "{chat_id}"',
    send_group_cmd='~/.claude/skills/dispatch-app/scripts/reply-sven "{chat_id}"',
    history_cmd="",
    supports_image_context=True,
),
```

> **TODO**: Make backends.py auto-derive the app backend from `config.local.yaml` instead of hardcoding.

### 4. Build & Run

```bash
# Start the API server
cd ~/dispatch/services/dispatch-api && nohup uv run server.py > ~/dispatch/logs/dispatch-api.log 2>&1 &

# Build the mobile app (iOS)
cd ~/dispatch/apps/dispatch-app
npm install
npx expo prebuild --clean --platform ios
npx expo run:ios --device "DEVICE_UDID"
```

### 5. Allowed Tokens

On first app launch, register the device token:
```bash
# The app auto-generates a UUID token on first launch
# Add it to ~/dispatch/services/dispatch-api/allowed_tokens.json
```

---

## Backend API (dispatch-api)

FastAPI server providing the API backend for the app and system dashboard.

### Quick Reference

| Item | Value |
|------|-------|
| Location | `~/dispatch/services/dispatch-api/` |
| Health check | `curl -s http://localhost:9091/health` |
| Check if running | `lsof -ti tcp:9091 -sTCP:LISTEN` |
| Start | `cd ~/dispatch/services/dispatch-api && uv run server.py` |
| Logs | `~/dispatch/logs/dispatch-api.log` |

### Starting the Server

**CRITICAL: The ONLY correct way to start dispatch-api:**

```bash
cd ~/dispatch/services/dispatch-api && uv run server.py
```

**Never do any of these:**
- `uvicorn server:app` — fails because fastapi dependency comes from PEP 723 inline metadata
- `source .venv && uvicorn ...` — no .venv exists
- `python3 server.py` — always use `uv run`
- `kill -HUP <pid>` — silently kills the process instead of restarting

### Restarting

```bash
# 1. Check if running
PID=$(lsof -ti tcp:9091 -sTCP:LISTEN)

# 2. Kill existing process (if any)
[ -n "$PID" ] && kill "$PID"

# 3. Start fresh
cd ~/dispatch/services/dispatch-api && nohup uv run server.py > ~/dispatch/logs/dispatch-api.log 2>&1 &

# 4. Verify
sleep 2 && curl -s http://localhost:9091/health
```

### Server Architecture

The server loads `~/dispatch/config.local.yaml` at startup to derive:
- `ASSISTANT_NAME` — from `assistant.name` (default: "Dispatch")
- `APP_SESSION_PREFIX` — `{name.lower()}-app` (e.g. "sven-app", "pang-app")

These drive session routing, display names, and SDK event lookups.

### Key Endpoints

#### App Endpoints
- `POST /prompt` — receive voice transcript, inject into session
- `POST /prompt-with-image` — receive transcript + image (multipart/form-data)
- `GET /messages?since=<timestamp>&chat_id=<id>` — poll for new messages
- `GET /audio/<message_id>` — download TTS audio file
- `POST /restart-session` — restart a Claude session

#### Multi-Chat
- `POST /chats` — create a new chat
- `GET /chats` — list all chats (includes `is_thinking` status)
- `PATCH /chats/{chat_id}` — rename a chat
- `DELETE /chats/{chat_id}` — delete chat + messages + session

#### System Dashboard
- `GET /` — main dashboard HTML
- `GET /health` — health check

---

## Frontend (Expo/React Native)

### Quick Reference

```bash
cd ~/dispatch/apps/dispatch-app

# Lint (ALWAYS before committing)
npm run lint

# Web build (served by dispatch-api at /app/)
npx expo export --platform web

# iOS dev build
npx expo run:ios --device "DEVICE_UDID"

# iOS clean rebuild (after native config changes)
npx expo prebuild --clean --platform ios
npx expo run:ios --device "DEVICE_UDID"
```

### Architecture

- **Polling-based** — no WebSocket. Chat list polls every 3s, messages every 1.5s
- **Device token auth** — UUID generated on first launch, registered via POST /register
- **API URL configurable** at runtime via Settings tab

### Key Files

| Path | Purpose |
|------|---------|
| `app/chat/[id].tsx` | Chat detail screen |
| `app/agents/[id].tsx` | Agent session detail screen |
| `app/(tabs)/index.tsx` | Chat list screen |
| `src/config/branding.ts` | App name, accent color, session prefix |
| `app.config.ts` | Expo config (reads app.yaml) |
| `app.yaml` | Per-instance config (gitignored) |
| `config.default.json` | Default runtime config |

### Naming Convention

The codebase uses generic names everywhere. Instance-specific branding comes from `app.yaml`:
- `app.yaml` — display name, bundle ID, voice corrections, session prefix
- `src/config/branding.ts` — exports `branding` and `sessionPrefix` from Expo config

Do NOT add instance-specific names to app code, component names, or file names.

---

## Backend (Message Bus + TTS + Push)

### Message Bus (SQLite)

Location: `~/dispatch/state/dispatch-messages.db`

### reply-sven CLI

Location: `~/.claude/skills/dispatch-app/scripts/reply-sven`

Called by Claude to send responses. Stores message in SQLite, generates TTS audio on demand, and sends push notification.

### Sessions (Multi-Chat)

Each chat in the app gets its own dedicated SDK session:

| Item | Format |
|------|--------|
| Session name | `{session_prefix}/{session_prefix}:<uuid>` |
| Transcript dir | `~/transcripts/{session_prefix}/{session_prefix}:<uuid>/` |
| Tier | admin (full access) |

---

## is_thinking Detection

The app shows "thinking dots" when a session is actively processing. This uses the daemon's BUSY flag via a shared `session_states` table in bus.db.

### How It Works

1. **Daemon writes**: `sdk_session.py` calls `producer.set_session_busy(session_name, True/False)` at transition points:
   - `True` when `_pending_queries` goes 0→1 (query starts)
   - `False` on ResultMessage, query errors, and session shutdown (finally block)

2. **Table**: `session_states` in bus.db — one row per session, upserted on state changes:
   ```sql
   CREATE TABLE session_states (
       session_name TEXT PRIMARY KEY,
       is_busy INTEGER NOT NULL DEFAULT 0,
       updated_at INTEGER NOT NULL
   ) WITHOUT ROWID;
   ```

3. **dispatch-api reads**: `_check_is_thinking(session_name)` does a single PK lookup on `session_states`. Returns `True` if `is_busy=1` and `updated_at` is within 5 minutes (staleness guard for daemon crashes).

4. **Frontend polls**: `/chats` and `/messages` endpoints include `is_thinking` field. App polls every 3s (chat list) and 1.5s (messages).

### Why Not a Time Window?

Previously used a 30-second window on `sdk_events` — checked if the latest event was within 30s and not a "result". This had false negatives during long subagent calls or gaps between turn injection and first tool_use. The BUSY flag is authoritative and has no window limitations.

---

## Common Gotchas

### Adding native Expo modules (e.g. expo-network, expo-camera)

When you add a new native Expo module:

1. **Install**: `bun add expo-network` (or `npx expo install expo-network`)
2. **Pod install**: `cd ios && pod install` — native modules need CocoaPods linking
3. **Native rebuild required**: `npx expo run:ios --device "DEVICE_NAME"` — JS-only metro reload is NOT enough
4. **Clear metro cache**: If the app still shows "Unable to resolve module", kill ALL metro processes and restart with `npx expo start --clear`

**The full sequence when you hit "Unable to resolve module" for a native package:**
```bash
cd ~/dispatch/apps/dispatch-app

# 1. Verify the package is in node_modules
ls node_modules/expo-network

# 2. Install pods (often the missing step)
cd ios && pod install && cd ..

# 3. Kill any stale metro bundlers
pkill -f metro; pkill -f "expo start"; pkill -f "expo run"

# 4. Rebuild native + start fresh metro
npx expo run:ios --device "Nikhil iPhone 16"
```

**Key insight**: If pods are missing but node_modules has the package, the native build will succeed but metro will fail to resolve the module at JS bundle time. Old metro processes with stale caches make this worse — always kill them before rebuilding.

### Finding device names for `--device`

```bash
xcrun xctrace list devices  # Lists all connected devices + simulators
```

### Message pagination — NEWEST N, not oldest
The SQL MUST use a subquery to get the NEWEST 200:
```sql
SELECT * FROM (SELECT ... ORDER BY created_at DESC LIMIT 200) ORDER BY created_at ASC
```

### Web build path
The web build is served from `~/dispatch/apps/dispatch-app/dist/`.

### Expo Fast Refresh
Fast Refresh preserves React state across file edits. `useState` initializers are IGNORED during hot reload.

---

## Remaining Hardcoded Items (Follow-up)

These items still reference "sven" and need future refactoring:

1. **`backends.py`** — The `sven-app` backend entry is hardcoded. Should auto-derive from `config.local.yaml`.
2. **`cli.py`** — The `--sven-app` flag on `inject-prompt`. Consider renaming to `--app`.
3. **`~/.claude/skills/sven-app/`** — Skill directory name. Currently symlinked to `dispatch-app`.
4. **`reply-sven` script name** — Should be renamed to `reply-app` or similar.
5. **`tests/test_sven_app.py`** — Test file references `sven-app` backend by name.
6. **`readers.py`** — Has `sven-app` backend-specific reader class.
7. **`common.py`** — Has `sven-app` source check for reply command routing.

---

---

## Manual Testing (Simulator)

Comprehensive test plan for all Critical User Journeys (CUJs). Run in the iOS Simulator.

### Test Constants

These values are referenced throughout. Update here if the app changes.

| Constant | Value | Source |
|----------|-------|--------|
| API port | `9091` | `~/dispatch/services/dispatch-api/server.py` |
| Chat list poll interval | 3s | `MESSAGE_POLL_INTERVAL` |
| Message poll interval | 1.5s | `MESSAGE_POLL_INTERVAL` |
| SDK events poll interval | 2s | `useSdkEvents.ts` |
| Text truncation threshold | 840 chars | `MessageBubble.tsx` `MAX_COLLAPSED_LENGTH` |
| Input max length | 10,000 chars | `InputBar.tsx` |
| Message bubble max width | 85% of screen | `MessageBubble.tsx` |
| Image thumbnail preview | 72×72px | `InputBar.tsx` |
| Connection auto-retry | 5s | `settings.tsx` |

### Glossary

| Term | Meaning |
|------|---------|
| **FAB** | Floating Action Button — the circular **+** button (56×56px, accent-colored) pinned to the bottom-right corner |
| **Lazy TTS** | Text-to-speech audio generated on-demand the first time you tap play, then cached for instant replay |
| **SDK Events** | Real-time log of Claude's tool executions (Bash → "Running command", Read → "Reading file", etc.) |
| **Agent session** | A persistent Claude conversation — either a contact session (iMessage/Signal) or a dispatch-api session (app-created) |
| **Thinking indicator** | Animated 3-dot bubble (bottom-left, assistant style) that appears while Claude is processing |
| **Device token** | UUID generated on first app launch, used to authenticate API requests |

### UI Layout Reference

**Chat List screen:**
```
┌───────────────────────────────────┐
│             Chats                 │  ← Header
├───────────────────────────────────┤
│ ┌───────────────────────────────┐ │
│ │ Chat Title             2m ago │ │  ← Chat row (swipe right → red Delete)
│ │ Last message preview...       │ │
│ └───────────────────────────────┘ │
│ ┌───────────────────────────────┐ │
│ │ Another Chat           1h ago │ │
│ │ Preview text...               │ │
│ └───────────────────────────────┘ │
│                             [+]   │  ← FAB (bottom-right)
├───────────────────────────────────┤
│ [Chats] [Agents] [Dashboard] [⚙] │  ← Tab bar
└───────────────────────────────────┘

Empty state: "No conversations yet" / "Tap + to start a new chat"
```

**Chat Detail screen:**
```
┌───────────────────────────────────┐
│ [← Chats]  Chat Title   [Rename] │  ← Header
├───────────────────────────────────┤
│                                   │
│  ┌──────────────────┐             │  ← Assistant bubble (left, #27272a)
│  │ Response text     │ [▶][↓]     │     [▶] = play audio, [↓] = save image
│  └──────────────────┘             │
│         ┌──────────────────┐      │  ← User bubble (right, accent color)
│         │ Your message     │      │
│         └──────────────────┘      │
│                                   │
│  ⬤ ⬤ ⬤                          │  ← Thinking indicator (when active)
├───────────────────────────────────┤
│ [+img] [  Message...  ] [🎤/↑]   │  ← Input bar
└───────────────────────────────────┘
```

### Prerequisites

```bash
# 1. Start the API server
cd ~/dispatch/services/dispatch-api && nohup uv run server.py > ~/dispatch/logs/dispatch-api.log 2>&1 &

# 2. Verify it's running (expect: {"status": "ok"})
curl -s http://localhost:9091/health

# 3. Build & launch in simulator
cd ~/dispatch/apps/dispatch-app
npm install
npx expo prebuild --clean --platform ios
npx expo run:ios  # launches default simulator

# 4. Ensure the daemon is running (needed for session creation & is_thinking)
claude-assistant status

# 5. First launch: configure API URL
#    Settings tab → API Server → enter "http://localhost:9091"
```

> **Tip**: Add test photos to the simulator by dragging image files onto the simulator window.

---

### CUJ 1: Chat List & Create Chat

1. App opens to **Chats** tab — verify either:
   - Existing chats appear as a scrollable list with title, last message preview, and relative timestamp, OR
   - Empty state shows "No conversations yet" with subtitle "Tap + to start a new chat"
2. **Pull-to-refresh**: Pull down on the chat list — verify a loading spinner appears briefly, then list reloads
3. Tap the **+ FAB** (blue circle, bottom-right) — a new chat screen opens with empty state: "No messages yet / Send a message to start the conversation"
4. Tap **← Chats** to go back — verify the new chat now appears in the list with title "New Chat"

### CUJ 2: Send Text Message (First Message Flow)

1. Open a chat (or create a new one)
2. Verify the input bar shows: `[+ image picker]` on the left, text field with placeholder "Message {AppName}...", and a **microphone icon** on the right (send button is hidden when input is empty)
3. Type `hello` — verify the mic icon is replaced by a **blue ↑ send button**
4. Tap send — verify:
   - Your message appears as a right-aligned bubble (accent color) with reduced opacity (pending state)
   - Within the chat list poll interval (see Test Constants), an assistant response appears as a left-aligned bubble (#27272a dark gray)
   - Your message returns to full opacity
5. If this was the first message in a new chat, go back to chat list — verify the chat title auto-updated from "New Chat" to a title derived from your message

### CUJ 3: Send Message with Image

1. Open a chat
2. Tap the **+ button** (dark gray circle, left of text input) — the system photo picker opens
3. Select a photo — verify a 72×72px thumbnail preview appears above the input bar with an **× remove button** (small circle, top-right of thumbnail)
4. Type `what's in this image?` in the text field, then tap **↑ send**
5. Verify your message bubble contains both the image (full-width, 4:3 aspect ratio) and the text
6. Verify the assistant responds with a description of the image
7. **Remove before sending**: Tap **×** on the thumbnail — verify it disappears and the image picker button returns
8. **Clipboard paste**: Copy any image to clipboard, then tap the text input field — verify a bar appears above the input: "📋 Paste image from clipboard" (tap it to attach)

### CUJ 4: Voice Dictation

1. Open a chat — verify the **mic button** (gray microphone icon, right side) is visible when the text field is empty
2. Tap the mic — grant microphone permission if prompted
3. Verify the input border turns **red**, placeholder changes to "Listening...", and the mic button is replaced by a **red square stop button**
4. Speak "hello world" — verify text appears in the input field as you speak (interim results update in real-time)
5. Tap the **red stop button** — verify dictation stops, final text remains in the input field
6. Tap **↑ send** to submit the dictated text

> **Note**: Simulator uses your Mac's microphone. Speech recognition requires network connectivity.

### CUJ 5: Rename Chat

1. Open a chat — verify the header shows the chat title with a **"Rename"** button (accent-colored text, right side of header)
2. Tap **Rename** — a prompt dialog appears with title "Rename Chat"
3. Enter "Test Conversation" and confirm
4. Verify the header title updates to "Test Conversation"
5. Go back to chat list — verify the updated title appears there too

### CUJ 6: Delete Chat

1. On the chat list, **swipe a chat row to the right** — a red panel (80px wide) slides in from the right with "Delete" text
2. Tap **Delete** — a confirmation dialog appears
3. Confirm — verify the chat disappears from the list immediately (optimistic delete)
4. **Multi-chat safety**: If you have other chats, verify they are completely unaffected (still present, messages intact)

### CUJ 7: Audio Playback (Lazy TTS)

> **Requires**: Kokoro TTS installed at `~/.claude/skills/tts/`.

1. Open a chat with at least one assistant message
2. Find the **▶ play button** (small dark circle with triangle, to the right of the assistant's message bubble)
3. Tap ▶ — verify:
   - Button changes to a **spinner** (generating TTS for the first time — may take 2-5 seconds)
   - Once generated, audio plays and the button becomes **‖ pause** (two vertical bars)
   - Audio plays even if the device is in silent mode
4. Tap **‖ pause** — verify playback pauses (button returns to ▶)
5. Tap **▶** again — verify playback resumes from where it paused (not from the beginning)
6. Let audio finish — verify button returns to ▶ automatically
7. Tap ▶ a second time — verify audio starts **instantly** (cached, no spinner)

### CUJ 8: Thinking Indicator & SDK Events

> **Requires**: Daemon running (`claude-assistant status` shows active).

1. Send a message that triggers multi-step processing, e.g.: `search the web for the latest news about AI`
2. Within 1-2 seconds, verify the **thinking indicator** appears: three gray pulsing dots (8×8px each) in an assistant-style bubble above the input bar, with a small **▾ chevron**
3. Tap the thinking bubble — verify it expands to show a scrolling list of SDK events with labels like:
   - "Searching the web" (for WebSearch tool)
   - "Fetching webpage" (for WebFetch)
   - "Running command" (for Bash)
   - Completed steps show a blue **✓** checkmark with duration (e.g., "2.5s")
   - Active step shows a purple **●** dot
4. Tap the expanded indicator again (▴ chevron) — verify it collapses back to 3 dots
5. When the assistant's response arrives, verify the thinking indicator disappears completely

### CUJ 9: Agent Sessions

1. Switch to the **Agents** tab (second tab in tab bar)
2. Verify either:
   - Existing agent/contact sessions appear in a list, OR
   - Empty state: "No agent sessions / Tap + to create a new agent session"
3. **Filter**: Tap filter pills at the top — "All", "Contact", "Dispatch API" — verify the list filters correctly
4. **Search**: Type a session name in the search bar — verify results filter in real-time
5. **Create**: Tap the **+ FAB** — enter a name (e.g., "Test Agent") — verify a new session opens
6. The session detail screen shows:
   - Header with session name and tier/source badges (e.g., "Admin", "Dispatch API")
   - Two tabs: **Messages** and **SDK Events**
7. **Send message**: Type a message and send (input bar only shows for dispatch-api type sessions)
8. **Rename**: Tap **Rename** in header → enter new name → verify it updates (dispatch-api sessions only)
9. **Delete**: Tap **Delete** (red text) → confirm dialog → verify session removed from list (dispatch-api sessions only)

### CUJ 10: Settings

1. Switch to **Settings** tab (rightmost tab) — verify the header shows the app name, "v1.0.0", and "Powered by Claude"
2. **CONNECTION section**:
   - **API Server**: Shows current URL. Tap → enter a URL → verify connection re-checks
   - **Status**: Green dot (●) + "Connected" when server is reachable. Tap to manually re-check
   - **Scan for Servers**: Tap to auto-discover servers on your network
3. **ABOUT section**:
   - **Device Token**: Shows truncated token (first 8 + "..." + last 4 chars, monospace). Tap → verify "Copied!" feedback appears for 2 seconds
4. **DEBUG section**:
   - **Logs**: Tap → verify logs screen opens showing live system logs
   - **Restart Session**: Tap → confirmation dialog "Restart the Claude session? This will clear the conversation context." → tap "Restart" → verify session restarts (new messages won't have prior context)
   - **Clear Notifications**: Tap → verify alert "Done - Notifications cleared." appears

### CUJ 11: Push Notifications (Device Only)

> **Skip in simulator** — APNs push notifications require a physical device or TestFlight build. Simulator cannot receive remote push notifications.

**On a real device:**
1. Send a message and wait for the assistant to respond
2. Background the app (swipe up / press home)
3. Verify a push notification banner appears with the assistant's response
4. Tap the notification — verify the app opens directly to the correct chat
5. Verify the notification is dismissed from the notification center for that chat

### CUJ 12: Dashboard

1. Switch to **Dashboard** tab (third tab)
2. Verify a WebView loads the system dashboard from the `/dashboard` endpoint
3. Verify the page loads without errors (not a blank white screen). The dashboard content is server-rendered HTML — as long as it displays text and data, it is working
4. If WebView fails to load, verify a fallback "Open in Browser" button appears that launches Safari

### CUJ 13: Error Handling & Retry

1. **Kill the API server**: `kill $(lsof -ti tcp:9091 -sTCP:LISTEN)`
2. Try sending a message — verify:
   - Your message appears grayed-out (pending), then the gray clears and a **red ● ! badge** appears to the right of the bubble with **"Not Delivered"** text (#ef4444 red) below it
3. Switch to Settings — verify the Status row shows a red dot (●) + "Disconnected"
4. **Restart the API server**: `cd ~/dispatch/services/dispatch-api && nohup uv run server.py > ~/dispatch/logs/dispatch-api.log 2>&1 &`
5. Wait up to 10 seconds — verify Settings status auto-recovers to green "Connected" (auto-retry interval per Test Constants)
6. Go back to the chat — tap the **red ! badge / "Not Delivered"** on the failed message — verify the message retries and the assistant eventually responds

### CUJ 14: Message Bubble Features

1. **Long text truncation**: Send a message with 900+ characters (e.g., paste a long paragraph). The assistant's response may also be long. Verify messages over the truncation threshold (see Test Constants) show truncated text ending with "..." and a **"Show more"** link (#a1a1aa gray, 13px)
2. **Expand**: Tap "Show more" — verify full text appears with a **"Show less"** link at the bottom
3. **Collapse**: Tap "Show less" — verify it truncates again
4. **Timestamp**: Tap any message bubble — verify a relative timestamp appears below it (e.g., "2 minutes ago", gray #71717a, 11px)
5. **Save image**: On an assistant message with an image, find the **↓ save button** (dark circle with download arrow, right of bubble). Tap it — verify a spinner appears briefly, then the image is saved to the photo library

### CUJ 15: App Suspend & Resume

1. Open a chat with several messages
2. **Background the app**: Press Cmd+Shift+H (simulator home)
3. Wait 5 seconds
4. **Reopen the app** — verify:
   - Chat state is fully preserved (same messages, same scroll position)
   - Polling resumes (new messages from assistant appear if any were generated while backgrounded)
5. Switch to chat list — verify pull-to-refresh works after resume

### CUJ 16: Scroll Behavior

1. Open a chat and send 15+ messages (back and forth with the assistant)
2. Verify the list **auto-scrolls to the bottom** when a new message arrives
3. **Scroll up** to read older messages — verify the list stays at your scroll position (does NOT snap back to bottom)
4. Send a new message — verify the list scrolls back to the bottom to show your new message

### Quick Smoke Test (5 minutes)

Run through these 10 steps to quickly validate all major flows:

```
 1. Launch app → Chats tab loads (list or empty state)        ✓ CUJ 1
 2. Tap + FAB → New chat opens with empty state               ✓ CUJ 1
 3. Type "hello" → Tap ↑ → Message appears as pending         ✓ CUJ 2
 4. Wait ~3s → Assistant response appears (left-aligned)      ✓ CUJ 2
 5. Tap ▶ on response → Audio generates, then plays           ✓ CUJ 7
 6. Verify thinking dots appeared during step 4               ✓ CUJ 8
 7. Tap Rename → Enter "Smoke Test" → Title updates           ✓ CUJ 5
 8. Go back → Swipe chat right → Delete → Confirm → Gone     ✓ CUJ 6
 9. Agents tab → Tap + → Create "Test" → Send message         ✓ CUJ 9
10. Settings tab → Verify green "Connected" status             ✓ CUJ 10
```

**Extended smoke test** (add 5 more minutes):
```
11. Send image + text → Both appear in bubble                 ✓ CUJ 3
12. Mic button → Speak → Stop → Text in field                 ✓ CUJ 4
13. Kill API → Send message → "Not Delivered" appears          ✓ CUJ 13
14. Restart API → Tap retry → Message sends                   ✓ CUJ 13
15. Dashboard tab → WebView loads                             ✓ CUJ 12
```
