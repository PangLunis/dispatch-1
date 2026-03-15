<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Message Bus</h1>
    <p class="lead">Kafka-on-SQLite event bus for audit trails and analytics.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      All system events flow through a SQLite-backed message bus organized into
      <strong>5 topics</strong>: <code>messages</code>, <code>sessions</code>,
      <code>system</code>, <code>reminders</code>, and <code>tasks</code>.
      Fire-and-forget writes with an in-memory queue ensure the event loop is
      never blocked. Multiple consumer groups can process events independently
      with committed offsets.
    </p>
  </section>

  <section>
    <h2>Architecture</h2>
    <ul>
      <li><strong>Producer:</strong> <code>produce_event()</code> enqueues events to an in-memory write queue (~microsecond enqueue time)</li>
      <li><strong>Background thread</strong> batches commits to SQLite (no event loop blocking)</li>
      <li><strong>Consumer groups</strong> with independent committed offsets</li>
      <li><strong>Two tables:</strong> <code>records</code> (business events, 7-day retention) and <code>sdk_events</code> (tool call traces, 3-day retention)</li>
    </ul>
  </section>

  <section>
    <h2>Event Taxonomy</h2>
    <table>
      <thead>
        <tr>
          <th>Topic</th>
          <th>Events</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>messages</code></td>
          <td><code>message.received</code>, <code>message.sent</code>, <code>message.failed</code>, <code>message.queued</code>, <code>message.delivered</code>, <code>reaction.received</code></td>
        </tr>
        <tr>
          <td><code>sessions</code></td>
          <td><code>session.created</code>, <code>session.restarted</code>, <code>session.killed</code>, <code>session.compacted</code>, <code>session.crashed</code>, <code>session.injected</code>, <code>session.idle_killed</code>, <code>permission.denied</code></td>
        </tr>
        <tr>
          <td><code>system</code></td>
          <td><code>daemon.started</code>, <code>daemon.stopped</code>, <code>daemon.crashed</code>, <code>daemon.recovered</code>, <code>health.check_completed</code>, <code>consolidation.started</code>, <code>consolidation.completed</code>, <code>reminder.fired</code>, <code>vision.analyzed</code>, <code>sdk.turn_complete</code>, <code>session.heartbeat</code></td>
        </tr>
        <tr>
          <td><code>reminders</code></td>
          <td><code>reminder.due</code></td>
        </tr>
        <tr>
          <td><code>tasks</code></td>
          <td><code>task.requested</code>, <code>task.started</code>, <code>task.completed</code>, <code>task.failed</code>, <code>task.timeout</code>, <code>task.skipped</code></td>
        </tr>
      </tbody>
    </table>
  </section>

  <section>
    <h2>Bus CLI</h2>
    <pre><code># List all topics
./bin/bus topics

# Show event statistics
./bin/bus stats
./bin/bus stats --topic messages

# Tail recent events (like kafka-console-consumer)
./bin/bus tail
./bin/bus tail --type message.received

# Query records with filters
./bin/bus query --topic sessions --since 1h

# Export events to JSON
./bin/bus export --since 24h > events.json</code></pre>
  </section>

  <section>
    <h2>SDK Event Tracking</h2>
    <ul>
      <li>Every tool call recorded: tool name, duration, success/failure</li>
      <li>Stored in separate <code>sdk_events</code> table with 3-day retention</li>
      <li>Used by analytics consumers for latency monitoring</li>
    </ul>
  </section>

  <section>
    <h2>Consumer Framework</h2>
    <ul>
      <li>Declarative consumer configs</li>
      <li>Independent offset tracking per consumer group</li>
      <li>Future consumers: alerting, analytics dashboard, anomaly detection</li>
    </ul>
  </section>

  <section>
    <h2>Code Integration</h2>
    <pre><code>from assistant.bus_helpers import produce_event

# Fire-and-forget — returns immediately
produce_event(producer, "messages", "message.received", {'{'}"chat_id": "+16175551234",
    "contact": "Alice",
    "tier": "admin",
    "text": "what's the weather?",
{'}'})</code></pre>
  </section>

  <section>
    <h2>Related</h2>
    <ul>
      <li>
        <button class="text-link" on:click={() => navigateTo('analytics')}>Analytics</button>
        <span class="link-desc">- Dashboards and metrics powered by bus events</span>
      </li>
      <li>
        <button class="text-link" on:click={() => navigateTo('cli')}>CLI Reference</button>
        <span class="link-desc">- All commands including bus CLI</span>
      </li>
      <li>
        <button class="text-link" on:click={() => navigateTo('scheduling')}>Scheduling</button>
        <span class="link-desc">- Reminders and tasks that produce bus events</span>
      </li>
    </ul>
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
</style>
