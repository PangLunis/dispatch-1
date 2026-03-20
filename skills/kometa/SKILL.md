---
name: kometa
description: Run Kometa (formerly Plex Meta Manager) to update metadata, overlays, collections. Trigger words - kometa, pmm, metadata, overlays, collections, ratings overlay.
---

# Kometa (Plex Meta Manager)

Enriches Plex library metadata with overlays, collections, and cross-source ratings.

## Installation

Kometa is cloned to `/tmp/Kometa` (re-clone if missing):

```bash
git clone https://github.com/Kometa-Team/Kometa.git /tmp/Kometa
cd /tmp/Kometa && uv pip install -r requirements.txt
```

## Config

Config lives at `~/kometa/config/config.yml`.

### Credentials

- **TMDB API key:** stored in keychain as `tmdb` / `api_key`
- **TMDB Read Access Token:** stored in keychain as `tmdb` / `read_access_token`
- **TMDB Account:** stored in keychain as `tmdb` / `account` (username + email + password)
- **Plex token:** see /plex skill

### Retrieve keys

```bash
security find-generic-password -s "tmdb" -a "api_key" -w
security find-generic-password -s "tmdb" -a "read_access_token" -w
```

## Running Kometa

```bash
# Run on all libraries
cd /tmp/Kometa && uv run python kometa.py --config ~/kometa/config/config.yml --run

# Run on specific library
cd /tmp/Kometa && uv run python kometa.py --config ~/kometa/config/config.yml --run --library "Movies"

# Run on specific library (TV)
cd /tmp/Kometa && uv run python kometa.py --config ~/kometa/config/config.yml --run --library "TV Shows"
```

## What Kometa Does

### Operations (mass updates)
- **mass_critic_rating_update: imdb** — pulls IMDb rating as critic score
- **mass_audience_rating_update: tmdb** — pulls TMDb rating as audience score
- **mass_genre_update: tmdb** — standardizes genres from TMDb
- **mass_content_rating_update: omdb** — needs OMDb API key (not configured yet)

### Collections (auto-created)
- Newly Released, IMDb Popular, IMDb Top 250, IMDb Lowest Rated
- Requires minimum items (most need 1+ matching items in library)

### Overlays (poster badges)
- Resolution (4K/1080p/720p)
- Audio codec (DTS, Atmos, TrueHD, etc.)
- Ratings (IMDb critic + TMDb audience displayed on poster)

## Post-Download Workflow

After downloading new media:
1. Move file to correct Plex library folder
2. Refresh Plex library section
3. Verify Plex matched the item (check guid isn't `local://`)
4. Run Kometa on that library: `--library "Movies"` or `--library "TV Shows"`
5. Verify overlays and ratings applied

## Config Format

The config uses `collection_files`, `metadata_files`, and `overlay_files` (not the deprecated `metadata_path` / `overlay_path`). See Kometa wiki for full docs.

## Notes

- Kometa downloads the full IMDb interface (~100MB) on first run for rating lookups
- Collections with `Minimum 1 Not Met` = not enough matching items in library yet
- Run takes ~1-2 minutes for a small library
- Schedule nightly runs for automatic updates as library grows
