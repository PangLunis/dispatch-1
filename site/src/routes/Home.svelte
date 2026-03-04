<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
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
    <button class="action-btn" on:click={() => navigateTo('philosophy')}>
      Philosophy
    </button>
    <a href="https://github.com/svenflow/dispatch" class="action-btn" target="_blank" rel="noopener">
      GitHub
    </a>
  </div>

  <section>
    <h2>The Core Idea</h2>
    <p>
      Dispatch creates an assistant that exists as its own person—with its own accounts,
      its own phone number, its own presence. People text the assistant directly.
      It doesn't pretend to be you or act on your behalf.
    </p>

    <div class="concept-grid">
      <div class="concept">
        <div class="concept-title">Own Identity</div>
        <div class="concept-desc">
          Dedicated iCloud account, Gmail, Chrome profile. The assistant's accounts
          are completely separate from yours.
        </div>
      </div>
      <div class="concept">
        <div class="concept-title">Own Phone Number</div>
        <div class="concept-desc">
          People message the assistant's number via iMessage or Signal.
          Not forwarding your messages—direct communication.
        </div>
      </div>
      <div class="concept">
        <div class="concept-title">Own Machine</div>
        <div class="concept-desc">
          A dedicated Mac (Mini recommended) running 24/7 with Full Disk Access
          and all the permissions it needs.
        </div>
      </div>
      <div class="concept">
        <div class="concept-title">Own Personality</div>
        <div class="concept-desc">
          Defined by SOUL.md—casual tone, genuine opinions, family member energy.
          Customizable to match your household.
        </div>
      </div>
    </div>
  </section>

  <section>
    <h2>What It Does</h2>
    <div class="feature-grid">
      <div class="feature">
        <div class="feature-title">Messaging</div>
        <div class="feature-desc">iMessage + Signal with real-time polling and group chat support</div>
      </div>
      <div class="feature">
        <div class="feature-title">Tiered Access</div>
        <div class="feature-desc">Admin, Partner, Family, Favorite tiers with scoped permissions</div>
      </div>
      <div class="feature">
        <div class="feature-title">67+ Skills</div>
        <div class="feature-desc">Browser automation, smart home, iOS dev, payments, and more</div>
      </div>
      <div class="feature">
        <div class="feature-title">Persistent Memory</div>
        <div class="feature-desc">Remembers conversations, preferences, and context across sessions</div>
      </div>
      <div class="feature">
        <div class="feature-title">Computer Control</div>
        <div class="feature-desc">Full access to the Mac—files, apps, browser, terminal</div>
      </div>
      <div class="feature">
        <div class="feature-title">Auto-Recovery</div>
        <div class="feature-desc">Watchdog daemon with crash recovery and health monitoring</div>
      </div>
    </div>
  </section>

  <section>
    <h2>Requirements</h2>
    <ul class="req-list">
      <li><strong>macOS</strong> — Uses Messages.app, Contacts.app, and macOS permissions</li>
      <li><strong>Dedicated Mac</strong> — Mac Mini recommended, runs 24/7</li>
      <li><strong>Separate iCloud account</strong> — The assistant's own Apple ID</li>
      <li><strong>Claude API access</strong> — Anthropic API key</li>
    </ul>
    <p class="note">
      This is not a cloud service. It's software you run on your own hardware,
      with your own API key, under your control.
    </p>
  </section>

  <section>
    <h2>How It Works</h2>
    <div class="architecture">
      <div class="arch-row">
        <div class="arch-box source">iMessage</div>
        <div class="arch-box source">Signal</div>
      </div>
      <div class="arch-arrow"></div>
      <div class="arch-row">
        <div class="arch-box core">Manager Daemon</div>
      </div>
      <div class="arch-arrow"></div>
      <div class="arch-row">
        <div class="arch-box">Contact Lookup</div>
        <div class="arch-box">Tier Check</div>
      </div>
      <div class="arch-arrow"></div>
      <div class="arch-row">
        <div class="arch-box core">Claude Sessions</div>
      </div>
      <div class="arch-arrow"></div>
      <div class="arch-row">
        <div class="arch-box">Skills</div>
        <div class="arch-box">Memory</div>
        <div class="arch-box">Tools</div>
      </div>
    </div>
  </section>

  <section>
    <h2>Quick Start</h2>
    <pre><code>git clone https://github.com/svenflow/dispatch.git ~/dispatch
cd ~/dispatch
uv sync
cp config.example.yaml config.local.yaml
./bin/claude-assistant start</code></pre>
    <p class="note">
      Full setup requires configuring macOS permissions, creating the assistant's
      iCloud account, and setting up Contacts groups. See the
      <button class="text-link" on:click={() => navigateTo('getting-started')}>Getting Started</button>
      guide.
    </p>
  </section>
</article>

<style>
  .page {
    max-width: var(--content-max-width);
  }

  .page-header {
    margin-bottom: var(--space-8);
  }

  .lead {
    font-size: 15px;
    color: var(--text-secondary);
    line-height: 1.6;
    margin: 0;
    max-width: 560px;
  }

  /* Actions */
  .quick-actions {
    display: flex;
    gap: var(--space-3);
    margin-bottom: var(--space-12);
    flex-wrap: wrap;
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

  /* Concept grid - larger cards for the core ideas */
  .concept-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1px;
    background: var(--border-default);
    border: 1px solid var(--border-default);
    margin: var(--space-6) 0;
  }

  .concept {
    padding: var(--space-6);
    background: var(--bg-elevated);
  }

  .concept-title {
    font-weight: 600;
    font-size: 14px;
    color: var(--text-primary);
    margin-bottom: var(--space-2);
  }

  .concept-desc {
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.6;
  }

  /* Feature grid - smaller cards */
  .feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 1px;
    background: var(--border-default);
    border: 1px solid var(--border-default);
    margin: var(--space-6) 0;
  }

  .feature {
    padding: var(--space-4);
    background: var(--bg-elevated);
  }

  .feature-title {
    font-weight: 600;
    font-size: 13px;
    color: var(--text-primary);
    margin-bottom: var(--space-1);
  }

  .feature-desc {
    font-size: 12px;
    color: var(--text-secondary);
    line-height: 1.5;
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

  /* Architecture diagram */
  .architecture {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-6);
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
    margin: var(--space-4) 0;
  }

  .arch-row {
    display: flex;
    gap: var(--space-3);
    flex-wrap: wrap;
    justify-content: center;
  }

  .arch-box {
    padding: var(--space-2) var(--space-4);
    border: 1px solid var(--border-default);
    background: var(--bg-surface);
    font-size: 12px;
    font-family: var(--font-mono);
    color: var(--text-secondary);
  }

  .arch-box.source {
    border-color: var(--border-strong);
  }

  .arch-box.core {
    background: var(--text-primary);
    border-color: var(--text-primary);
    color: var(--bg-surface);
    font-weight: 500;
  }

  .arch-arrow {
    width: 1px;
    height: 16px;
    background: var(--border-strong);
  }

  section {
    margin-bottom: var(--space-8);
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
    .concept-grid {
      grid-template-columns: 1fr;
    }

    .feature-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
