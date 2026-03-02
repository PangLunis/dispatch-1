---
name: webfetch
description: Fetch web pages using zendriver headless browser. Use as alternative to WebFetch for better success on blocked sites. Trigger words - fetch, web, scrape.
---

# WebFetch CLI

A CLI that fetches web pages using zendriver headless browser for reliable anti-bot bypass.

## Usage

```bash
# Basic fetch (returns markdown)
~/.claude/skills/webfetch/scripts/webfetch "https://reddit.com/r/programming"

# Raw HTML output
~/.claude/skills/webfetch/scripts/webfetch "https://example.com" --raw

# Custom timeout
~/.claude/skills/webfetch/scripts/webfetch "https://slow-site.com" --timeout 60
```

## How It Works

Uses `zendriver` headless browser (undetected Chrome fork):
- ~50-83% bypass rate on anti-bot protection
- Handles JavaScript rendering
- Works on most sites including Reddit, Medium, Amazon

## Output

- Converts HTML to clean markdown
- Removes nav, footer, scripts, styles
- Tries to find main content area
- Includes source URL

## First Run

Zendriver uses your installed Chrome, no extra setup needed. Just ensure `uv pip install zendriver` has been run.

## When to Use

Use this instead of WebFetch when:
- Site returns 403/503 (antibot blocking)
- Site requires JavaScript rendering
- Site blocks non-browser User-Agents

## Limitations

- Won't work on sites with heavy Cloudflare protection (use chrome-control for text extraction)
- Won't work on sites requiring login (use chrome-control with existing session)
- Takes ~3-5s per fetch (headless browser startup)

## Tier 3: Chrome Control Fallback

If webfetch still fails (Cloudflare captcha, login required), use chrome-control:

```bash
# Open page in Chrome (uses real browser session with cookies)
chrome open "https://example.com"
# Output: Opened tab 123456

# Get page text (works on CSP-protected sites like Discord)
chrome text 123456

# Get page HTML
chrome html 123456

# Clean up
chrome close 123456
```
