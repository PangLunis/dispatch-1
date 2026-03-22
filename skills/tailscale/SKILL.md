---
name: tailscale
description: Tailscale network info. Show IP address, hostname, URLs for local services. Use this when sharing localhost links with the user — always provide the Tailscale IP URL so they can access it remotely.
---

# Tailscale

## Quick Reference

- **Tailscale binary**: `/opt/homebrew/opt/tailscale/bin/tailscale`
- **Socket**: `--socket=/tmp/tailscale.sock` (REQUIRED — default socket path doesn't work)
- **Get Tailscale IP**: `/opt/homebrew/opt/tailscale/bin/tailscale --socket=/tmp/tailscale.sock ip -4`
- **Local IP**: `ipconfig getifaddr en0`

## IMPORTANT: Never Send Raw Localhost URLs

**When sharing URLs with the user (via SMS, Signal, etc.), NEVER send `localhost` or `127.0.0.1` URLs.** The user is almost always on a different device (phone, laptop) and can't reach localhost.

**NEVER hardcode the Tailscale IP.** Always look it up dynamically:
```bash
TSIP=$(/opt/homebrew/opt/tailscale/bin/tailscale --socket=/tmp/tailscale.sock ip -4)
# Then send: http://$TSIP:<PORT><PATH>
```

**Do NOT use the hostname** (`svens-mac-mini.tail6669f2.ts.net`) — it hasn't been working reliably. Always use the numeric IP from the command above.

For internal use (curl, testing from this machine), localhost is fine. But any URL sent to a human must use the Tailscale IP.

## CRITICAL: Plain HTTP Only

Local services behind Tailscale have **no TLS certificates**. Browsers (especially mobile Safari and Chrome) silently auto-upgrade URLs to HTTPS, causing:

```
client sent an HTTP request to an HTTPS server
```

**Workarounds:**
- Tell the user to manually type `http://` in the address bar (not just the IP)
- Use incognito/private browsing (less aggressive HSTS)
- If the URL was previously visited over HTTPS, the browser may have cached an HSTS entry — clearing site data or using incognito fixes this

Always include the `http://` scheme explicitly when sending Tailscale URLs.

## Known Services

| Service | Port | Path |
|---------|------|------|
| Dashboard | 9091 | /dashboard |
| API | 9091 | /api/* |
| Agents | 9091 | /agents |
| Plex | 32400 | /web |
