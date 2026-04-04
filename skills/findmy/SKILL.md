---
name: findmy
description: Query real-time locations of people sharing via Find My. Look up where someone is, reverse geocode GPS coordinates, set up geofence alerts. Trigger words - findmy, find my, location, where is, geofence, track location.
---

# Find My Skill

Query live locations of people who have shared their location with this Mac via Apple Find My.

## ⚠️ SECURITY — ADMIN ONLY

**This skill is RESTRICTED to admin tier only.**

- **Admin**: Full access — can query any shared location
- **Everyone else (partner, family, favorites, unknown)**: **HARD REJECT** — never reveal any location data
  - Response: "Sorry, location data is restricted. Ask Sven to grant you access."
- **Explicit blessing**: Admin can grant per-contact access via contact notes. Format: `findmy_access: allowed`. Only then may that contact query their own location or others.

## Scripts

### `findmy-location` — Get current location (city-level, works now)
```bash
~/.claude/skills/findmy/scripts/findmy-location "!`identity owner.name`"
# → !`identity owner.name`: San Francisco, CA • Now
# → !`identity owner.name`: Boston, MA • 3 min ago
```
Uses Find My app accessibility API. Always works. City-level precision.

### `findmy-gps` — Get real-time GPS (street-level precision) ✅ LIVE
```bash
~/.claude/skills/findmy/scripts/findmy-gps
# → 📍 !`identity owner.name`
# →    123 Example Street, Neighborhood, City, State
# →    (42.348541, -71.156790), ±12m
# →    stationary • 2026-04-04 01:03:42

~/.claude/skills/findmy/scripts/findmy-gps "!`identity owner.name`"
~/.claude/skills/findmy/scripts/findmy-gps --raw   # JSON output
```
Decrypts `LocalStorage.db` on demand with extracted key. Sub-20m precision.
Key stored at: `~/code/findmy-key-extractor/keys/LocalStorage.key`

### `findmy-geocode` — Reverse geocode GPS → street address
```bash
~/.claude/skills/findmy/scripts/findmy-geocode 37.611 -122.385
# → Short: South McDonnell Road, San Francisco, San Mateo County
# → Full:  B18, 780 South McDonnell Road, SF, CA 94128
```
Uses OpenStreetMap Nominatim. Free, no API key. Street-level precision.

## GPS Precision (requires one-time setup)

Real-time GPS coordinates live in `LocalStorage.db` (encrypted with Apple's custom AES-256). To unlock:

### One-time key extraction (requires physical Mac access)

```bash
# Step 1: Boot into Recovery Mode
# Apple Silicon: hold power → Options
# Intel: hold Cmd+R on restart

# In Recovery terminal:
csrutil disable
# Reboot, then:
sudo nvram boot-args="amfi_get_out_of_my_way=1"
# Reboot again

# Step 2: Extract keys (~10s)
cd ~/code/findmy-key-extractor
./extract.sh
# → saves keys/LocalStorage.key (32 bytes, stable across reboots)

# Step 3: Re-enable security (back in Recovery)
csrutil enable       # in Recovery terminal
# Reboot, then:
sudo nvram -d boot-args
# Reboot — Mac back to normal, key still works
```

Tools cloned at: `~/code/findmy-key-extractor` (manonstreet/findmy-key-extractor)

### After key extraction: decrypt and read GPS

```bash
cd ~/code/findmy-key-extractor
# Decrypt to plain SQLite:
python3 decrypt_localstorage.py keys/LocalStorage.key
# → LocalStorage_decrypted.sqlite

# Query friend GPS coordinates:
sqlite3 LocalStorage_decrypted.sqlite \
  "SELECT name, latitude, longitude, altitude, timestamp FROM friends;"
```

Or install `FindMySyncPlus` (manonstreet/FindMySyncPlus) for real-time WAL-watching + MQTT publish.

**Status**: ✅ Key extracted. GPS live. Re-enable SIP in Recovery when convenient (optional).

## How Location Data Works

| Source | Precision | Status |
|--------|-----------|--------|
| Find My AX API (`findmy-location`) | City ("San Francisco, CA • Now") | ✅ Working |
| Initial share payload (iMessage) | GPS one-time (37.611, -122.385) | ✅ Decoded on share |
| `LocalStorage.db` decrypted (`findmy-gps`) | Real-time GPS + speed + motion + address | ✅ Live |

**Key insight**: Location updates go directly iCloud → `findmylocateagent` → `LocalStorage.db`. They do NOT arrive as new iMessages. The WAL file updates continuously while location is shared.

The local DB is encrypted with Apple's custom `sqliteCodecCCCrypto` (AES-256 keystream XOR, not SQLCipher). Key is in Keychain behind `CS_PLATFORM_BINARY` ACL — only extractable via lldb attach with SIP/AMFI disabled.

## Geofencing

### City-level (works now)
```bash
# Poll every 10 min, alert on city change
~/.claude/skills/findmy/scripts/findmy-location "!`identity owner.name`"
# Compare "San Francisco" → "Boston" = fire alert
```

Config at `~/.claude/skills/findmy/geofences.json`:
```json
{
  "!`identity owner.name`": [
    {"name": "Boston arrival", "city": "Boston", "on": "enter", "action": "sms"},
    {"name": "SFO departure", "city": "San Francisco", "on": "exit", "action": "sms"}
  ]
}
```

### GPS-level (after key extraction)
- Haversine distance check vs fence center + radius
- Motion state, speed, altitude also available from DB
- Sub-100m precision
