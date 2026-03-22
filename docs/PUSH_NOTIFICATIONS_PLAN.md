# Push Notifications for Sven App

> **Note:** The native SwiftUI Sven app has been deprecated. It has been moved to `~/dispatch/apps/sven-ios-deprecated/`. The active app is the Expo/React Native app at `~/dispatch/apps/dispatch-app/`.

Implementation plan for adding push notifications so Nikhil gets notified when Sven responds.

## Overview

**Goal:** When Sven stores a response via `reply-sven`, send a push notification to the iOS app.

**Flow:**
```
User speaks → Sven processes → reply-sven stores message
                                      ↓
                              Send APNs push notification
                                      ↓
                              iPhone receives notification
                                      ↓
                              User taps → Opens app → Plays audio response
```

## Components to Modify

### 1. iOS App (~/dispatch/apps/dispatch-app)

#### A. Enable Push Notifications Capability
- Open Xcode project
- Select target → Signing & Capabilities
- Add "Push Notifications" capability
- Add "Background Modes" → Remote notifications (for silent pushes)

#### B. Create AppDelegate for Push Registration
```swift
// New file: AppDelegate.swift
import UIKit
import UserNotifications

class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        registerForPushNotifications()
        return true
    }

    func registerForPushNotifications() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            DispatchQueue.main.async {
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
    }

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        print("APNs token: \(token)")

        // Send token to backend
        Task {
            try? await SvenAPIClient.shared.registerAPNsToken(token)
        }
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("Failed to register for APNs: \(error)")
    }

    // Handle notification when app is in foreground
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }

    // Handle notification tap
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        // Trigger message refresh
        NotificationCenter.default.post(name: .refreshMessages, object: nil)
        completionHandler()
    }
}
```

#### C. Update SvenApp.swift
```swift
@main
struct SvenApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
```

#### D. Add API Method in SvenAPIClient.swift
```swift
/// Register APNs device token with backend
func registerAPNsToken(_ apnsToken: String) async throws {
    let deviceToken = getOrCreateDeviceToken()  // existing device token
    guard let url = URL(string: "\(baseURL)/register-apns") else {
        throw APIError.invalidURL
    }

    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    let body: [String: String] = [
        "device_token": deviceToken,
        "apns_token": apnsToken
    ]

    request.httpBody = try JSONSerialization.data(withJSONObject: body)

    let (_, response) = try await URLSession.shared.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
        throw APIError.serverError(statusCode: 0, message: "Failed to register APNs token")
    }
}
```

### 2. Backend (Mac Server)

#### A. Store APNs Token
Add endpoint to sven-server to store APNs token:

```python
# In sven-server or new service
# Store mapping: device_token -> apns_token

APNS_TOKENS_FILE = Path.home() / "dispatch" / "state" / "sven-apns-tokens.json"

@app.post("/register-apns")
async def register_apns(device_token: str, apns_token: str):
    tokens = json.loads(APNS_TOKENS_FILE.read_text()) if APNS_TOKENS_FILE.exists() else {}
    tokens[device_token] = apns_token
    APNS_TOKENS_FILE.write_text(json.dumps(tokens))
    return {"status": "ok"}
```

#### B. Create Push Notification Script
New script: `~/.claude/skills/sven-app/scripts/send-push`

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "PyJWT"]
# ///
"""
send-push - Send APNs push notification to Sven iOS app.

Usage:
    send-push <message_id> <preview_text>
"""

import argparse
import json
import time
from pathlib import Path
import httpx
import jwt

# Config paths
APNS_KEY_PATH = Path.home() / ".claude" / "secrets" / "apns-key.p8"
APNS_TOKENS_PATH = Path.home() / "dispatch" / "state" / "sven-apns-tokens.json"

# APNs config (update these after creating key in dev portal)
TEAM_ID = "YOUR_TEAM_ID"  # From Apple Developer account
KEY_ID = "YOUR_KEY_ID"    # From APNs key in dev portal
BUNDLE_ID = "com.yourcompany.Sven"  # Your app's bundle ID

# APNs endpoints
APNS_HOST_PROD = "https://api.push.apple.com"
APNS_HOST_SANDBOX = "https://api.sandbox.push.apple.com"


def create_apns_jwt():
    """Create JWT for APNs authentication."""
    key = APNS_KEY_PATH.read_text()

    headers = {
        "alg": "ES256",
        "kid": KEY_ID
    }

    payload = {
        "iss": TEAM_ID,
        "iat": int(time.time())
    }

    return jwt.encode(payload, key, algorithm="ES256", headers=headers)


def send_notification(apns_token: str, message_id: str, preview: str, sandbox: bool = False):
    """Send push notification via APNs."""
    host = APNS_HOST_SANDBOX if sandbox else APNS_HOST_PROD

    token = create_apns_jwt()

    headers = {
        "authorization": f"bearer {token}",
        "apns-topic": BUNDLE_ID,
        "apns-push-type": "alert",
        "apns-priority": "10"
    }

    payload = {
        "aps": {
            "alert": {
                "title": "Sven",
                "body": preview[:100] + "..." if len(preview) > 100 else preview
            },
            "sound": "default",
            "badge": 1
        },
        "message_id": message_id
    }

    with httpx.Client(http2=True) as client:
        response = client.post(
            f"{host}/3/device/{apns_token}",
            headers=headers,
            json=payload
        )

        if response.status_code == 200:
            print(f"Push sent successfully to {apns_token[:20]}...")
        else:
            print(f"Push failed: {response.status_code} - {response.text}")


def main():
    parser = argparse.ArgumentParser(description="Send APNs push notification")
    parser.add_argument("message_id", help="Message ID")
    parser.add_argument("preview", help="Preview text for notification")
    parser.add_argument("--sandbox", action="store_true", help="Use sandbox APNs")
    args = parser.parse_args()

    # Load registered tokens
    if not APNS_TOKENS_PATH.exists():
        print("No APNs tokens registered")
        return

    tokens = json.loads(APNS_TOKENS_PATH.read_text())

    # Send to all registered devices
    for device_token, apns_token in tokens.items():
        send_notification(apns_token, args.message_id, args.preview, args.sandbox)


if __name__ == "__main__":
    main()
```

#### C. Modify reply-sven to Trigger Push
Add to end of `reply-sven` after storing message:

```python
# After store_message()

# Trigger push notification
PUSH_SCRIPT = Path.home() / ".claude" / "skills" / "sven-app" / "scripts" / "send-push"
if PUSH_SCRIPT.exists():
    try:
        # Truncate for preview
        preview = message[:100] + "..." if len(message) > 100 else message
        subprocess.run(
            [str(PUSH_SCRIPT), message_id, preview],
            capture_output=True,
            timeout=10
        )
    except Exception as e:
        print(f"Push notification failed: {e}", file=sys.stderr)
```

### 3. Apple Developer Portal Setup

#### A. Create APNs Key
1. Go to https://developer.apple.com/account/resources/authkeys
2. Create new key → Enable "Apple Push Notifications service (APNs)"
3. Download the .p8 file
4. Save to `~/.claude/secrets/apns-key.p8`
5. Note the Key ID (10 character string)

#### B. Enable Push Capability for App ID
1. Go to Identifiers → App IDs
2. Select Sven app ID (or create one)
3. Enable "Push Notifications" capability
4. Save

#### C. Get Team ID
1. Go to Membership (top right of developer portal)
2. Note your Team ID

### 4. Configuration File

Create `~/dispatch/state/sven-push-config.json`:
```json
{
  "team_id": "YOUR_TEAM_ID",
  "key_id": "YOUR_KEY_ID",
  "bundle_id": "com.yourcompany.Sven",
  "key_path": "~/.claude/secrets/apns-key.p8",
  "use_sandbox": false
}
```

## TestFlight Considerations

- TestFlight builds use **PRODUCTION** APNs environment, not sandbox
- Set `use_sandbox: false` in config for TestFlight testing
- Device tokens are different between debug and TestFlight builds
- Re-register APNs token each time app launches (tokens can change)

## Implementation Order

1. **Apple Developer Portal** - Create APNs key, enable capability ✅ (2026-02-11)
   - Key ID: X3H9DPHLAM
   - Environment: Sandbox & Production
   - Key saved: ~/.claude/secrets/AuthKey_X3H9DPHLAM.p8
2. **iOS App** - Add AppDelegate, request permissions, send token to backend ✅ (2026-02-11)
   - AppDelegate.swift created with push registration
   - SvenApp.swift updated with @UIApplicationDelegateAdaptor
   - SvenAPIClient.swift updated with registerAPNsToken method
   - Sven.entitlements created with aps-environment
   - Build 36 with push notifications (used Tailscale IP)
   - Build 38 with local network IP fix (10.10.10.59)
3. **Backend** - Add /register-apns endpoint to store tokens ✅ (2026-02-11)
   - Endpoint added to ~/dispatch/services/dispatch-api/server.py
   - Stores mapping: device_token -> apns_token
   - File: ~/dispatch/state/sven-apns-tokens.json
4. **Push Script** - Create send-push script ✅ (2026-02-11)
   - ~/.claude/skills/sven-app/scripts/send-push
   - Config: ~/dispatch/state/sven-push-config.json
5. **Integrate** - Modify reply-sven to call send-push ✅ (2026-02-11)
   - Triggers push notification after storing message
6. **Test** - Deploy to TestFlight and test end-to-end ⏳
   - Build 36: Push permission alert showed but APNs token not registered (Tailscale not connected)
   - Build 38: Fixed to use local network IP (10.10.10.59) - awaiting testing

## Fallback: Polling

If push fails, the app already polls for messages when in foreground. Consider adding:
- Background fetch for periodic polling
- Silent push notifications to trigger background refresh

## Security Notes

- APNs key (.p8) is sensitive - keep in ~/.claude/secrets/
- Device tokens are device-specific, not sensitive
- APNs tokens rotate occasionally - always re-register on app launch
