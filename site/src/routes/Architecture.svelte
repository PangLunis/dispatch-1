<script>
  export let navigateTo;
  let animating = false;
  let step = 0;

  // Tableau 10 colors
  const colors = {
    blue: '#4e79a7',
    orange: '#f28e2c',
    green: '#59a14f',
    teal: '#76b7b2',
    purple: '#af7aa1',
    red: '#e15759',
    gray: '#78716c',
  };

  function animate() {
    if (animating) return;
    animating = true;
    step = 0;

    const steps = [1, 2, 3, 4, 5, 6, 7, 8, 9];
    let i = 0;
    const interval = setInterval(() => {
      step = steps[i];
      i++;
      if (i >= steps.length) {
        clearInterval(interval);
        setTimeout(() => {
          animating = false;
          step = 0;
        }, 2000);
      }
    }, 700);
  }
</script>

<article class="page">
  <header class="page-header">
    <h1>Architecture</h1>
    <p class="lead">How messages flow through Dispatch's multi-agent system</p>
  </header>

  <section class="diagram-section">
    <div class="diagram-header">
      <button class="animate-btn" on:click={animate} disabled={animating}>
        {animating ? 'Animating...' : '▶ Watch Message Flow'}
      </button>
    </div>

    <div class="diagram-container">
      <svg viewBox="0 0 500 950" class="architecture-svg">
        <defs>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="blur"/>
            <feMerge>
              <feMergeNode in="blur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
          <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.15"/>
          </filter>
          <marker id="arrowBlue" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="{colors.blue}"/>
          </marker>
          <marker id="arrowGreen" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="{colors.green}"/>
          </marker>
          <marker id="arrowGray" markerWidth="6" markerHeight="6" refX="5" refY="2.5" orient="auto">
            <path d="M0,0 L0,5 L6,2.5 z" fill="{colors.gray}"/>
          </marker>
          <marker id="arrowOrange" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="{colors.orange}"/>
          </marker>
        </defs>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- ROW 1: CHATS (1:1 + Group) - Mini iPhone mockups -->
        <!-- ════════════════════════════════════════════════════════════ -->
        <g transform="translate(90, 5)">
          <!-- 1:1 DM - iPhone mockup -->
          <!-- Phone outer frame -->
          <rect x="0" y="0" width="140" height="90" rx="14" fill="#1a1a1a"/>
          <!-- Dynamic Island -->
          <rect x="50" y="4" width="40" height="10" rx="5" fill="#000"/>
          <!-- Screen -->
          <rect x="4" y="16" width="132" height="70" rx="10" fill="#f2f2f7"/>
          <!-- Nav bar -->
          <rect x="4" y="16" width="132" height="16" rx="10" fill="#f9f9f9"/>
          <rect x="4" y="26" width="132" height="6" fill="#f9f9f9"/>
          <text x="70" y="27" class="iphone-nav-title">Alice</text>
          <!-- Chat bubbles -->
          <g transform="translate(10, 38)">
            <!-- Received bubble (gray, left aligned) -->
            <rect x="0" y="0" width="55" height="16" rx="8" fill="#e5e5ea"/>
            <text x="8" y="11" class="imessage-text">weather?</text>
            <!-- Sent bubble (blue, right aligned) -->
            <rect x="67" y="0" width="55" height="16" rx="8" fill="#0b93f6"/>
            <text x="75" y="11" class="imessage-text-sent">45°F ☀️</text>
          </g>
          <!-- Tier badge -->
          <rect x="4" y="74" width="132" height="12" rx="0 0 10 10" fill="rgba(242,142,44,0.15)"/>
          <text x="70" y="83" class="phone-tier admin">admin</text>
        </g>

        <g transform="translate(260, 5)">
          <!-- Group chat - iPhone mockup -->
          <!-- Phone outer frame -->
          <rect x="0" y="0" width="140" height="90" rx="14" fill="#1a1a1a"/>
          <!-- Dynamic Island -->
          <rect x="50" y="4" width="40" height="10" rx="5" fill="#000"/>
          <!-- Screen -->
          <rect x="4" y="16" width="132" height="70" rx="10" fill="#f2f2f7"/>
          <!-- Nav bar -->
          <rect x="4" y="16" width="132" height="16" rx="10" fill="#f9f9f9"/>
          <rect x="4" y="26" width="132" height="6" fill="#f9f9f9"/>
          <text x="70" y="27" class="iphone-nav-title">Family (3)</text>
          <!-- Chat bubbles -->
          <g transform="translate(10, 38)">
            <!-- Received bubble 1 -->
            <rect x="0" y="0" width="45" height="16" rx="8" fill="#e5e5ea"/>
            <text x="6" y="11" class="imessage-text">Mom: hi!</text>
            <!-- Received bubble 2 -->
            <rect x="50" y="0" width="50" height="16" rx="8" fill="#e5e5ea"/>
            <text x="56" y="11" class="imessage-text">Dad: hey</text>
          </g>
          <!-- Tier badge -->
          <rect x="4" y="74" width="132" height="12" rx="0 0 10 10" fill="rgba(118,183,178,0.2)"/>
          <text x="70" y="83" class="phone-tier">family</text>
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- CHAT.DB (below chats, messages flow into it) -->
        <!-- ════════════════════════════════════════════════════════════ -->
        <g transform="translate(20, 100)">
          <rect x="0" y="0" width="95" height="70" rx="8" class="db-box"/>
          <text x="47" y="25" class="db-label">💾 chat.db</text>
          <text x="47" y="42" class="db-sublabel">Messages.app</text>
          <text x="47" y="55" class="db-sublabel">database</text>
        </g>

        <!-- Arrows from chats DOWN to chat.db (staggered, no overlap) -->
        <g class="flow-to-db">
          <!-- 1:1 chat arrow: straight down from bottom-left of iPhone -->
          <path d="M 115 95 L 115 100" class="flow-path-thin" marker-end="url(#arrowGray)"/>
          <!-- Group chat arrow: down then left along y=102, enters chat.db from right side -->
          <path d="M 330 95 L 330 102 L 115 102 L 115 100" class="flow-path-thin" marker-end="url(#arrowGray)"/>
          {#if step === 1}
            <circle r="5" fill="{colors.blue}" filter="url(#glow)">
              <animateMotion dur="0.5s" fill="freeze" path="M 115 95 L 115 100"/>
            </circle>
          {/if}
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- DAEMON polls chat.db (arrow FROM daemon TO chat.db) -->
        <!-- ════════════════════════════════════════════════════════════ -->

        <!-- Arrow from daemon pointing LEFT to chat.db (daemon polls it) - direct diagonal -->
        <g class="flow-poll">
          <path d="M 155 195 L 115 170" class="flow-path-solid incoming" marker-end="url(#arrowBlue)"/>
          <text x="110" y="195" class="flow-label-small" fill="{colors.gray}">polls</text>
          {#if step === 2}
            <circle r="5" fill="{colors.blue}" filter="url(#glow)">
              <animateMotion dur="0.4s" fill="freeze" path="M 155 195 L 115 170"/>
            </circle>
          {/if}
        </g>

        <!-- Daemon -->
        <g transform="translate(155, 175)">
          <g class="daemon" class:active={step >= 3 && step <= 4}>
            <rect x="0" y="0" width="280" height="100" rx="12" class="daemon-box"/>
            <text x="140" y="24" class="daemon-title">Manager Daemon</text>

            <!-- Contact lookup -->
            <g transform="translate(15, 38)">
              <rect x="0" y="0" width="115" height="50" rx="8" class="daemon-inner-box" class:active={step === 3}/>
              <text x="57" y="18" class="daemon-inner-title">🔍 Lookup</text>
              <text x="57" y="35" class="daemon-inner-result" class:visible={step >= 3}>+1617... → Alice</text>
            </g>

            <!-- ACL check -->
            <g transform="translate(145, 38)">
              <rect x="0" y="0" width="115" height="50" rx="8" class="daemon-inner-box" class:active={step === 4}/>
              <text x="57" y="18" class="daemon-inner-title">🛡️ ACL</text>
              <text x="57" y="35" class="daemon-inner-result tier-admin" class:visible={step >= 4}>tier → admin ✓</text>
            </g>
          </g>
        </g>

        <!-- Watchdog -->
        <g transform="translate(20, 200)">
          <rect x="0" y="0" width="95" height="50" rx="6" fill="{colors.red}" opacity="0.15"/>
          <text x="47" y="18" class="watchdog-label">🛡️ Watchdog</text>
          <text x="47" y="32" class="watchdog-desc">monitors health</text>
          <text x="47" y="44" class="watchdog-desc">auto-restarts</text>
          <!-- Dashed line to left side of daemon (from watchdog right edge to daemon left edge) -->
          <path d="M 95 25 L 135 25" class="watchdog-line" stroke-dasharray="3,3"/>
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- FAN OUT: Daemon to Sessions -->
        <!-- ════════════════════════════════════════════════════════════ -->
        <g class="fan-out">
          <!-- Main line down from daemon -->
          <path d="M 295 275 L 295 305" class="flow-path-solid incoming"/>

          <!-- Branch node (small circle) -->
          <circle cx="295" cy="310" r="5" fill="{colors.blue}"/>

          <!-- Fan lines from branch node - faded for idle sessions -->
          <path d="M 295 315 L 100 365" class="flow-path-thin faded" marker-end="url(#arrowGray)"/>
          <path d="M 295 315 L 210 365" class="flow-path-thin faded" marker-end="url(#arrowGray)"/>
          <!-- Active/selected session path - highlighted in orange -->
          <path d="M 295 315 L 350 365" class="flow-path-solid" stroke="{colors.orange}" stroke-width="2.5" marker-end="url(#arrowOrange)"/>

          {#if step === 5}
            <circle r="4" fill="{colors.orange}" filter="url(#glow)">
              <animateMotion dur="0.5s" fill="freeze" path="M 295 315 L 350 365"/>
            </circle>
          {/if}
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- SESSION BUBBLES -->
        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- Family Group session (faded) -->
        <g transform="translate(55, 365)">
          <rect x="0" y="0" width="90" height="50" rx="8" class="session-bubble faded"/>
          <rect x="0" y="0" width="90" height="18" rx="8" fill="{colors.teal}" opacity="0.3"/>
          <rect x="0" y="10" width="90" height="8" fill="{colors.teal}" opacity="0.3"/>
          <text x="45" y="13" class="session-bubble-name faded">Family</text>
          <text x="45" y="33" class="session-bubble-tier faded">group</text>
          <text x="45" y="45" class="session-bubble-status">idle</text>
        </g>

        <!-- Friend session (faded) -->
        <g transform="translate(165, 365)">
          <rect x="0" y="0" width="90" height="50" rx="8" class="session-bubble faded"/>
          <rect x="0" y="0" width="90" height="18" rx="8" fill="{colors.purple}" opacity="0.3"/>
          <rect x="0" y="10" width="90" height="8" fill="{colors.purple}" opacity="0.3"/>
          <text x="45" y="13" class="session-bubble-name faded">Friend</text>
          <text x="45" y="33" class="session-bubble-tier faded">favorite</text>
          <text x="45" y="45" class="session-bubble-status">idle</text>
        </g>

        <!-- Active 1:1 session (Alice) -->
        <g transform="translate(300, 365)">
          <rect x="0" y="0" width="100" height="50" rx="8" class="session-bubble" class:selected={step >= 5}/>
          <rect x="0" y="0" width="100" height="18" rx="8" fill="{colors.orange}"/>
          <rect x="0" y="10" width="100" height="8" fill="{colors.orange}"/>
          <text x="50" y="13" class="session-bubble-name">Alice</text>
          <text x="50" y="33" class="session-bubble-tier admin">admin</text>
          <text x="50" y="45" class="session-bubble-status" class:active={step >= 5}>active</text>
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- INJECT-PROMPT -->
        <!-- ════════════════════════════════════════════════════════════ -->
        <path d="M 350 415 L 350 445" class="flow-path-solid incoming"/>

        <g transform="translate(220, 450)">
          <rect x="0" y="0" width="200" height="30" rx="6" fill="{colors.blue}" class:glow={step === 6}/>
          <text x="100" y="19" class="inject-label">inject-prompt(tier=admin)</text>
        </g>

        <g class="flow-down">
          <path d="M 320 480 L 320 515" class="flow-path-solid incoming" marker-end="url(#arrowBlue)"/>
          <text x="335" y="502" class="flow-label-small" fill="{colors.blue}">to Claude</text>
          {#if step === 6}
            <circle r="5" fill="{colors.blue}" filter="url(#glow)">
              <animateMotion dur="0.4s" fill="freeze" path="M 320 480 L 320 515"/>
            </circle>
          {/if}
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- AGENT SESSION (active work) -->
        <!-- ════════════════════════════════════════════════════════════ -->
        <g transform="translate(120, 525)">
          <g class="session" class:active={step >= 7}>
            <rect x="0" y="0" width="300" height="100" rx="10" class="session-box"/>
            <rect x="0" y="0" width="300" height="30" rx="10" fill="{colors.orange}"/>
            <rect x="0" y="15" width="300" height="15" fill="{colors.orange}"/>
            <text x="15" y="21" class="session-title">Alice</text>
            <text x="285" y="21" class="session-tier-label">admin</text>

            <g transform="translate(15, 40)">
              <text x="0" y="12" class="session-path">~/transcripts/imessage/_16175969496/</text>
              <rect x="0" y="18" width="270" height="32" rx="4" class="session-work" class:active={step >= 7}/>
              <text x="8" y="34" class="session-work-text">🔧 "what's the weather?"</text>
              <text x="8" y="46" class="session-work-text">✓ "45°F and cloudy!"</text>
            </g>
          </g>
        </g>

        <!-- Arrow to send-sms -->
        <g class="flow-down">
          <path d="M 270 625 L 270 665" class="flow-path-solid outgoing" marker-end="url(#arrowGreen)"/>
          <text x="285" y="650" class="flow-label-small" fill="{colors.green}">reply</text>
          {#if step === 8}
            <circle r="5" fill="{colors.green}" filter="url(#glow)">
              <animateMotion dur="0.4s" fill="freeze" path="M 270 625 L 270 665"/>
            </circle>
          {/if}
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- SEND-SMS -->
        <!-- ════════════════════════════════════════════════════════════ -->
        <g transform="translate(170, 675)">
          <rect x="0" y="0" width="200" height="40" rx="8" fill="{colors.green}"/>
          <text x="100" y="16" class="node-label">send-sms</text>
          <text x="100" y="30" class="node-sublabel">delivers response</text>
        </g>

        <!-- Return path - goes RIGHT side, enters 1:1 iPhone from bottom -->
        <g class="flow-return">
          <!-- Path: right from send-sms, up the right side, then to 1:1 iPhone bottom edge -->
          <path d="M 370 695 L 460 695 L 460 105 L 160 105 L 160 95"
                class="flow-path-solid outgoing" marker-end="url(#arrowGreen)"/>
          <text x="470" y="400" class="flow-label-vertical" fill="{colors.green}">response</text>
          {#if step === 9}
            <circle r="5" fill="{colors.green}" filter="url(#glow)">
              <animateMotion dur="1.0s" fill="freeze"
                path="M 370 695 L 460 695 L 460 105 L 160 105 L 160 95"/>
            </circle>
          {/if}
        </g>

        <!-- Legend -->
        <g transform="translate(40, 820)">
          <g>
            <circle r="5" cx="5" cy="5" fill="{colors.blue}"/>
            <text x="16" y="9" class="legend-text">Incoming</text>
          </g>
          <g transform="translate(80, 0)">
            <circle r="5" cx="5" cy="5" fill="{colors.green}"/>
            <text x="16" y="9" class="legend-text">Outgoing</text>
          </g>
          <g transform="translate(165, 0)">
            <rect x="0" y="0" width="10" height="10" rx="2" fill="{colors.orange}"/>
            <text x="16" y="9" class="legend-text">Active</text>
          </g>
          <g transform="translate(230, 0)">
            <line x1="0" y1="5" x2="15" y2="5" class="flow-path-thin faded"/>
            <text x="22" y="9" class="legend-text">Idle</text>
          </g>
        </g>
      </svg>
    </div>
  </section>

  <!-- How inject-prompt works -->
  <section class="explain-section">
    <h2>How inject-prompt works</h2>
    <div class="code-comparison">
      <div class="code-block">
        <div class="code-label">Raw message</div>
        <pre><code>"Hey what's the weather today?"</code></pre>
      </div>
      <div class="arrow">→</div>
      <div class="code-block">
        <div class="code-label">Wrapped for Claude</div>
        <pre><code>---SMS FROM Alice (admin)---
"Hey what's the weather today?"
---END SMS---</code></pre>
      </div>
    </div>
    <p class="explain-note">Each contact gets their own isolated session in <code>~/transcripts/{'{backend}'}/{'{chat_id}'}/</code></p>
  </section>

  <!-- Prose explanation -->
  <section>
    <h2>How It Works</h2>
    <p>
      The <strong>Manager Daemon</strong> is a single Python async event loop that polls
      iMessage's <code>chat.db</code> every 100ms and listens on Signal's JSON-RPC socket
      for push notifications. Both backends feed into the same pipeline.
    </p>
    <p>
      When a message arrives, the daemon looks up the sender in macOS Contacts.app to
      determine their <button class="text-link" on:click={() => navigateTo('tiers')}>tier</button>.
      Unknown contacts are ignored. Known contacts get their message wrapped with metadata
      and injected into their dedicated Claude SDK session.
    </p>
    <p>
      Each contact's session runs in the same async event loop (no separate processes).
      Sessions persist across daemon restarts via SDK resume tokens stored in the
      <code>sessions.json</code> registry. When a session's context fills up, it compacts
      (summarizes conversation history) and restarts with the summary.
    </p>
    <p>
      All events — messages, session lifecycle, health checks — flow through the
      <button class="text-link" on:click={() => navigateTo('message-bus')}>Message Bus</button>
      for audit trails and analytics. A separate
      <button class="text-link" on:click={() => navigateTo('health')}>watchdog daemon</button>
      monitors the manager and auto-recovers from crashes.
    </p>
  </section>

  <section>
    <h2>Session Lifecycle</h2>
    <div class="lifecycle">
      <div class="lifecycle-step">
        <div class="lifecycle-label">Create</div>
        <div class="lifecycle-desc">New message from known contact → SDK session spawned with SOUL.md + skills</div>
      </div>
      <div class="lifecycle-arrow">→</div>
      <div class="lifecycle-step">
        <div class="lifecycle-label">Active</div>
        <div class="lifecycle-desc">Messages injected between tool calls, mid-turn steering enabled</div>
      </div>
      <div class="lifecycle-arrow">→</div>
      <div class="lifecycle-step">
        <div class="lifecycle-label">Compact</div>
        <div class="lifecycle-desc">Context full → summarize history → restart with summary</div>
      </div>
      <div class="lifecycle-arrow">→</div>
      <div class="lifecycle-step">
        <div class="lifecycle-label">Idle</div>
        <div class="lifecycle-desc">No messages for 2h → session stopped, resume token saved</div>
      </div>
    </div>
  </section>

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('messaging')}>
        <span class="related-label">Messaging</span>
        <span class="related-desc">iMessage and Signal backends</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('health')}>
        <span class="related-label">Health & Healing</span>
        <span class="related-desc">Monitoring and recovery</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('cli')}>
        <span class="related-label">CLI Reference</span>
        <span class="related-desc">Daemon and session commands</span>
      </button>
    </div>
  </section>
</article>

<style>
  .page {
    max-width: 700px;
  }

  .page-header {
    margin-bottom: var(--space-6);
  }

  .page-header h1 {
    margin-bottom: var(--space-1);
  }

  .lead {
    font-size: 15px;
    color: var(--text-secondary);
    margin: 0;
  }

  .diagram-section {
    margin-bottom: var(--space-6);
  }

  .diagram-header {
    display: flex;
    justify-content: flex-end;
    margin-bottom: var(--space-3);
  }

  .animate-btn {
    background: #292524;
    color: white;
    border: none;
    padding: 10px 20px;
    font-family: var(--font-sans);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    border-radius: 8px;
    transition: all 0.15s ease;
  }

  .animate-btn:hover:not(:disabled) {
    background: #1c1917;
    transform: translateY(-1px);
  }

  .animate-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .diagram-container {
    background: linear-gradient(135deg, #fafaf9 0%, #f5f5f4 100%);
    border: 1px solid #e7e5e4;
    border-radius: 16px;
    padding: var(--space-4);
  }

  .architecture-svg {
    width: 100%;
    height: auto;
    display: block;
  }

  /* iPhone mockup styles */
  .iphone-nav-title {
    font-family: var(--font-sans);
    font-size: 9px;
    font-weight: 600;
    fill: #000;
    text-anchor: middle;
  }

  .imessage-text {
    font-family: var(--font-sans);
    font-size: 7px;
    fill: #000;
  }

  .imessage-text-sent {
    font-family: var(--font-sans);
    font-size: 7px;
    fill: #fff;
  }

  .phone-tier {
    font-family: var(--font-mono);
    font-size: 8px;
    fill: #78716c;
    text-anchor: middle;
  }

  .phone-tier.admin {
    fill: #f28e2c;
  }

  .bubble-text-tiny {
    font-family: var(--font-sans);
    font-size: 7px;
    fill: #292524;
  }

  .bubble-text-tiny-out {
    font-family: var(--font-sans);
    font-size: 7px;
    fill: white;
  }

  /* DB box */
  .db-box {
    fill: #fef3c7;
    stroke: #fbbf24;
    stroke-width: 2;
    filter: url(#shadow);
  }

  .db-label {
    font-family: var(--font-sans);
    font-size: 11px;
    font-weight: 600;
    fill: #78350f;
    text-anchor: middle;
  }

  .db-sublabel {
    font-family: var(--font-mono);
    font-size: 8px;
    fill: #92400e;
    text-anchor: middle;
  }

  /* Flow paths */
  .flow-path-solid {
    fill: none;
    stroke-width: 2.5;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .flow-path-solid.incoming {
    stroke: #4e79a7;
  }

  .flow-path-solid.outgoing {
    stroke: #59a14f;
  }

  .flow-path-thin {
    fill: none;
    stroke: #a8a29e;
    stroke-width: 1.5;
    stroke-linecap: round;
  }

  .flow-path-thin.faded {
    opacity: 0.4;
  }

  .flow-label-small {
    font-family: var(--font-mono);
    font-size: 8px;
    font-weight: 500;
  }

  .flow-label-vertical {
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 500;
    writing-mode: vertical-rl;
  }

  /* Daemon styles */
  .daemon-box {
    fill: white;
    stroke: #e7e5e4;
    stroke-width: 2;
    filter: url(#shadow);
  }

  .daemon.active .daemon-box {
    stroke: #4e79a7;
  }

  .daemon-title {
    font-family: var(--font-sans);
    font-size: 13px;
    font-weight: 600;
    fill: #292524;
    text-anchor: middle;
  }

  .daemon-inner-box {
    fill: #fafaf9;
    stroke: #e7e5e4;
    stroke-width: 1.5;
    transition: all 0.2s ease;
  }

  .daemon-inner-box.active {
    fill: #eff6ff;
    stroke: #4e79a7;
  }

  .daemon-inner-title {
    font-family: var(--font-sans);
    font-size: 10px;
    font-weight: 600;
    fill: #44403c;
    text-anchor: middle;
  }

  .daemon-inner-result {
    font-family: var(--font-mono);
    font-size: 8px;
    fill: #059669;
    text-anchor: middle;
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .daemon-inner-result.visible {
    opacity: 1;
  }

  .daemon-inner-result.tier-admin {
    fill: #f28e2c;
  }

  /* Watchdog */
  .watchdog-label {
    font-family: var(--font-sans);
    font-size: 9px;
    fill: #e15759;
    text-anchor: middle;
    font-weight: 600;
  }

  .watchdog-desc {
    font-family: var(--font-mono);
    font-size: 7px;
    fill: #a8a29e;
    text-anchor: middle;
  }

  .watchdog-line {
    fill: none;
    stroke: #e15759;
    stroke-width: 1;
    opacity: 0.5;
  }

  /* Session bubbles */
  .session-bubble {
    fill: #fafaf9;
    stroke: #e7e5e4;
    stroke-width: 1.5;
  }

  .session-bubble.faded {
    opacity: 0.5;
  }

  .session-bubble.selected {
    fill: #fff7ed;
    stroke: #f28e2c;
    stroke-width: 2;
  }

  .session-bubble-name {
    font-family: var(--font-sans);
    font-size: 9px;
    font-weight: 600;
    fill: white;
    text-anchor: middle;
  }

  .session-bubble-name.faded {
    opacity: 0.7;
  }

  .session-bubble-tier {
    font-family: var(--font-mono);
    font-size: 8px;
    fill: #78716c;
    text-anchor: middle;
  }

  .session-bubble-tier.faded {
    opacity: 0.6;
  }

  .session-bubble-tier.admin {
    fill: #f28e2c;
  }

  .session-bubble-status {
    font-family: var(--font-mono);
    font-size: 7px;
    fill: #a8a29e;
    text-anchor: middle;
  }

  .session-bubble-status.active {
    fill: #f28e2c;
    font-weight: 600;
  }

  /* Inject label */
  .inject-label {
    font-family: var(--font-mono);
    font-size: 10px;
    fill: white;
    text-anchor: middle;
  }

  rect.glow {
    filter: url(#glow);
  }

  /* Node styles */
  .node-label {
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 600;
    fill: white;
    text-anchor: middle;
  }

  .node-sublabel {
    font-family: var(--font-sans);
    font-size: 9px;
    fill: rgba(255,255,255,0.8);
    text-anchor: middle;
  }

  /* Session box styles */
  .session-box {
    fill: white;
    stroke: #e7e5e4;
    stroke-width: 2;
    filter: url(#shadow);
    transition: all 0.2s ease;
  }

  .session.active .session-box {
    stroke: #f28e2c;
    stroke-width: 3;
  }

  .session-title {
    font-family: var(--font-sans);
    font-size: 12px;
    font-weight: 600;
    fill: white;
  }

  .session-tier-label {
    font-family: var(--font-mono);
    font-size: 9px;
    fill: rgba(255,255,255,0.8);
    text-anchor: end;
  }

  .session-path {
    font-family: var(--font-mono);
    font-size: 8px;
    fill: #78716c;
  }

  .session-work {
    fill: #fef3c7;
    stroke: #fbbf24;
    stroke-width: 1;
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .session-work.active {
    opacity: 1;
  }

  .session-work-text {
    font-family: var(--font-mono);
    font-size: 8px;
    fill: #78350f;
  }

  /* Legend */
  .legend-text {
    font-family: var(--font-sans);
    font-size: 9px;
    fill: #57534e;
  }

  /* Explain section */
  .explain-section {
    margin-top: var(--space-6);
    padding: var(--space-5);
    background: #fafaf9;
    border: 1px solid #e7e5e4;
    border-radius: 12px;
  }

  .explain-section h2 {
    font-size: 16px;
    margin: 0 0 var(--space-4) 0;
  }

  .code-comparison {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    flex-wrap: wrap;
  }

  .code-block {
    flex: 1;
    min-width: 200px;
  }

  .code-label {
    font-size: 11px;
    color: var(--text-secondary);
    margin-bottom: var(--space-1);
  }

  .code-block pre {
    background: #1c1917;
    padding: var(--space-3);
    border-radius: 8px;
    margin: 0;
    overflow-x: auto;
  }

  .code-block code {
    font-size: 11px;
    color: #a3e635;
  }

  .arrow {
    font-size: 20px;
    color: var(--text-tertiary);
  }

  .explain-note {
    margin-top: var(--space-4);
    font-size: 13px;
    color: var(--text-secondary);
  }

  .explain-note code {
    background: #e7e5e4;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
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

  .lifecycle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex-wrap: wrap;
    margin: var(--space-4) 0;
  }

  .lifecycle-step {
    flex: 1;
    min-width: 120px;
    padding: var(--space-3);
    background: var(--bg-elevated);
    border: 1px solid var(--border-default);
  }

  .lifecycle-label {
    font-weight: 600;
    font-size: 13px;
    color: var(--text-primary);
    margin-bottom: var(--space-1);
  }

  .lifecycle-desc {
    font-size: 11px;
    color: var(--text-secondary);
    line-height: 1.5;
  }

  .lifecycle-arrow {
    color: var(--text-muted);
    font-size: 16px;
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

  @media (max-width: 600px) {
    .diagram-container {
      padding: var(--space-2);
    }

    .code-comparison {
      flex-direction: column;
    }

    .arrow {
      transform: rotate(90deg);
    }
  }
</style>
