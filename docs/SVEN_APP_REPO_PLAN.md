# Moving Sven iOS App to Dispatch Repo

> **Note:** The native SwiftUI Sven app has been deprecated. It has been moved to `~/dispatch/apps/sven-ios-deprecated/`. The active app is the Expo/React Native app at `~/dispatch/apps/dispatch-app/`.

**STATUS: COMPLETED (2026-02-11)**

Plan for consolidating the Sven iOS app into the dispatch repository.

## Current State

- **Sven iOS app (deprecated)**: `~/dispatch/apps/sven-ios-deprecated/` (moved from ~/code/ios-apps/Sven/, now deprecated in favor of `~/dispatch/apps/dispatch-app/`)
- **Dispatch repo**: `~/dispatch/` (GitHub: nicklaude/dispatch)
- **Sven backend skill**: `~/.claude/skills/sven-app/` (symlinked into dispatch)

## The Challenge

Several things reference `~/code/ios-apps/`:
- iOS development skill (`~/dispatch/skills/ios-app/SKILL.md`)
- Various docs in dispatch
- Potentially Xcode derived data, build caches

## Options

### Option A: Move into dispatch/apps/sven-ios/
**Pros:**
- Single repo for all dispatch code
- Easier to keep iOS and backend in sync
- One `git pull` updates everything

**Cons:**
- Need to update ios-app skill paths
- Need to update any hardcoded references
- Xcode project needs to be opened from new location

**Steps:**
1. Copy `~/code/ios-apps/Sven/` to `~/dispatch/apps/sven-ios/`
2. Update `~/dispatch/skills/ios-app/SKILL.md` to support both locations or new location
3. Update these files (grep for `~/code/ios-apps`):
   - `dispatch/docs/IOS_DEVELOPMENT.md`
   - `dispatch/docs/architecture-summary.md`
   - `dispatch/CLAUDE.md`
   - `dispatch/skills/ios-app/SKILL.md`
   - And others (21 files total reference this path)
4. Test Xcode build from new location
5. Delete old location after confirming everything works
6. Commit and push

### Option B: Git Submodule
**Pros:**
- Sven app has its own repo/history
- Can be developed independently
- Cleaner separation

**Cons:**
- More complex git workflow
- Two repos to manage
- Submodule sync issues

**Steps:**
1. `cd ~/code/ios-apps/Sven && git init`
2. Create GitHub repo (nicklaude/sven-ios or similar)
3. Push to GitHub
4. `cd ~/dispatch && git submodule add <repo-url> apps/sven-ios`
5. Update path references as in Option A

### Option C: Separate Repo (Simplest)
**Pros:**
- No changes to dispatch
- Quick to set up
- Independent versioning

**Cons:**
- Not consolidated with dispatch
- Have to remember to commit separately

**Steps:**
1. `cd ~/code/ios-apps/Sven && git init`
2. Create GitHub repo
3. Push
4. Done (leave in current location)

## Recommendation

**Option A (move into dispatch)** is cleanest long-term if you want everything together. The path updates are mechanical - just find/replace.

**Option C** is fastest if you just want it on GitHub now and don't care about consolidation.

## Files to Update for Option A

Based on grep for `ios-apps` and `~/code`:

```
dispatch/skills/ios-app/SKILL.md              # Main skill file
dispatch/docs/IOS_DEVELOPMENT.md              # iOS dev docs
dispatch/docs/architecture-summary.md         # Architecture overview
dispatch/CLAUDE.md                            # Main project instructions
dispatch/skills/setup-wizard/SKILL.md         # Setup wizard
dispatch/skills/setup-wizard/scripts/check.py # Setup check script
dispatch/docs/blog/*.md                       # Blog posts
dispatch/README.md                            # Readme
# ... and others
```

## Xcode Considerations

The Xcode project uses relative paths (`sourceTree = "<group>"`) so it should work from any location. Things to verify:
- Signing & Capabilities still work
- Derived data doesn't break (stored in ~/Library/Developer/Xcode/DerivedData/)
- Provisioning profiles still valid

## Implementation Checklist

For Option A (COMPLETED 2026-02-11):
- [x] Create `~/dispatch/apps/` directory if not exists
- [x] Copy Sven folder: `cp -r ~/code/ios-apps/Sven ~/dispatch/apps/sven-ios`
- [x] Update all path references in dispatch
- [ ] Open in Xcode from new location, verify it builds
- [ ] Test ios-app skill commands work
- [ ] Commit to dispatch repo
- [ ] Delete old location after 1 week of successful use
