---
name: manual-test
description: Manual testing orchestrator. Enumerate CUJs for any feature, execute via browser or API, report results. Trigger words - manual test, test, CUJ, test feature, verify, QA.
---

# /manual-test — Manual Testing Skill

**Purpose:** Enumerate CUJs for a feature, execute them via browser or API, report results. Wraps chrome-control and curl.

## Invocation

```
/manual-test                        # auto-detect mode, enumerate CUJs
/manual-test web                    # browser testing via chrome-control
/manual-test api                    # API testing via curl
/manual-test smoke                  # top 3-5 CUJs only
/manual-test run <name>             # load saved CUJs, confirm, execute
/manual-test list                   # list saved CUJ sets in .manual-test/
```

Two modes: **web** (chrome-control) and **api** (curl).

## Step 0: Preflight

- Web: `chrome list-tabs` succeeds. API: health endpoint returns 200.
- Fails → print fix → STOP
- Create `/tmp/manual-test/run-{timestamp}/` for evidence (cleared on reboot; copy out if needed)
- Screenshots: `cuj-N-before.png`, `cuj-N-after.png`. Results: `results.json`. All in the run directory.

## Step 1: Enumerate CUJs

*`run <name>`: load from `.manual-test/<name>.json` (relative to project root), show list, confirm before executing.*

**Discovery:**
1. `git diff --name-only` → changed files
2. Grep changed files for route/handler registrations and exported components (patterns vary by framework — Express routes, Next.js pages, React Navigation screens, Django urlpatterns, Flask routes, etc.)
3. Each route/component touched → 1 CUJ. At least 1 error-path CUJ for every 2-3 happy paths. Target at least 3, cap 15. If discovery yields fewer than 3, enumerate what exists — don't fabricate. If exceeds 15, prioritize by code churn (most-changed first), then route depth (top-level before nested).
4. Check adjacent test files — extract CUJs from existing tests when available
5. If no changed files or context, ask user what to test

**Auth:** If app has auth, insert CUJ 0 "Establish session." Ask user: (a) log in via UI, (b) assume active session, (c) provide token. Auth is shared across CUJs. If auth fails mid-run (401), pause and re-prompt user.

**CUJ format (Arrange-Act-Assert):**
```
CUJ 3: Send a message
ARRANGE: Navigate to /chat/123, ensure input bar visible
ACT: Type "hello" → click send
ASSERT:
  - DOM: input.value === ''
  - Visual: user bubble appears on right [opt-in]
```

- **DOM** (default): `chrome execute` returning boolean. Deterministic.
- **Visual** (opt-in, ~90% reliable): LLM reads screenshot. Tagged `[visual-only]` when no DOM check.
- CUJs are independent (except shared auth).

**User commands:** `run all` / `run 1,3,5` / `skip 2` / `edit 3` (describe change → rewrite → confirm) / `save <name>` (writes to `.manual-test/<name>.json` in project root, overwrites if exists) / `abort`

## Step 2: Execute

**Per-CUJ timeout: 60s.** Real-time progress: `CUJ 1/6: Create chat... ✅ PASS (2.1s)`

**State cleanup (web):** Reload page at start of each CUJ's ARRANGE (fresh DOM, preserves auth cookies).

**Web mode per CUJ:**
1. Navigate to URL (ARRANGE) → screenshot "before"
2. Click/type (ACT)
3. Poll for assertion target element (500ms, 5s timeout; visual-only: 2s wait)
4. DOM assertions via `chrome execute`
5. Screenshot "after"
6. Visual assertions if opted-in: Read screenshot → evaluate

**API mode per CUJ:** Preconditions (ARRANGE) → `curl` (ACT) → assert status + body (ASSERT)

### Status Rules

**Assertion logic:** FAIL on any assertion → ❌ FAIL. All assertions PASS → ✅ PASS. Any assertion UNCERTAIN or UNAVAILABLE (tool failed) with no FAILs → ⚠️ REVIEW. Visual-only CUJs are flagged as lower-confidence. Per-CUJ timeout (60s) → ⏱️ TIMEOUT.

**Non-assertion failures:** ARRANGE failure (404, setup error) → 🚫 SETUP_FAIL. Chrome unresponsive (`list-tabs` fails) → health check, wait 2s, retry CUJ once → ⚠️ ENV. Chrome command fails but extension alive → wait 1s, retry command once → 💥 TOOL_ERROR.

**Guardrails:**
- Page reload + health check between web CUJs
- 2 consecutive SETUP_FAILs → pause, ask user if environment is correct
- Auth 401 mid-run → pause, re-prompt
- Abort = finish current CUJ, stop, partial report

## Step 3: Report

```
## Test Results: [Feature]
Mode: web | Run: 2026-03-22T21:50 | 6/6 | ✅ 4 | ❌ 1 | ⚠️ 1 | 🚫 0 | ⚠️ ENV 0 | 💥 0 | ⏱️ 0

| # | CUJ | Type | Status | Evidence |
|---|-----|------|--------|----------|
| 1 | Create chat | dom | ✅ | cuj-1-after.png |
| 2 | Send message | dom+visual | ❌ | cuj-2-after.png |

### Failures
**CUJ 2: Send message**
- DOM: FAIL — input.value="hello" (expected "")
- Suggested fix: onSubmit in InputBar.tsx

### Needs Review [visual-only, lower confidence]
**CUJ 3: Color hover**
- Visual: UNCERTAIN — may be mid-animation
```

**Machine-readable:** `/tmp/manual-test/run-{timestamp}/results.json`
Fields: `schema_version`, `feature`, `mode`, `timestamp`, `summary` {total, pass, fail, review, env, setup_fail, tool_error, timeout}, `cujs[]` {id, name, status, assertion_type, dom_result, visual_result, evidence, duration_ms, error}.

## Smoke Mode

Top CUJs: (1) primary happy path, (2) highest code churn, (3) error handling. Cap at 5.

## Scope

Web + API only. iOS → /ios-app, real devices → /lambdatest, perf → /latency-finder, code → /bug-finder.
