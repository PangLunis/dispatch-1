<script>
  let { navigateTo } = $props();
</script>

<article class="page">
  <header class="page-header">
    <h1>Dispatch</h1>
    <p class="lead">
      A daemon that turns Claude into a full personal assistant with computer control,
      multi-channel messaging, and persistent memory.
    </p>
  </header>

  <div class="quick-actions">
    <button class="action-btn primary" onclick={() => navigateTo('getting-started')}>
      Get Started
    </button>
    <a href="https://github.com/svenflow/dispatch" class="action-btn" target="_blank" rel="noopener">
      View Source
    </a>
  </div>

  <section>
    <h2>Overview</h2>
    <p>
      Dispatch runs a background daemon that receives messages from iMessage and Signal,
      routes them to per-contact Claude SDK sessions, and gives Claude full control of the
      host machine. Each contact gets their own persistent session with appropriate access
      based on their tier.
    </p>

    <div class="feature-grid">
      <div class="feature">
        <div class="feature-title">Messaging</div>
        <div class="feature-desc">iMessage + Signal with real-time polling and group chat support</div>
      </div>
      <div class="feature">
        <div class="feature-title">Tiered Access</div>
        <div class="feature-desc">Admin, Partner, Family, Favorite, and Bot tiers with scoped permissions</div>
      </div>
      <div class="feature">
        <div class="feature-title">67+ Skills</div>
        <div class="feature-desc">Browser automation, smart home, iOS dev, payments, and more</div>
      </div>
      <div class="feature">
        <div class="feature-title">Persistent Memory</div>
        <div class="feature-desc">Full-text search across all conversations with semantic retrieval</div>
      </div>
      <div class="feature">
        <div class="feature-title">Auto-Recovery</div>
        <div class="feature-desc">Watchdog daemon with exponential backoff and crash notifications</div>
      </div>
      <div class="feature">
        <div class="feature-title">Mid-Turn Steering</div>
        <div class="feature-desc">New messages reach Claude between tool calls for real-time context</div>
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
        <div class="arch-box core">SDK Sessions</div>
      </div>
    </div>
    <p class="arch-caption">
      Messages flow through the manager daemon, get routed based on contact tier,
      and land in per-contact Claude sessions with full conversation persistence.
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

  .page-header h1 {
    margin-bottom: var(--space-3);
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

  /* Feature grid */
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

  .arch-caption {
    font-size: 12px;
    color: var(--text-tertiary);
    text-align: center;
    margin-top: var(--space-2);
  }

  section {
    margin-bottom: var(--space-8);
  }

  @media (max-width: 768px) {
    .feature-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
