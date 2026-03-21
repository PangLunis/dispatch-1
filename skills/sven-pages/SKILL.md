---
name: sven-pages
description: Publish HTML folders with per-folder ACLs. Default is PRIVATE (admin-only). Supports public access or email-based access control. Trigger words - deploy, pages, report, html hosting, publish.
---

# sven-pages

Publish HTML folders to Cloudflare with per-folder access control. **Default is PRIVATE (admin-only).**

## Privacy-First Policy

**Pages are PRIVATE by default.** Only use `--public` when the user explicitly asks to make something public.

- **In a chat context**: Always use `--acl` with the chat participants' emails
- **For personal/admin pages**: Use default (no flags) for admin-only access
- **Public pages**: Only use `--public` when explicitly told "make it public"

## Quick Start

```bash
# Publish a folder (private, admin-only — this is the default)
~/.claude/skills/sven-pages/scripts/publish ./my-report

# Publish shared with specific users (use this in chat contexts)
~/.claude/skills/sven-pages/scripts/publish ./my-report --acl "alice@gmail.com,bob@gmail.com"

# Publish publicly (ONLY when explicitly asked)
~/.claude/skills/sven-pages/scripts/publish ./my-report --public

# List all published pages
~/.claude/skills/sven-pages/scripts/publish --list

# Update ACL for existing folder
~/.claude/skills/sven-pages/scripts/publish --set-acl my-report --acl "new-user@gmail.com"

# Make existing folder public
~/.claude/skills/sven-pages/scripts/publish --set-acl my-report --public

# Delete a folder
~/.claude/skills/sven-pages/scripts/publish --delete my-report
```

## Access Control

Each folder can have its own ACL:

- **No ACL (default)**: Only admin can access
- **Email list (`--acl "a@x.com,b@x.com"`)**: Only listed emails can access
- **Public (`--public`)**: Anyone with the URL can access

## Two Publishing Systems

### System 1: sven-pages-worker (Cloudflare Workers KV)

- **URL**: `https://sven-pages-worker.nicklaudethorat.workers.dev/{folder}/`
- **Storage**: Cloudflare KV namespace `SVEN_PAGES`
- **CLI**: `~/.claude/skills/sven-pages/scripts/publish`
- ACLs managed per-folder via the CLI

### System 2: svenflow.ai (Cloud Run + Hono)

- **URL**: `https://svenflow.ai/pages/{folder}/`
- **Storage**: Filesystem `./pages/` dir on Cloud Run
- **ACLs**: Stored in `ACL_JSON` env var as JSON
- **Auth**: Google OAuth login for protected pages
- Pages without an ACL entry are **PRIVATE** (require admin login)
- Pages with `["*"]` in ACL are **PUBLIC**
- The `/pages` listing only shows PUBLIC pages

To make a page public on svenflow.ai, add `"pagename": ["*"]` to the `ACL_JSON` env var.

## For Group Chats

When publishing a report in a group chat, always share with participants:

```bash
# Get emails of group members, then publish with ACL
~/.claude/skills/sven-pages/scripts/publish ./report --acl "participant1@gmail.com,participant2@gmail.com"
```

## Architecture

- **Worker**: `sven-pages-worker` on Cloudflare Workers
- **Storage**: Cloudflare KV namespace `SVEN_PAGES`
- **URL**: `https://sven-pages-worker.nicklaudethorat.workers.dev/{folder}/`

## Admin Notes

The API key is stored at `~/.claude/skills/sven-pages/.api-key` and was set as a secret on the worker.

### Adding Google OAuth (Optional)

To enable Google login instead of email OTPs:

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create OAuth Client ID (Web application)
3. Add redirect URI: `https://your-team.cloudflareaccess.com/cdn-cgi/access/callback`
4. In Cloudflare Zero Trust > Settings > Authentication > Add new > Google
5. Paste client ID and secret

Then create an Access Application protecting the worker domain.

## Legacy Deploy Script

The old `deploy` script still works for simple Cloudflare Pages deployments (no ACLs):

```bash
~/.claude/skills/sven-pages/scripts/deploy ./folder
```
