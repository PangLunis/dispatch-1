<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Getting Started</h1>
    <p class="lead">Set up Dispatch on your Mac.</p>
  </header>

  <nav class="toc">
    <div class="toc-title">Contents</div>
    <ul>
      <li><a href="#requirements">Requirements</a></li>
      <li><a href="#installation">Installation</a></li>
      <li><a href="#verify">Verification</a></li>
      <li><a href="#next-steps">Next steps</a></li>
    </ul>
  </nav>

  <section id="requirements">
    <h2>Requirements</h2>
    <ul>
      <li><strong>macOS</strong> with Messages.app and Contacts.app</li>
      <li><strong>Python 3.12+</strong> with <a href="https://github.com/astral-sh/uv">uv</a></li>
      <li><strong>Claude API key</strong> from Anthropic</li>
      <li><strong>Optional:</strong> signal-cli for Signal messaging</li>
      <li><strong>Optional:</strong> Chrome with extension for browser automation</li>
    </ul>
  </section>

  <section id="installation">
    <h2>Installation</h2>

    <h3>1. Clone and install</h3>
    <pre><code>git clone https://github.com/svenflow/dispatch.git ~/dispatch
cd ~/dispatch
uv sync</code></pre>

    <h3>2. Configure</h3>
    <pre><code>cp config.example.yaml config.local.yaml</code></pre>
    <p>Edit <code>config.local.yaml</code> with:</p>
    <ul>
      <li><code>assistant.name</code> - Your assistant's name</li>
      <li><code>contacts.owner_phone</code> - Your phone (admin tier)</li>
      <li><code>messaging.enabled_backends</code> - imessage, signal, etc.</li>
    </ul>

    <h3>3. Set up contact groups</h3>
    <p>Create these groups in Contacts.app:</p>
    <div class="group-list">
      <div class="group"><code>Claude Admin</code><span>Full access</span></div>
      <div class="group"><code>Claude Partner</code><span>Full access + warm tone</span></div>
      <div class="group"><code>Claude Family</code><span>Read-only</span></div>
      <div class="group"><code>Claude Favorites</code><span>Restricted tools</span></div>
      <div class="group"><code>Claude Bots</code><span>AI agents</span></div>
    </div>

    <h3>4. Start</h3>
    <pre><code>./bin/claude-assistant start</code></pre>

    <h3>5. Install watchdog (recommended)</h3>
    <pre><code>./bin/watchdog-install</code></pre>
  </section>

  <section id="verify">
    <h2>Verification</h2>
    <pre><code>./bin/claude-assistant status
./bin/claude-assistant logs</code></pre>
    <p>Send yourself a text. The daemon should respond.</p>
  </section>

  <section id="next-steps">
    <h2>Next steps</h2>
    <ul>
      <li>
        <button class="text-link" on:click={() => navigateTo('tiers')}>Contact Tiers</button>
        <span class="link-desc">- Access control system</span>
      </li>
      <li>
        <button class="text-link" on:click={() => navigateTo('skills')}>Skills</button>
        <span class="link-desc">- Built-in capabilities</span>
      </li>
      <li>
        <button class="text-link" on:click={() => navigateTo('cli')}>CLI Reference</button>
        <span class="link-desc">- Full command docs</span>
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

  .group-list {
    display: flex;
    flex-direction: column;
    gap: 1px;
    background: var(--border-default);
    border: 1px solid var(--border-default);
    margin: var(--space-4) 0;
  }

  .group {
    display: flex;
    justify-content: space-between;
    padding: var(--space-3) var(--space-4);
    background: var(--bg-elevated);
    font-size: 12px;
  }

  .group code {
    font-size: 12px;
  }

  .group span {
    color: var(--text-tertiary);
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

  .link-desc {
    color: var(--text-tertiary);
  }
</style>
