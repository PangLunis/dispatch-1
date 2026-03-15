<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Messaging</h1>
    <p class="lead">iMessage and Signal integration with real-time polling and group chat support.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      Dispatch receives messages from two backends — iMessage (polls chat.db every 100ms)
      and Signal (JSON-RPC socket via signal-cli daemon). Messages are routed to per-contact
      Claude sessions based on tier.
    </p>
  </section>

  <section>
    <h2>iMessage</h2>
    <p>
      Polls Messages.app's <code>chat.db</code> SQLite database every 100ms for new messages.
      Supports both individual and group chats. Images are analyzed via Gemini Vision with
      conversation context. Sending is handled via osascript through Messages.app.
    </p>

    <h3>CLI Commands</h3>
    <pre><code># Send to individual
~/.claude/skills/sms-assistant/scripts/send-sms "+phone" "message"

# Send to group
~/.claude/skills/sms-assistant/scripts/send-sms "hex-group-id" "message"

# Read recent messages
~/.claude/skills/sms-assistant/scripts/read-sms --chat "+phone" --limit 20</code></pre>
  </section>

  <section>
    <h2>Signal</h2>
    <p>
      Runs via signal-cli daemon with JSON-RPC socket at <code>/tmp/signal-cli.sock</code>.
      Must use <code>--receive-mode on-connection</code> for push notifications.
      Health-checked every 5 minutes with auto-restart on failure.
    </p>

    <h3>CLI Commands</h3>
    <pre><code># Send individual
~/.claude/skills/signal/scripts/send-signal "+phone" "message"

# Send to group
~/.claude/skills/signal/scripts/send-signal-group "base64-group-id" "message"</code></pre>
  </section>

  <section>
    <h2>Universal Reply CLI</h2>
    <p>
      A single command that auto-detects the backend and chat_id from the current working directory.
      Works from any transcript directory and routes to the correct send command (send-sms,
      send-signal, or send-signal-group).
    </p>
    <pre><code>~/.claude/skills/sms-assistant/scripts/reply "message"</code></pre>
  </section>

  <section>
    <h2>Image Handling</h2>
    <ul>
      <li>Incoming images extracted from chat.db (iMessage) or signal-cli attachments</li>
      <li>Analyzed via Gemini Vision API with conversation context for understanding</li>
      <li>Sessions can send images back using <code>--image</code> flag on send CLIs</li>
    </ul>
  </section>

  <section>
    <h2>Message Flow</h2>
    <table>
      <thead>
        <tr>
          <th>Step</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>1</td>
          <td>Message arrives via chat.db or signal socket</td>
        </tr>
        <tr>
          <td>2</td>
          <td>Manager detects new message (100ms poll / socket push)</td>
        </tr>
        <tr>
          <td>3</td>
          <td>Contact lookup and tier determination</td>
        </tr>
        <tr>
          <td>4</td>
          <td>Message wrapped: <code>---SMS FROM ContactName (tier)---</code></td>
        </tr>
        <tr>
          <td>5</td>
          <td>Injected into contact's SDK session via inject-prompt</td>
        </tr>
        <tr>
          <td>6</td>
          <td>Claude processes and calls reply CLI to respond</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section>
    <h2>Mid-Turn Steering</h2>
    <p>
      New messages can reach Claude between tool calls. The system uses async queue injection —
      messages are queued and delivered at the next tool call boundary. This enables real-time
      conversation even while Claude is working on a task.
    </p>
  </section>

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('architecture')}>
        <span class="related-label">Architecture</span>
        <span class="related-desc">Message flow</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('tiers')}>
        <span class="related-label">Contact Tiers</span>
        <span class="related-desc">Per-tier handling</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('cli')}>
        <span class="related-label">CLI Reference</span>
        <span class="related-desc">Send commands</span>
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
