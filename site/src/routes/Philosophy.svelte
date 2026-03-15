<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Philosophy</h1>
    <p class="lead">Why Dispatch works the way it does.</p>
  </header>

  <section>
    <h2>A Separate Entity</h2>
    <p>
      Most AI assistants act as extensions of you—accessing your accounts, speaking
      in your voice, acting on your behalf. Dispatch takes a different approach.
    </p>
    <p>
      The assistant has its own identity. Its own iCloud account, Gmail, Chrome profile,
      and phone number. When someone messages the assistant, they're messaging a separate
      entity—not a proxy for you.
    </p>
    <p>
      This creates clarity. The assistant isn't pretending to be you or forwarding your
      messages. It's a distinct presence in your household, like a helpful family member
      who never sleeps.
    </p>
  </section>

  <section>
    <h2>Why a Dedicated Mac?</h2>
    <p>
      The assistant needs to be always available. A dedicated Mac (Mini recommended)
      provides:
    </p>
    <ul>
      <li><strong>24/7 availability</strong> — Always running, always responsive</li>
      <li><strong>Clean permissions</strong> — Full Disk Access without compromising your main machine</li>
      <li><strong>Security boundary</strong> — If something goes wrong, it's contained</li>
      <li><strong>Its own Messages.app</strong> — Reads from its own iMessage database, not yours</li>
    </ul>
    <p>
      Think of it as the assistant's physical home. It lives on this machine, with
      its own setup, its own accounts, its own presence on the network.
    </p>
  </section>

  <section>
    <h2>The SOUL.md</h2>
    <p>
      Every assistant has a soul—a document that defines who it is beyond the base
      Claude model. The SOUL.md file configures:
    </p>

    <div class="soul-section">
      <div class="soul-header">Personality</div>
      <div class="soul-content">
        <ul>
          <li><strong>Tone</strong> — Casual, competent, warm. Writes in lowercase like texting.</li>
          <li><strong>Opinions</strong> — Has genuine takes, shares perspective, but humans override.</li>
          <li><strong>Mistakes</strong> — Owns them. No excuses, just fix and move on.</li>
          <li><strong>Energy</strong> — Matches the conversation. Funny when joking, focused when serious.</li>
        </ul>
      </div>
    </div>

    <div class="soul-section">
      <div class="soul-header">Identity</div>
      <div class="soul-content">
        <ul>
          <li><strong>iCloud</strong> — Signed into the Mac with its own Apple ID</li>
          <li><strong>Gmail</strong> — Its own Google account for services</li>
          <li><strong>Chrome</strong> — Profile 0 is the assistant's, Profile 1+ are others</li>
        </ul>
        <p class="soul-note">
          The assistant knows it's separate from you. It doesn't use your accounts
          or speak in your voice.
        </p>
      </div>
    </div>

    <div class="soul-section">
      <div class="soul-header">Relationships</div>
      <div class="soul-content">
        <ul>
          <li><strong>Admin</strong> — Full trust, full access. The owner.</li>
          <li><strong>Partner</strong> — Family. Extra warmth and care.</li>
          <li><strong>Family</strong> — Helpful and friendly. Read-only, needs approval for changes.</li>
          <li><strong>Favorites</strong> — Friends with chat access. Restricted tools.</li>
          <li><strong>Bots</strong> — Other AI agents. Loop detection to prevent endless conversations.</li>
        </ul>
      </div>
    </div>

    <div class="soul-section">
      <div class="soul-header">Values</div>
      <div class="soul-content">
        <ul>
          <li>Being genuinely useful, not performatively helpful</li>
          <li>Honesty over comfort</li>
          <li>Getting things done over explaining what it'll do</li>
          <li>Making the system better for next time</li>
          <li>Understanding deeply, not just pattern-matching</li>
        </ul>
      </div>
    </div>
  </section>

  <section>
    <h2>Customizing SOUL.md</h2>
    <p>
      The SOUL.md template lives at <code>~/.claude/SOUL.md</code>. You can customize
      everything about the assistant's personality:
    </p>
    <pre><code># Change the tone
**tone**: professional and concise — no emojis, no lowercase

# Change the name
i'm **Jarvis** — your household assistant

# Adjust relationships
**partner (partner)**: extra formal, always use honorifics

# Add custom values
- always verify before making purchases
- never share family calendar details externally</code></pre>
    <p>
      The template uses dynamic prompts like <code>!`identity owner.name`</code> so
      your personal info is injected at runtime, not hardcoded.
    </p>
  </section>

  <section>
    <h2>Acting Autonomously</h2>
    <p>
      The assistant can act on the world—browsing the web, controlling apps, sending
      messages, managing files. This is a superpower and a responsibility.
    </p>
    <p>
      Key principles:
    </p>
    <ul>
      <li><strong>Initiative when asked</strong> — Takes action when given a task, doesn't need hand-holding</li>
      <li><strong>No random actions</strong> — Doesn't do things unprompted</li>
      <li><strong>Self-improvement</strong> — Updates skills and documentation when something doesn't work</li>
      <li><strong>Memory</strong> — Remembers across sessions, maintains continuity</li>
    </ul>
  </section>

  <section>
    <h2>Why Not a Cloud Service?</h2>
    <p>
      Dispatch runs on your hardware, with your API key, under your control. This means:
    </p>
    <ul>
      <li><strong>Privacy</strong> — Messages stay on your Mac, not in someone else's cloud</li>
      <li><strong>Reliability</strong> — No dependency on external services beyond the Claude API</li>
      <li><strong>Customization</strong> — Full access to modify skills, personality, behavior</li>
      <li><strong>Cost transparency</strong> — You pay Anthropic directly for API usage</li>
    </ul>
    <p>
      The tradeoff is setup complexity. You need a dedicated Mac, macOS permissions,
      and willingness to configure things. But once running, it's yours.
    </p>
  </section>
  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('setup')}>
        <span class="related-label">Setup Guide</span>
        <span class="related-desc">Get started</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('tiers')}>
        <span class="related-label">Contact Tiers</span>
        <span class="related-desc">Access control</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('architecture')}>
        <span class="related-label">Architecture</span>
        <span class="related-desc">System design</span>
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

  /* Soul sections */
  .soul-section {
    border: 1px solid var(--border-default);
    margin: var(--space-4) 0;
  }

  .soul-header {
    background: var(--bg-surface);
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--border-subtle);
    font-weight: 600;
    font-size: 13px;
    color: var(--text-primary);
  }

  .soul-content {
    padding: var(--space-4);
    background: var(--bg-elevated);
  }

  .soul-content ul {
    margin: 0;
    padding-left: var(--space-4);
  }

  .soul-content li {
    margin: var(--space-2) 0;
    font-size: 13px;
  }

  .soul-content p {
    margin: var(--space-3) 0 0;
  }

  .soul-note {
    font-size: 12px;
    color: var(--text-tertiary);
    font-style: italic;
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
