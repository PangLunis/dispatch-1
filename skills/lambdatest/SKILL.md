---
name: lambdatest
description: Test web apps on real iPhones/iPads via LambdaTest cloud devices. Use when testing iOS Safari, WebGPU on mobile, or verifying web app behavior on real devices. Trigger words - lambdatest, lambda test, real iphone, test on iphone, real device, mobile testing.
---

# LambdaTest — Real Device Testing

Test web apps on real iPhones and iPads in the cloud. Essential for WebGPU, Safari-specific bugs, and iOS compatibility testing.

## Account

- **Login**: Already logged in via Chrome (uses assistant's Google account)
- **Platform**: https://app.lambdatest.com
- **Plan**: Free tier (limited minutes, real device access)

## How to Start a Real Device Session

Use chrome-control to navigate the LambdaTest UI:

### 1. Open Mobile Browser Testing

```bash
chrome open "https://app.lambdatest.com/console/realtime/browser/mobile"
```

### 2. Select Device

The mobile browser testing page shows iOS and Android devices. For iOS Safari testing:
- Select **iPhone 17 Pro Max** (or latest available)
- Select **iOS 26** (or latest)
- Select **Safari** browser
- Paste the target URL in the URL bar at the top
- Click **Start**

### 3. Navigate and Interact

Once the session starts, you'll see a remote device screen. Use chrome-control to:
- `chrome screenshot <tab_id>` — capture the remote device display
- `chrome click <tab_id> <ref>` — interact with LambdaTest UI controls
- `chrome text <tab_id>` — read text from the remote session

### 4. End Session

Sessions auto-expire after inactivity. Close the tab or click the end session button.

## Key Workflows

### Test a GitHub Pages Deploy

1. Open a real device session (steps above)
2. Navigate to the deployed URL (e.g., `svenflow.github.io/webgpu-kitten-tts/`)
3. Screenshot to verify it loads
4. Interact with the page (click generate, etc.)
5. Screenshot results

### Debug iOS Safari Issues

LambdaTest provides DevTools access for real devices:
- Look for the **DevTools** icon in the session toolbar
- Console logs, network tab, and elements panel are available
- Useful for catching WebGPU errors, WASM hangs, and Safari-specific bugs

### Compare Audio/Output Between Desktop and Mobile

1. Run the same test on desktop Chrome (locally)
2. Run on LambdaTest iPhone Safari
3. Compare outputs — differences indicate Safari-specific issues (e.g., WASM phonemizer hanging, command encoder errors)

## Interacting with the Remote Device

The remote device is rendered as a video stream, NOT as real DOM elements. This limits how you can interact with it.

- **Set the URL before starting the session** (preferred) — paste it into the LambdaTest URL bar before clicking Start. This avoids having to navigate within the remote Safari.
- **Dispatch synthetic mouse events to the video element** — use `chrome js <tab_id> "..."` to dispatch `mousedown`/`mouseup`/`click` events directly on the video `<canvas>` or `<video>` element at the correct coordinates. This simulates taps on the remote device.
- **Use LambdaTest toolbar controls** — the toolbar buttons (home, rotate, volume, screenshot) are real DOM elements in the wrapper UI and work with `chrome click`.
- **Standard `chrome click` on the device screen does NOT work** — the remote display is a flat media element with no interactive DOM underneath. `chrome click` targeting refs inside the device viewport will miss.

## Gotchas

- **Session startup takes 30-60s** — the device needs to boot and load Safari
- **Free tier has limited minutes** — don't leave sessions idle
- **URL bar is at the TOP of the LambdaTest UI** — paste your URL there before starting, or use the address bar in the remote Safari
- **Navigation can be tricky** — the remote device is rendered as a video stream. Use chrome-control to interact with the LambdaTest wrapper UI (buttons, URL bar), not the remote device content directly
- **WebGPU support** — iPhone 17 Pro Max with iOS 26 supports WebGPU in Safari. Older devices may not
- **Previous sessions visible on home page** — https://app.lambdatest.com shows recent sessions under "Recents" with device info and duration

## When to Use

- Before deploying WebGPU changes that might break Safari (command batching, encoder changes)
- When user reports iOS-specific issues ("sounds different on my iPhone", "invalid command error")
- To verify WASM/WebAssembly compatibility on Safari
- To capture real device performance numbers (generation time, model load time)
