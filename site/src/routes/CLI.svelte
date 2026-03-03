<article class="page">
  <header class="page-header">
    <h1>CLI Reference</h1>
    <p class="lead">Command-line interface for managing Dispatch.</p>
  </header>

  <nav class="toc">
    <div class="toc-title">Contents</div>
    <ul>
      <li><a href="#daemon">Daemon</a></li>
      <li><a href="#session">Sessions</a></li>
      <li><a href="#watchdog">Watchdog</a></li>
      <li><a href="#identity">Identity</a></li>
      <li><a href="#env">Environment</a></li>
    </ul>
  </nav>

  <section id="daemon">
    <h2>Daemon Management</h2>

    <div class="cmd-block">
      <div class="cmd-name">start</div>
      <div class="cmd-desc">Start the daemon (if not running)</div>
      <pre><code>./bin/claude-assistant start</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">stop</div>
      <div class="cmd-desc">Stop the daemon</div>
      <pre><code>./bin/claude-assistant stop</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">restart</div>
      <div class="cmd-desc">Restart via launchctl (always use this over stop+start)</div>
      <pre><code>./bin/claude-assistant restart</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">status</div>
      <div class="cmd-desc">Show daemon status and active sessions</div>
      <pre><code>./bin/claude-assistant status</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">logs</div>
      <div class="cmd-desc">Tail the daemon log</div>
      <pre><code>./bin/claude-assistant logs</code></pre>
    </div>
  </section>

  <section id="session">
    <h2>Session Management</h2>

    <div class="cmd-block">
      <div class="cmd-name">kill-session</div>
      <div class="cmd-desc">Kill a specific session</div>
      <pre><code>./bin/claude-assistant kill-session &lt;session&gt;</code></pre>
      <p class="cmd-note">Session: <code>imessage/_16175551234</code> or <code>+16175551234</code> or <code>"John Smith"</code></p>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">restart-session</div>
      <div class="cmd-desc">Restart a session with optional flags</div>
      <pre><code>./bin/claude-assistant restart-session &lt;session&gt;
./bin/claude-assistant restart-session &lt;session&gt; --no-compact
./bin/claude-assistant restart-session &lt;session&gt; --tier family</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">inject-prompt</div>
      <div class="cmd-desc">Inject a prompt into a session</div>
      <pre><code>./bin/claude-assistant inject-prompt &lt;session&gt; "prompt"
./bin/claude-assistant inject-prompt &lt;session&gt; --sms "message"
./bin/claude-assistant inject-prompt &lt;session&gt; --admin "command"</code></pre>
      <p class="cmd-note">Always use inject-prompt instead of direct injection</p>
    </div>
  </section>

  <section id="watchdog">
    <h2>Watchdog</h2>

    <div class="cmd-block">
      <div class="cmd-name">watchdog-install</div>
      <div class="cmd-desc">Install auto-recovery watchdog</div>
      <pre><code>./bin/watchdog-install</code></pre>
      <p class="cmd-note">Checks every 60s, auto-restarts with exponential backoff, SMS alerts</p>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">watchdog-uninstall / watchdog-status</div>
      <pre><code>./bin/watchdog-uninstall
./bin/watchdog-status</code></pre>
    </div>
  </section>

  <section id="identity">
    <h2>Identity</h2>

    <div class="cmd-block">
      <div class="cmd-name">identity</div>
      <div class="cmd-desc">Look up configuration values</div>
      <pre><code>./bin/identity owner.name      # John Smith
./bin/identity owner.phone     # +16175551234
./bin/identity assistant.name  # Sven</code></pre>
    </div>
  </section>

  <section id="env">
    <h2>Environment Variables</h2>
    <table>
      <thead>
        <tr>
          <th>Variable</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>DISPATCH_CONFIG</code></td>
          <td>Config file path</td>
        </tr>
        <tr>
          <td><code>DISPATCH_LOG_LEVEL</code></td>
          <td>DEBUG, INFO, WARNING, ERROR</td>
        </tr>
        <tr>
          <td><code>ANTHROPIC_API_KEY</code></td>
          <td>Claude API key</td>
        </tr>
      </tbody>
    </table>
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

  .toc {
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
    padding: var(--space-4);
    margin-bottom: var(--space-8);
  }

  .toc-title {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin-bottom: var(--space-3);
  }

  .toc ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-6);
  }

  .toc li {
    margin: 0;
  }

  .toc a {
    font-size: 12px;
  }

  section {
    margin-bottom: var(--space-8);
  }

  .cmd-block {
    margin: var(--space-6) 0;
  }

  .cmd-name {
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 500;
    color: var(--text-primary);
    margin-bottom: var(--space-1);
  }

  .cmd-desc {
    font-size: 12px;
    color: var(--text-secondary);
    margin-bottom: var(--space-2);
  }

  .cmd-block pre {
    margin: var(--space-2) 0;
  }

  .cmd-note {
    font-size: 11px;
    color: var(--text-tertiary);
    margin: var(--space-2) 0 0;
  }
</style>
