<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Health & Healing</h1>
    <p class="lead">Multi-tier health monitoring with automatic recovery.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      Dispatch uses a layered approach to detect and recover from failures.
      Fast regex scans catch known errors, deep LLM analysis catches subtle issues,
      and a watchdog daemon recovers from crashes.
    </p>
    <p>
      Each tier adds coverage for failure modes the previous tier cannot detect,
      creating defense in depth across all running sessions.
    </p>
  </section>

  <section>
    <h2>Tier 1: Regex Scan</h2>
    <p class="tier-interval">Every 60 seconds</p>
    <p>
      Scans recent transcript entries for known fatal error patterns using compiled regular expressions.
      Runs across all active sessions for instant detection of known failure modes.
    </p>
    <div class="pattern-list">
      <div class="pattern-header">Detected patterns</div>
      <ul>
        <li>API 400 errors</li>
        <li>Image dimension errors</li>
        <li>Context length exceeded</li>
        <li>Auth and billing errors</li>
        <li>Buffer overflow</li>
      </ul>
    </div>
    <p>
      Compiled regex ensures minimal overhead even when scanning dozens of sessions simultaneously.
    </p>
  </section>

  <section>
    <h2>Tier 2: Haiku Analysis</h2>
    <p class="tier-interval">Every 5 minutes</p>
    <p>
      Sends recent assistant messages to Claude Haiku for classification.
      Haiku returns a structured verdict: <code>FATAL</code> (needs restart) or
      <code>HEALTHY</code> (normal operation).
    </p>
    <p>
      This catches subtle issues that regex cannot: stuck loops, error cascades, and
      unresponsive sessions. Uses a one-shot classification with a structured prompt
      to keep latency and cost low.
    </p>
  </section>

  <section>
    <h2>Tier 3: Stuck Session Detection</h2>
    <p>
      Detects sessions where messages were injected but no response was returned.
      Haiku analyzes the transcript to distinguish genuinely stuck sessions from
      those working on long tasks.
    </p>
    <div class="pattern-list">
      <div class="pattern-header">Classification</div>
      <table>
        <thead>
          <tr>
            <th>Signal</th>
            <th>Verdict</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>No activity</td>
            <td><code>stuck</code></td>
          </tr>
          <tr>
            <td>Error loops</td>
            <td><code>stuck</code></td>
          </tr>
          <tr>
            <td>Active tool calls</td>
            <td><code>working</code></td>
          </tr>
          <tr>
            <td>Subagent operations</td>
            <td><code>working</code></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p>
      This prevents false positives on long-running tasks like browser automation or
      multi-step research.
    </p>
  </section>

  <section>
    <h2>Watchdog Daemon</h2>
    <p>
      A separate LaunchAgent monitors the main daemon process. If the daemon crashes,
      the watchdog spawns a healing Claude session to diagnose and restart it.
    </p>
    <ul>
      <li>Checks every 60 seconds</li>
      <li>Exponential backoff: 60s &rarr; 120s &rarr; 240s &rarr; 480s &rarr; 900s</li>
      <li>SMS alerts to admin on recovery attempts</li>
      <li>Max 5 consecutive failures before requiring manual intervention</li>
    </ul>

    <h3>Management</h3>
    <pre><code>./bin/watchdog-install
./bin/watchdog-uninstall
./bin/watchdog-status</code></pre>
  </section>

  <section>
    <h2>Disk Space Monitoring</h2>
    <p>
      Monitors root volume usage every health check cycle (approximately 5 minutes).
    </p>
    <ul>
      <li>Warning at <strong>90%</strong> usage, critical at <strong>95%</strong></li>
      <li>SMS alerts to admin, rate-limited to 1 per 30 minutes</li>
      <li>Emits <code>disk_used_pct</code> and <code>disk_free_gb</code> performance gauges</li>
    </ul>
  </section>

  <section>
    <h2>Session Idle Reaping</h2>
    <p>
      Sessions idle for 2+ hours are automatically stopped to free resources for active
      conversations. A reaped session can be resumed on the next incoming message via the
      session registry.
    </p>
  </section>

  <section>
    <h2>Recovery Actions</h2>
    <table>
      <thead>
        <tr>
          <th>Trigger</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Fatal regex match</td>
          <td>Restart session</td>
        </tr>
        <tr>
          <td>Haiku FATAL verdict</td>
          <td>Restart session</td>
        </tr>
        <tr>
          <td>Stuck session confirmed</td>
          <td>Restart session</td>
        </tr>
        <tr>
          <td>Daemon crash</td>
          <td>Watchdog spawns healing session</td>
        </tr>
      </tbody>
    </table>
    <p>
      All restarts preserve conversation history via SDK resume, so contacts experience
      no data loss.
    </p>
  </section>

  <section>
    <h2>Self-Improvement Tools</h2>
    <p>
      Beyond reactive health monitoring, Dispatch includes proactive tools for
      finding and fixing issues before they become incidents.
    </p>

    <div class="pattern-list">
      <div class="pattern-header">Bug Finder</div>
      <ul>
        <li>Parallel discovery and refinement agents scan recent code changes, system health, test failures, and consistency issues</li>
        <li>Uses multiple subagents to cast a wide net, then refines findings into actionable bug reports</li>
      </ul>
    </div>

    <div class="pattern-list">
      <div class="pattern-header">Latency Finder</div>
      <ul>
        <li>Analyzes performance JSONL files, bus.db sdk_events, bus.db records, and system metrics</li>
        <li>Uses parallel discovery agents to scan multiple data sources simultaneously</li>
        <li>Synthesizes findings into prioritized recommendations</li>
      </ul>
    </div>

    <div class="pattern-list">
      <div class="pattern-header">Skillify</div>
      <ul>
        <li>Mines conversation transcripts for automation opportunities</li>
        <li>Proposes new skills, improvements to existing skills, and skill merges</li>
        <li>Ensures the system gets smarter over time by converting recurring patterns into reusable capabilities</li>
      </ul>
    </div>
  </section>

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('analytics')}>
        <span class="related-label">Analytics</span>
        <span class="related-desc">Health metrics</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('cli')}>
        <span class="related-label">CLI Reference</span>
        <span class="related-desc">Watchdog commands</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('postmortems')}>
        <span class="related-label">Postmortems</span>
        <span class="related-desc">Past incidents</span>
      </button>
    </div>
  </section>
</article>

<style>
  .page-header h1 {
    margin-bottom: var(--space-1);
  }

  .tier-interval {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: var(--space-2);
  }

  .pattern-list {
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
    padding: var(--space-4);
    margin: var(--space-4) 0;
  }

  .pattern-header {
    font-weight: 600;
    font-size: 13px;
    margin-bottom: var(--space-3);
    color: var(--text-primary);
  }

  .pattern-list ul {
    margin: 0;
    padding-left: var(--space-4);
  }

  .pattern-list li {
    margin: var(--space-1) 0;
    font-size: 12px;
  }

  .pattern-list table {
    margin: 0;
  }

</style>
