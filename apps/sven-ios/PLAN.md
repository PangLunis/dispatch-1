# Sven App - Implementation Plan

**Status:** iOS app deployed to TestFlight, Tailscale connected, API endpoint pending

## Overview

Sven is an iOS app that lets you talk to the AI assistant via the iPhone Action Button:
1. Press Action Button → app opens and immediately starts recording
2. Speak your message → on-device transcription with silence detection
3. Auto-stops after 2s of silence → POSTs transcript to mac via Tailscale
4. Mac injects prompt into your session → responds via SMS

## Architecture

```
┌─────────────────┐     Tailscale      ┌─────────────────┐
│   iPhone        │    (100.x.x.x)     │   Mac Mini      │
│                 │ ──────────────────>│                 │
│  Sven App       │   POST /prompt     │  API Server     │
│  - Action Button│   {transcript,     │  - Verify token │
│  - AVAudioEngine│    token, attest}  │  - inject-prompt│
│  - Speech Recog │                    │  - SMS response │
└─────────────────┘                    └─────────────────┘
```

## Security (App Attest + Per-User Tokens)

### Layer 1: App Attest (Hardware Attestation)
- iOS DeviceCheck framework proves request comes from genuine app on real device
- Can't be spoofed without Apple's private keys
- Blocks: emulators, jailbroken devices, modified binaries

### Layer 2: Per-Device Token
- Generated on first launch, stored in iOS Keychain
- Mac maintains allowlist of registered tokens
- One-time pairing like AirPods

### Layer 3: Network Isolation (Tailscale)
- No public URL - only devices on your tailnet can reach the API
- Phone Tailscale IP: 100.96.157.83
- Mac Tailscale IP: 100.127.42.15

### Layer 4: Rate Limiting
- Max N requests per minute per token
- Stops abuse even if token somehow leaks

## iOS App Components

### 1. App Intents (Action Button)
```swift
struct AskSvenIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask Sven"
    static var openAppWhenRun: Bool = true

    func perform() async throws -> some IntentResult {
        AppState.shared.shouldStartRecording = true
        return .result()
    }
}

struct SvenShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: AskSvenIntent(),
                    phrases: ["Ask Sven", "Hey Sven"],
                    shortTitle: "Ask Sven",
                    systemImageName: "mic.fill")
    }
}
```

### 2. Audio Recording (AVAudioEngine)
- Real-time audio capture
- Save to .caf file (proper format, not fake .m4a)
- Audio level metering for UI feedback

### 3. Speech Recognition (SFSpeechRecognizer)
- On-device recognition (`requiresOnDeviceRecognition = true`)
- Real-time partial transcripts
- Accumulate final segments (don't overwrite on pauses)

### 4. Silence Detection
- Track last speech timestamp
- 2-second threshold triggers auto-stop
- 2-minute max duration cap

### 5. API Client
```swift
func sendToMac(transcript: String) async throws {
    let url = URL(string: "http://100.127.42.15:9091/prompt")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    let body: [String: Any] = [
        "transcript": transcript,
        "token": KeychainHelper.getDeviceToken(),
        "attestation": try await getAppAttestAssertion()
    ]
    request.httpBody = try JSONSerialization.data(withJSONObject: body)

    let (_, response) = try await URLSession.shared.data(for: request)
    // Response comes via SMS, not HTTP
}
```

## Mac API Server

### Endpoint: POST /prompt
```python
@app.post("/prompt")
async def receive_prompt(request: PromptRequest):
    # 1. Verify App Attest assertion
    if not verify_app_attest(request.attestation):
        raise HTTPException(401, "Invalid attestation")

    # 2. Verify device token
    if request.token not in allowed_tokens:
        raise HTTPException(401, "Unknown device")

    # 3. Rate limit check
    if is_rate_limited(request.token):
        raise HTTPException(429, "Too many requests")

    # 4. Inject prompt into user's session
    inject_prompt(chat_id, request.transcript)

    return {"status": "ok"}
```

### Running the Server
```bash
# Start on boot via launchd or systemd
uvicorn sven_api:app --host 0.0.0.0 --port 9091
```

## Testing Strategy

### Simulator Testing
- Xcode > Product > Scheme > Edit Scheme > Options > Audio Input: Mac Microphone
- Can test recording, transcription, UI
- Cannot test App Attest (requires real device)

### Device Testing (TestFlight)
- App is deployed: "Sven Assistant" (App ID: 6758918985)
- Action Button: Settings > Action Button > Shortcut > "Ask Sven"
- Full end-to-end testing with Tailscale

## Known Issues & Fixes

1. **Transcript overwrites on pauses** - accumulate final segments instead of replacing
2. **Audio format** - use .caf not .m4a (or add AAC encoding)
3. **Thread safety** - @MainActor for UI updates, locks for shared state
4. **Cold launch race** - use AppState singleton, not NotificationCenter
5. **iOS 17 onChange** - use new signature `{ _, newValue in }`

## File Locations

- iOS App: `~/dispatch/apps/sven-ios/` (moved from ~/code/ios-apps/Sven/ on 2026-02-11)
- Mac API: `~/dispatch/services/dispatch-api/` (to be created)
- This Plan: `~/dispatch/apps/sven-ios/PLAN.md`

## Next Steps

1. [x] Build iOS app with recording + transcription
2. [x] Deploy to TestFlight
3. [x] Set up Tailscale between phone and mac
4. [x] Fix transcript overwrite bug - switched to Moonshine, accumulates lines
5. [x] Create API server on mac (port 9091) - ~/dispatch/services/dispatch-api/server.py
6. [ ] Add App Attest to iOS app
7. [ ] Update iOS app to POST to mac
8. [ ] Test end-to-end flow
9. [x] Add push notifications (2026-02-11)
   - APNs key created: X3H9DPHLAM
   - iOS app: AppDelegate.swift, SvenApp.swift updated
   - Backend: /register-apns endpoint added
   - Push script: ~/.claude/skills/sven-app/scripts/send-push
   - reply-sven now triggers push after storing message

## Moonshine Integration (2026-02-09)

Replaced Apple's SpeechAnalyzer/SFSpeechRecognizer with Moonshine:
- SPM: `https://github.com/moonshine-ai/moonshine-swift.git` v0.0.45
- Model: base-en (~134MB, stored in app bundle at `models/base-en/`)
- Handles pause accumulation better - uses `lineId` to track and update transcript lines
- Events: LineStarted, LineTextChanged, LineCompleted (not enum, separate struct types)
- Build 13 deployed with Moonshine
- Build 14: Added post-processing to fix "spin" → "Sven" misrecognition
  - Moonshine doesn't support custom vocabulary/hotwords
  - Added `postProcessTranscript()` function with word boundary regex replacement

---

*Reconstructed from chat history on 2026-02-08*
