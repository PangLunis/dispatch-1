---
name: ios-app
description: Build, test, and deploy iOS apps to Simulator and TestFlight. Use when working with Xcode projects, iOS development, simulator, archiving, or TestFlight distribution.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# iOS App Development Skill

Build, test, and deploy iOS apps from the command line.

**Project locations:**
- **Sven app**: `~/dispatch/apps/sven-ios/` (consolidated into dispatch repo)
- **Other apps**: `~/code/ios-apps/`

## Development Workflow (MUST FOLLOW)

**CRITICAL: Always test in simulator and get user approval BEFORE deploying to device.**

### The Golden Rule: Simulator First, Device/TestFlight Last

1. **Build for Simulator** - fast iteration, no signing required
2. **Test all CUJs manually** - walk through every critical user journey
3. **Screenshot each CUJ** - capture evidence of working features
4. **Send screenshots to user** - get explicit approval before proceeding
5. **Deploy to device** - prefer direct deploy (see below), fall back to TestFlight

### Deployment Priority: Direct Device Deploy > TestFlight

**When deploying to Nikhil's device:**
1. **FIRST: Try direct device deploy via Xcode** - instant (~30 seconds), no TestFlight processing
2. **FALLBACK: Use TestFlight** - only if direct deploy fails (not on wifi, device unavailable)

Direct device deploy is 10x faster than TestFlight (30s vs 10-30 min processing).

**Decision tree:**
```
Is Nikhil available on same WiFi network?
├── YES → Direct device deploy (preferred)
│   └── Check with: xcrun devicectl list devices
│   └── Deploy with: xcrun devicectl device install app --device "Nikhil iPhone 16" <app_path>
└── NO → TestFlight
    └── When: Nikhil is away, device sleeping, or sharing with multiple testers
```

### Why This Matters

- TestFlight builds take 10-30 min to process
- Each TestFlight upload creates a new build number (can't reuse)
- Users have to wait for install + trust the app
- Bugs found in TestFlight waste everyone's time
- Simulator catches 90% of issues instantly

### CUJ Testing Checklist

Before ANY TestFlight upload, manually verify:

```
[ ] App launches without crash
[ ] Main screen renders correctly (screenshot)
[ ] All buttons/interactions work (screenshot each)
[ ] Navigation flows work (screenshot each screen)
[ ] Data displays correctly
[ ] Error states handled gracefully
[ ] Console logs show no errors
```

**Send ALL screenshots to user with `--image` flag and wait for approval.**

```bash
# Take screenshot
xcrun simctl io booted screenshot /tmp/cuj-main-screen.png
# Send to user for review
~/.claude/skills/sms-assistant/scripts/send-sms "CHAT_ID" "Main screen ready for review" --image /tmp/cuj-main-screen.png
```

### Example Workflow

```
1. User: "Build me a todo app"
2. You: Create app, build for simulator
3. You: Test adding a todo → screenshot → send to user
4. You: Test completing a todo → screenshot → send to user
5. You: Test deleting a todo → screenshot → send to user
6. User: "Looks good, ship it!"
7. You: NOW archive and upload to TestFlight
```

**Never skip to TestFlight. Always get user sign-off on simulator screenshots first.**

## Prerequisites

- Xcode installed (verify: `xcodebuild -version`)
- Apple Developer Program membership ($99/yr) for TestFlight
- Xcode license accepted: `sudo xcodebuild -license accept`
- First launch setup: `sudo xcodebuild -runFirstLaunch` (installs CoreSimulator framework)
- iOS simulator runtime: `xcodebuild -downloadPlatform iOS` (~8.4 GB download)
- Apple ID signed into Xcode (Settings > Accounts) for code signing - requires 2FA approval

## Critical First-Time Setup Notes

**After installing Xcode from App Store, you MUST run these in order:**
1. `sudo xcodebuild -license accept` (needs Terminal with sudo)
2. `sudo xcodebuild -runFirstLaunch` (installs CoreSimulator and other frameworks)
3. `xcodebuild -downloadPlatform iOS` (downloads simulator runtime, ~8.4 GB)
4. Open Xcode and click "Download & Install" if component installer dialog appears
5. Sign into Xcode with Apple ID (Settings > Accounts > "+") for signing certificates

**First simulator boot is VERY slow** (5-10+ minutes for iOS 26.x). The simulator will show the Apple logo with a progress bar for a long time. Be patient. Use `xcrun simctl io booted screenshot /tmp/check.png` to check progress without relying on the Simulator.app window.

**The `mas` CLI can install from App Store** but needs sudo: `brew install mas && mas install 497799835` (Xcode's App Store ID)

## Project Structure

**Sven app (in dispatch repo):**
```
~/dispatch/apps/sven-ios/
├── Sven.xcodeproj/
├── Sven/
│   ├── SvenApp.swift
│   └── ...
└── build/
```

**Other apps:**
```
~/code/ios-apps/
├── AppName/
│   ├── AppName.xcodeproj/
│   │   └── project.pbxproj
│   └── AppName/
│       ├── AppNameApp.swift      # @main entry point
│       ├── ContentView.swift     # Main UI
│       └── Assets.xcassets/      # (optional) App icons, colors
```

## Simulator Workflow

### List Available Simulators
```bash
xcrun simctl list devices available
```

### Boot a Simulator
```bash
xcrun simctl boot "iPhone 16 Pro"

# Open Simulator.app to see it
open -a Simulator
```

### Build for Simulator
```bash
xcodebuild \
  -project ~/code/ios-apps/AppName/AppName.xcodeproj \
  -scheme AppName \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro' \
  -configuration Debug \
  CODE_SIGN_IDENTITY="" \
  CODE_SIGNING_REQUIRED=NO \
  build
```

The built .app will be in DerivedData:
```bash
# Find it
find ~/Library/Developer/Xcode/DerivedData -name "AppName.app" -path "*/Debug-iphonesimulator/*" 2>/dev/null
```

### Install and Launch on Simulator
```bash
# Install
xcrun simctl install booted /path/to/AppName.app

# Launch (basic)
xcrun simctl launch booted com.dispatch.AppName

# Launch with console output (captures print() statements)
xcrun simctl launch --console-pty booted com.dispatch.AppName
```

**Tip:** Use `--console-pty` to see `print()` output directly in your terminal. This is the easiest way to debug.

### Screenshot the Simulator
```bash
xcrun simctl io booted screenshot ~/Desktop/screenshot.png
```

### Stream Logs
```bash
# Easiest: launch with --console-pty to see print() output
xcrun simctl launch --console-pty booted com.dispatch.AppName

# All logs from simulator (verbose)
xcrun simctl spawn booted log stream --level debug

# Filter to your app by process name
xcrun simctl spawn booted log stream --level debug --predicate 'processImagePath contains "AppName"'

# Filter by subsystem (if using os.Logger)
xcrun simctl spawn booted log stream --level debug --predicate 'subsystem == "com.dispatch.AppName"'

# Show recent logs (not streaming)
xcrun simctl spawn booted log show --last 5m --predicate 'processImagePath contains "AppName"'
```

**Logging best practices:**
- Use `print()` for quick debugging - captured by `--console-pty`
- Use `os.Logger` for structured logging - captured by `log stream`
- Example Logger setup:
```swift
import os
extension Logger {
    static let app = Logger(subsystem: "com.dispatch.AppName", category: "app")
}
// Usage: Logger.app.info("Something happened")
```

### Other Useful Simulator Commands
```bash
# Shutdown simulator
xcrun simctl shutdown booted

# Erase all content (factory reset)
xcrun simctl erase "iPhone 16 Pro"

# Open a URL in simulator
xcrun simctl openurl booted "https://example.com"

# Set dark/light mode
xcrun simctl ui booted appearance dark
xcrun simctl ui booted appearance light

# Uninstall app
xcrun simctl uninstall booted com.dispatch.AppName

# Get app container path (to inspect files)
xcrun simctl get_app_container booted com.dispatch.AppName
```

## Direct Device Deployment (PREFERRED)

**Deploy directly to physical devices via Xcode - instant, no TestFlight wait.**

**⚠️ ALWAYS try this first when Nikhil is available.** It's 10-30x faster than TestFlight.

### Prerequisites (One-Time Setup)

1. **Pair device via USB:** Connect phone with cable, tap "Trust This Computer" on phone
2. **Enable Developer Mode:** Settings → Privacy & Security → Developer Mode → ON (restart required)
3. **Same wifi network:** Mac and phone must be on same network for wireless deploy

After USB pairing once, future deploys can be wireless.

**Known paired devices:**
- "Nikhil iPhone 16" - Nikhil's iPhone (paired 2026-02-09)

### Check Device Availability

```bash
# List all connected devices (USB and wireless)
xcrun devicectl list devices

# Look for your device name and connection state
# "available" = ready to deploy
# "unavailable" = not on network or asleep
```

### Deploy to Device

```bash
# Build and run on physical device
xcodebuild \
  -project ~/code/ios-apps/AppName/AppName.xcodeproj \
  -scheme AppName \
  -destination 'platform=iOS,name=Device Name' \
  -allowProvisioningUpdates \
  build

# Find the built .app
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData -name "AppName.app" -path "*/Debug-iphoneos/*" 2>/dev/null | head -1)

# Install on device
xcrun devicectl device install app --device "Device Name" "$APP_PATH"
```

**Or use xcodebuild with `-destination` for build + install in one step:**

```bash
xcodebuild \
  -project ~/code/ios-apps/AppName/AppName.xcodeproj \
  -scheme AppName \
  -destination 'platform=iOS,name=Device Name' \
  -allowProvisioningUpdates \
  build
```

### Device Names

Find exact device name with `xcrun devicectl list devices`. Example names:
- "Nikhil iPhone 16" - Nikhil's iPhone
- "iPhone 16 Pro Max" - generic name if renamed

### Quick Deploy Command

For rapid iteration, use this one-liner after building:

```bash
# Build for device
xcodebuild \
  -project ~/code/ios-apps/AppName/AppName.xcodeproj \
  -scheme AppName \
  -destination 'platform=iOS,name=Nikhil iPhone 16' \
  -allowProvisioningUpdates \
  build

# Find and install
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData -name "AppName.app" -path "*/Debug-iphoneos/*" 2>/dev/null | head -1)
xcrun devicectl device install app --device "Nikhil iPhone 16" "$APP_PATH"
```

### When to Use TestFlight Instead

Use TestFlight only when:
- Device not on same wifi network (Nikhil is away)
- Device unavailable/sleeping and user can't wake it
- Need to distribute to multiple testers (not just Nikhil)
- Need build to persist (device deploys expire after ~7 days)
- Sharing with external beta testers

**Default to direct deploy** for Nikhil when he's available and on the same network.

## TestFlight Deployment Workflow

### Step 1: Find Your Team ID

```bash
# Best method: Look up from keychain after signing in to Xcode
security find-certificate -c "Apple Development" -p 2>/dev/null | openssl x509 -text | grep -oE 'OU=[A-Z0-9]+' | head -1 | cut -d= -f2

# Or via App Store Connect > Membership > Team ID
```

Store it in `~/.dispatch.env` as `APPLE_DEV_TEAM_ID=XXXXXXXXXX` for reuse.

### Step 2: Archive the App

```bash
xcodebuild archive \
  -project ~/code/ios-apps/AppName/AppName.xcodeproj \
  -scheme AppName \
  -configuration Release \
  -archivePath ~/code/ios-apps/AppName/build/AppName.xcarchive \
  -allowProvisioningUpdates
```

### Step 3: Create ExportOptions.plist

```bash
cat > ~/code/ios-apps/AppName/build/ExportOptions.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store-connect</string>
    <key>destination</key>
    <string>upload</string>
    <key>signingStyle</key>
    <string>automatic</string>
    <key>uploadSymbols</key>
    <true/>
</dict>
</plist>
EOF
```

### Step 4: Export and Upload IPA

```bash
xcodebuild -exportArchive \
  -archivePath ~/code/ios-apps/AppName/build/AppName.xcarchive \
  -exportPath ~/code/ios-apps/AppName/build \
  -exportOptionsPlist ~/code/ios-apps/AppName/build/ExportOptions.plist \
  -allowProvisioningUpdates
```

With `destination: upload`, this exports AND uploads to App Store Connect in one step.

### Alternative Upload Method (if exporting separately)

```bash
# Upload with altool using API key
xcrun altool --upload-app \
  --file ~/code/ios-apps/AppName/build/AppName.ipa \
  --apiKey YOUR_API_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID
```

### Step 5: App Store Connect Setup

**Apple Login CAN Be Automated** using the chrome-control skill's iframe commands.

The login form uses a cross-origin iframe (`idmsa.apple.com`), but the Chrome extension has special commands (`iframe-click` and `insert-text`) that can interact with it. Credentials are stored in `~/.claude/secrets.env`.

#### Automated Apple Login Flow

```bash
# 1. Navigate to App Store Connect
chrome navigate <tab_id> "https://appstoreconnect.apple.com"
sleep 3

# 2. Click email field and enter email (from secrets.env)
chrome iframe-click <tab_id> 'input[type="text"]'
chrome insert-text <tab_id> '${APPLE_ID_EMAIL}'  # from secrets.env

# 3. Click Continue
chrome iframe-click <tab_id> 'button#sign-in'
sleep 3

# 4. Click "Continue with Password"
chrome iframe-click <tab_id> 'text:Continue with Password'
sleep 2

# 5. Enter password (auto-focused after step 4)
chrome insert-text <tab_id> 'YOUR_PASSWORD_HERE'

# 6. Click Sign In
chrome iframe-click <tab_id> 'button#sign-in'
sleep 4

# Done - should now be logged in!
```

**Note:** The `iframe-click` and `insert-text` commands use `Page.createIsolatedWorld` with `grantUniversalAccess:true` to bypass cross-origin restrictions. See the chrome-control skill for full documentation.

Once logged in, you can automate everything else in App Store Connect.

If this is the first upload for an app, you need to:
1. **Register the Bundle ID** in Apple Developer Portal
2. **Create the App** in App Store Connect
3. Then upload will work

#### Registering Bundle ID (automated via Chrome)

Navigate to https://developer.apple.com/account/resources/identifiers/add/bundleId and fill the form with JS:

```javascript
// On developer.apple.com/account/resources/identifiers/add/bundleId
// FIRST: Click "App IDs" > "App" > Continue to get to the form
// Then run this JS:

const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;

// Get text inputs by position (form doesn't have name attributes)
// First input = Description, Second input = Bundle ID
const inputs = Array.from(document.querySelectorAll("input[type=text]"));
const descInput = inputs[0];
const bundleInput = inputs[1];

// Fill Description
nativeInputValueSetter.call(descInput, "App Name");
descInput.dispatchEvent(new Event("input", {bubbles: true}));

// Fill Bundle ID (use com.sven.AppName format)
nativeInputValueSetter.call(bundleInput, "com.sven.AppName");
bundleInput.dispatchEvent(new Event("input", {bubbles: true}));

// Explicit is already selected by default
// Click Continue when ready (scroll to top first)
// document.querySelector("button").innerText === "Continue" && document.querySelector("button[type=button]").click()
```

**Note:** Refresh page after registering bundle ID to see it in the dropdown when creating the app.

#### Creating App in App Store Connect (automated via Chrome/JS)

Navigate to https://appstoreconnect.apple.com/apps, click "+" > "New App", then fill with JS:

```javascript
// Fill New App form in App Store Connect (run via chrome js <tab_id>)
// Must have React native value setter for text inputs

// Check iOS
document.getElementById("platformsById.IOS").click();

// Set name (React input requires native setter)
const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
const nameInput = document.getElementById("name");
nativeInputValueSetter.call(nameInput, "App Name Here");
nameInput.dispatchEvent(new Event("input", {bubbles: true}));

// Set language
document.getElementById("primaryLocale").value = "en-US";
document.getElementById("primaryLocale").dispatchEvent(new Event("change", {bubbles: true}));

// Set bundle ID (must be registered first!) - use com.sven.AppName format
document.getElementById("bundleId").value = "com.sven.AppName";
document.getElementById("bundleId").dispatchEvent(new Event("change", {bubbles: true}));

// Set SKU
const skuInput = document.getElementById("sku");
nativeInputValueSetter.call(skuInput, "appname-sku");
skuInput.dispatchEvent(new Event("input", {bubbles: true}));

// Select Full Access
document.getElementById("userAccessFull").click();

// Then click Create button
```

**Key insight:** React text inputs need the native value setter trick. Regular `.value = x` doesn't trigger React's state update.

**contentEditable divs:** Some form fields (like Beta App Description) use `contentEditable="true"` divs instead of textareas:
```javascript
// For contentEditable divs:
const editableDiv = document.querySelector('[contenteditable="true"]');
editableDiv.focus();
editableDiv.innerText = 'Your description here';
editableDiv.dispatchEvent(new Event('input', {bubbles: true}));
editableDiv.dispatchEvent(new Event('blur', {bubbles: true}));
```

4. The uploaded build will appear in TestFlight tab after processing (10-30 min)

### Step 6: Handle Encryption Compliance (CRITICAL - BLOCKS TESTING!)

**⚠️ IMPORTANT:** Builds get stuck in "Missing Compliance" status until you explicitly set encryption export compliance. Testers CANNOT download the app until this is resolved.

**BEST PRACTICE: Add to Info.plist to skip compliance questions automatically:**

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

This tells Apple the app doesn't use custom encryption (only standard HTTPS), so compliance is handled automatically on every build. No more manual clicking!

**Manual fallback (if plist key not set):**
After upload, check the build status in TestFlight:
1. If you see "Missing Compliance" - click "Manage" next to the warning
2. For apps that don't use custom encryption (only HTTPS): Select "No" / "None of the algorithms mentioned above"
3. Click Save - this unlocks the build for testing

Most simple apps only use standard HTTPS, which counts as "No" for encryption compliance.

### Step 7: Enable TestFlight Testing

**Internal testing** (up to 100 people on your team - FASTEST, NO REVIEW):
- App Store Connect > TestFlight > Internal Testing > "New Group"
- Add testers from your team (they must be in Users and Access first)
- Testers get an email invite and app appears in their TestFlight app
- No Apple review required - ready immediately

**⚠️ CRITICAL: Each app needs its own internal testing group!**

Even if testers are already in Users and Access from other apps, you must:
1. **Create a new Internal Testing group** for the new app (TestFlight > Internal Testing > New Group)
2. **Add testers to this app-specific group** - they won't automatically have access to new apps

This is a common gotcha: testers in Users and Access can test ANY app they're added to, but they must be explicitly added to each app's testing group.

**Pre-configured internal testers (already in Users and Access):**
- See App Store Connect for current tester list
- Includes account admins and developers

For new apps, create a testing group and add these users to it - they're already set up in Users and Access.

**To add NEW internal testers (not yet in Users and Access):**

⚠️ **Common failure mode:** User added to Internal Testing group but never receives invite → They weren't added to Users and Access first!

⚠️ **API Limitation:** The App Store Connect API does NOT support adding users to Users and Access. You MUST use Chrome automation for step 1.

1. **First add them to Users and Access (Chrome automation required):**
   - Navigate to https://appstoreconnect.apple.com/access/users
   - Click the blue "+" button (find it by searching for SVG elements ~25x25px near top-left)
   - Fill in First Name, Last Name, Email
   - Select role (Developer is good for testers - NOT Admin)
   - Click Next, select apps, click Invite
   - **IMPORTANT:** They must accept the email invitation BEFORE they appear in TestFlight
2. **Then add them to the Internal Testing group (can use API or Chrome):**
   - Via API: `asc groups add-tester "Group Name" email@example.com --app "App Name"`
   - Via Chrome: Go to TestFlight > Internal Testing group > Testers tab > "+" or Add Testers
   - They will now appear in the list of available testers
   - Select them and click Add
3. They receive TestFlight invite via email automatically

**⚠️ CRITICAL: New builds must be added to the Internal Testers group!**

When you upload a new build, it does NOT automatically get added to the Internal Testers group. You must:
1. Go to TestFlight > Version X.X section (scroll down past "Build Uploads")
2. Find your new build in the list
3. Click the "+" button in the GROUPS column to add it to Internal Testers
4. Or click on the build number and add groups from the build detail page

If the GROUPS column is empty for your build, testers won't see the update!

**Debugging "no email received":**
1. Check encryption compliance is set (Step 6) - builds stuck on "Missing Compliance" won't notify testers
2. Check build is added to Internal Testers group (see above)
3. Verify tester is in Users and Access (not just the beta group)
4. Check tester email matches exactly
5. Have them check spam folder

**Note:** Internal testers MUST accept their App Store Connect invitation first. They won't appear in the "Add Testers" dialog until they've accepted. This is different from external testing where you can invite anyone by email directly.

**To add existing internal testers to a new app:**
1. Go to Internal Testing group > Testers tab > Add Testers
2. Select team members (must already be in Users and Access AND have accepted)
3. They receive invite via email automatically

**Note on invite links:** Internal tester invite links are generated by Apple and only delivered via email. The App Store Connect API (`POST /v1/betaTesterInvitations`) can resend emails but cannot retrieve the link. For shareable links, use external testing with public link (requires one-time review).

**External testing** (up to 10,000 people):
- App Store Connect > TestFlight > External Testing > "New Group"
- First external build requires Apple review (~24-48 hours)
- Must fill out: Beta App Description, Contact Info, Sign-in info (or uncheck if no login)
- contentEditable divs for text fields need `.innerText = value` (not .value)

**Public link** (after external review):
- External Testing group > Settings > Enable Public Link
- Share the link with anyone - no email invite needed

### Step 8: Send TestFlight Invite

**CRITICAL: Always send invite link/info as a STANDALONE message for easy copy-paste.**

For internal testers:
```bash
# They get email automatically, but confirm:
~/.claude/skills/sms-assistant/scripts/send-sms "CHAT_ID" "$(cat <<'ENDMSG'
added you as internal tester. check your email for TestFlight invite, or open TestFlight app directly - should appear there.
ENDMSG
)"
```

For public link (external):
```bash
# Send JUST the link on its own line:
~/.claude/skills/sms-assistant/scripts/send-sms "CHAT_ID" "https://testflight.apple.com/join/XXXXXX"
```

Don't embed the link in a paragraph - send it standalone so they can tap/copy easily.

## TestFlight Daily Limits

Apple caps TestFlight uploads at approximately **25 builds per day per app**. The limit resets roughly 24 hours after the first upload in the window.

### Guidelines

- **Check build count before iterative sessions** — if you're planning multiple build-test cycles, know how many uploads you've already used today
- **At 20+ builds in a day, warn and switch to direct device deploy via Xcode** — don't burn the last few slots on iteration; save them for the final candidate
- **If the limit is hit, schedule the upload for after reset — don't retry in a loop** — retrying wastes time and won't succeed until the window resets
- **Prefer simulator + direct device deploy during development iteration** — these have no daily limits and are faster anyway
- **Save TestFlight for release candidates** — once the build is verified on simulator and device, then upload to TestFlight for wider distribution

### Practical Workflow

```
Development iteration:
  Simulator build → test → fix → repeat (unlimited)
  Direct device deploy → test → fix → repeat (unlimited)

Release candidate:
  Final verified build → TestFlight upload (counts toward daily limit)
```

## App Store Connect CLI (`asc`)

**Location:** `~/.claude/skills/ios-app/scripts/asc`

A CLI for App Store Connect REST API operations. Handles JWT auth automatically using the API key stored at `~/.claude/secrets/AuthKey_55288ANG97.p8`.

### Available Commands

```bash
# List all apps
asc apps list

# List bundle IDs
asc bundles list

# Register new bundle ID (required before creating app)
asc bundles create <bundle_id> <name>
asc bundles create com.sven.MyApp "My App"

# List beta testers
asc testers list

# Add tester by email
asc testers add <email> <first_name> <last_name>

# Remove tester
asc testers remove <tester_id>

# List beta groups
asc groups list
asc groups list <app_id>  # For specific app

# Create beta group
asc groups create <app_id> <group_name>

# Add tester to group
asc groups add-tester <group_id> <tester_id>

# List builds
asc builds list
asc builds list <app_id>  # For specific app
```

### What the API Can and CANNOT Do

**✅ CAN do via API:**
- List apps, builds, testers, groups
- Register bundle IDs
- Manage beta testers (add/remove)
- Create/manage beta groups
- Add testers to groups

**❌ CANNOT do via API (Apple limitation):**
- **Create new apps** - API only supports GET/UPDATE for apps resource
- Delete apps
- **Add internal testers who aren't already in Users and Access** - they must be team members first

### Adding Testers via API

**For external testing (non-team members like friends):**
```bash
# 1. Create external group
asc groups create "External Beta" --app "App Name" --external

# 2. Add tester directly to external group (creates tester + adds to group)
asc groups add-tester "External Beta" "friend@email.com" --app "App Name"

# 3. Submit build for beta review (required for external testing)
#    Must be done in App Store Connect UI
```
External testing requires Apple beta review (~24-48 hours for first build).

**For internal testing (team members):**
```bash
# Can only add testers who are ALREADY in Users and Access
asc groups add-tester "Internal Testers" "team@member.com" --app "App Name"
```
If they're not in Users and Access, you'll get: `"Tester(s) cannot be assigned"`

**Quick decision tree:**
- Is tester already in Users and Access? → Use internal testing (no review)
- Is tester external? → Use external testing (requires beta review)

### Adding NEW Internal Testers (Chrome + API Hybrid)

For friends who should be internal testers (no beta review needed), you must add them to Users and Access first via Chrome:

**Step 1: Add to Users and Access via Chrome**
```bash
chrome navigate <tab_id> "https://appstoreconnect.apple.com/access/users"
sleep 3
```

Then use JS injection to:
1. Click the blue "+" button (id="add-user-btn-icon")
2. Fill form: First Name, Last Name, Email
3. Check "Developer" role (good for testers)
4. Click Next → select apps → click Invite

```javascript
// Click add button
document.querySelector("#add-user-btn-icon").dispatchEvent(new MouseEvent("click", { bubbles: true }));

// After modal opens, fill form (sorted by position: First Name, Last Name, Email)
const inputs = Array.from(document.querySelectorAll("input[type=text], input:not([type])"))
  .filter(i => i.offsetParent !== null)
  .sort((a, b) => {
    const aRect = a.getBoundingClientRect();
    const bRect = b.getBoundingClientRect();
    if (Math.abs(aRect.y - bRect.y) > 20) return aRect.y - bRect.y;
    return aRect.x - bRect.x;
  });

const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
nativeInputValueSetter.call(inputs[0], "First");
inputs[0].dispatchEvent(new Event("input", { bubbles: true }));
nativeInputValueSetter.call(inputs[1], "Last");
inputs[1].dispatchEvent(new Event("input", { bubbles: true }));
nativeInputValueSetter.call(inputs[2], "email@example.com");
inputs[2].dispatchEvent(new Event("input", { bubbles: true }));

// Check Developer role
const devCheckbox = Array.from(document.querySelectorAll("input[type=checkbox]")).find(cb => {
  const label = cb.closest("label") || document.querySelector("label[for=\"" + cb.id + "\"]");
  return label && label.textContent.includes("Developer");
});
if (devCheckbox && !devCheckbox.checked) devCheckbox.click();
```

**Step 2: Wait for acceptance**
The user must accept the email invitation before they appear in TestFlight. You'll get `"Tester(s) cannot be assigned"` if they haven't accepted yet.

**Step 3: Add to internal testing group via API**
```bash
asc groups add-tester "Internal Testers" "email@example.com" --app "App Name"
```

**Pre-configured internal testers (already in Users and Access):**
Use `asc groups list-testers "Internal Testers"` to see current testers.

### Creating Apps (Chrome + API Hybrid)

Apple's API doesn't support app creation, so we use a hybrid approach: **2 tool calls total** (API + single JS injection).

**Step 1: Register bundle ID via API**
```bash
asc bundles create com.sven.MyNewApp "My New App"
```

**Step 2: Navigate to App Store Connect**
```bash
chrome navigate <tab_id> "https://appstoreconnect.apple.com/apps"
sleep 3  # Wait for page load
```

**Step 3: Single JS injection does EVERYTHING** (clicks, form fill, submit)

```bash
chrome js <tab_id> '
(async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));

    // Click + button to open dropdown
    document.querySelector("#new-app-btn-icon").click();
    await sleep(500);

    // Click "New App" in dropdown
    document.querySelector("#new-app-btn").click();
    await sleep(1500);

    // Fill form using React-compatible value setter
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;

    // Check iOS platform
    const iosCheckbox = document.getElementById("platformsById.IOS");
    if (iosCheckbox && !iosCheckbox.checked) iosCheckbox.click();

    // App name
    const nameInput = document.getElementById("name");
    nativeInputValueSetter.call(nameInput, "My New App");
    nameInput.dispatchEvent(new Event("input", {bubbles: true}));

    // Language
    const languageSelect = document.getElementById("primaryLocale");
    languageSelect.value = "en-US";
    languageSelect.dispatchEvent(new Event("change", {bubbles: true}));

    // Bundle ID (must be registered first via API!)
    const bundleIdSelect = document.getElementById("bundleId");
    bundleIdSelect.value = "com.sven.MyNewApp";
    bundleIdSelect.dispatchEvent(new Event("change", {bubbles: true}));

    // SKU
    const skuInput = document.getElementById("sku");
    nativeInputValueSetter.call(skuInput, "mynewapp-001");
    skuInput.dispatchEvent(new Event("input", {bubbles: true}));

    // Full Access
    const accessRadio = document.getElementById("userAccessFull");
    if (accessRadio && !accessRadio.checked) accessRadio.click();

    await sleep(500);

    // Click Create button
    const createBtn = Array.from(document.querySelectorAll("button")).find(b => b.innerText.trim() === "Create");
    if (createBtn) createBtn.click();

    return "App creation initiated";
})();
'
```

**Performance:** ~10 seconds total (vs 2+ minutes with separate tool calls)

**Key insights:**
- **Single JS injection** with async/await handles all clicks + form + submit
- React text inputs need `nativeInputValueSetter` trick (regular `.value =` doesn't work)
- Bundle ID dropdown only shows bundle IDs not already assigned to apps
- Internal `await sleep()` handles timing between UI interactions
- Form IDs: `platformsById.IOS`, `name`, `primaryLocale`, `bundleId`, `sku`, `userAccessFull`/`userAccessLimited`

### API Key Setup

The API key is pre-configured:
- **Key ID:** 55288ANG97
- **Issuer ID:** 3495282b-f9a7-4f98-90a5-0e58dd374f9e
- **Private Key:** `~/.claude/secrets/AuthKey_55288ANG97.p8`

To create a new API key:
1. Go to App Store Connect > Users and Access > Integrations > App Store Connect API
2. Generate API Key with "App Manager" role
3. Download the .p8 key file (one-time download)
4. Note the Key ID and Issuer ID
5. Store the .p8 file at `~/.claude/secrets/AuthKey_{KEY_ID}.p8`

## Quick Reference: Full Build-to-TestFlight Script

```bash
#!/bin/bash
set -e

APP_NAME="$1"
BUILD_VERSION="$2"  # e.g., "13"
PROJECT_DIR=~/code/ios-apps/$APP_NAME
BUILD_DIR=$PROJECT_DIR/build

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

echo "==> Archiving $APP_NAME..."
xcodebuild archive \
  -project "$PROJECT_DIR/$APP_NAME.xcodeproj" \
  -scheme "$APP_NAME" \
  -configuration Release \
  -archivePath "$BUILD_DIR/$APP_NAME.xcarchive" \
  -allowProvisioningUpdates

cat > "$BUILD_DIR/ExportOptions.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store-connect</string>
    <key>destination</key>
    <string>upload</string>
    <key>signingStyle</key>
    <string>automatic</string>
    <key>uploadSymbols</key>
    <true/>
</dict>
</plist>
PLIST

echo "==> Exporting and uploading to App Store Connect..."
xcodebuild -exportArchive \
  -archivePath "$BUILD_DIR/$APP_NAME.xcarchive" \
  -exportPath "$BUILD_DIR" \
  -exportOptionsPlist "$BUILD_DIR/ExportOptions.plist" \
  -allowProvisioningUpdates

echo "==> Waiting for build $BUILD_VERSION to be ready..."
~/.claude/skills/ios-app/scripts/asc builds list --wait "$BUILD_VERSION" --timeout 300

echo "==> Build $BUILD_VERSION is VALID and ready in TestFlight!"
```

Usage: `bash deploy.sh HelloWorld 13`

### Post-Upload Workflow (REQUIRED)

**After uploading to TestFlight, ALWAYS:**

1. **Wait for the build to be VALID** using the `--wait` flag:
   ```bash
   ~/.claude/skills/ios-app/scripts/asc builds list --wait <BUILD_VERSION> --timeout 300
   ```

2. **Text the user** when the build is ready:
   ```bash
   ~/.claude/skills/sms-assistant/scripts/send-sms "CHAT_ID" "build <VERSION> is ready in TestFlight! 🚀"
   ```

This ensures the user knows exactly when they can test the new build without having to check manually.

## App Icons (Required for TestFlight)

TestFlight uploads REQUIRE app icons. Icons must:
- Be PNG format with NO alpha/transparency
- Include all required sizes in an asset catalog

### Generate Solid Color Icons (Quick)

```bash
# Generate solid blue icons with Pillow
uv run --with Pillow python3 << 'EOF'
from PIL import Image

sizes = [20, 29, 40, 58, 60, 76, 80, 87, 120, 152, 167, 180, 1024]
output_dir = "HelloWorld/Assets.xcassets/AppIcon.appiconset"

for size in sizes:
    img = Image.new('RGB', (size, size), color=(0, 122, 255))  # Apple blue
    img.save(f"{output_dir}/icon_{size}.png", "PNG")
EOF
```

### Asset Catalog Contents.json

Create `Assets.xcassets/AppIcon.appiconset/Contents.json`:

```json
{
  "images": [
    {"filename": "icon_40.png", "idiom": "iphone", "scale": "2x", "size": "20x20"},
    {"filename": "icon_60.png", "idiom": "iphone", "scale": "3x", "size": "20x20"},
    {"filename": "icon_58.png", "idiom": "iphone", "scale": "2x", "size": "29x29"},
    {"filename": "icon_87.png", "idiom": "iphone", "scale": "3x", "size": "29x29"},
    {"filename": "icon_80.png", "idiom": "iphone", "scale": "2x", "size": "40x40"},
    {"filename": "icon_120.png", "idiom": "iphone", "scale": "3x", "size": "40x40"},
    {"filename": "icon_120.png", "idiom": "iphone", "scale": "2x", "size": "60x60"},
    {"filename": "icon_180.png", "idiom": "iphone", "scale": "3x", "size": "60x60"},
    {"filename": "icon_20.png", "idiom": "ipad", "scale": "1x", "size": "20x20"},
    {"filename": "icon_40.png", "idiom": "ipad", "scale": "2x", "size": "20x20"},
    {"filename": "icon_29.png", "idiom": "ipad", "scale": "1x", "size": "29x29"},
    {"filename": "icon_58.png", "idiom": "ipad", "scale": "2x", "size": "29x29"},
    {"filename": "icon_40.png", "idiom": "ipad", "scale": "1x", "size": "40x40"},
    {"filename": "icon_80.png", "idiom": "ipad", "scale": "2x", "size": "40x40"},
    {"filename": "icon_76.png", "idiom": "ipad", "scale": "1x", "size": "76x76"},
    {"filename": "icon_152.png", "idiom": "ipad", "scale": "2x", "size": "76x76"},
    {"filename": "icon_167.png", "idiom": "ipad", "scale": "2x", "size": "83.5x83.5"},
    {"filename": "icon_1024.png", "idiom": "ios-marketing", "scale": "1x", "size": "1024x1024"}
  ],
  "info": {"author": "xcode", "version": 1}
}
```

### Adding Assets to project.pbxproj

The project file needs:
1. File reference for Assets.xcassets
2. Build file entry for Assets.xcassets in Resources
3. PBXResourcesBuildPhase in the target's build phases
4. Assets.xcassets in the HelloWorld group's children

See the Sven project at `~/dispatch/apps/sven-ios/` for a working example.

### Generate Custom Icons with Gemini (nano-banana skill)

For nicer icons, use the nano-banana skill to generate an app icon image, then resize it to all required sizes.

## Common Issues

| Problem | Solution |
|---------|----------|
| "Not agreed to license" | Run `sudo xcodebuild -license accept` |
| "required plugin failed to load" / CoreSimulator missing | Run `sudo xcodebuild -runFirstLaunch` |
| No simulator runtimes / `simctl list runtimes` empty | Run `xcodebuild -downloadPlatform iOS` |
| Simulator stuck on Apple logo | First boot takes 5-10+ min. Be patient. Check with `xcrun simctl io booted screenshot` |
| "No profiles found" | Add `-allowProvisioningUpdates` flag |
| "Signing requires a development team" | Sign into Xcode with Apple ID (Settings > Accounts), set DEVELOPMENT_TEAM in project |
| "0 valid identities found" | Must sign into Xcode with Apple Developer account first |
| Build not appearing in TestFlight | Wait 10-30 min for processing; check email for errors |
| "Code signing identity not found" | Sign into Xcode with Apple ID first, or install distribution cert |
| Archive fails for simulator-only build | Use `-sdk iphoneos` (not `iphonesimulator`) for archives |
| Duplicate version error | Bump `CURRENT_PROJECT_VERSION` or `MARKETING_VERSION` in build settings |
| `simctl install` hangs | Simulator might still be booting. Wait for home screen first. Check with screenshot. |
| Xcode component installer dialog on first open | Click "Download & Install" or use axctl to click it |

## Bundle ID Convention

All apps use: `com.sven.AppName` (using assistant name from identity CLI)

```bash
# Get the correct prefix dynamically:
~/dispatch/bin/identity assistant.name  # Returns "Sven"
# Bundle ID format: com.sven.AppName (lowercase)
```

**Note:** Legacy apps may still use `com.dispatch.*` or `com.jsmith.*`. New apps should use `com.sven.*`

## Complete Build-Run-Debug Workflow

Here's the full workflow to build, install, run, and debug an app:

```bash
# 1. Build for simulator
xcodebuild \
  -project ~/code/ios-apps/AppName/AppName.xcodeproj \
  -scheme AppName \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -configuration Debug \
  CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO \
  build

# 2. Find the built .app
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData -name "AppName.app" -path "*/Debug-iphonesimulator/*" 2>/dev/null | head -1)

# 3. Install on booted simulator
xcrun simctl install booted "$APP_PATH"

# 4. Launch with console output (to see print() logs)
xcrun simctl launch --console-pty booted com.dispatch.AppName

# 5. Screenshot the simulator
xcrun simctl io booted screenshot ~/Desktop/app-screenshot.png

# 6. Send screenshot to user via iMessage (MUST use --image flag!)
~/.claude/skills/sms-assistant/scripts/send-sms "CHAT_ID" --image ~/Desktop/app-screenshot.png
```

## Sending Screenshots to Users

**CRITICAL: ALWAYS use the `--image` flag to send screenshots. NEVER use raw AppleScript.**

```bash
# ✅ CORRECT - use send-sms CLI with --image flag
~/.claude/skills/sms-assistant/scripts/send-sms "CHAT_ID" --image /tmp/screenshot.png

# ✅ With caption
~/.claude/skills/sms-assistant/scripts/send-sms "CHAT_ID" "Here's the app running" --image /tmp/screenshot.png

# ❌ WRONG - raw AppleScript fails silently for images
# osascript -e 'tell application "Messages"...'
```

The send-sms CLI handles the macOS quirks (copying to ~/Pictures, proper file references) automatically.

**One-liner for rebuild + run:**
```bash
xcodebuild -project ~/code/ios-apps/AppName/AppName.xcodeproj -scheme AppName -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 17 Pro' CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO build 2>&1 | tail -5 && xcrun simctl install booted $(find ~/Library/Developer/Xcode/DerivedData -name "AppName.app" -path "*/Debug-iphonesimulator/*" 2>/dev/null | head -1) && xcrun simctl launch --console-pty booted com.dispatch.AppName
```

## XCUITest - Automated UI Testing (REQUIRED FOR ALL CUJs)

**XCUITest is Apple's official UI testing framework.** Use it to automate all user journeys, capture screenshots as proof, and send results to the user.

### Why XCUITest?

- `simctl` has NO tap command - you cannot interact with UI elements via simulator commands
- XCUITest is the ONLY supported way to automate UI interactions on iOS
- Even cross-platform tools like Appium use XCUITest under the hood
- Tests run in a separate process via accessibility APIs (no app code duplication)

### Project Structure with UI Tests

```
~/code/ios-apps/AppName/
├── AppName.xcodeproj/
│   ├── project.pbxproj          # Must include UITests target
│   └── xcshareddata/xcschemes/
│       └── AppName.xcscheme     # Must configure TestAction
├── AppName/
│   ├── AppNameApp.swift
│   └── ContentView.swift
└── AppNameUITests/
    └── AppNameUITests.swift     # XCUITest test cases
```

### Creating a UI Test Target

1. Add test file at `AppNameUITests/AppNameUITests.swift`:

```swift
import XCTest

final class AppNameUITests: XCTestCase {

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testExampleUserJourney() throws {
        let app = XCUIApplication()
        app.launch()

        // Find and interact with elements
        let button = app.buttons["Button Label"]
        XCTAssertTrue(button.exists, "Button should exist")
        button.tap()

        // Verify expected state
        let label = app.staticTexts["Expected Text"]
        XCTAssertTrue(label.exists, "Label should show expected text")

        // CRITICAL: Take screenshot and save to /tmp for sending to user
        let screenshot = app.screenshot()
        let data = screenshot.pngRepresentation
        try? data.write(to: URL(fileURLWithPath: "/tmp/test-screenshot.png"))
        print("Screenshot saved to /tmp/test-screenshot.png")
    }
}
```

2. Add UITests target to `project.pbxproj` (see HelloWorld example for reference)

3. Create `xcshareddata/xcschemes/AppName.xcscheme` with TestAction configured:
   - BlueprintIdentifier must match the UITests target ID from project.pbxproj

### Running UI Tests

```bash
# Run all UI tests
xcodebuild test \
  -project ~/code/ios-apps/AppName/AppName.xcodeproj \
  -scheme AppName \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro'

# Run specific test
xcodebuild test \
  -project ~/code/ios-apps/AppName/AppName.xcodeproj \
  -scheme AppName \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -only-testing:AppNameUITests/AppNameUITests/testExampleUserJourney
```

### XCUITest Common Patterns

```swift
// Finding elements
app.buttons["Tap Me!"]           // By accessibility label
app.staticTexts["Hello"]         // Text labels
app.textFields["Email"]          // Text input fields
app.switches["Dark Mode"]        // Toggle switches
app.navigationBars["Settings"]   // Navigation bars

// Interactions
element.tap()                    // Tap
element.doubleTap()              // Double tap
element.swipeUp()                // Swipe gestures
textField.typeText("hello")      // Type text

// Assertions
XCTAssertTrue(element.exists)
XCTAssertEqual(element.label, "Expected")

// Waiting for elements
let exists = element.waitForExistence(timeout: 5)
XCTAssertTrue(exists, "Element should appear within 5 seconds")

// Screenshots during test
let screenshot = app.screenshot()
let data = screenshot.pngRepresentation
try? data.write(to: URL(fileURLWithPath: "/tmp/cuj-step-1.png"))
```

### REQUIRED: CUJ Testing Workflow with Screenshots

**For EVERY user journey, you MUST:**

1. Write an XCUITest that performs the user journey
2. Take screenshots at key steps (save to `/tmp/`)
3. Run the test
4. Send screenshots to user via SMS with description of what was tested

**Example: Testing a Todo App**

```swift
func testAddTodo() throws {
    let app = XCUIApplication()
    app.launch()

    // Step 1: Initial state
    let screenshot1 = app.screenshot()
    try? screenshot1.pngRepresentation.write(to: URL(fileURLWithPath: "/tmp/todo-1-initial.png"))

    // Step 2: Add a todo
    app.textFields["New todo"].tap()
    app.textFields["New todo"].typeText("Buy groceries")
    app.buttons["Add"].tap()

    // Step 3: Verify and screenshot
    XCTAssertTrue(app.staticTexts["Buy groceries"].exists)
    let screenshot2 = app.screenshot()
    try? screenshot2.pngRepresentation.write(to: URL(fileURLWithPath: "/tmp/todo-2-added.png"))
}
```

**After running the test, send screenshots to user:**

```bash
# Run the test
xcodebuild test -project ~/code/ios-apps/TodoApp/TodoApp.xcodeproj -scheme TodoApp -destination 'platform=iOS Simulator,name=iPhone 17 Pro' 2>&1 | tail -20

# Send screenshots with descriptions
~/.claude/skills/sms-assistant/scripts/send-sms "CHAT_ID" "CUJ: Add Todo - Step 1: Initial empty state" --image /tmp/todo-1-initial.png
~/.claude/skills/sms-assistant/scripts/send-sms "CHAT_ID" "CUJ: Add Todo - Step 2: After adding 'Buy groceries'" --image /tmp/todo-2-added.png
```

### Best Practices

1. **Use accessibility identifiers** - More stable than text labels which can change
2. **Keep tests focused** - One CUJ per test method
3. **Screenshot at every significant state change**
4. **Save screenshots to /tmp/** - Easy to access and send
5. **Always send screenshots to user** - They need to approve before TestFlight
6. **Add small delays if needed** - `Thread.sleep(forTimeInterval: 0.2)` for UI updates

## Audio Recording Optimization (Fast Startup)

For apps that need instant audio recording (like Shazam-style apps), use these optimizations:

### The Problem

Default audio setup in `startRecording()` can take 300-500ms:
- `AVAudioSession.setCategory()` + `setActive()`: 100-300ms
- `AVAudioEngine` creation + start: 100-200ms
- `SFSpeechRecognizer` initialization: 50-100ms

### The Solution: Pre-warm Everything

**1. Add UIKit AppDelegate for earliest lifecycle hooks:**

```swift
import SwiftUI
import AVFoundation

class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey : Any]? = nil) -> Bool {
        // Pre-warm audio session BEFORE any views load
        Task.detached(priority: .userInitiated) {
            await AudioPrewarmer.shared.prewarm()
        }
        return true
    }
}

@main
struct MyApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    // ...
}
```

**2. Create AudioPrewarmer singleton:**

```swift
@MainActor
class AudioPrewarmer {
    static let shared = AudioPrewarmer()
    private(set) var audioEngine: AVAudioEngine?
    private(set) var isPrewarmed = false

    func prewarm() async {
        guard !isPrewarmed else { return }
        do {
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker])
            try audioSession.setActive(true)
            audioEngine = AVAudioEngine()
            audioEngine?.prepare()
            isPrewarmed = true
        } catch { print("Prewarm failed: \(error)") }
    }

    func getEngine() -> AVAudioEngine {
        audioEngine ?? AVAudioEngine()
    }
}
```

**3. Defer speech recognition (start recording immediately):**

```swift
func startRecording() {
    // Use pre-warmed engine
    audioEngine = AudioPrewarmer.shared.getEngine()

    // Install tap and start engine IMMEDIATELY
    inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
        // Buffer audio for speech recognition (set up async)
        if self.isSpeechReady {
            self.recognitionRequest?.append(buffer)
        } else {
            self.pendingBuffers.append(buffer)
        }
    }
    try audioEngine.start()  // NOW RECORDING!

    // Set up speech recognition AFTER recording starts
    Task { await setupSpeechRecognition() }
}
```

**Key insight:** Recording can start before transcription is ready. Buffer the audio and feed it to the recognizer once it's initialized.

### Results

- **Before:** 300-500ms from tap to recording
- **After:** <50ms from tap to recording (speech catches up ~100ms later)

## Push Notifications (APNs)

**Complete guide for setting up push notifications, based on real debugging experience.**

### Overview

Push notifications require:
1. **APNs Key** (from Apple Developer Portal) - authenticates your server
2. **Entitlements file** (in Xcode project) - tells iOS your app can receive pushes
3. **AppDelegate** (in Swift code) - registers for push and receives token
4. **Backend** - stores tokens and sends pushes via APNs HTTP/2 API

### Step 1: Create APNs Key (One-Time Setup)

1. Go to https://developer.apple.com/account/resources/authkeys/add
2. Enter key name (e.g., "Sven APNs Key")
3. Check "Apple Push Notifications service (APNs)"
4. Click Continue → Register → Download
5. Save the `.p8` file securely (e.g., `~/.claude/secrets/AuthKey_KEYID.p8`)
6. Note your **Key ID** (10 characters) and **Team ID** (from Membership page)

**CRITICAL:** You can only download the key ONCE. Store it safely!

### Step 2: Enable Push Notifications Capability in App

**This is the most commonly missed step!** Without the entitlements file, iOS will NOT call `didRegisterForRemoteNotificationsWithDeviceToken`.

#### Create Entitlements File

Create `AppName/AppName.entitlements`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>aps-environment</key>
    <string>development</string>
</dict>
</plist>
```

**Note:** The value `development` is for debug builds. Xcode automatically changes this to `production` when archiving for TestFlight/App Store.

#### Add to project.pbxproj

Add these entries to your project file:

```
/* In PBXFileReference section */
A7000001 /* AppName.entitlements */ = {isa = PBXFileReference; lastKnownFileType = text.plist.entitlements; path = AppName.entitlements; sourceTree = "<group>"; };

/* In PBXGroup children (HelloWorld group) */
A7000001 /* AppName.entitlements */,

/* In XCBuildConfiguration (BOTH Debug and Release) */
CODE_SIGN_ENTITLEMENTS = AppName/AppName.entitlements;
```

### Step 3: Add AppDelegate for Push Registration

SwiftUI apps need an AppDelegate to handle push notification callbacks.

**AppDelegate.swift:**

```swift
import UIKit
import UserNotifications

class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey : Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        requestNotificationPermission(application: application)
        return true
    }

    private func requestNotificationPermission(application: UIApplication) {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            print("Notification permission granted: \(granted)")
            if granted {
                DispatchQueue.main.async {
                    application.registerForRemoteNotifications()
                }
            }
        }
    }

    // MARK: - Remote Notification Registration

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        // Convert token to hex string
        let tokenString = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        print("APNs token: \(tokenString)")

        // Send to your backend
        Task {
            await YourAPIClient.shared.registerAPNsToken(tokenString)
        }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("Failed to register for remote notifications: \(error)")
    }

    // MARK: - Notification Handling (foreground)

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        // Show notification even when app is in foreground
        completionHandler([.banner, .sound, .badge])
    }
}
```

**Wire up in SwiftUI App:**

```swift
@main
struct MyApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
```

### Step 4: Backend Token Registration

Your backend needs an endpoint to store APNs tokens:

```python
# Example: FastAPI endpoint
@app.post("/register-apns")
async def register_apns(request: APNsRegisterRequest):
    # Map device_token (your app's ID) to apns_token (Apple's push token)
    apns_tokens[request.device_token] = request.apns_token
    save_tokens()
    return {"status": "ok"}
```

### Step 5: Sending Push Notifications

Use HTTP/2 to send to APNs. Example Python script:

```python
#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["httpx[http2]", "PyJWT", "cryptography"]
# ///

import jwt
import time
import httpx

def create_apns_jwt(team_id: str, key_id: str, key_path: str) -> str:
    key = open(key_path).read()
    return jwt.encode(
        {"iss": team_id, "iat": int(time.time())},
        key,
        algorithm="ES256",
        headers={"alg": "ES256", "kid": key_id}
    )

def send_push(apns_token: str, title: str, body: str, config: dict):
    # TestFlight/App Store = production, Debug = sandbox
    host = "https://api.push.apple.com"  # or api.sandbox.push.apple.com

    headers = {
        "authorization": f"bearer {create_apns_jwt(config['team_id'], config['key_id'], config['key_path'])}",
        "apns-topic": config["bundle_id"],
        "apns-push-type": "alert",
        "apns-priority": "10"
    }

    payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
            "badge": 1
        }
    }

    with httpx.Client(http2=True) as client:
        response = client.post(
            f"{host}/3/device/{apns_token}",
            headers=headers,
            json=payload
        )
        return response.status_code == 200
```

**CRITICAL: HTTP/2 is required!** APNs only accepts HTTP/2 connections. Use `httpx[http2]` in Python.

### APNs Environments: Sandbox vs Production

| Build Type | APNs Environment | Host |
|------------|------------------|------|
| Debug (Xcode) | Sandbox | api.sandbox.push.apple.com |
| TestFlight | **Production** | api.push.apple.com |
| App Store | **Production** | api.push.apple.com |

**Common mistake:** Using sandbox APNs for TestFlight builds. TestFlight builds are signed with production entitlements, so they need production APNs!

**Device tokens are environment-specific!** A token from a debug build won't work with production APNs, and vice versa. When switching environments, the app must re-register and get a new token.

### Troubleshooting Push Notifications

| Problem | Cause | Solution |
|---------|-------|----------|
| `didRegisterForRemoteNotifications` never called | Missing entitlements file | Add `AppName.entitlements` with `aps-environment` |
| Token registered but push fails | Wrong APNs environment | TestFlight = production, Debug = sandbox |
| "BadDeviceToken" error | Token/environment mismatch | Get fresh token after switching debug↔release |
| Push works in debug, fails in TestFlight | Using sandbox URL | Switch to `api.push.apple.com` for TestFlight |
| Backend /register-apns returns 404 | Server running old code | Restart the backend server |

### Advanced: Rich Notifications

You can enhance notifications with:

**1. Images/Media (Notification Service Extension)**
- Add a "Notification Service Extension" target in Xcode
- Download images when notification arrives
- Supports images, GIFs, video, audio (max 10MB)

**2. Action Buttons**
- Define `UNNotificationCategory` with `UNNotificationAction`s
- Users can tap buttons without opening app

**3. Custom UI (Notification Content Extension)**
- Fully custom notification interface
- Interactive controls, maps, timelines

**4. Live Activities (iOS 16+)**
- Dynamic Island updates
- Lock screen live updates

### Example Config File

Store push config at `~/dispatch/state/push-config.json`:

```json
{
  "team_id": "B5JUGARUU6",
  "key_id": "X3H9DPHLAM",
  "bundle_id": "com.sven.Sven",
  "key_path": "~/.claude/secrets/AuthKey_X3H9DPHLAM.p8",
  "use_sandbox": false
}
```

Set `use_sandbox: true` only for debug builds run directly from Xcode.
