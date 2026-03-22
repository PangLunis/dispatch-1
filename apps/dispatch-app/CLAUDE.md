# Dispatch App

Expo/React Native app (iOS + web) for the dispatch-api backend.

## Development

### Linting

**ALWAYS run `npm run lint` before committing or creating PRs.** Fix all errors before pushing.

```bash
npm run lint          # Run oxlint on src/ and app/
npx oxlint src/ app/  # Direct invocation
```

### Building

```bash
# Web (served by dispatch-api at /app/)
npx expo export --platform web

# iOS (dev build to device)
APP_VARIANT=sven npx expo run:ios --device "DEVICE_UDID"

# iOS (clean rebuild — needed after native config changes)
APP_VARIANT=sven npx expo prebuild --clean --platform ios
APP_VARIANT=sven npx expo run:ios --device "DEVICE_UDID"
```

### App Variants

- `dispatch` (default) — bundle ID `com.dispatch.app`, display name "Dispatch"
- `sven` — bundle ID `com.nikhil.sven`, display name "Sven"

Set via `APP_VARIANT=sven` env var. Config in `app.config.ts` + `config.default.json`.

### Key Architecture

- **Polling-based** — no WebSocket. Chat list polls every 3s, messages every 1.5s
- **Device token auth** — UUID generated on first launch, registered via POST /register
- **Platform storage** — iOS uses Keychain (expo-secure-store), web uses localStorage
- **API URL configurable** at runtime via Settings tab (persisted in storage)
- **ATS disabled** — `NSAllowsArbitraryLoads: true` in app.config.ts for Tailscale HTTP

### Important Notes

- After `expo prebuild --clean`, ATS settings are applied from `app.config.ts` automatically
- The `sven-icon.png` must exist in `assets/images/` for the sven variant to build
- Push notifications require Apple Developer Portal setup (aps-environment entitlement)
