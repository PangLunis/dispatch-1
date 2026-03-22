---
name: ruview
description: WiFi-based human sensing with ESP32-S3 and RuView. Presence detection, pose estimation, vital signs monitoring via WiFi CSI. Trigger words - ruview, wifi sensing, esp32, presence detection, vital signs, csi.
---

# RuView WiFi Sensing Skill

WiFi-based human perception using ESP32-S3 CSI (Channel State Information). No cameras, no wearables — just WiFi signals.

## Capabilities

- **Presence detection** — detect people in a room through walls
- **Pose estimation** — reconstruct body position from WiFi disturbances
- **Vital signs** — breathing rate (6-30 BPM) and heart rate (40-120 BPM)
- **Multi-person tracking** — independent tracking per person

## Configuration

All config lives in `~/dispatch/config.local.yaml` under the `ruview` key:

```yaml
ruview:
  repo_path: "~/code/RuView"
  esp32:
    serial_port: "/dev/cu.usbserial-XXXXXX"
    mac: "XX:XX:XX:XX:XX:XX"
    chip: "esp32s3"
    flash_size: "8MB"
    node_id: 1
  wifi:
    ssid: "YourSSID"
    # password stored in macOS Keychain as "ruview-wifi"
  server:
    http_port: 3000
    ws_port: 8766
    udp_port: 5005
    bind_addr: "0.0.0.0"
```

WiFi password is stored in macOS Keychain (service: `ruview-wifi`, account: `ruview`).

## Quick Commands

### Server Management

```bash
~/.claude/skills/ruview/scripts/ruview start      # Start sensing server
~/.claude/skills/ruview/scripts/ruview stop       # Stop sensing server
~/.claude/skills/ruview/scripts/ruview status     # Server status + live readings
~/.claude/skills/ruview/scripts/ruview vitals     # Current vital signs
~/.claude/skills/ruview/scripts/ruview presence   # Current presence status
```

### ESP32 Firmware (requires USB)

```bash
~/.claude/skills/ruview/scripts/ruview flash      # Flash firmware
~/.claude/skills/ruview/scripts/ruview provision   # Provision WiFi creds
~/.claude/skills/ruview/scripts/ruview monitor     # Serial monitor
```

### Visualization

```bash
~/.claude/skills/ruview/scripts/ruview dashboard   # Open observatory in Chrome
~/.claude/skills/ruview/scripts/ruview screenshot  # Screenshot live viz
```

## Architecture

```
ESP32-S3 (WiFi CSI sensor) --UDP--> Sensing Server (Rust) --HTTP/WS--> Dashboard
```

## Calibration Notes

- Single-node vital signs (HR/RR) need calibration — initial readings are noisy
- System learns room's baseline RF signature over time (hours)
- Heart rate needs subject to be relatively still
- Breathing rate more reliable than heart rate with single node
- For accurate multi-person tracking, 3-6 nodes recommended
- Through-wall sensing works up to ~5m
