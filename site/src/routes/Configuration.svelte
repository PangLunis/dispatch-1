<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Configuration</h1>
    <p class="lead">Settings reference.</p>
  </header>

  <section>
    <h2>Config File</h2>
    <p>Configuration lives in <code>config.local.yaml</code> (gitignored):</p>
    <pre><code>cp config.example.yaml config.local.yaml</code></pre>
  </section>

  <section>
    <h2>Required Settings</h2>

    <div class="config-block">
      <div class="config-header">Owner</div>
      <pre><code>owner:
  name: "John Smith"
  phone: "+16175551234"
  email: "john@example.com"</code></pre>
    </div>

    <div class="config-block">
      <div class="config-header">Assistant</div>
      <pre><code>assistant:
  name: "Sven"
  email: "assistant@example.com"
  phone: "+19495551234"</code></pre>
    </div>
  </section>

  <section>
    <h2>Optional Settings</h2>

    <div class="config-block">
      <div class="config-header">Partner</div>
      <pre><code>partner:
  name: "Jane Smith"</code></pre>
      <p class="config-note">Used for partner tier's warm tone.</p>
    </div>

    <div class="config-block">
      <div class="config-header">Signal</div>
      <pre><code>signal:
  account: "+19495551234"</code></pre>
      <p class="config-note">Phone registered with signal-cli.</p>
    </div>

    <div class="config-block">
      <div class="config-header">Smart Home</div>
      <pre><code>hue:
  bridges:
    home:
      ip: "10.10.10.10"

lutron:
  bridge_ip: "10.10.10.12"</code></pre>
    </div>

    <div class="config-block">
      <div class="config-header">Chrome Profiles</div>
      <pre><code>chrome:
  profiles:
    0:
      name: "assistant"
      email: "assistant@example.com"
    1:
      name: "owner"
      email: "john@example.com"</code></pre>
      <p class="config-note">Profile 0 is the assistant's Chrome profile.</p>
    </div>
  </section>

  <section>
    <h2>Accessing Values</h2>
    <p>Use the <code>identity</code> CLI:</p>
    <pre><code>~/dispatch/bin/identity owner.name
~/dispatch/bin/identity hue.bridges.home.ip</code></pre>

    <p>In skills, use dynamic prompts:</p>
    <pre><code>**!`identity owner.name`** is the owner.</code></pre>
  </section>

  <section>
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
          <td>Config file path (default: config.local.yaml)</td>
        </tr>
        <tr>
          <td><code>DISPATCH_LOG_LEVEL</code></td>
          <td>DEBUG, INFO, WARNING, ERROR</td>
        </tr>
        <tr>
          <td><code>ANTHROPIC_API_KEY</code></td>
          <td>Claude API key (required)</td>
        </tr>
        <tr>
          <td><code>GEMINI_API_KEY</code></td>
          <td>Google AI key for image analysis/vision (optional)</td>
        </tr>
        <tr>
          <td><code>DISABLE_SIGNAL</code></td>
          <td>Set to disable Signal integration</td>
        </tr>
        <tr>
          <td><code>DISABLE_SEARCH_DAEMON</code></td>
          <td>Set to disable memory search service</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section>
    <h2>Full Example</h2>
    <pre><code>owner:
  name: "John Smith"
  phone: "+16175551234"
  email: "john@example.com"

partner:
  name: "Jane Smith"

assistant:
  name: "Sven"
  email: "assistant@example.com"
  phone: "+19495551234"

signal:
  account: "+19495551234"

hue:
  bridges:
    home:
      ip: "10.10.10.10"

lutron:
  bridge_ip: "10.10.10.12"

chrome:
  profiles:
    0:
      name: "sven"
      email: "assistant@example.com"</code></pre>
  </section>
  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('setup')}>
        <span class="related-label">Setup Guide</span>
        <span class="related-desc">Initial setup</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('cli')}>
        <span class="related-label">CLI Reference</span>
        <span class="related-desc">All commands</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('skills')}>
        <span class="related-label">Skills</span>
        <span class="related-desc">Skill configuration</span>
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

  .config-block {
    margin: var(--space-4) 0;
  }

  .config-header {
    font-weight: 600;
    font-size: 13px;
    color: var(--text-primary);
    margin-bottom: var(--space-2);
  }

  .config-note {
    font-size: 11px;
    color: var(--text-tertiary);
    margin: var(--space-2) 0 0;
  }
</style>
