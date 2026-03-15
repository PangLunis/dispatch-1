<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Setup Guide</h1>
    <p class="lead">Get Dispatch running on a dedicated Mac.</p>
  </header>

  <nav class="toc">
    <div class="toc-title">Contents</div>
    <ul>
      <li><a href="#human-setup">Part 1: Human Setup</a></li>
      <li><a href="#claude-setup">Part 2: Claude Setup</a></li>
    </ul>
  </nav>

  <div class="callout">
    <strong>Dedicated Mac recommended.</strong> Dispatch runs 24/7 and needs persistent access to Messages.app.
    A Mac Mini is ideal.
  </div>

  <!-- PART 1: HUMAN SETUP -->
  <section id="human-setup">
    <h2>Part 1: Human Setup</h2>
    <p class="section-desc">Do these steps manually. Takes about 30 minutes.</p>

    <h3>1. Dedicated Mac with separate iCloud</h3>
    <p>The assistant needs its own Apple ID for its own iMessage phone number.</p>
    <ol>
      <li>Create a dedicated Gmail (e.g., <code>dispatch-assistant@gmail.com</code>)</li>
      <li>Create an Apple ID at <a href="https://appleid.apple.com" target="_blank" rel="noopener">appleid.apple.com</a> using that email</li>
      <li>Sign in to the Mac with this Apple ID</li>
      <li>Enable iMessage in Messages.app</li>
      <li>Enable Messages in iCloud (Messages &gt; Settings &gt; iMessage &gt; Enable Messages in iCloud)</li>
    </ol>

    <h3>2. Grant terminal Full Disk Access</h3>
    <p>Open System Settings &gt; Privacy & Security &gt; Full Disk Access and add your terminal app (Terminal.app or iTerm).</p>
    <p class="note">Claude will help you add the Python binary path later — it requires following symlinks.</p>

    <h3>3. Install prerequisites</h3>
    <pre><code># Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Follow post-install to add brew to PATH, then:
brew install git gh node uv mas

# Claude Code CLI
npm install -g @anthropic-ai/claude-code</code></pre>

    <h3>4. Clone the repo</h3>
    <pre><code>gh auth login
gh repo clone svenflow/dispatch ~/dispatch
cd ~/dispatch
uv sync</code></pre>

    <p>That's it! Now hand off to Claude.</p>
  </section>

  <!-- PART 2: CLAUDE SETUP -->
  <section id="claude-setup">
    <h2>Part 2: Claude Setup</h2>
    <p class="section-desc">Hand off to Claude to finish the installation.</p>

    <h3>Start Claude and run setup</h3>
    <pre><code>cd ~/dispatch
claude</code></pre>
    <p>When prompted, log in with your Claude account (or create one). Then type:</p>
    <div class="prompt-box">
      <pre><code>/setup</code></pre>
    </div>
    <p>The setup wizard will guide you through the rest interactively.</p>

    <h3>What happens next</h3>
    <p>Claude will work through the bootstrap guides autonomously:</p>
    <ol>
      <li><strong>Keep-awake</strong> - Installs <a href="https://apps.apple.com/app/amphetamine/id937984704" target="_blank" rel="noopener">Amphetamine</a> via mas-cli, configures it to run indefinitely at startup</li>
      <li><strong>Full Disk Access</strong> - Identifies the Python binary path and walks you through adding it to FDA</li>
      <li><strong>Contact groups</strong> - Creates the tier groups in Contacts.app and adds you to Claude Admin</li>
      <li><strong>Identity setup</strong> - Creates config.local.yaml with your info</li>
      <li><strong>Messaging core</strong> - Sets up the daemon that polls iMessage</li>
      <li><strong>Skills system</strong> - Installs modular capabilities</li>
      <li><strong>LaunchAgent</strong> - Installs the daemon to run at boot via launchd</li>
    </ol>

    <h3>The daemon runs via launchd</h3>
    <p>Once set up, the daemon auto-starts at boot. You don't manually run it.</p>
    <pre><code># Check status
./bin/claude-assistant status

# View logs
./bin/claude-assistant logs

# Restart if needed
./bin/claude-assistant restart</code></pre>

    <h3>Verify it works</h3>
    <p>Text the assistant's phone number from your phone. You should see the message in logs and get a response.</p>
  </section>

  <section id="optional">
    <h2>Optional: Additional Integrations</h2>
    <p>After basic setup, you can add:</p>
    <ul>
      <li><strong>Signal</strong> - Second messaging channel via signal-cli</li>
      <li><strong>Chrome extension</strong> - Browser automation</li>
      <li><strong>Smart home</strong> - Hue, Lutron, Sonos control</li>
      <li><strong>Gemini</strong> - Image analysis and vision (add GEMINI_API_KEY to ~/.claude/secrets.env)</li>
    </ul>
    <p>Claude can help set these up when you're ready.</p>
  </section>

  <section id="next">
    <h2>Next Steps</h2>
    <ul>
      <li>
        <button class="text-link" on:click={() => navigateTo('cli')}>CLI Reference</button>
        <span class="link-desc">- All commands and options</span>
      </li>
      <li>
        <button class="text-link" on:click={() => navigateTo('tiers')}>Contact Tiers</button>
        <span class="link-desc">- Access control system</span>
      </li>
      <li>
        <button class="text-link" on:click={() => navigateTo('philosophy')}>Philosophy</button>
        <span class="link-desc">- Why a separate entity?</span>
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
    margin-bottom: var(--space-6);
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

  .callout {
    background: var(--bg-elevated);
    border-left: 3px solid var(--accent);
    padding: var(--space-4);
    margin-bottom: var(--space-8);
    font-size: 13px;
  }

  section {
    margin-bottom: var(--space-8);
  }

  .section-desc {
    font-size: 13px;
    color: var(--text-secondary);
    margin-bottom: var(--space-4);
  }

  .prompt-box {
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
    padding: var(--space-4);
    margin: var(--space-4) 0;
  }

  .prompt-box pre {
    margin: 0;
    white-space: pre-wrap;
  }

  .note {
    font-size: 12px;
    color: var(--text-tertiary);
    margin-top: var(--space-2);
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
