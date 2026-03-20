---
name: plex
description: Manage Plex Media Server - libraries, metadata, playback. Trigger words - plex, media server, library, metadata, watch, stream.
---

# Plex Media Server

Local Plex Media Server running on this Mac Mini.

## Credentials

- **Account:** stored in keychain as `plex` / `email`
- **Password:** stored in keychain as `plex` / `password`
- **Auth token:** stored in keychain as `plex` / `token`
- **Local admin token:** `~/Library/Application Support/Plex Media Server/.LocalAdminToken`
- **Machine ID:** stored in keychain as `plex` / `machine_id`

## API Access

```bash
# Get local admin token
TOKEN=$(cat ~/Library/Application\ Support/Plex\ Media\ Server/.LocalAdminToken)

# Server identity
curl -s "http://localhost:32400/identity" -H "Accept: application/json"

# List libraries
curl -s "http://localhost:32400/library/sections?X-Plex-Token=$TOKEN" -H "Accept: application/json"

# List items in a library section
curl -s "http://localhost:32400/library/sections/{SECTION_ID}/all?X-Plex-Token=$TOKEN" -H "Accept: application/json"

# Get item metadata
curl -s "http://localhost:32400/library/metadata/{ID}?X-Plex-Token=$TOKEN" -H "Accept: application/json"

# Search for metadata matches (to fix unmatched items)
curl -s "http://localhost:32400/library/metadata/{ID}/matches?manual=1&title=TITLE&year=YEAR&X-Plex-Token=$TOKEN" -H "Accept: application/json"

# Apply a match
curl -s -X PUT "http://localhost:32400/library/metadata/{ID}/match?guid=ENCODED_GUID&name=TITLE&year=YEAR&X-Plex-Token=$TOKEN"

# Refresh library
curl -s -X GET "http://localhost:32400/library/sections/{SECTION_ID}/refresh?X-Plex-Token=$TOKEN"

# Web UI
open "http://localhost:32400/web"
# Or: https://app.plex.tv/desktop
```

## Libraries

| Section | Name      | Path                   | Agent                  | Scanner     |
|---------|-----------|------------------------|------------------------|-------------|
| 1       | TV Shows  | /Users/sven/Movies/TV  | tv.plex.agents.series  | Plex TV Series |
| 2       | Movies    | /Users/sven/Movies/movies | tv.plex.agents.movie | Plex Movie  |

## Metadata Requirements

**CRITICAL: Every item added to Plex MUST have accurate metadata.**

After adding new media files:
1. Refresh the library section: `GET /library/sections/{ID}/refresh`
2. Check the new item's `guid` — if it shows `local://` prefix, the item is **unmatched**
3. For unmatched items, search for matches and apply the correct one:
   - `GET /library/metadata/{ID}/matches?manual=1&title=TITLE&year=YEAR`
   - `PUT /library/metadata/{ID}/match?guid=ENCODED_GUID&name=TITLE&year=YEAR`
4. Verify metadata populated: summary, genres, ratings, cast, images

Required metadata fields:
- **Summary** — plot description
- **Genres** — at least 2-3 genres
- **Ratings** — critic and audience ratings
- **Content rating** — G, PG, PG-13, R, etc.
- **Cast & crew** — director, main actors
- **Artwork** — poster and background art (auto-downloaded on match)

## File Naming

Plex matches best with clean filenames:
- Movies: `Movie Name (Year).ext` or `Movie.Name.Year.Quality.mkv`
- TV: `Show Name/Season 01/Show Name - S01E01 - Episode Title.ext`

## Notes

- Plex runs as a menubar app (LSUIElement=1) — no Dock icon
- Install: `brew install --cask plex-media-server`
- Config: `~/Library/Application Support/Plex Media Server/`
- Logs: `~/Library/Logs/Plex Media Server/`
- The server is claimed under the owner's email — remote access enabled
- `secureConnections=1`, `PublishServerOnPlexOnlineKey=1` for remote access

## Kometa Integration

After metadata is confirmed, run Kometa to add overlays, update ratings from IMDb/TMDb, and standardize genres:

```bash
cd /tmp/Kometa && uv run python kometa.py --config ~/kometa/config/config.yml --run --library "Movies"
```

See `/kometa` skill for full details. Kometa updates:
- Critic rating → IMDb score
- Audience rating → TMDb score
- Genres → TMDb standardized genres
- Poster overlays → resolution, audio codec, ratings badges

## Remote Access via Tailscale

Plex Web requires sign-in even on local/Tailscale networks. A Caddy reverse proxy on port 8443 bypasses this by injecting the auth token into every request.

**Access URLs:**
- Local: `http://10.10.10.59:32400/web` (requires Plex sign-in)
- Tailscale (no auth): `http://100.127.42.15:8443/web` or `http://svens-mac-mini.tail6669f2.ts.net:8443/web`

**How it works:**
- Caddy listens on `:8443`, proxies to `localhost:32400`, injects `X-Plex-Token` header
- Config: `~/caddy/Caddyfile`
- LaunchAgent: `~/Library/LaunchAgents/com.caddy.plex-proxy.plist` (auto-starts on boot)
- Tailscale CGNAT IPs (100.x.x.x) are NOT RFC 1918, so Plex's `allowedNetworks` setting ignores them — the proxy is the only workaround

**Why not just sign in:** Plex account sign-in flow pushes users toward Plex Pass (paid). The proxy avoids this entirely.

**Manage Caddy:**
\`\`\`bash
caddy start --config ~/caddy/Caddyfile   # Start
caddy stop                                 # Stop
caddy reload --config ~/caddy/Caddyfile   # Reload config
\`\`\`
