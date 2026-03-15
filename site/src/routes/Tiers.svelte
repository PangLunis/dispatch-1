<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Contact Tiers</h1>
    <p class="lead">Access control via macOS Contacts groups.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      Dispatch uses a tier system to control tool access per contact.
      Add contacts to Contacts.app groups to assign their tier.
    </p>
  </section>

  <section>
    <h2>Tier Comparison</h2>
    <table>
      <thead>
        <tr>
          <th>Tier</th>
          <th>Group</th>
          <th>Access</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Admin</strong></td>
          <td><code>Claude Admin</code></td>
          <td>Full computer control, all tools</td>
        </tr>
        <tr>
          <td><strong>Partner</strong></td>
          <td><code>Claude Partner</code></td>
          <td>Full access + personalized tone</td>
        </tr>
        <tr>
          <td><strong>Family</strong></td>
          <td><code>Claude Family</code></td>
          <td>Read-only, mutations need approval</td>
        </tr>
        <tr>
          <td><strong>Favorite</strong></td>
          <td><code>Claude Favorites</code></td>
          <td>Own session, restricted tools</td>
        </tr>
        <tr>
          <td><strong>Bots</strong></td>
          <td><code>Claude Bots</code></td>
          <td>Read-only with loop detection</td>
        </tr>
        <tr>
          <td><strong>Unknown</strong></td>
          <td>-</td>
          <td>Ignored</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section>
    <h2>Tier Details</h2>

    <div class="tier-card">
      <div class="tier-header">Admin</div>
      <ul>
        <li>Full computer control</li>
        <li>Browser automation</li>
        <li>All skills enabled</li>
        <li>Skip-permissions mode</li>
      </ul>
    </div>

    <div class="tier-card">
      <div class="tier-header">Partner</div>
      <p>Same access as Admin with warmer, more caring tone. Goes above and beyond.</p>
    </div>

    <div class="tier-card">
      <div class="tier-header">Family</div>
      <ul>
        <li>Can read files and search</li>
        <li>Cannot modify or run destructive commands</li>
        <li>Mutations require admin SMS approval</li>
      </ul>
    </div>

    <div class="tier-card">
      <div class="tier-header">Favorite</div>
      <ul>
        <li>Web search and image analysis</li>
        <li>Limited bash commands</li>
        <li>No file modifications</li>
      </ul>
    </div>

    <div class="tier-card">
      <div class="tier-header">Bots</div>
      <ul>
        <li>Same restrictions as Favorite</li>
        <li>Automatic loop detection</li>
        <li>Stops if no forward progress</li>
      </ul>
    </div>
  </section>

  <section>
    <h2>Setup</h2>

    <h3>Via Contacts.app</h3>
    <ol>
      <li>Open Contacts.app</li>
      <li>Create groups: <code>Claude Admin</code>, <code>Claude Partner</code>, etc.</li>
      <li>Drag contacts into groups</li>
    </ol>

    <h3>Via CLI</h3>
    <pre><code># List by tier
~/.claude/skills/contacts/scripts/contacts list --tier admin

# Set tier
~/.claude/skills/contacts/scripts/contacts tier "John Smith" family

# Lookup
~/.claude/skills/contacts/scripts/contacts lookup +16175551234</code></pre>

    <h3>Rules files</h3>
    <p>Per-tier behavior is configured in:</p>
    <pre><code>~/.claude/skills/sms-assistant/admin-rules.md
~/.claude/skills/sms-assistant/partner-rules.md
~/.claude/skills/sms-assistant/family-rules.md
~/.claude/skills/sms-assistant/favorites-rules.md
~/.claude/skills/sms-assistant/bots-rules.md</code></pre>
  </section>
  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('skills')}>
        <span class="related-label">Skills</span>
        <span class="related-desc">Capabilities per tier</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('cli')}>
        <span class="related-label">CLI Reference</span>
        <span class="related-desc">Manage tiers via CLI</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('philosophy')}>
        <span class="related-label">Philosophy</span>
        <span class="related-desc">Why tiers exist</span>
      </button>
    </div>
  </section>
</article>

<style>
  .tier-card {
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
    padding: var(--space-4);
    margin: var(--space-4) 0;
  }

  .tier-header {
    font-weight: 600;
    font-size: 13px;
    margin-bottom: var(--space-3);
    color: var(--text-primary);
  }

  .tier-card ul {
    margin: 0;
    padding-left: var(--space-4);
  }

  .tier-card li {
    margin: var(--space-1) 0;
    font-size: 12px;
  }

  .tier-card p {
    margin: 0;
    font-size: 12px;
    color: var(--text-secondary);
  }
</style>
