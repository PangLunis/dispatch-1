# iOS Development with Dispatch

> **Note:** The native SwiftUI Sven app has been deprecated. It has been moved to `~/dispatch/apps/sven-ios-deprecated/`. The active app is the Expo/React Native app at `~/dispatch/apps/dispatch-app/`.

This guide covers setting up iOS development capabilities for Dispatch, enabling Claude to build, test, and deploy iOS apps to TestFlight.

## Overview

Dispatch can:
- Create SwiftUI/UIKit projects
- Build and run apps in the iOS Simulator
- Take screenshots of running apps
- Archive and upload to TestFlight
- All via command line (no Xcode GUI needed for most tasks)

## Prerequisites Checklist

| Requirement | How to Check | How to Install |
|-------------|--------------|----------------|
| Xcode | `xcodebuild -version` | App Store or `mas install 497799835` |
| Xcode license accepted | N/A | `sudo xcodebuild -license accept` |
| CoreSimulator framework | `xcrun simctl list` works | `sudo xcodebuild -runFirstLaunch` |
| iOS Simulator runtime | `xcrun simctl list runtimes` shows iOS | `xcodebuild -downloadPlatform iOS` |
| Apple Developer account | N/A | developer.apple.com ($99/yr for TestFlight) |
| Signed into Xcode | Xcode > Settings > Accounts | Manual (requires 2FA) |

## Installation Steps

### Step 1: Install Xcode (~12GB)

**Option A: App Store CLI**
```bash
# Requires mas CLI (brew install mas)
mas install 497799835
```

**Option B: App Store GUI**
1. Open App Store
2. Search "Xcode"
3. Click Install

**Option C: Direct Download**
- developer.apple.com/download/applications/

### Step 1.5: Point xcode-select to Xcode.app

**IMPORTANT:** After installing Xcode, `xcode-select` may still point to CommandLineTools. Fix this first:

```bash
# Check current path
xcode-select -p
# If it shows /Library/Developer/CommandLineTools, switch it:
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
```

### Step 2: Accept License Agreement

```bash
sudo xcodebuild -license accept
```

### Step 3: Install Additional Components

```bash
# Installs CoreSimulator and other frameworks (required for simulators)
sudo xcodebuild -runFirstLaunch
```

### Step 4: Download iOS Simulator Runtime (~8.4GB)

```bash
xcodebuild -downloadPlatform iOS
```

Check installed runtimes:
```bash
xcrun simctl list runtimes
```

### Step 5: Sign into Xcode with Apple ID

**This step requires manual interaction (2FA):**

1. Open Xcode
2. Go to Xcode > Settings > Accounts (Cmd+,)
3. Click "+" to add an Apple ID
4. Sign in with your Apple Developer account
5. Approve 2FA on your device

This enables:
- Automatic code signing
- Provisioning profile management
- TestFlight uploads

## Verification

Run these commands to verify setup:

```bash
# Check Xcode version
xcodebuild -version

# List available simulators
xcrun simctl list devices available

# Check for iOS runtime
xcrun simctl list runtimes | grep iOS

# Boot a simulator
xcrun simctl boot "iPhone 16 Pro"
open -a Simulator

# Take a screenshot (to verify simulator is working)
sleep 5  # wait for boot
xcrun simctl io booted screenshot ~/Desktop/sim-test.png
```

## Project Structure

iOS apps live in two locations:

**Dispatch app (active, Expo/React Native):**
```
~/dispatch/apps/dispatch-app/
```

**Sven SwiftUI app (deprecated):**
```
~/dispatch/apps/sven-ios-deprecated/
```

**Other iOS apps:**
```
~/code/ios-apps/
├── AppName/
│   ├── AppName.xcodeproj/
│   │   └── project.pbxproj
│   └── AppName/
│       ├── AppNameApp.swift      # @main entry point
│       ├── ContentView.swift     # Main UI
│       └── Assets.xcassets/      # App icons, colors
```

**Bundle ID convention:** `com.sven.AppName`

## Skill Reference

Full documentation is in the ios-app skill:
- `~/.claude/skills/ios-app/SKILL.md`

Quick commands:

```bash
# Build for simulator
xcodebuild -project ~/code/ios-apps/AppName/AppName.xcodeproj \
  -scheme AppName -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro' \
  CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO build

# Install on booted simulator
xcrun simctl install booted /path/to/AppName.app

# Launch app
xcrun simctl launch booted com.dispatch.AppName

# Screenshot
xcrun simctl io booted screenshot ~/Desktop/screenshot.png
```

## TestFlight Deployment

See `~/.claude/skills/ios-app/SKILL.md` for full TestFlight workflow:
1. Archive the app
2. Create ExportOptions.plist
3. Export and upload to App Store Connect
4. Enable TestFlight testing in App Store Connect

## Lessons Learned

<!-- Add lessons as we learn them -->

### First-Time Setup

1. **First simulator boot is SLOW** (5-10+ minutes for iOS 26.x). The simulator shows an Apple logo with progress bar. Use `xcrun simctl io booted screenshot` to check status instead of waiting for Simulator.app window.

2. **Component installer dialog** - First time opening Xcode may show a dialog to download additional components. Click "Download & Install" or use axctl to click it programmatically.

3. **Signing requires Xcode sign-in** - You can't archive for TestFlight without signing into Xcode with an Apple Developer account. This can't be automated (requires 2FA).

4. **mas install may need sudo** - If `mas install` fails with permission errors, run it from a terminal with sudo access or use the App Store GUI.

5. **xcode-select points to wrong path** - After Xcode install, `xcode-select -p` may still show `/Library/Developer/CommandLineTools`. Run `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer` to fix. This causes "Xcode required" errors even when Xcode is installed.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `xcodebuild: error: unable to find utility` | Xcode not installed or not selected. Run `xcode-select -s /Applications/Xcode.app` |
| `simctl: error: unable to boot device` | Run `sudo xcodebuild -runFirstLaunch` first |
| No simulators in list | Download platform: `xcodebuild -downloadPlatform iOS` |
| Signing errors | Sign into Xcode with Apple Developer account |
| Archive fails | Use `-sdk iphoneos` not `iphonesimulator` |
