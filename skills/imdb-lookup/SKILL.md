---
name: imdb-lookup
description: Look up movie/TV info from TMDB. Trigger words - imdb, movie info, tv show info, tmdb, lookup movie.
---

# IMDb Lookup Skill

Look up movie or TV show information using the TMDB API. Returns a formatted card with title, year, ratings, director/creator, cast, genres, runtime, and IMDb link.

## Usage

```bash
~/.claude/skills/imdb-lookup/scripts/imdb-lookup "The Matrix"
~/.claude/skills/imdb-lookup/scripts/imdb-lookup "Breaking Bad" --format sms
~/.claude/skills/imdb-lookup/scripts/imdb-lookup "Inception" --format discord
```

## Options

- `--format discord` (default): Markdown-formatted card with bold headers
- `--format sms`: Compact plain-text card suitable for SMS

## API Key

Retrieved from macOS Keychain:
```bash
security find-generic-password -s tmdb -a api_key -w
```

## Notes

- Uses TMDB `/search/multi` to find movies and TV shows
- Fetches full details with `append_to_response=credits,external_ids`
- Shows TMDB rating; includes IMDb rating when available via external IDs
- For TV shows, displays creator instead of director and episode runtime
