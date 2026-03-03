<article class="page">
  <header class="page-header">
    <h1>Architecture</h1>
    <p class="lead">How Dispatch works.</p>
  </header>

  <section>
    <h2>System Diagram</h2>
    <div class="diagram">
      <div class="diagram-row">
        <div class="diagram-box">iMessage</div>
        <div class="diagram-box">Signal</div>
      </div>
      <div class="diagram-connector"></div>
      <div class="diagram-row">
        <div class="diagram-box primary">Manager Daemon</div>
      </div>
      <div class="diagram-connector"></div>
      <div class="diagram-row">
        <div class="diagram-box">Contact Lookup</div>
        <div class="diagram-box">Tier Check</div>
      </div>
      <div class="diagram-connector"></div>
      <div class="diagram-row">
        <div class="diagram-box primary">SDK Sessions</div>
      </div>
      <div class="diagram-connector"></div>
      <div class="diagram-row">
        <div class="diagram-box">Tools &amp; Skills</div>
      </div>
    </div>
  </section>

  <section>
    <h2>Components</h2>

    <div class="component">
      <div class="component-name">Manager Daemon</div>
      <div class="component-path">assistant/manager.py</div>
      <ul>
        <li>Polls Messages.app every 100ms</li>
        <li>Listens to Signal JSON-RPC socket</li>
        <li>Routes messages to sessions</li>
        <li>Handles session lifecycle</li>
      </ul>
    </div>

    <div class="component">
      <div class="component-name">SDK Backend</div>
      <div class="component-path">assistant/sdk_backend.py</div>
      <ul>
        <li>Creates per-contact sessions</li>
        <li>Configures tool access by tier</li>
        <li>Handles session resumption</li>
        <li>Manages idle reaping</li>
      </ul>
    </div>

    <div class="component">
      <div class="component-name">SDK Session</div>
      <div class="component-path">assistant/sdk_session.py</div>
      <ul>
        <li>Wraps Claude Agent SDK</li>
        <li>Manages async message queue</li>
        <li>Handles mid-turn steering</li>
        <li>Tracks health and activity</li>
      </ul>
    </div>
  </section>

  <section>
    <h2>Message Flow</h2>

    <h3>Inbound</h3>
    <ol>
      <li>Message arrives in Messages.app or Signal</li>
      <li>Manager detects via poll/socket</li>
      <li>Contact lookup → tier, name, phone</li>
      <li>Unknown tier → ignore</li>
      <li>Known tier → get/create session → inject message</li>
    </ol>

    <h3>Outbound</h3>
    <p>Claude explicitly calls send CLIs:</p>
    <pre><code>~/.claude/skills/sms-assistant/scripts/send-sms "+phone" "message"</code></pre>
    <p class="note">No auto-send. Claude controls when and how to respond.</p>
  </section>

  <section>
    <h2>Mid-Turn Steering</h2>
    <p>New messages can reach Claude between tool calls:</p>
    <div class="flow-diagram">
      <div class="flow-step">User sends message</div>
      <div class="flow-arrow"></div>
      <div class="flow-step">Added to session queue</div>
      <div class="flow-arrow"></div>
      <div class="flow-step">Claude checks queue between tool calls</div>
      <div class="flow-arrow"></div>
      <div class="flow-step">New messages included in context</div>
    </div>
  </section>

  <section>
    <h2>Health Monitoring</h2>

    <div class="health-tier">
      <div class="health-header">Tier 1: Fast Regex (60s)</div>
      <p>Low CPU. Checks for stuck patterns. Catches obvious failures.</p>
    </div>

    <div class="health-tier">
      <div class="health-header">Tier 2: LLM Analysis (5min)</div>
      <p>Haiku analyzes state. Catches subtle issues. Higher fidelity.</p>
    </div>
  </section>

  <section>
    <h2>Design Decisions</h2>
    <ol>
      <li><strong>No auto-send</strong> — Claude explicitly calls send CLIs</li>
      <li><strong>In-process sessions</strong> — No tmux/subprocess shells</li>
      <li><strong>Mid-turn steering</strong> — Async queues for injection</li>
      <li><strong>Two-tier health</strong> — Speed vs accuracy tradeoff</li>
      <li><strong>Skills as modules</strong> — Shared, version-controlled, symlinked</li>
      <li><strong>Opus only</strong> — Never Sonnet/Haiku for contacts</li>
    </ol>
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

  /* Diagram */
  .diagram {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: var(--space-6);
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
  }

  .diagram-row {
    display: flex;
    gap: var(--space-3);
    flex-wrap: wrap;
    justify-content: center;
  }

  .diagram-box {
    padding: var(--space-2) var(--space-4);
    border: 1px solid var(--border-default);
    background: var(--bg-surface);
    font-size: 12px;
    font-family: var(--font-mono);
    color: var(--text-secondary);
  }

  .diagram-box.primary {
    background: var(--text-primary);
    border-color: var(--text-primary);
    color: var(--bg-surface);
    font-weight: 500;
  }

  .diagram-connector {
    width: 1px;
    height: 16px;
    background: var(--border-strong);
    margin: var(--space-2) 0;
  }

  /* Components */
  .component {
    margin: var(--space-4) 0;
    padding: var(--space-4);
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
  }

  .component-name {
    font-weight: 600;
    font-size: 13px;
    color: var(--text-primary);
  }

  .component-path {
    font-size: 11px;
    font-family: var(--font-mono);
    color: var(--text-tertiary);
    margin-bottom: var(--space-3);
  }

  .component ul {
    margin: 0;
    padding-left: var(--space-4);
  }

  .component li {
    margin: var(--space-1) 0;
    font-size: 12px;
  }

  .note {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  /* Flow diagram */
  .flow-diagram {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-1);
    padding: var(--space-4);
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
  }

  .flow-step {
    font-size: 12px;
    color: var(--text-secondary);
    padding: var(--space-1) 0;
  }

  .flow-arrow {
    width: 8px;
    height: 1px;
    background: var(--border-strong);
    margin-left: var(--space-2);
    position: relative;
  }

  .flow-arrow::before {
    content: '';
    position: absolute;
    left: 0;
    top: -2px;
    height: 12px;
    width: 1px;
    background: var(--border-strong);
  }

  /* Health tiers */
  .health-tier {
    margin: var(--space-4) 0;
    padding: var(--space-4);
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
  }

  .health-header {
    font-weight: 600;
    font-size: 12px;
    color: var(--text-primary);
    margin-bottom: var(--space-2);
  }

  .health-tier p {
    font-size: 12px;
    color: var(--text-secondary);
    margin: 0;
  }
</style>
