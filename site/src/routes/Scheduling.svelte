<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Scheduling & Tasks</h1>
    <p class="lead">Reminders, scheduled events, and ephemeral task execution.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      Dispatch has a built-in scheduling system that combines traditional reminders
      with a generalized event bus integration. Reminders can inject prompts into
      contact sessions (legacy mode) or produce arbitrary bus events (generalized mode).
      Ephemeral tasks run one-off Claude sessions for background work.
    </p>
  </section>

  <section>
    <h2>Reminders</h2>
    <p>
      Reminders are stored in <code>~/dispatch/state/reminders.json</code> (file-locked
      with <code>fcntl</code>) and polled every 5 seconds by the daemon.
    </p>

    <h3>Legacy Mode</h3>
    <p>
      Fires by producing a <code>reminder.due</code> event, then injects a prompt
      into a contact's session. Used for simple "remind me" flows tied to a specific contact.
    </p>

    <h3>Generalized Mode</h3>
    <p>
      Fires arbitrary bus events to any topic/type. This enables task scheduling,
      system automation, and anything else that can be triggered by a bus event.
    </p>

    <h3>Schedule Types</h3>
    <ul>
      <li><strong><code>once</code></strong> — One-shot reminder, fires once and is removed</li>
      <li><strong><code>cron</code></strong> — Recurring schedule with timezone support</li>
    </ul>

    <h3>CLI</h3>
    <pre><code># One-shot reminder
./bin/claude-assistant remind add --title "Check deploy" --in 30m --contact "+phone"

# Cron reminder
./bin/claude-assistant remind add --title "Nightly scan" --cron "0 2 * * *" --tz "America/New_York"

# List reminders
./bin/claude-assistant remind list

# Cancel
./bin/claude-assistant remind cancel &lt;id&gt;

# Preview cron schedule
./bin/claude-assistant remind preview "0 2 * * *" --next 5</code></pre>
  </section>

  <section>
    <h2>Ephemeral Tasks</h2>
    <p>
      One-off Claude sessions that run a task and exit. Tasks are requested via bus
      events and managed by the daemon's task runner.
    </p>

    <h3>Task Modes</h3>
    <ul>
      <li><strong>Script mode:</strong> Run a specific script or command</li>
      <li><strong>Agent mode:</strong> Spawn a Claude session with a prompt, runs autonomously</li>
    </ul>

    <h3>Task Lifecycle</h3>
    <p>
      <code>requested</code> &rarr; <code>started</code> &rarr; <code>completed</code> / <code>failed</code> / <code>timeout</code>
    </p>

    <h3>Bus Events</h3>
    <ul>
      <li><code>task.requested</code> — Task submitted for execution</li>
      <li><code>task.started</code> — Task runner picked up the task</li>
      <li><code>task.completed</code> — Task finished successfully</li>
      <li><code>task.failed</code> — Task errored out</li>
      <li><code>task.timeout</code> — Task exceeded time limit</li>
      <li><code>task.skipped</code> — Task was skipped (e.g., duplicate or precondition unmet)</li>
    </ul>
  </section>

  <section>
    <h2>Nightly Tasks</h2>
    <p>
      Scheduled via cron reminders that produce <code>task.requested</code> events.
      All nightly tasks run at 2am ET.
    </p>
    <ul>
      <li><strong>Consolidation:</strong> Syncs contact memories, cleans up stale state</li>
      <li><strong>Skillify:</strong> Analyzes transcripts to propose new skills and improvements</li>
      <li><strong>Bug-finder:</strong> Scans codebase for bugs using parallel discovery+refinement subagents</li>
    </ul>
  </section>

  <section>
    <h2>Reminder Fields</h2>
    <table>
      <thead>
        <tr>
          <th>Field</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>id</code></td>
          <td>8-char UUID</td>
        </tr>
        <tr>
          <td><code>title</code></td>
          <td>Human description</td>
        </tr>
        <tr>
          <td><code>schedule</code></td>
          <td><code>{'{'}"type": "once"/"cron", "value": "...", "timezone": "..."{'}'}</code></td>
        </tr>
        <tr>
          <td><code>next_fire</code></td>
          <td>ISO datetime (UTC)</td>
        </tr>
        <tr>
          <td><code>contact</code> + <code>target</code></td>
          <td>Legacy mode: who to inject, where (fg/bg/spawn)</td>
        </tr>
        <tr>
          <td><code>event</code></td>
          <td>Generalized mode: bus event template</td>
        </tr>
        <tr>
          <td><code>fired_count</code></td>
          <td>Times fired</td>
        </tr>
        <tr>
          <td><code>last_error</code></td>
          <td>Last failure message</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section class="related-pages">
    <h2>Related</h2>
    <ul>
      <li>
        <button class="text-link" on:click={() => navigateTo('message-bus')}>Message Bus</button>
        <span class="link-desc">- Event taxonomy and bus integration</span>
      </li>
      <li>
        <button class="text-link" on:click={() => navigateTo('health')}>Health & Healing</button>
        <span class="link-desc">- Monitoring and automatic recovery</span>
      </li>
      <li>
        <button class="text-link" on:click={() => navigateTo('cli')}>CLI Reference</button>
        <span class="link-desc">- Full command reference</span>
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
