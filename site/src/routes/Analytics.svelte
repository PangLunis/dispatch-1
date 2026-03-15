<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Analytics</h1>
    <p class="lead">Performance metrics, SDK event tracking, and operational insights.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      Dispatch records performance metrics and SDK events for operational visibility.
      Daily JSONL metric files, bus-backed event tracking, and CLI tools provide
      insights into system behavior.
    </p>
  </section>

  <section>
    <h2>Performance Metrics</h2>
    <p>
      Recorded via the <code>perf.py</code> module. Stored as daily JSONL files at
      <code>~/dispatch/logs/perf-YYYY-MM-DD.jsonl</code>.
    </p>

    <h3>Metric Types</h3>
    <ul>
      <li><strong>Timers</strong> — durations (e.g., how long an operation took)</li>
      <li><strong>Counters</strong> — counts (e.g., number of events)</li>
      <li><strong>Gauges</strong> — point-in-time values (e.g., current resource usage)</li>
    </ul>

    <h3>Key Metrics</h3>
    <table>
      <thead>
        <tr>
          <th>Metric</th>
          <th>Type</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>msg_processing_ms</code></td>
          <td>timer</td>
          <td>Time to process incoming message</td>
        </tr>
        <tr>
          <td><code>session_start_ms</code></td>
          <td>timer</td>
          <td>Time to create/resume session</td>
        </tr>
        <tr>
          <td><code>tool_call_ms</code></td>
          <td>timer</td>
          <td>Individual tool call duration</td>
        </tr>
        <tr>
          <td><code>disk_used_pct</code></td>
          <td>gauge</td>
          <td>Disk usage percentage</td>
        </tr>
        <tr>
          <td><code>disk_free_gb</code></td>
          <td>gauge</td>
          <td>Free disk space in GB</td>
        </tr>
        <tr>
          <td><code>active_sessions</code></td>
          <td>gauge</td>
          <td>Number of active sessions</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section>
    <h2>SDK Event Tracking</h2>
    <p>
      Every tool call is recorded to the <code>sdk_events</code> table in <code>bus.db</code>.
    </p>

    <h3>Fields</h3>
    <table>
      <thead>
        <tr>
          <th>Field</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>session_name</code></td>
          <td>Which session made the call</td>
        </tr>
        <tr>
          <td><code>tool_name</code></td>
          <td>Name of the tool invoked</td>
        </tr>
        <tr>
          <td><code>duration_ms</code></td>
          <td>How long the call took</td>
        </tr>
        <tr>
          <td><code>success</code></td>
          <td>Whether the call succeeded</td>
        </tr>
        <tr>
          <td><code>error_message</code></td>
          <td>Error details on failure</td>
        </tr>
      </tbody>
    </table>

    <p>
      Events have a <strong>3-day retention</strong> and are auto-pruned.
      This enables latency analysis per tool, per session.
    </p>
  </section>

  <section>
    <h2>Bus Event Analytics</h2>
    <p>
      All business events live in the <code>records</code> table with 7-day retention.
      See <button class="text-link" on:click={() => navigateTo('message-bus')}>Message Bus</button> for
      the full event taxonomy and CLI reference.
    </p>
  </section>

  <section>
    <h2>Session Logs</h2>
    <p>
      Per-session log files at <code>~/dispatch/logs/sessions/</code>.
      10MB max size with 5 backup rotations.
    </p>

    <h3>Color-Coded Monitoring</h3>
    <pre><code># Watch single session
./bin/claude-assistant attach &lt;session&gt;

# Watch all sessions
./bin/claude-assistant monitor</code></pre>
  </section>

  <section>
    <h2>FD Leak Detection</h2>
    <p>
      The <code>ResourceRegistry</code> monitors <code>/dev/fd/</code> delta vs tracked resources.
      Checks run every 5 minutes. Alerts on unexpected file descriptor growth,
      helping catch resource leaks before they cause issues.
    </p>
  </section>

  <section>
    <h2>Future: Analytics Consumers</h2>
    <p>
      The bus consumer framework supports independent consumer groups.
      Each consumer tracks its own committed offset independently.
    </p>

    <h3>Planned Consumers</h3>
    <ul>
      <li><strong>Real-time alerting</strong> — immediate notifications on anomalies</li>
      <li><strong>Dashboard aggregation</strong> — periodic rollups for visualization</li>
      <li><strong>Anomaly detection</strong> — statistical analysis of metric trends</li>
    </ul>
  </section>

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('message-bus')}>
        <span class="related-label">Message Bus</span>
        <span class="related-desc">Event source</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('health')}>
        <span class="related-label">Health & Healing</span>
        <span class="related-desc">Health metrics</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('cli')}>
        <span class="related-label">CLI Reference</span>
        <span class="related-desc">Monitoring commands</span>
      </button>
    </div>
  </section>
</article>

<style>
  .page {
    max-width: var(--content-max-width);
  }

  .page-header {
    margin-bottom: var(--space-6);
  }

  .lead {
    font-size: 15px;
    color: var(--text-secondary);
    margin: 0;
  }

  section {
    margin-bottom: var(--space-8);
  }

  .text-link {
    background: none;
    border: none;
    padding: 0;
    color: var(--accent);
    font-size: inherit;
    font-family: inherit;
    cursor: pointer;
    transition: color var(--transition-fast);
  }

  .text-link:hover {
    color: var(--accent-hover);
  }

  .related {
    margin-top: var(--space-12);
    padding-top: var(--space-8);
    border-top: 1px solid var(--border-subtle);
  }

  .related h2 {
    font-size: 14px;
    margin-bottom: var(--space-4);
  }

  .related-links {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: var(--space-3);
  }

  .related-link {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-4);
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
    cursor: pointer;
    text-align: left;
    font-family: inherit;
    transition: border-color var(--transition-fast);
  }

  .related-link:hover {
    border-color: var(--border-strong);
  }

  .related-label {
    font-weight: 500;
    font-size: 13px;
    color: var(--text-primary);
  }

  .related-desc {
    font-size: 12px;
    color: var(--text-tertiary);
  }
</style>
