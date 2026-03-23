<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Discord</h1>
    <p class="lead">Full Discord backend via bot integration.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      Discord is a fully integrated messaging backend, running alongside iMessage and Signal.
      It uses a Discord bot connected via Gateway WebSocket for real-time message receiving
      and the REST API for sending responses. Messages flow through the same daemon, tier
      system, and bus infrastructure as all other backends.
    </p>
  </section>

  <section>
    <h2>How It Works</h2>
    <ul>
      <li><strong>Incoming:</strong> <code>discord_listener.py</code> connects to Discord Gateway as a daemon thread</li>
      <li><strong>Outgoing:</strong> REST API calls via discord.py, auto-chunked at 2000 characters</li>
      <li><strong>Sessions:</strong> Each Discord channel gets its own Claude session</li>
      <li><strong>Transcripts:</strong> Stored at <code>~/transcripts/discord/{'{channel_id}'}/</code></li>
    </ul>
  </section>

  <section>
    <h2>CLI</h2>
    <pre><code># Send a message to a Discord channel
~/.claude/skills/discord/scripts/send-discord "channel_id" "message"</code></pre>
  </section>

  <section>
    <h2>Configuration</h2>
    <p>Requires <code>DISCORD_BOT_TOKEN</code> environment variable set in the daemon's environment.</p>
    <p>
      The bot must be added to target servers with message read/send permissions.
      Channel IDs are used as chat_ids for session routing.
    </p>
  </section>

  <section>
    <h2>Message Format</h2>
    <p>Discord messages are wrapped with the standard format:</p>
    <pre><code>---DISCORD FROM ContactName (channel_id) (tier)---
Message content here
---END DISCORD---</code></pre>
  </section>

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('messaging')}>
        <span class="related-label">Messaging</span>
        <span class="related-desc">All messaging backends</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('tiers')}>
        <span class="related-label">Tiers</span>
        <span class="related-desc">Access control</span>
      </button>
    </div>
  </section>
</article>
