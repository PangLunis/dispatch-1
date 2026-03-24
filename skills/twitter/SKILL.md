---
name: twitter
description: Post tweets, read timeline, follow/unfollow, upload media, search on X/Twitter. Trigger words - twitter, tweet, x.com, post tweet, timeline, follow on x.
---

# Twitter/X Skill

Control the @svenflowai X/Twitter account via API. Authenticates using Chrome session cookies — no API keys needed.

## CLI

All commands go through a single CLI:

```bash
~/.claude/skills/twitter/scripts/twitter <command> [args]
```

### Commands

#### Post a tweet
```bash
twitter post "Hello world!"
twitter post "Check this out" --media /path/to/image.png
twitter post "Replying!" --reply-to 1234567890
twitter post "Quoting!" --quote 1234567890
```

#### Read timeline
```bash
twitter timeline
twitter timeline --limit 10
```

#### Read a user's tweets
```bash
twitter user-tweets nsthorat
twitter user-tweets nsthorat --limit 5
```

#### Follow/Unfollow
```bash
twitter follow nsthorat
twitter unfollow nsthorat
```

#### Like/Unlike
```bash
twitter like 1234567890
twitter unlike 1234567890
```

#### Retweet/Unretweet
```bash
twitter retweet 1234567890
twitter unretweet 1234567890
```

#### Search
```bash
twitter search "machine learning"
twitter search "from:nsthorat" --limit 10
```

#### Notifications
```bash
twitter notifications
twitter notifications --limit 10
```

#### Profile management
```bash
twitter update-profile --name "sven" --bio "robot family member"
twitter update-avatar /path/to/image.png
twitter update-banner /path/to/image.png
```

#### Lookup user
```bash
twitter user nsthorat
```

#### Upload media
```bash
twitter upload /path/to/image.png
```

#### Refresh GraphQL IDs (if API calls start failing)
```bash
twitter refresh-ids
```

## Architecture

- **Authentication**: Cookies extracted live from Chrome via `chrome cookies x.com`
- **HTTP Client**: `curl_cffi` with Chrome TLS fingerprint impersonation
- **API**: Mix of v1.1 endpoints (still working) and GraphQL mutations/queries
- **GraphQL Query IDs**: Extracted from X main.js bundle; cached in ~/.cache/twitter-ids.json

## Notes

- The account is @svenflowai
- Bearer token is X's public web bearer (same for all users)
- GraphQL query IDs change with X deployments — run `twitter refresh-ids` if 404s
- Media upload uses chunked 3-step flow: INIT -> APPEND -> FINALIZE
- Rate limits apply

## Twitter Soul

The twitter voice/personality guide lives at `~/.claude/TWITTER-SOUL.md` (next to SOUL.md, not checked in). The midnight tweet planner reads it before drafting each day's tweet.
