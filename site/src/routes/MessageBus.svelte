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
      <strong>8 topics</strong>: <code>messages</code>, <code>messages.dlq</code>,
      <code>sessions</code>, <code>system</code>, <code>reminders</code>,
      <code>tasks</code>, <code>facts</code>, and <code>imessage.ui</code>.
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
    <p>Common events shown. See <code>assistant/bus_helpers.py</code> for the full list (~67 event types).</p>
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
          <td><code>message.received</code>, <code>message.sent</code>, <code>message.failed</code>, <code>message.queued</code>, <code>message.delivered</code>, <code>message.ignored</code>, <code>message.produce_failed</code>, <code>message.processing_failed</code>, <code>message.replay_failed</code>, <code>reaction.received</code>, <code>reaction.ignored</code></td>
        </tr>
        <tr>
          <td><code>sessions</code></td>
          <td><code>session.created</code>, <code>session.restarted</code>, <code>session.killed</code>, <code>session.compacted</code>, <code>session.crashed</code>, <code>session.injected</code>, <code>session.idle_killed</code>, <code>session.prewarmed</code>, <code>session.tier_mismatch</code>, <code>session.prompt_built</code>, <code>session.receive_error</code>, <code>session.stop_failed</code>, <code>session.model_changed</code>, <code>permission.denied</code></td>
        </tr>
        <tr>
          <td><code>system</code></td>
          <td><code>daemon.started</code>, <code>daemon.stopped</code>, <code>daemon.crashed</code>, <code>daemon.recovered</code>, <code>health.check_completed</code>, <code>health.check_failed</code>, <code>health.fast_check_completed</code>, <code>health.deep_check_completed</code>, <code>health.service_restarted</code>, <code>health.service_spawned</code>, <code>consolidation.started</code>, <code>consolidation.completed</code>, <code>consolidation.failed</code>, <code>consumer.crashed</code>, <code>consumer.restart_failed</code>, <code>scan.started</code>, <code>scan.completed</code>, <code>scan.failed</code>, <code>healme.triggered</code>, <code>healme.completed</code>, <code>compaction.triggered</code>, <code>compaction.completed</code>, <code>reminder.fired</code>, <code>vision.analyzed</code>, <code>sdk.turn_complete</code>, <code>session.heartbeat</code>, <code>command.restart</code>, <code>signal.connection_state</code></td>
        </tr>
        <tr>
          <td><code>reminders</code></td>
          <td><code>reminder.due</code></td>
        </tr>
        <tr>
          <td><code>tasks</code></td>
          <td><code>task.requested</code>, <code>task.started</code>, <code>task.completed</code>, <code>task.failed</code>, <code>task.timeout</code>, <code>task.skipped</code></td>
        </tr>
        <tr>
          <td><code>messages.dlq</code></td>
          <td><code>message.dead_lettered</code> — dead letter queue for failed messages</td>
        </tr>
        <tr>
          <td><code>facts</code></td>
          <td><code>fact.created</code>, <code>fact.updated</code>, <code>fact.expired</code></td>
        </tr>
        <tr>
          <td><code>imessage.ui</code></td>
          <td><code>tapback</code>, <code>typing.start</code>, <code>typing.stop</code></td>
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

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('analytics')}>
        <span class="related-label">Analytics</span>
        <span class="related-desc">Dashboards and metrics powered by bus events</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('cli')}>
        <span class="related-label">CLI Reference</span>
        <span class="related-desc">All commands including bus CLI</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('scheduling')}>
        <span class="related-label">Scheduling & Tasks</span>
        <span class="related-desc">Reminders and tasks that produce bus events</span>
      </button>
    </div>
  </section>
</article>
