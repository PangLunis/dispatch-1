# Dispatch Postmortems

Incident logs and lessons learned. Read by bug-finder, debug skill, and future sessions to avoid repeating mistakes.

---

## 2026-03-15: Disk Full (99.7%) — Zombie llama-cli Processes

**Severity:** Critical (system unresponsive, required HEALME)
**Duration:** ~45 minutes (10:25 - 11:10 ET)
**Impact:** Daemon couldn't restart, all sessions down

### Timeline

- **10:25** — Committed PostCompact hook, smart stuck detector, bug-finder improvements (a08d36b)
- **10:36** — Admin approved daemon restart
- **10:42** — Daemon failed to restart (disk full). Admin messaged "did you restart" — no response
- **10:50** — Admin triggered HEALME
- **10:53** — Healing session found disk 99.7% full. Identified 510GB in `/tmp/claude-501/` from session `2df6be1ed7534cd797e5fdb2c4bd6bd8` ("sven sven sven" group). Deleted the directory.
- **11:10** — Disk still at 98%. Investigation revealed 30 zombie `llama-cli` processes holding 500GB+ of deleted files via open file handles. Killed processes → disk dropped to 80%.

### Root Cause

The "sven sven sven" session was doing WebGPU ML benchmarking with `llama-cli` (gemma-3-270m model). Each `llama-cli` invocation memory-maps the model file (~67-165GB virtual). The session spawned ~30 `llama-cli` processes via Bash tool calls that never terminated — they were waiting on stdin or stuck.

When the healing session deleted `/tmp/claude-501/.../` contents, the files were unlinked from the filesystem but the space wasn't freed because the zombie processes still held open file descriptors. This is standard Unix behavior: `rm` removes the directory entry, but the inode and data blocks aren't freed until all file descriptors are closed.

### Additional Disk Hogs Found

- `~/.cache/uv/environments-v2/`: 70GB (430 cached virtual environments from uv shebang scripts)
- `~/.cache/huggingface/hub/`: 83GB (downloaded model weights)
- `~/.cache/memory-search/index.sqlite`: 61GB (legacy FTS search index — RETIRED, replaced by bus FTS5)
- `~/Library/Messages/Attachments/`: 50GB (iMessage media)

### Fixes Applied

1. **Disk space monitor** (a3832ca) — Health check now monitors disk usage every cycle (~5min). Warns at 90%, critical at 95%. Sends admin SMS (rate-limited to 1 per 30min). Emits `disk_used_pct` and `disk_free_gb` perf gauges.

2. **Manual cleanup** — Cleared uv cache (103GB) and huggingface cache (83GB). Killed zombie llama-cli processes (freed 500GB of deleted-but-held files).

### Lessons

1. **Deleting files doesn't free space if processes hold them open.** Always check `lsof +L1` for deleted-but-open files after cleanup. The healing skill should do this automatically.

2. **Long-running Bash tool commands can become zombies.** When a session dies or compacts, its spawned child processes (especially those waiting on stdin like `llama-cli`) may survive indefinitely. Sessions should track and clean up child processes on shutdown.

3. **Memory-mapped model files are deceptively large.** A 270MB model file can map to 67-165GB of virtual memory. Multiple instances compound this.

4. **Cache directories grow unbounded without maintenance.** uv and huggingface caches grew to 50-100GB each without any cleanup policy. Consider periodic `uv cache prune` and huggingface cache management. The 61GB memory-search cache has been retired (replaced by bus FTS5).

5. **The disk monitor would have caught this.** At 90% threshold, we would have been alerted ~100GB before the system became unusable, giving time to investigate and clean up.

### Action Items

- [x] Add disk space monitoring to health checks
- [ ] Add `lsof +L1` check to HEALME/healing skill to detect deleted-but-held files
- [ ] Add orphaned child process detection to session cleanup (kill spawned processes when session dies)
- [x] ~~Investigate memory-search 51GB sqlite~~ — RETIRED: memory-search daemon replaced by bus FTS5. Delete `~/.cache/memory-search/` to reclaim 61GB.
- [ ] Consider adding zombie process detection to health checks (processes from dead sessions)
