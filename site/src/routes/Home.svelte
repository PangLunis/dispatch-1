<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <div class="hero-badge">Personal Infrastructure</div>
    <h1>Dispatch</h1>
    <p class="lead">
      Turn a Mac into an always-on AI assistant with its own identity—its own iCloud,
      Gmail, and phone number. Not acting as you. A separate entity in your household.
    </p>
  </header>

  <div class="quick-actions">
    <button class="action-btn primary" on:click={() => navigateTo('setup')}>
      Setup Guide
    </button>
    <button class="action-btn ghost" on:click={() => navigateTo('philosophy')}>
      Philosophy
    </button>
    <a href="https://github.com/svenflow/dispatch" class="action-btn text-only" target="_blank" rel="noopener">
      View on GitHub →
    </a>
  </div>

  <section class="section-tight">
    <h2>The Core Idea</h2>
    <p>
      Dispatch creates an assistant that exists as its own person—with its own accounts,
      its own phone number, its own presence. People text the assistant directly.
      It doesn't pretend to be you or act on your behalf.
    </p>
  </section>

  <!-- Break the card grid - asymmetric layout with varied sizes -->
  <div class="concepts">
    <div class="concept concept-hero">
      <div class="concept-label">Identity</div>
      <div class="concept-title">Own Everything</div>
      <div class="concept-desc">
        Dedicated iCloud account, Gmail, Chrome profile, phone number.
        The assistant's accounts are completely separate from yours.
        People message it directly via iMessage or Signal.
      </div>
    </div>
    <div class="concept-stack">
      <div class="concept concept-small">
        <div class="concept-label">Hardware</div>
        <div class="concept-title">Own Machine</div>
        <div class="concept-desc">
          Mac Mini running 24/7 with Full Disk Access
        </div>
      </div>
      <div class="concept concept-small">
        <div class="concept-label">Personality</div>
        <div class="concept-title">SOUL.md</div>
        <div class="concept-desc">
          Casual tone, genuine opinions, family member energy
        </div>
      </div>
    </div>
  </div>

  <section class="section-generous">
    <h2>What It Does</h2>
    <!-- Replace card grid with inline list - more distinctive -->
    <div class="feature-list">
      <div class="feature-item">
        <span class="feature-name">Messaging</span>
        <span class="feature-detail">iMessage + Signal, real-time polling, group chats</span>
      </div>
      <div class="feature-item">
        <span class="feature-name">Tiered Access</span>
        <span class="feature-detail">Admin, Partner, Family, Favorite — scoped permissions</span>
      </div>
      <div class="feature-item">
        <span class="feature-name">67+ Skills</span>
        <span class="feature-detail">Browser automation, smart home, iOS dev, payments</span>
      </div>
      <div class="feature-item">
        <span class="feature-name">Memory</span>
        <span class="feature-detail">Persistent context across sessions</span>
      </div>
      <div class="feature-item">
        <span class="feature-name">Computer Control</span>
        <span class="feature-detail">Full Mac access — files, apps, browser, terminal</span>
      </div>
      <div class="feature-item">
        <span class="feature-name">Auto-Recovery</span>
        <span class="feature-detail">Watchdog daemon, crash recovery, health monitoring</span>
      </div>
    </div>
  </section>

  <section>
    <h2>How It Works</h2>
    <!-- Signature element: ASCII-style flow diagram -->
    <div class="flow-diagram">
      <pre class="flow-ascii"><code>┌─────────────┐   ┌─────────────┐
│  iMessage   │   │   Signal    │
└──────┬──────┘   └──────┬──────┘
       │                 │
       └────────┬────────┘
                ▼
┌───────────────────────────────┐
│       <span class="flow-highlight">Manager Daemon</span>          │
│  ┌─────────┐  ┌────────────┐  │
│  │Contacts │  │ Tier Check │  │
│  └─────────┘  └────────────┘  │
└───────────────┬───────────────┘
                ▼
┌───────────────────────────────┐
│       <span class="flow-highlight">Claude Sessions</span>         │
│                               │
│  Skills · Memory · Tools      │
└───────────────────────────────┘</code></pre>
    </div>
  </section>

  <section class="section-tight">
    <h2>Requirements</h2>
    <ul class="req-list">
      <li><strong>macOS</strong> — Messages.app, Contacts.app, system permissions</li>
      <li><strong>Dedicated Mac</strong> — Mac Mini recommended, runs 24/7</li>
      <li><strong>Separate iCloud</strong> — The assistant's own Apple ID</li>
      <li><strong>Claude API</strong> — Anthropic API key</li>
    </ul>
    <p class="note">
      Not a cloud service. Software on your hardware, your API key, your control.
    </p>
  </section>

  <section class="section-generous">
    <h2>Quick Start</h2>
    <pre><code>git clone https://github.com/svenflow/dispatch.git ~/dispatch
cd ~/dispatch
uv sync
cp config.example.yaml config.local.yaml
./bin/claude-assistant start</code></pre>
    <p class="note">
      Full setup requires macOS permissions, iCloud account, and Contacts groups.
      <button class="text-link" on:click={() => navigateTo('getting-started')}>Getting Started →</button>
    </p>
  </section>
</article>

<style>
  .page {
    max-width: var(--content-max-width);
  }

  .page-header {
    margin-bottom: var(--space-6);
  }

  /* Signature element: hero badge */
  .hero-badge {
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--accent);
    margin-bottom: var(--space-3);
    padding: var(--space-1) 0;
    border-bottom: 2px solid var(--accent);
  }

  .lead {
    font-size: 15px;
    color: var(--text-secondary);
    line-height: 1.6;
    margin: 0;
    max-width: 560px;
  }

  /* Button hierarchy - clear visual distinction */
  .quick-actions {
    display: flex;
    gap: var(--space-3);
    margin-bottom: var(--space-12);
    flex-wrap: wrap;
    align-items: center;
  }

  .action-btn {
    display: inline-flex;
    align-items: center;
    padding: var(--space-2) var(--space-4);
    font-size: 13px;
    font-weight: 500;
    font-family: inherit;
    border: 1px solid var(--border-default);
    background: var(--bg-elevated);
    color: var(--text-primary);
    cursor: pointer;
    transition: all var(--transition-fast);
    text-decoration: none;
  }

  .action-btn:hover {
    border-color: var(--border-strong);
    color: var(--text-primary);
  }

  .action-btn.primary {
    background: var(--text-primary);
    border-color: var(--text-primary);
    color: var(--bg-surface);
  }

  .action-btn.primary:hover {
    background: var(--text-secondary);
    border-color: var(--text-secondary);
  }

  .action-btn.ghost {
    background: transparent;
    border-color: var(--border-subtle);
    color: var(--text-secondary);
  }

  .action-btn.ghost:hover {
    border-color: var(--border-default);
    color: var(--text-primary);
  }

  .action-btn.text-only {
    background: none;
    border: none;
    padding: var(--space-2) 0;
    color: var(--text-tertiary);
    font-weight: 400;
  }

  .action-btn.text-only:hover {
    color: var(--accent);
  }

  /* Visual rhythm - varied section spacing */
  section {
    margin-bottom: var(--space-8);
  }

  .section-tight {
    margin-bottom: var(--space-6);
  }

  .section-generous {
    margin-bottom: var(--space-12);
  }

  /* Asymmetric concept layout - NOT a card grid */
  .concepts {
    display: grid;
    grid-template-columns: 1.5fr 1fr;
    gap: var(--space-4);
    margin: var(--space-8) 0 var(--space-12);
  }

  .concept {
    padding: var(--space-6);
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
  }

  .concept-hero {
    display: flex;
    flex-direction: column;
  }

  .concept-stack {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .concept-small {
    padding: var(--space-4);
  }

  .concept-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin-bottom: var(--space-2);
  }

  .concept-title {
    font-weight: 600;
    font-size: 16px;
    color: var(--text-primary);
    margin-bottom: var(--space-2);
  }

  .concept-small .concept-title {
    font-size: 14px;
  }

  .concept-desc {
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.6;
  }

  .concept-small .concept-desc {
    font-size: 12px;
    line-height: 1.5;
  }

  /* Feature list - NOT cards */
  .feature-list {
    display: flex;
    flex-direction: column;
    gap: 0;
    border-top: 1px solid var(--border-default);
    margin: var(--space-4) 0;
  }

  .feature-item {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--border-subtle);
    gap: var(--space-4);
  }

  .feature-name {
    font-weight: 600;
    font-size: 13px;
    color: var(--text-primary);
    flex-shrink: 0;
  }

  .feature-detail {
    font-size: 12px;
    color: var(--text-tertiary);
    text-align: right;
  }

  /* Signature element: ASCII flow diagram */
  .flow-diagram {
    margin: var(--space-4) 0;
    overflow-x: auto;
  }

  .flow-ascii {
    background: var(--code-bg);
    color: var(--code-text);
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.4;
    padding: var(--space-6);
    margin: 0;
    border: 1px solid var(--code-border);
    white-space: pre;
    overflow-x: auto;
  }

  .flow-ascii code {
    background: none;
    border: none;
    padding: 0;
    font-size: inherit;
  }

  .flow-highlight {
    color: var(--accent);
    font-weight: 500;
  }

  /* Requirements list */
  .req-list {
    list-style: none;
    padding: 0;
    margin: var(--space-4) 0;
  }

  .req-list li {
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--border-subtle);
    font-size: 13px;
  }

  .req-list li:last-child {
    border-bottom: none;
  }

  .note {
    font-size: 12px;
    color: var(--text-tertiary);
    margin-top: var(--space-4);
  }

  .text-link {
    background: none;
    border: none;
    padding: 0;
    color: var(--accent);
    font: inherit;
    cursor: pointer;
  }

  .text-link:hover {
    color: var(--accent-hover);
  }

  @media (max-width: 768px) {
    .concepts {
      grid-template-columns: 1fr;
    }

    .concept-stack {
      flex-direction: column;
    }

    .feature-item {
      flex-direction: column;
      gap: var(--space-1);
      align-items: flex-start;
    }

    .feature-detail {
      text-align: left;
    }
  }
</style>
