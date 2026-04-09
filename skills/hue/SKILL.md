---
name: hue
description: Control Philips Hue lights (on/off, brightness, colors, scenes). Multi-bridge support with auto-discovery and pairing. Use together with lutron skill for smart home lighting.
allowed_tiers: admin, family
---

# Philips Hue Skill

Control Philips Hue lights across multiple bridges. Supports discovery, pairing, scenes, color temperature, rooms, and alerts.

## Quick Reference

```bash
# All commands use: uv run ~/.claude/skills/hue/scripts/control.py <command>
HUE="uv run ~/.claude/skills/hue/scripts/control.py"
```

### Individual Lights

```bash
$HUE list                          # List all lights (alias: ls)
$HUE list alpha                    # List lights on Alpha bridge only
$HUE on "Kitchen Ceiling 1"       # Turn on
$HUE off "Kitchen Ceiling 1"      # Turn off
$HUE toggle "Kitchen Ceiling 1"   # Toggle on/off
$HUE brightness "Kitchen" 200     # Set brightness 0-254 (alias: bri)
$HUE color "Kristens Room 1" 10000 254   # Set color (hue 0-65535, sat 0-254)
$HUE temp "Kitchen Ceiling 1" 300        # Color temperature 153-500 (alias: ct)
$HUE alert "Kitchen Ceiling 1"          # Flash once
$HUE alert "Kitchen Ceiling 1" long     # Flash for 15 seconds
```

### Rooms / Groups

```bash
$HUE room list                    # List all rooms with on/off state
$HUE room on "Basement"           # Turn on all lights in room
$HUE room off "Master Bedroom"    # Turn off all lights in room
$HUE room blink "Front Hallway" 1 # Blink room (off, 1s delay, on)
```

### Scenes

```bash
$HUE scenes                       # List all scenes across all bridges
$HUE scenes alpha                 # List scenes on Alpha only
$HUE scene "Energize"             # Activate a scene by name
```

### Bridge Management

```bash
$HUE discover                     # Find all bridges on network (via meethue N-UPnP)
$HUE bridges                      # Show configured bridges + connectivity status
$HUE pair <bridge-ip>             # Pair with a new bridge (press button first!)
$HUE status                       # Full health check — bridges + discovery
```

### Global Options (position-independent)

```bash
$HUE on "light" --transition 2.0     # Transition over 2 seconds
$HUE off "light" --bridge alpha      # Target specific bridge
$HUE list --json                     # JSON output (for scripting/jq pipelines)
$HUE --json room list                # Flags work before or after command
$HUE bridges --json                  # JSON bridge status
$HUE on "light" --quiet              # Suppress OK messages (for scripting)
```

## Bridges

Use `$HUE bridges` or `$HUE discover` to see current bridge IPs and pairing status. Credentials stored in `~/.hue/` as JSON files.

**To pair a new bridge:** Press the physical button on the bridge, then within 30 seconds run:
```bash
$HUE pair <bridge-ip>
```

## Configuration

Credentials stored in `~/.hue/` as JSON files. The config loader dynamically reads ALL `*.json` files in this directory (no hardcoded filenames).

Each JSON file contains:
```json
{
  "bridge_ip": "<bridge-ip>",
  "bridge_name": "<name>",
  "bridge_id": "<serial>",
  "username": "<api-key>"
}
```

## Entertainment / Light Show (Basement Ceiling Grid)

For beat-synced or animation-driven light shows on the basement ceiling, use the entertainment server:

**Server:** `~/code/hue-latency-tester/entertainment-v2.js`
**Port:** 8788 (HTTP + web UI at `http://localhost:8788`)

Start the server:
```bash
cd ~/code/hue-latency-tester && node entertainment-v2.js
```

### HTTP API

```bash
# Check status (streaming: true/false)
curl http://localhost:8788/api/status

# Reconnect DTLS stream
curl -X POST http://localhost:8788/api/reconnect

# Set all 20 grid lights to a color (r/g/b: 0-255)
curl -X POST http://localhost:8788/api/cmd -H 'Content-Type: application/json' \
  -d '{"action":"setAll","r":255,"g":0,"b":0}'

# Set a single grid cell (row 0-3, col 0-4)
curl -X POST http://localhost:8788/api/cmd -H 'Content-Type: application/json' \
  -d '{"action":"setCell","row":1,"col":2,"r":0,"g":255,"b":0}'

# Run a named animation
curl -X POST http://localhost:8788/api/cmd -H 'Content-Type: application/json' \
  -d '{"action":"anim","name":"rainbow"}'

# Stop animation
curl -X POST http://localhost:8788/api/cmd -H 'Content-Type: application/json' \
  -d '{"action":"anim","name":"stop"}'
```

### Grid Layout (4 rows x 5 cols = 20 lights)

```
col:  0     1     2     3     4
row 0: 55    49    40    43    38
row 1: 56    35    46    41    48
row 2: 39    50    47    42    32
row 3: 37    36    44    45    51
```
Values are Hue light IDs on the home bridge.

**Entertainment group:** 200 (pre-configured on home bridge)

**DTLS channels** (entertainment API, real-time ~25fps): cols 2-4 rows 0-3 (10 lights)
- Channels are ordered as: [43, 41, 42, 45, 38, 48, 32, 51, 40, 46]
- Cols 0-1 rows 0-3 are REST-only (slower but still addressable via setCell)

**Approach:** Hybrid - DTLS for low-latency channels (cols 2-4), REST API for the outer two columns. The server uses phea to do the DTLS handshake and then hijacks the raw socket to send hand-built HueStream packets, bypassing phea's tween system for direct frame control.

### Running on pocket-sven (DJ Beat-Sync)

The entertainment server can run remotely on pocket-sven (the Pi) instead of locally:

```bash
# SSH to pocket-sven and start server
ssh pocket-sven "cd ~/code/hue-latency-tester && node entertainment-v2.js &"

# Check server status
ssh pocket-sven "curl -s http://localhost:8788/api/status"

# Send commands remotely (forward the port or use ssh tunnel)
ssh -L 8788:localhost:8788 pocket-sven &  # tunnel
curl http://localhost:8788/api/status       # now works locally

# Send color command via Pi
curl -X POST http://localhost:8788/api/cmd -H 'Content-Type: application/json' \
  -d '{"action":"setAll","r":255,"g":0,"b":0}'
```

**DTLS runs from the Pi** at ~25fps over 10 lights. The Pi has local network access to the Hue bridge and handles the DTLS handshake. Streaming logs show: "DTLS attempt 1/3... Hue Entertainment streaming ACTIVE (10 lights)"

Stop the server:
```bash
ssh pocket-sven "pkill -f entertainment-v2.js"
```

## Light Names

**Do NOT hardcode light names in this file.** Light names change as Ryan adds/removes bulbs. Always use `control.py list` for current inventory.

Run `$HUE list` to see current lights with:
- Name, on/off state, reachability (✓/✗), brightness, color temp, model, product type

## Troubleshooting

### Bulb Factory Reset (Philips Hue)
If a bulb is unresponsive, unreachable, or you want to move it to a different bridge:
1. Screw bulb into any socket
2. Turn power on/off **5 times** (1 sec on, 1 sec off each cycle)
3. Bulb will blink to confirm factory reset
4. Open Hue app → room → **Search for lights** → bulb appears as new
5. Old dead reference on previous bridge can be deleted

### Bridge Unreachable
- Check IP hasn't changed: `$HUE discover`
- If IP changed, update `~/.hue/<bridge>.json` with new IP
- If bridge was factory reset, re-pair: `$HUE pair <new_ip>`

### Light Shows Unreachable (✗)
- Physical switch is off (most common)
- Bulb is too far from bridge (Zigbee range ~30ft)
- Bulb needs factory reset (see above)

## Scripting Notes

- Errors go to **stderr**, data to **stdout** — safe for piping: `$HUE list --json | jq '.[] | .name'`
- Use `--quiet` to suppress OK messages in scripts
- Exit codes: 0 = success, 1 = error (bad args, not found, API failure)
- Partial name matching: `"Kitchen"` matches `"Kitchen Ceiling 1"` (exact match preferred)

## Integration

- **Lutron skill**: Use together for full home lighting (Hue = color/smart, Lutron = dimmers/shades)
- **House app**: Hue lights accessible via house-app frontend
- **Sonos**: Pair with announcements for notification workflows
