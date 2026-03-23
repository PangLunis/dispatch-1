<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Dispatch App</h1>
    <p class="lead">Expo/React Native mobile app with FastAPI backend, push notifications, and voice.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      The Dispatch App is a native iOS app (Expo/React Native) that provides a direct
      chat interface to the assistant. It connects to a FastAPI backend (<code>dispatch-api</code>)
      running on port 9091, which bridges messages to the same daemon and bus infrastructure
      used by iMessage and Signal.
    </p>
  </section>

  <section>
    <h2>Architecture</h2>
    <div class="arch-grid">
      <div class="arch-item">
        <div class="arch-label">Frontend</div>
        <div class="arch-desc">Expo/React Native app at <code>~/dispatch/apps/dispatch-app/</code></div>
      </div>
      <div class="arch-item">
        <div class="arch-label">Backend</div>
        <div class="arch-desc">FastAPI server at <code>~/dispatch/services/dispatch-api/</code> (port 9091)</div>
      </div>
      <div class="arch-item">
        <div class="arch-label">Networking</div>
        <div class="arch-desc">Connects via Tailscale VPN for remote access</div>
      </div>
      <div class="arch-item">
        <div class="arch-label">Auth</div>
        <div class="arch-desc">Session-based with per-conversation chat IDs</div>
      </div>
    </div>
  </section>

  <section>
    <h2>Features</h2>
    <ul>
      <li><strong>Chat interface</strong> — real-time messaging with the assistant</li>
      <li><strong>Voice input</strong> — speech-to-text via Whisper transcription</li>
      <li><strong>TTS responses</strong> — audio playback of assistant messages</li>
      <li><strong>Push notifications</strong> — via Expo Push for new messages</li>
      <li><strong>Image support</strong> — send and receive images in conversation</li>
      <li><strong>Agent logs</strong> — view what the assistant is doing in real-time</li>
      <li><strong>Session management</strong> — start, restart, and monitor sessions from the app</li>
    </ul>
  </section>

  <section>
    <h2>Backend API</h2>
    <p>
      The <code>dispatch-api</code> FastAPI server exposes REST endpoints for the mobile app
      and produces events to the message bus just like iMessage and Signal backends.
    </p>
    <pre><code># Start the API server
cd ~/dispatch/services/dispatch-api
uv run uvicorn main:app --host 0.0.0.0 --port 9091</code></pre>
  </section>

  <section>
    <h2>Messaging CLI</h2>
    <pre><code># Send message to a dispatch-app conversation
~/.claude/skills/dispatch-app/scripts/reply-app "chat-id" "message"</code></pre>
    <p>
      Sessions use <code>dispatch-app</code> as their backend prefix. Transcript directories
      are at <code>~/transcripts/dispatch-app/{chat_id}/</code>.
    </p>
  </section>

  <section>
    <h2>Configuration</h2>
    <p>
      App-specific settings live in <code>~/dispatch/apps/dispatch-app/app.yaml</code> (gitignored):
    </p>
    <pre><code>appName: Sven
bundleIdentifier: com.example.sven
apiHost: 100.x.x.x:9091
metroHost: 100.x.x.x
sessionPrefix: sven-app
accentColor: "#3478f7"
iconPath: ./assets/images/sven-icon.png</code></pre>
  </section>

  <section>
    <h2>Development</h2>
    <pre><code># Install dependencies
cd ~/dispatch/apps/dispatch-app
npm install

# Start Metro bundler
npx expo start

# Build for iOS
npx expo run:ios</code></pre>
  </section>

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('messaging')}>
        <span class="related-label">Messaging</span>
        <span class="related-desc">All messaging backends</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('architecture')}>
        <span class="related-label">Architecture</span>
        <span class="related-desc">System design</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('voice')}>
        <span class="related-label">Voice & TTS</span>
        <span class="related-desc">Speech capabilities</span>
      </button>
    </div>
  </section>
</article>

<style>
  .arch-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1px;
    background: var(--border-default);
    border: 1px solid var(--border-default);
    margin: var(--space-4) 0;
  }

  .arch-item {
    padding: var(--space-4);
    background: var(--bg-elevated);
  }

  .arch-label {
    font-weight: 600;
    font-size: 13px;
    color: var(--text-primary);
    margin-bottom: var(--space-1);
  }

  .arch-desc {
    font-size: 12px;
    color: var(--text-secondary);
    line-height: 1.5;
  }

  @media (max-width: 768px) {
    .arch-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
