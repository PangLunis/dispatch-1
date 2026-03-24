---
name: instagram
description: Post photos, follow/unfollow, like, comment, search, and manage Instagram profile. Trigger words - instagram, ig, post photo, follow on instagram, insta.
---

# Instagram Skill

Control Instagram via authenticated API calls. Uses Chrome session cookies — no API keys needed.

## CLI

All commands go through a single CLI:

```bash
~/.claude/skills/instagram/scripts/instagram <command> [args]
```

### Commands

#### Post a photo
```bash
instagram post /path/to/image.jpg "My caption here"
```

#### Post a reel (video)
```bash
instagram post-reel /path/to/video.mp4 "My caption here"
instagram post-reel /path/to/video.mp4  # no caption
```
- Auto-extracts cover photo from video (at 1 second mark) via ffmpeg
- Uploads video + cover photo, then configures as a Reel/Clip
- Video should be mp4 format

#### Get own feed/timeline
```bash
instagram feed
instagram feed --limit 10
```

#### Get a user's posts
```bash
instagram user-posts someuser
instagram user-posts someuser --limit 5
```

#### Follow/Unfollow
```bash
instagram follow someuser
instagram unfollow someuser
```

#### Like/Unlike
```bash
instagram like MEDIA_ID
instagram unlike MEDIA_ID
instagram like-url "https://www.instagram.com/p/ABC123/"
```

#### Comment
```bash
instagram comment MEDIA_ID "Nice photo!"
```

#### Search users
```bash
instagram search "john doe"
```

#### Get user info
```bash
instagram user someuser
```

#### Get notifications
```bash
instagram notifications
instagram notifications --limit 10
```

#### Profile management
```bash
instagram update-profile --name "Sven" --bio "robot family member"
instagram update-avatar /path/to/image.jpg
```

#### Get post info by URL
```bash
instagram post-info "https://www.instagram.com/p/ABC123/"
```

## Notes

- Authentication uses Chrome session cookies (extracted via chrome-control extension)
- The sessionid cookie is HttpOnly, extracted from Chrome's cookie jar
- Instagram rate-limits aggressively — the CLI adds conservative delays
- Media IDs are numeric; shortcodes are the alphanumeric strings in post URLs
- For private accounts, follow requests are sent (not instant follows)
