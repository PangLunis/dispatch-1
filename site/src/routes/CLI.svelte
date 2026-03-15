<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>CLI Reference</h1>
    <p class="lead">Command-line interface for managing Dispatch.</p>
  </header>

  <nav class="toc">
    <div class="toc-title">Contents</div>
    <ul>
      <li><button class="text-link" on:click={() => { document.getElementById('daemon')?.scrollIntoView({ behavior: 'smooth' }) }}>Daemon</button></li>
      <li><button class="text-link" on:click={() => { document.getElementById('session')?.scrollIntoView({ behavior: 'smooth' }) }}>Sessions</button></li>
      <li><button class="text-link" on:click={() => { document.getElementById('monitoring')?.scrollIntoView({ behavior: 'smooth' }) }}>Monitoring</button></li>
      <li><button class="text-link" on:click={() => { document.getElementById('watchdog')?.scrollIntoView({ behavior: 'smooth' }) }}>Watchdog</button></li>
      <li><button class="text-link" on:click={() => { document.getElementById('identity')?.scrollIntoView({ behavior: 'smooth' }) }}>Identity</button></li>
      <li><button class="text-link" on:click={() => { document.getElementById('messaging')?.scrollIntoView({ behavior: 'smooth' }) }}>Messaging</button></li>
      <li><button class="text-link" on:click={() => { document.getElementById('scheduling')?.scrollIntoView({ behavior: 'smooth' }) }}>Scheduling</button></li>
      <li><button class="text-link" on:click={() => { document.getElementById('bus')?.scrollIntoView({ behavior: 'smooth' }) }}>Event Bus</button></li>
      <li><button class="text-link" on:click={() => { document.getElementById('identifiers')?.scrollIntoView({ behavior: 'smooth' }) }}>Session Identifiers</button></li>
      <li><button class="text-link" on:click={() => { document.getElementById('env')?.scrollIntoView({ behavior: 'smooth' }) }}>Environment</button></li>
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
      <p class="cmd-note">Critical: Always use restart, not stop+start. Uses launchctl kickstart for clean environment.</p>
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
    </div>

    <div class="cmd-block">
      <div class="cmd-name">kill-sessions</div>
      <div class="cmd-desc">Kill all active sessions at once</div>
      <pre><code>./bin/claude-assistant kill-sessions</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">restart-session</div>
      <div class="cmd-desc">Restart a session with optional flags</div>
      <pre><code>./bin/claude-assistant restart-session &lt;session&gt;
./bin/claude-assistant restart-session &lt;session&gt; --clean
./bin/claude-assistant restart-session &lt;session&gt; --tier family</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">restart-sessions</div>
      <div class="cmd-desc">Restart all active sessions</div>
      <pre><code>./bin/claude-assistant restart-sessions</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">compact-session</div>
      <div class="cmd-desc">Generate session summary without restarting</div>
      <pre><code>./bin/claude-assistant compact-session &lt;session&gt;</code></pre>
      <p class="cmd-note">Useful for reducing context size mid-conversation</p>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">set-model</div>
      <div class="cmd-desc">Change model for a session mid-conversation</div>
      <pre><code>./bin/claude-assistant set-model &lt;session&gt; opus
./bin/claude-assistant set-model &lt;session&gt; sonnet
./bin/claude-assistant set-model &lt;session&gt; haiku</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">inject-prompt</div>
      <div class="cmd-desc">Inject a prompt into a session</div>
      <pre><code>./bin/claude-assistant inject-prompt &lt;session&gt; "prompt"
./bin/claude-assistant inject-prompt &lt;session&gt; --sms "message"
./bin/claude-assistant inject-prompt &lt;session&gt; --admin "command"
./bin/claude-assistant inject-prompt &lt;session&gt; --bg "background task"</code></pre>
      <p class="cmd-note">Always use inject-prompt instead of direct injection. Auto-creates sessions for unknown contacts.</p>
    </div>
  </section>

  <section id="monitoring">
    <h2>Monitoring</h2>

    <div class="cmd-block">
      <div class="cmd-name">attach</div>
      <div class="cmd-desc">Tail a specific session's log output</div>
      <pre><code>./bin/claude-assistant attach &lt;session&gt;</code></pre>
      <p class="cmd-note">Watch real-time output from a single session</p>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">monitor</div>
      <div class="cmd-desc">Tail ALL session logs simultaneously</div>
      <pre><code>./bin/claude-assistant monitor</code></pre>
      <p class="cmd-note">Color-coded output from all active sessions</p>
    </div>
  </section>

  <section id="watchdog">
    <h2>Watchdog</h2>

    <div class="cmd-block">
      <div class="cmd-name">watchdog-install</div>
      <div class="cmd-desc">Install auto-recovery watchdog</div>
      <pre><code>./bin/watchdog-install</code></pre>
      <p class="cmd-note">Checks every 60s, auto-restarts with exponential backoff (60s, 120s, 240s...), SMS alerts on failure</p>
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
      <div class="cmd-desc">Look up configuration values from config.local.yaml</div>
      <pre><code>./bin/identity owner.name      # Your Name
./bin/identity owner.phone     # +15555551234
./bin/identity assistant.name  # Dispatch</code></pre>
      <p class="cmd-note">Used by <code>!`identity key`</code> dynamic prompts in CLAUDE.md files</p>
    </div>
  </section>

  <section id="messaging">
    <h2>Messaging</h2>

    <div class="cmd-block">
      <div class="cmd-name">reply</div>
      <div class="cmd-desc">Universal reply CLI (auto-detects backend and chat_id from cwd)</div>
      <pre><code>~/.claude/skills/sms-assistant/scripts/reply "message"</code></pre>
      <p class="cmd-note">Works from any transcript directory, routes to correct send command</p>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">send-sms</div>
      <div class="cmd-desc">Send iMessage to individual or group</div>
      <pre><code>~/.claude/skills/sms-assistant/scripts/send-sms "+15555551234" "message"
~/.claude/skills/sms-assistant/scripts/send-sms "hex-group-id" "message"</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">send-signal</div>
      <div class="cmd-desc">Send Signal message</div>
      <pre><code>~/.claude/skills/signal/scripts/send-signal "+15555551234" "message"
~/.claude/skills/signal/scripts/send-signal-group "base64-group-id" "message"</code></pre>
    </div>
  </section>

  <section id="scheduling">
    <h2>Scheduling</h2>

    <div class="cmd-block">
      <div class="cmd-name">remind add</div>
      <div class="cmd-desc">Create a reminder (one-shot or recurring)</div>
      <pre><code>./bin/claude-assistant remind add --title "Check deploy" --in 30m --contact "+phone"
./bin/claude-assistant remind add --title "Nightly scan" --cron "0 2 * * *" --tz "America/New_York"</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">remind list / cancel / preview</div>
      <pre><code>./bin/claude-assistant remind list
./bin/claude-assistant remind cancel &lt;id&gt;
./bin/claude-assistant remind preview "0 2 * * *" --next 5</code></pre>
    </div>
  </section>

  <section id="bus">
    <h2>Event Bus</h2>

    <div class="cmd-block">
      <div class="cmd-name">bus stats</div>
      <div class="cmd-desc">Show event counts by type and time range</div>
      <pre><code>./bin/bus stats</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">bus tail</div>
      <div class="cmd-desc">Tail recent events (like kafka-console-consumer)</div>
      <pre><code>./bin/bus tail
./bin/bus tail --type message.received
./bin/bus tail --type session.compacted --limit 10</code></pre>
    </div>

    <div class="cmd-block">
      <div class="cmd-name">bus export</div>
      <div class="cmd-desc">Export events to JSON for analysis</div>
      <pre><code>./bin/bus export --since 24h > events.json
./bin/bus export --type sdk.tool_call --since 1h</code></pre>
    </div>
  </section>

  <section id="identifiers">
    <h2>Session Identifiers</h2>
    <p>All session commands accept any of these identifier formats:</p>

    <table>
      <thead>
        <tr>
          <th>Format</th>
          <th>Example</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>session_name</code></td>
          <td><code>imessage/_15555551234</code></td>
          <td>Full session name with backend prefix</td>
        </tr>
        <tr>
          <td><code>chat_id</code></td>
          <td><code>+15555551234</code></td>
          <td>Phone number or group UUID</td>
        </tr>
        <tr>
          <td><code>contact_name</code></td>
          <td><code>"John Smith"</code></td>
          <td>Contact name (quotes required if spaces)</td>
        </tr>
      </tbody>
    </table>

    <div class="key-concepts">
      <h3>Key Concepts</h3>
      <dl>
        <dt><code>chat_id</code></dt>
        <dd>Canonical identifier. Phone number (<code>+15555551234</code>) for individuals, hex UUID for groups.</dd>

        <dt><code>sanitized_chat_id</code></dt>
        <dd>Chat ID with <code>+</code> replaced by <code>_</code>. Used in directory paths: <code>~/transcripts/imessage/_15555551234/</code></dd>

        <dt><code>session_id</code></dt>
        <dd>Resume token for Claude SDK. Enables persistent conversations across restarts.</dd>
      </dl>
    </div>
  </section>

  <section id="env">
    <h2>Environment Variables</h2>
    <p>See <button class="text-link" on:click={() => navigateTo('configuration')}>Configuration</button> for the full environment variables reference.</p>
  </section>

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('configuration')}>
        <span class="related-label">Configuration</span>
        <span class="related-desc">Config file and env vars</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('architecture')}>
        <span class="related-label">Architecture</span>
        <span class="related-desc">System design and message flow</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('messaging')}>
        <span class="related-label">Messaging</span>
        <span class="related-desc">Send commands and backends</span>
      </button>
    </div>
  </section>
</article>

<style>
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

  .key-concepts {
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
    padding: var(--space-4);
    margin-top: var(--space-6);
  }

  .key-concepts h3 {
    font-size: 12px;
    font-weight: 600;
    margin-bottom: var(--space-3);
  }

  .key-concepts dl {
    margin: 0;
  }

  .key-concepts dt {
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 500;
    color: var(--text-primary);
    margin-top: var(--space-3);
  }

  .key-concepts dt:first-child {
    margin-top: 0;
  }

  .key-concepts dd {
    font-size: 12px;
    color: var(--text-secondary);
    margin: var(--space-1) 0 0 0;
  }
</style>
