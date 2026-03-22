# Dispatch App: Expo/React Native Migration Plan

## 1. Executive Summary

Migrate the existing native Swift/SwiftUI iOS app ("Sven") to an Expo/React Native app called "dispatch-app". The new app targets **iOS native and web from a single codebase** using `react-native-web`. It will achieve full feature parity with the Swift app (multi-chat, voice recording with on-device speech recognition, TTS playback, push notifications, image attachments) and merge the agents dashboard (currently `agents.html`) as a first-class tab. On web, the app replaces `agents.html` as a static export served by dispatch-api. A build-time branding config via EAS Build profiles enables the same codebase to ship as "Dispatch" (default) or "Sven" (admin's phone).

**Repo location:** `~/dispatch/apps/dispatch-app/`
> **Note:** The native SwiftUI Sven app has been deprecated and moved to `~/dispatch/apps/sven-ios-deprecated/`.
**Package manager:** bun
**Build system:** EAS Build -> TestFlight (iOS), `expo export --platform web` -> static files served by dispatch-api (web)

---

## 2. Architecture Overview

### 2.1 Directory Structure

```
dispatch-app/
  app/                          # Expo Router file-based routing
    (tabs)/                     # Tab layout
      _layout.tsx               # Tab navigator (Chats, Agents, Settings)
      index.tsx                 # Chat list (home tab)
      agents.tsx                # Agents dashboard tab
      settings.tsx              # Settings / profile tab
    chat/
      [id].tsx                  # Individual chat conversation screen
    agents/
      [id].tsx                  # Agent session conversation screen
    modal/
      recording.tsx             # Recording modal (expo-router modal route)
  src/
    api/                        # Shared API client layer (pure TS, no React deps)
      client.ts                 # Base HTTP client (fetch wrapper with auth, base URL)
      chats.ts                  # Chat CRUD: GET/POST/PATCH/DELETE /chats, /messages, /prompt
      agents.ts                 # Agents API: /api/agents/sessions, /api/agents/messages
      audio.ts                  # Audio download + caching: /audio/{id}
      push.ts                   # APNs registration: /register-apns
      types.ts                  # Shared TypeScript types (ChatMessage, Conversation, etc.)
    hooks/                      # React hooks
      useMessages.ts            # Shared message hook (polling, optimistic send, pagination)
      useChatList.ts            # Chat list state, CRUD
      useAgentSessions.ts       # Agent sessions list + CRUD
      useAudioPlayer.ts         # TTS playback (expo-audio on iOS, HTMLAudioElement on web)
      useAudioPlayer.web.ts     # Web-specific audio playback
      useSpeechRecognition.ts   # On-device STT (iOS: @jamsch/expo-speech-recognition)
      useSpeechRecognition.web.ts # Web Speech API implementation
      useDeviceToken.ts         # Persistent device token (expo-secure-store on iOS, localStorage on web)
    components/
      ChatRow.tsx               # Chat list row (title, preview, timestamp)
      MessageBubble.tsx         # Message bubble (user/assistant, expand/collapse, audio button)
      InputBar.tsx              # Mic button / text input toggle bar
      RecordingModal.tsx        # Modal for recording (transcript, timer, send/cancel)
      RecordingModal.web.tsx    # Web-specific recording modal (CSS modal with backdrop)
      ThinkingIndicator.tsx     # Animated "Thinking..." dots
      RecordingIndicator.tsx    # Audio level waveform bars
      RecordingPlaceholder.tsx  # Pulsing coral "Recording..." bubble in chat
      TranscriptionView.tsx     # Live word-by-word transcript display
      AgentSessionRow.tsx       # Agent session list row (name, tier badge, preview)
      AgentMessageBubble.tsx    # Agent message bubble (sender label, text)
      ErrorBanner.tsx           # Dismissable error banner
      EmptyState.tsx            # Empty state placeholder
    config/
      branding.ts               # Build-time branding config
      constants.ts              # API base URL, polling intervals, limits
    platform/                   # Platform abstraction layer
      haptics.ts                # expo-haptics on iOS
      haptics.web.ts            # no-op on web
      secureStore.ts            # expo-secure-store on iOS
      secureStore.web.ts        # localStorage on web
      notifications.ts          # expo-notifications on iOS
      notifications.web.ts      # Web Notifications API
    utils/
      time.ts                   # Relative time formatting
  assets/
    icon.png                    # Default "Dispatch" app icon
    adaptive-icon.png           # Android adaptive icon
    splash.png                  # Splash screen
  config.default.json           # Checked in - default "Dispatch" branding
  app.config.ts                 # Dynamic Expo config (reads branding for app name, icon)
  eas.json                      # EAS Build profiles (development, preview, production, sven)
  package.json
  tsconfig.json
  jest.config.ts                # Jest configuration
  maestro/                      # E2E test flows
    chat-send-message.yaml
    recording-flow.yaml
    agents-browse.yaml
  .gitignore
  babel.config.js
```

### 2.2 Key Architectural Decisions

1. **Expo Router** for file-based navigation (replaces SwiftUI NavigationStack).
2. **react-native-web** for web platform support — one codebase, two targets.
3. **Tab layout** with three tabs: Chats (feature parity with Swift app), Agents (replaces agents.html), Settings.
4. **Shared API client** (`src/api/`) is a pure TypeScript layer with zero React dependencies — works identically on iOS and web.
5. **Shared `useMessages` hook** abstracts conversation polling/send for both chat and agent views, with pluggable API adapters.
6. **Platform-specific files** (`.web.ts` / `.web.tsx`) for features with different native/web implementations.
7. **`expo-audio`** (new API, forward path) for playback. Recording is only needed if the audio spike (Phase 0) proves we need audio files — otherwise transcript text from speech recognition is sufficient.
8. **`@jamsch/expo-speech-recognition`** for on-device STT on iOS; Web Speech API on web.
9. **expo-notifications** for push notifications on iOS; Web Notifications API on web.
10. **expo-secure-store** for device token persistence on iOS; localStorage on web.
11. **expo-haptics** for haptic feedback on iOS; no-op on web.
12. **React Native Modal + Animated API** for recording sheet (no third-party bottom sheet dependency).
13. **Build-time branding** via EAS Build profiles (no runtime `useBranding` hook needed).

---

## 3. Web Platform Strategy

### 3.1 Overview

The web build replaces `agents.html` and provides the full app experience in the browser. Web is a first-class target from Phase 1.

- **Dev:** `npx expo start --web`
- **Build:** `npx expo export --platform web` produces static files
- **Deploy:** Static files served by dispatch-api at `/app/` (replaces agents.html)

### 3.2 Dependency Web Compatibility Audit

| Package | iOS | Web | Web Strategy |
|---|---|---|---|
| `expo-router` | Native navigation | react-router under the hood | Full support |
| `react-native-web` | N/A | Core web runtime | Full support |
| `expo-secure-store` | Keychain | **No web support** | `.web.ts` → `localStorage` |
| `expo-haptics` | UIImpactFeedbackGenerator | **No web support** | `.web.ts` → no-op functions |
| `expo-notifications` | APNs | **No native support** | `.web.ts` → Web Notifications API |
| `@jamsch/expo-speech-recognition` | Apple Speech framework | **No web support** | `.web.ts` → Web Speech API (`webkitSpeechRecognition`) |
| `expo-audio` | AVFoundation | **Broken for events** | `.web.ts` → `HTMLAudioElement` is **mandatory** (not a graceful fallback). `expo-audio`'s `useEventListener` does not fire events on web ([GitHub #35897](https://github.com/expo/expo/issues/35897)). `MediaRecorder` for recording (if needed) |
| `expo-image-picker` | UIImagePicker | Partial (file input) | Works via `<input type="file">` fallback |
| `expo-file-system` | Native FS | **No web support** | Web: skip caching, stream from URL directly |
| `react-native-reanimated` | Native driver | JS fallback | Works but slower; use CSS animations on web where possible |
| `react-native-gesture-handler` | Native gestures | Web touch/mouse events | Works for basic gestures |
| `react-native-safe-area-context` | Native safe area | CSS env(safe-area-*) | Full support |

### 3.3 Platform-Specific File Strategy

Expo/React Native resolves `*.web.ts` files automatically on web builds. Every platform-divergent feature gets a pair:

```
src/platform/haptics.ts       → expo-haptics (iOS)
src/platform/haptics.web.ts   → export const impactAsync = () => {} (no-op)

src/platform/secureStore.ts       → expo-secure-store
src/platform/secureStore.web.ts   → localStorage wrapper with same API

src/hooks/useSpeechRecognition.ts      → @jamsch/expo-speech-recognition
src/hooks/useSpeechRecognition.web.ts  → Web Speech API (webkitSpeechRecognition)

src/hooks/useAudioPlayer.ts      → expo-audio
src/hooks/useAudioPlayer.web.ts  → HTMLAudioElement (MANDATORY — expo-audio useEventListener does not fire on web, GitHub #35897)

src/platform/notifications.ts      → expo-notifications
src/platform/notifications.web.ts  → Web Notifications API (Notification.requestPermission + new Notification)
```

Both files in a pair export the **same interface** so consuming code is platform-agnostic.

### 3.4 Web-Specific Considerations

- **Speech recognition on web:** Uses `webkitSpeechRecognition` (Chrome/Edge) or `SpeechRecognition` (Firefox). Cloud-processed, not on-device. Quality and latency differ from iOS — document this to users. Safari support is limited.
- **Audio recording on web (if needed):** `MediaRecorder` API. Outputs webm/opus, not m4a. Backend must accept both formats or we transcode client-side.
- **Push notifications on web:** Web Notifications API for basic alerts. No badge counts. Requires HTTPS and user permission grant.
- **Bottom sheet / recording modal on web:** CSS modal with backdrop-filter, fixed positioning, slide-up animation via CSS transitions. No gesture-based snap points — tap/click to dismiss.
- **Haptics on web:** Pure no-op. No navigator.vibrate() — it's annoying on desktop.
- **File caching on web:** Browser cache handles this naturally. No expo-file-system needed.

### 3.5 Web Deployment Plan

1. `npx expo export --platform web` outputs to `dist/` directory
2. dispatch-api serves `dist/` as static files at `/app/`
3. `agents.html` redirects to `/app/agents` (backward compatibility)
4. No SSR needed — pure SPA with client-side routing

---

## 4. Audio Session Architecture

### 4.1 The Problem

On iOS, `expo-audio` and `@jamsch/expo-speech-recognition` both manage `AVAudioSession`. Running both simultaneously causes conflicts — one will steal the audio session from the other. This is a [known issue](https://github.com/jamsch/expo-speech-recognition/issues/72).

### 4.2 Key Insight: Do We Need Audio Recording?

The Swift app sends the **transcript text** (not an audio file) to the backend via `POST /prompt`. Speech recognition produces the text; the audio file itself is never uploaded. Therefore:

- **Only `@jamsch/expo-speech-recognition` is needed** for voice input
- **`expo-audio` recording is NOT needed** for the core flow
- This eliminates the AVAudioSession conflict entirely

### 4.3 Audio Session Ownership

| Feature | iOS Audio Session | Owner |
|---|---|---|
| Speech recognition (STT) | `.record` category, managed by Speech framework | `@jamsch/expo-speech-recognition` |
| TTS playback | `.playback` category | `expo-audio` |
| These never overlap | STT stops → playback starts | Sequential, no conflict |

**Rule:** Speech recognition and audio playback are never active simultaneously. The recording modal must be fully dismissed before any TTS playback can begin. This is enforced at the hook level.

### 4.4 If Audio File IS Needed Later

If a future requirement needs the raw audio file (e.g., server-side processing), the Phase 0 spike must prove that `expo-audio` recording and `@jamsch/expo-speech-recognition` can coexist. Options:
- Use `@jamsch/expo-speech-recognition`'s `recordingOptions` to get the audio file directly from the speech recognizer (avoids dual audio session)
- Sequence them: record first with `expo-audio`, then run speech recognition on the file
- **Do not ship this path without a working proof-of-concept**

---

## 5. Branding / Config System

### 5.1 Design: Build-Time via EAS Build Profiles

Branding is a build-time concern, not a runtime concern. Two users (Dispatch vs Sven) means two EAS Build profiles, not a runtime hook.

**`config.default.json`** (checked in):
```json
{
  "appName": "Dispatch",
  "displayName": "Dispatch",
  "accentColor": "#2563eb",
  "iconPath": "./assets/icon.png",
  "adaptiveIconPath": "./assets/adaptive-icon.png",
  "splashColor": "#09090b",
  "bundleIdentifier": "com.dispatch.app",
  "scheme": "dispatch"
}
```

**`eas.json`** profiles handle the Sven variant:
```json
{
  "build": {
    "production": {
      "env": { "APP_VARIANT": "dispatch" }
    },
    "sven": {
      "extends": "production",
      "env": {
        "APP_VARIANT": "sven",
        "APP_NAME": "Sven",
        "BUNDLE_ID": "com.dispatch.sven",
        "ACCENT_COLOR": "#3478f7"
      }
    }
  }
}
```

**`app.config.ts`** reads `process.env.APP_VARIANT` to select branding:
```ts
const variant = process.env.APP_VARIANT || "dispatch";
const configs = {
  dispatch: require("./config.default.json"),
  sven: {
    ...require("./config.default.json"),
    appName: "Sven",
    displayName: "Sven",
    accentColor: process.env.ACCENT_COLOR || "#3478f7",
    bundleIdentifier: process.env.BUNDLE_ID || "com.dispatch.sven",
    iconPath: "./assets/sven-icon.png",
    scheme: "sven",
  },
};
const config = configs[variant];
```

**Runtime access** to branding values uses `expo-constants` (which embeds `app.config.ts` values at build time):
```ts
import Constants from "expo-constants";
const appName = Constants.expoConfig?.name || "Dispatch";
```

No `useBranding` hook needed — `Constants.expoConfig` is available synchronously everywhere.

### 5.2 Build Commands

```bash
# Default "Dispatch" build
eas build --profile production --platform ios

# "Sven" build
eas build --profile sven --platform ios
```

---

## 6. Phase Breakdown

### Phase 0: Audio Spike / Proof of Concept (Day 1-2)

**Goal:** Validate core audio/speech assumptions before committing to architecture. This phase is a throwaway prototype.

**What to test:**

1. **iOS: `@jamsch/expo-speech-recognition` partial results**
   - Create minimal Expo app with a "Record" button
   - Start speech recognition with `interimResults: true`
   - Verify partial results stream in real-time (word-by-word)
   - Verify on-device recognition works (check `requiresOnDeviceRecognition` option)
   - Test stop/start cycling (does it reliably restart?)
   - Measure latency between speech and partial result callback

2. **iOS: `expo-audio` playback after speech recognition**
   - Stop speech recognition
   - Immediately start audio playback via `expo-audio`
   - Verify no AVAudioSession conflict
   - Test this transition 10+ times for reliability

3. **Web: Web Speech API**
   - Same "Record" button using `webkitSpeechRecognition`
   - Verify partial results (`interimResults: true`)
   - Test in Chrome, Edge, Safari (note: Safari has limited support)
   - Document quality/latency differences vs iOS on-device

4. **Web: Audio playback**
   - Play audio via `HTMLAudioElement` after speech recognition stops
   - Verify clean transition

5. **(If needed) iOS: `expo-audio` recording + `@jamsch/expo-speech-recognition` simultaneously**
   - Only test this if we determine we need the raw audio file
   - Try `recordingOptions` on the speech recognizer to avoid dual session
   - Document whether it works or conflicts

**Deliverable:** Written spike results document with go/no-go for each feature. Update this plan if any assumption is invalidated.

**Exit criteria:** Partial results work on iOS, Web Speech API works in Chrome, playback transition is clean. If any of these fail, revise architecture before proceeding.

---

### Phase 1: Project Scaffolding + API Client + Test Infra (Day 3-4)

**Goal:** Expo project bootstrapped, API client working, test infrastructure in place, can fetch chats from dispatch-api on both iOS and web.

**Steps:**

1. **Initialize Expo project:**
   ```bash
   cd ~/dispatch/apps
   bunx create-expo-app dispatch-app --template tabs
   cd dispatch-app
   ```

2. **Install core dependencies:**
   ```bash
   bun add expo-router expo-secure-store expo-haptics expo-audio expo-notifications expo-image-picker
   bun add @jamsch/expo-speech-recognition
   bun add react-native-reanimated react-native-gesture-handler react-native-web
   bun add react-dom @expo/metro-runtime
   bun add -d @types/react typescript
   ```

3. **Set up test infrastructure:**
   ```bash
   bun add -d jest @testing-library/react-native @testing-library/react jest-expo ts-jest
   ```
   - Configure `jest.config.ts` with `jest-expo` preset
   - Set up module mocks for platform-specific packages (expo-secure-store, expo-haptics, etc.)
   - Add test scripts to `package.json`: `"test": "jest"`, `"test:watch": "jest --watch"`
   - Write first test: API client `getChats()` with mocked fetch

4. **Create config system:**
   - `config.default.json`
   - `app.config.ts` (dynamic config loader with EAS variant support)
   - `src/config/constants.ts` (API base URL, polling intervals)

5. **Create platform abstraction layer (`src/platform/`):**
   - `haptics.ts` / `haptics.web.ts` — haptic feedback / no-op
   - `secureStore.ts` / `secureStore.web.ts` — expo-secure-store / localStorage
   - `notifications.ts` / `notifications.web.ts` — expo-notifications / Web Notifications API

6. **Implement API client (`src/api/`):**
   - `client.ts`: Base fetch wrapper with auth token header, error handling, timeout. Uses platform `secureStore` for device token.
   - `types.ts`: TypeScript interfaces:
     ```ts
     interface ChatMessage {
       id: string;
       role: "user" | "assistant";
       content: string;
       audio_url: string | null;
       created_at: string;
     }
     interface Conversation {
       id: string;
       title: string;
       created_at: string;
       updated_at: string;
       last_message: string | null;
       last_message_at: string | null;
       last_message_role: string | null;
     }
     interface PromptResponse {
       status: string;
       message: string;
       request_id: string;
     }
     interface AgentSession {
       id: string;
       type: "contact" | "dispatch-api";
       name: string;
       tier: string;
       source: string;
       chat_type: string;
       participants: string[] | null;
       last_message: string | null;
       last_message_time: string | null;
       last_message_is_from_me: boolean;
       status: string;
     }
     interface AgentMessage {
       id: string;
       role: string;
       text: string;
       sender: string;
       is_from_me: boolean;
       timestamp_ms: number;
       source: string;
       has_attachment: boolean;
     }
     ```
   - `chats.ts`: `getChats()`, `createChat()`, `updateChat()`, `deleteChat()`, `getMessages()`, `sendPrompt()`, `clearMessages()`, `restartSession()`
   - `agents.ts`: `getAgentSessions()`, `getAgentMessages()`, `createAgentSession()`, `sendAgentMessage()`, `renameAgentSession()`, `deleteAgentSession()`
   - `audio.ts`: `downloadAudio()` — on iOS uses expo-file-system cache, on web returns URL directly
   - `push.ts`: `registerAPNsToken()`

7. **Device token management (`src/hooks/useDeviceToken.ts`):**
   - On first launch, generate UUID and store via platform `secureStore`
   - All API calls include this token
   - Works identically on iOS (Keychain) and web (localStorage)

8. **Verify web builds:**
   - Run `npx expo start --web` — confirm app loads in browser
   - Run `npx expo start` — confirm app loads in iOS simulator

**Files created:** ~25 files
**Verification:** `bun test` passes. API client `getChats()` returns data. App loads on both iOS and web.

---

### Phase 2: Chat List + Navigation (Day 5)

**Goal:** Tab navigator, chat list screen, navigation to chat detail. Works on iOS and web.

**Steps:**

1. **Tab layout (`app/(tabs)/_layout.tsx`):**
   - Three tabs: Chats (chat bubble icon), Agents (terminal icon), Settings (gear icon)
   - Uses branding accent color from `expo-constants`

2. **Chat list screen (`app/(tabs)/index.tsx`):**
   - Pull-to-refresh
   - Chat rows showing title, preview text, relative timestamp
   - "New chat" button in header
   - Swipe-to-delete on iOS; delete button on web
   - Auto-refresh on app foreground (AppState listener on iOS, visibilitychange on web)

3. **Hook `useChatList.ts`:**
   - Manages `conversations: Conversation[]`, `isLoading`, `error`
   - `loadConversations()`, `createConversation()`, `deleteConversation()`

4. **Components:**
   - `ChatRow.tsx`: Title, preview (with "You: " prefix for user messages), relative time
   - `EmptyState.tsx`: "No conversations yet" placeholder

5. **Navigation to chat (`app/chat/[id].tsx`):**
   - Receives `chatId` and `chatTitle` via route params
   - Placeholder for ChatView (built in Phase 3)

**Files created:** ~8 files
**Verification:** App launches on iOS and web, shows chat list, tapping a row navigates to chat screen.

---

### Phase 3: Chat Conversation View + Shared useMessages Hook (Day 6-7)

**Goal:** Full messaging UI with text input, message bubbles, polling, optimistic send. Shared hook usable by both chat and agent views.

**Steps:**

1. **Shared hook `useMessages.ts`:**

   Both chat conversations and agent conversations follow the same pattern: fetch messages, poll for new ones, optimistic send. This hook abstracts the common logic with pluggable API adapters:

   ```ts
   interface MessageAdapter<T> {
     fetchMessages(opts: { since?: string; before?: string; limit?: number }): Promise<T[]>;
     sendMessage(content: string): Promise<{ id: string }>;
     clearMessages?(): Promise<void>;
   }

   function useMessages<T>(adapter: MessageAdapter<T>) {
     // State: messages, isLoading, error, isPolling
     // Polling with exponential backoff on errors (2^n seconds, max 30s)
     // Optimistic insert on send
     // Incremental fetch with dedup
   }
   ```

   - `chatAdapter(chatId)`: Wraps `chats.ts` API calls
   - `agentAdapter(sessionId)`: Wraps `agents.ts` API calls
   - Both return the same `useMessages` interface

2. **Chat screen (`app/chat/[id].tsx`):**
   - Navigation bar: title, auto-read toggle (speaker icon), menu (restart, clear, settings)
   - Message list: FlatList with auto-scroll to bottom on new messages
   - Input bar at bottom (mic button / text input toggle)
   - "Thinking..." indicator when waiting for response

3. **Components:**
   - `MessageBubble.tsx`:
     - User messages: right-aligned, accent background (opacity when pending)
     - Assistant messages: left-aligned, gray background
     - Long message truncation at 840 chars with "Show more" / "Show less"
     - "Sending..." / "Delivered" status on last user message
     - Play/Pause button for messages with `audio_url`
   - `InputBar.tsx`:
     - Three modes: idle (mic + keyboard toggle), keyboard (text field + send), recording (opens modal)
     - Keyboard mode: TextInput with "Message {appName}..." placeholder
     - Haptic feedback on send (no-op on web)
   - `ThinkingIndicator.tsx`: Animated dots (0.4s interval, 0-3 cycle)
   - `ErrorBanner.tsx`: Red banner with dismiss button

4. **Text input flow:**
   - Toggle between mic/keyboard modes
   - Send button appears when text is non-empty
   - Clear input on send

**Files created:** ~10 files
**Verification:** Can send text messages on iOS and web, see optimistic UI, see assistant responses via polling.

---

### Phase 4: Voice Recording + Speech Recognition (Day 8-10)

**Goal:** Full voice input with real-time transcription, recording modal, silence detection. Works on both iOS (on-device) and web (cloud-based).

**Steps:**

1. **Hook `useSpeechRecognition.ts` (iOS):**
   - Uses `@jamsch/expo-speech-recognition` (correct npm name: `@jamsch/expo-speech-recognition`)
   - `start()`: Begin recognition with `interimResults: true`, locale `en-US`
   - `stop()`: End recognition
   - Exposes: `transcript`, `partialTranscript`, `isListening`
   - Post-processing: "Sven" name corrections (same regex table as Swift `correctSvenMisrecognitions`)

2. **Hook `useSpeechRecognition.web.ts` (Web):**
   - Uses `webkitSpeechRecognition` / `SpeechRecognition` API
   - Same interface as iOS hook
   - `continuous: true`, `interimResults: true`, `lang: "en-US"`
   - Graceful degradation: if browser doesn't support it, `isSupported: false` and UI shows text-only input
   - Note: cloud-processed (not on-device), requires internet, different latency characteristics

3. **Recording Modal (`RecordingModal.tsx` for iOS, `RecordingModal.web.tsx` for web):**

   **iOS implementation:**
   - React Native `Modal` with `Animated` API for slide-up animation
   - PanResponder for swipe-down-to-dismiss gesture
   - Two states: recording (cancel/timer/stop) and stopped (discard/send)
   - Live transcription view with word-by-word animation
   - Duration timer (0:00.0 format)
   - Max recording: 120 seconds (auto-stop, no auto-send)
   - Warning color at 1:45, red at 1:55
   - Cancel confirmation dialog for recordings >30 seconds
   - Haptic feedback: medium on start, light on stop, success on send, error on cancel

   **Web implementation:**
   - CSS modal with `position: fixed`, `backdrop-filter: blur()`, slide-up CSS transition
   - Same two-state UI, click to dismiss backdrop
   - No haptics, no swipe gesture
   - "Speech recognition not supported" fallback message for unsupported browsers

4. **Recording modal route (alternative):**
   - Can use `app/modal/recording.tsx` with expo-router's built-in modal presentation
   - `router.push("/modal/recording")` opens it, `router.back()` dismisses
   - This avoids custom Modal management entirely

5. **Components:**
   - `RecordingIndicator.tsx`: 20 bars, height varies with audio level (iOS only; static on web)
   - `RecordingPlaceholder.tsx`: Pulsing coral dot + "Recording..." in chat
   - `TranscriptionView.tsx`: Word-by-word display, "Listening..." when empty

6. **Silence detection:**
   - On iOS: Track via speech recognition events (no audio metering needed since we're not recording audio)
   - On web: Track via `speechend` event from Web Speech API
   - Auto-stop after 4 seconds of silence if transcript has content

7. **Integration with InputBar:**
   - Tapping mic opens recording modal
   - Modal provides `onSend(transcript)` callback -> calls `sendMessage(transcript)`

**Files created:** ~10 files
**Verification:** Can record voice and see live transcription on both iOS and web. Send transcript as message.

---

### Phase 5: TTS Audio Playback (Day 11)

**Goal:** Play assistant response audio, auto-read mode. Works on iOS and web.

**Steps:**

1. **Hook `useAudioPlayer.ts` (iOS):**
   - Uses `expo-audio` (the modern API, not deprecated `expo-av`)
   - `play(url)`: Create `Audio.Sound`, load and play
   - `pause()` / `resume()` / `stop()`
   - `isPlaying`, `isPaused` state
   - Audio mode: playback category, spoken audio mode, duck others
   - Completion callback to reset state

2. **Hook `useAudioPlayer.web.ts` (Web) — MANDATORY, not a fallback:**
   - Uses `HTMLAudioElement` directly because `expo-audio`'s `useEventListener` does not fire events on web ([GitHub #35897](https://github.com/expo/expo/issues/35897)). This `.web.ts` file is required for web audio to function at all.
   - Same interface as iOS hook
   - `const audio = new Audio(url); audio.play()`
   - Progress/completion via native HTMLAudioElement event listeners (`ended`, `timeupdate`, `error`)

3. **Audio caching (`src/api/audio.ts`):**
   - **Format verification:** dispatch-api serves WAV files. Verify this early — the caching layer keys on `{message_id}.wav` and both platform paths assume WAV. On web, `HTMLAudioElement` handles WAV natively. On iOS, `expo-audio` handles WAV via AVFoundation. If dispatch-api ever changes format, both paths need updating.
   - iOS: Uses `expo-file-system` to cache WAV files in app cache directory
   - Web: Relies on browser HTTP cache (Cache-Control headers from dispatch-api)
   - Key: `{message_id}.wav`

4. **Integration with MessageBubble:**
   - Assistant messages with `audio_url` show Play/Pause button
   - Tapping toggles play/pause/resume
   - Visual state: play icon (idle), pause icon (playing), play icon (paused)

5. **Auto-read mode:**
   - Toggle via speaker icon in navigation bar
   - When enabled: automatically play audio for new assistant messages
   - Detect "new" by comparing previous and current message arrays
   - Works on both platforms (web uses HTMLAudioElement auto-play, may require user interaction first)

**Files created:** ~5 files
**Verification:** Can play assistant audio on both iOS and web. Auto-read works.

---

### Phase 6: Push Notifications (Day 12)

**Goal:** Receive push notifications on iOS, web notifications where supported. Navigate to specific chats.

**Steps:**

1. **iOS: `expo-notifications` setup:**
   - Register for push on app launch
   - Get native APNs token
   - Send to backend via `POST /register-apns`
   - Foreground: show banner, refresh chat list and current chat
   - Background tap: navigate to `router.push(/chat/${chatId})`

2. **Web: Web Notifications API (`src/platform/notifications.web.ts`):**
   - `Notification.requestPermission()` on first visit
   - Show `new Notification(title, { body })` for incoming messages
   - No APNs integration — web notifications are local-only for now
   - Future: Web Push API with service worker for background notifications

3. **Navigation on notification tap:**
   - iOS: Parse `chat_id` from notification `data`, use `router.push`
   - Web: `notification.onclick` handler focuses tab and navigates

4. **App config for iOS:**
   ```ts
   ios: {
     infoPlist: {
       UIBackgroundModes: ["remote-notification"],
     },
   }
   ```

**Files created:** ~3 files
**Verification:** iOS: receive push, see banner, tap navigates. Web: see browser notification.

---

### Phase 7: Agents Dashboard Tab (Day 13-14)

**Goal:** Merge the agents.html dashboard into the app as a native tab. Reuses `useMessages` hook.

**Steps:**

1. **Agents tab (`app/(tabs)/agents.tsx`):**
   - Session list with search and tier filters
   - Both session types: contact sessions + dispatch-api sessions
   - Tier badges (admin=amber, partner=pink, family=green, favorite=blue, bots=purple)
   - Source indicator: iMessage, Signal, dispatch-api
   - Status: active (green dot) / idle (gray)
   - "New Agent" button for dispatch-api sessions
   - Pull-to-refresh, auto-poll every 5 seconds

2. **Hook `useAgentSessions.ts`:**
   - Fetches from `GET /api/agents/sessions`
   - Search, tier filtering, sort by recency
   - `createSession(name)`: POST to `/api/agents/sessions`

3. **Agent conversation screen (`app/agents/[id].tsx`):**
   - Uses `useMessages(agentAdapter(sessionId))` — same shared hook as chat
   - `agentAdapter` implements `MessageAdapter` wrapping agents API
   - Cursor-based pagination: initial load, scroll up for history, poll for new
   - Sender labels on messages
   - Rename/delete session actions

4. **Components:**
   - `AgentSessionRow.tsx`: Name, tier badge, source icon, preview, timestamp, active indicator
   - `AgentMessageBubble.tsx`: Sender label above bubble, alignment based on `is_from_me`
   - Tier badge colors match agents.html CSS variables

5. **New agent creation flow:**
   - Modal with text input for name
   - On create: navigates to conversation view

**Files created:** ~8 files
**Verification:** Can browse sessions, open conversations, send messages. Works on iOS and web.

---

### Phase 8: Image Attachment Support (Day 15)

**Goal:** Send images with messages (matches /prompt-with-image endpoint).

**Steps:**

1. **Image picker:**
   - iOS: `expo-image-picker` for camera and photo library
   - Web: Falls back to `<input type="file" accept="image/*">` automatically
   - Image preview before sending

2. **API integration (`src/api/chats.ts`):**
   - `sendPromptWithImage(transcript, imageUri, chatId)`: FormData multipart upload
   - Maps to `POST /prompt-with-image` endpoint

3. **Message display:**
   - Messages with image attachments show thumbnail
   - Tap to expand full-screen

**Files created:** ~3 files
**Verification:** Can pick photo, send with text, see in conversation on both platforms.

---

### Phase 9: Settings Tab + Polish (Day 16-17)

**Goal:** Settings screen, UI polish, cross-platform refinements.

**Steps:**

1. **Settings screen (`app/(tabs)/settings.tsx`):**
   - Message count per chat
   - Clear all data option
   - About section (app name, version, "Powered by Claude")
   - Debug logs toggle
   - API server URL display

2. **UI polish:**
   - Keyboard avoidance (KeyboardAvoidingView on iOS, CSS on web)
   - Safe area handling
   - Dark/light mode support (system preference detection)
   - Loading skeletons
   - Smooth scroll-to-bottom animation
   - Error recovery (retry buttons)

3. **Performance:**
   - FlatList: `getItemLayout`, `maxToRenderPerBatch`, `windowSize`
   - `React.memo` on message bubbles
   - Web: virtualized list (FlatList works via react-native-web, but test scrolling performance)

4. **Web-specific polish:**
   - Responsive layout (mobile-width centered on desktop)
   - Keyboard shortcuts (Enter to send, Escape to close modals)
   - Proper `<title>` and favicon

**Files created:** ~5 files

---

### Phase 10: Integration Testing + E2E (Day 18-19)

**Goal:** Comprehensive testing, E2E flows, CI pipeline.

**Steps:**

1. **Unit/integration tests (expand from Phase 1 foundation):**
   - API client: mock fetch, verify all endpoints
   - `useMessages` hook: test polling, optimistic send, error backoff
   - `useChatList` hook: test CRUD operations
   - `useSpeechRecognition`: mock native module, test state transitions
   - Platform abstraction tests: verify `.web.ts` variants export correct interfaces
   - Use `renderHook` from `@testing-library/react` (NOT deprecated `@testing-library/react-hooks`)

2. **Maestro E2E tests (`maestro/`) — iOS:**
   - `chat-send-message.yaml`: Open chat, type message, verify it appears, verify response arrives
   - `recording-flow.yaml`: Tap mic, verify modal opens, stop, send (iOS only — Maestro doesn't support web)
   - `agents-browse.yaml`: Switch to agents tab, search, open session, verify messages load

3. **Playwright E2E smoke tests (`e2e/`) — Web:**
   - Install: `bun add -d @playwright/test`
   - `chat-list.spec.ts`: Navigate to app, verify chat list loads and renders conversations
   - `send-message.spec.ts`: Open a chat, send a message, verify it appears in the message list
   - `agents-tab.spec.ts`: Switch to agents tab, verify agent sessions render
   - Run against `npx expo start --web` dev server or static export
   - Add to CI: `bunx playwright install --with-deps && bunx playwright test`

4. **CI pipeline (GitHub Actions):**
   ```yaml
   # .github/workflows/dispatch-app.yml
   on:
     push:
       branches: [main]
       paths: ['apps/dispatch-app/**']
     pull_request:
       paths: ['apps/dispatch-app/**']
   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: oven-sh/setup-bun@v2
         - run: cd apps/dispatch-app && bun install && bun test
         - run: cd apps/dispatch-app && bunx expo export --platform web  # verify web build succeeds
         - run: cd apps/dispatch-app && bunx playwright install --with-deps && bunx playwright test  # web E2E
     build-ios:
       runs-on: ubuntu-latest
       if: github.ref == 'refs/heads/main'
       steps:
         - uses: actions/checkout@v4
         - uses: expo/expo-github-action@v8
           with:
             eas-version: latest
             token: ${{ secrets.EXPO_TOKEN }}
         - run: cd apps/dispatch-app && eas build --non-interactive --platform ios --profile preview
   ```

**Files created:** ~10 files (tests + CI config + Maestro flows)
**Verification:** `bun test` passes with >80% coverage on hooks/api. Maestro flows pass on iOS simulator. Playwright smoke tests pass on web. CI runs on push.

---

### Phase 11: Web Deployment + agents.html Replacement (Day 20)

**Goal:** Deploy web build, replace agents.html, final integration.

**Steps:**

1. **Web export:**
   - `npx expo export --platform web` → `dist/` directory
   - Verify all routes work (tabs, chat/[id], agents/[id])
   - Test in Chrome, Firefox, Safari

2. **dispatch-api integration:**
   - Serve `dist/` at `/app/` route
   - Add redirect: `/agents.html` → `/app/agents` (backward compat)
   - Update any existing links to agents.html

3. **Final testing:**
   - Full end-to-end on physical iOS device via TestFlight
   - Full end-to-end on web via dispatch-api
   - Parallel operation: both Swift app and Expo app work simultaneously
   - Push notifications: verify APNs token registration

4. **Migration cutover plan:**
   - Keep Swift app installed during 1-week validation period
   - Switch primary push notification token to Expo app
   - Archive Swift app repo

**Verification:** Web app served at `/app/`, all features work. iOS TestFlight build works. agents.html redirects correctly.

---

## 7. Shared useMessages Hook Design

Both `useConversation` (chat) and `useAgentMessages` (agents) share identical patterns. Instead of duplicating, we use a single `useMessages` hook with API adapters:

```ts
// src/api/adapters.ts
import * as chatsApi from "./chats";
import * as agentsApi from "./agents";

export function chatAdapter(chatId: string): MessageAdapter<ChatMessage> {
  return {
    fetchMessages: (opts) => chatsApi.getMessages(chatId, opts),
    sendMessage: (content) => chatsApi.sendPrompt(chatId, content),
    clearMessages: () => chatsApi.clearMessages(chatId),
  };
}

export function agentAdapter(sessionId: string): MessageAdapter<AgentMessage> {
  return {
    fetchMessages: (opts) => agentsApi.getAgentMessages(sessionId, opts),
    sendMessage: (content) => agentsApi.sendAgentMessage(sessionId, content),
  };
}
```

```ts
// src/hooks/useMessages.ts
export function useMessages<T extends { id: string }>(adapter: MessageAdapter<T>) {
  const [messages, setMessages] = useState<T[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Shared logic:
  // - Initial fetch
  // - Polling with since/after cursor (1s for chat, 2s for agents — configurable)
  // - Exponential backoff on errors (2^n, max 30s)
  // - Optimistic insert on send (isPending flag)
  // - Incremental fetch with dedup by id
  // - clearMessages (if adapter supports it)

  return { messages, isLoading, error, sendMessage, clearMessages, refresh };
}
```

Usage in components:
```ts
// app/chat/[id].tsx
const chat = useMessages(chatAdapter(chatId));

// app/agents/[id].tsx
const agent = useMessages(agentAdapter(sessionId));
```

---

## 8. Native Feature Mapping

| Swift Feature | iOS Equivalent | Package | Web Equivalent |
|---|---|---|---|
| AVAudioEngine (recording) | Not needed (transcript only) | — | Not needed |
| SFSpeechRecognizer | `@jamsch/expo-speech-recognition` | `@jamsch/expo-speech-recognition` | Web Speech API |
| AVAudioPlayer (TTS) | `expo-audio` Sound | `expo-audio` | `HTMLAudioElement` |
| AVAudioSession config | `expo-audio` Audio mode | `expo-audio` | N/A |
| UIImpactFeedbackGenerator | `Haptics.impactAsync` | `expo-haptics` | No-op |
| Keychain (device token) | `SecureStore.setItemAsync` | `expo-secure-store` | `localStorage` |
| APNs registration | `Notifications.getDevicePushTokenAsync` | `expo-notifications` | Web Notifications API |
| UNUserNotificationCenter | Notifications listeners | `expo-notifications` | `Notification` constructor |
| NavigationStack | Expo Router Stack | `expo-router` | React Router (via expo-router) |
| .sheet() | React Native Modal + Animated | Built-in | CSS modal |
| UIImagePickerController | `ImagePicker.launchImageLibraryAsync` | `expo-image-picker` | `<input type="file">` |
| Timer.scheduledTimer | `setInterval` / `useEffect` | Built-in | Same |

---

## 9. API Base URL Strategy

```ts
// src/config/constants.ts
import { Platform } from "react-native";
import Constants from "expo-constants";

const DEV_URL = "http://localhost:9091";
const PROD_URL = "http://100.127.42.15:9091"; // Tailscale IP

export const API_BASE_URL = Platform.select({
  web: __DEV__ ? DEV_URL : (window.location.origin), // web: same origin in prod
  default: __DEV__ && !Constants.isDevice ? DEV_URL : PROD_URL,
});
```

On web production, the app is served by dispatch-api, so API calls go to the same origin — no CORS issues.

---

## 10. Dependencies Summary

### Production Dependencies

| Package | Version | Purpose | Web Support |
|---|---|---|---|
| `expo` | ~52 | Core framework | Yes |
| `expo-router` | ~4 | File-based navigation | Yes (via react-router) |
| `expo-audio` | ~0.3 | Audio playback (forward path, replaces expo-av) | Broken for events — `.web.ts` (`HTMLAudioElement`) is mandatory ([#35897](https://github.com/expo/expo/issues/35897)) |
| `@jamsch/expo-speech-recognition` | ^1.0 | On-device STT | No (`.web.ts` → Web Speech API) |
| `expo-notifications` | ~0.29 | Push notifications | No (`.web.ts` → Web Notifications) |
| `expo-secure-store` | ~14 | Device token storage | No (`.web.ts` → localStorage) |
| `expo-haptics` | ~14 | Haptic feedback | No (`.web.ts` → no-op) |
| `expo-image-picker` | ~16 | Camera/photo library | Partial (file input fallback) |
| `expo-file-system` | ~18 | Audio file caching (iOS only) | No (not needed on web) |
| `expo-constants` | ~17 | Build-time config access | Yes |
| `react-native-web` | ~0.19 | Web runtime | Yes (core) |
| `react-native-reanimated` | ~3 | Animations | Yes (JS fallback) |
| `react-native-gesture-handler` | ~2 | Gestures | Yes (touch/mouse) |
| `react-native-safe-area-context` | ~5 | Safe area | Yes |
| `react-dom` | ~18 | Web React DOM | Yes (web only) |
| `@expo/metro-runtime` | ~4 | Web bundling | Yes (web only) |

### Dev Dependencies

| Package | Version | Purpose |
|---|---|---|
| `typescript` | ~5.6 | Type checking |
| `@types/react` | ~18 | React types |
| `jest` | ~29 | Test runner |
| `jest-expo` | ~52 | Expo Jest preset |
| `@testing-library/react-native` | ~12 | Component testing |
| `@testing-library/react` | ~16 | Hook testing (`renderHook`) |
| `ts-jest` | ~29 | TypeScript Jest transform |

**Note:** `@testing-library/react-hooks` is deprecated. Use `renderHook` exported from `@testing-library/react` instead.

---

## 11. Migration Strategy

### 11.1 Parallel Operation

The Swift app and Expo app can run simultaneously because:
- They share the same backend API (`dispatch-api` on port 9091)
- Device tokens are unique per app install
- Push notifications go to whichever app has the latest APNs token
- Different bundle identifiers

### 11.2 Web Replaces agents.html

The web build replaces `agents.html` entirely:
- Static export served at `/app/` by dispatch-api
- `/agents.html` redirects to `/app/agents`
- Full app experience in the browser (not just agents)

### 11.3 Data Migration

No data migration needed:
- All messages live server-side in `sven-messages.db`
- Device token regenerates on install
- APNs token re-registers on launch

---

## 12. Risk Assessment + Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `@jamsch/expo-speech-recognition` partial results unreliable | Medium | High | Phase 0 spike validates this before committing. Fallback: Whisper API server-side |
| AVAudioSession conflict between STT and playback | Low (sequential) | High | Architecture ensures they never overlap. Phase 0 validates transition |
| Web Speech API quality/latency differs from iOS | Certain | Medium | Document to users. Accept as platform difference. Chrome works best |
| Web Speech API unsupported in Safari | High | Medium | Detect and fall back to text-only input on unsupported browsers |
| `expo-audio` is new and less battle-tested than `expo-av` | Medium | Medium | Phase 0 validates playback. Can fall back to expo-av if needed |
| react-native-web performance for long message lists | Medium | Medium | Test early. FlatList works but may need virtualization tuning on web |
| Push notification setup complexity | Low | High | Follow Expo docs exactly. Test with EAS build, not Expo Go |
| Tailscale network not available | Low | Medium | Web prod uses same-origin. iOS config allows URL override |
| Reanimated animations janky on web | Medium | Low | Use CSS transitions on web where possible via `.web.tsx` files |

---

## 13. Future Enhancements (Post-MVP)

These are explicitly out of scope for the initial build but documented for future work:

- **Siri Shortcuts / Action Button:** Requires native config plugin for AppIntents. Low priority — can use URL scheme as lightweight alternative.
- **Web Push API with Service Worker:** Background push notifications on web. Requires HTTPS, service worker, and backend integration with web push protocol.
- **Android support:** Expo makes this feasible but requires testing all platform-specific code paths. Not in scope until iOS + web are stable.
- **Offline support:** Cache messages locally for offline reading. Would require expo-sqlite or AsyncStorage.
- **End-to-end encryption indicator:** Visual indicator for Signal vs iMessage sessions.

---

## 14. Timeline Summary

| Phase | Days | Deliverable |
|---|---|---|
| 0. Audio Spike / PoC | 2 | Validated: STT, Web Speech API, audio playback transition |
| 1. Scaffolding + API Client + Tests | 2 | Project bootstrapped, API layer, test infra, web builds |
| 2. Chat List + Navigation | 1 | Tab navigator, chat list, navigation (iOS + web) |
| 3. Chat View + useMessages Hook | 2 | Full text messaging, shared hook |
| 4. Voice Recording + STT | 3 | Voice input on iOS + web, recording modal |
| 5. TTS Audio Playback | 1 | Audio playback on iOS + web, auto-read |
| 6. Push Notifications | 1 | APNs (iOS) + Web Notifications |
| 7. Agents Dashboard | 2 | Agents tab (reuses useMessages), replaces agents.html |
| 8. Image Attachments | 1 | Photo picker + upload (iOS + web) |
| 9. Settings + Polish | 2 | Settings, dark mode, perf, web-specific polish |
| 10. Testing + E2E + CI | 2 | Unit tests, Maestro E2E, CI pipeline |
| 11. Web Deploy + Cutover | 1 | Web export, dispatch-api serving, agents.html redirect |
| **Total** | **~20 days** | **Full feature parity + agents dashboard + web** |
