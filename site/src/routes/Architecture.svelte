<script>
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
  };

  function animate() {
    if (animating) return;
    animating = true;
    step = 0;

    const steps = [1, 2, 3, 4, 5, 6];
    let i = 0;
    const interval = setInterval(() => {
      step = steps[i];
      i++;
      if (i >= steps.length) {
        clearInterval(interval);
        setTimeout(() => {
          animating = false;
          step = 0;
        }, 2500);
      }
    }, 800);
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
      <svg viewBox="0 0 900 750" class="architecture-svg">
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
        </defs>

        <!-- ═══════════════ LEFT: PHONE WITH MESSAGES ═══════════════ -->
        <g transform="translate(40, 40)">
          <!-- Phone frame -->
          <rect x="0" y="0" width="180" height="360" rx="24" class="phone-frame"/>
          <rect x="6" y="6" width="168" height="348" rx="20" class="phone-screen"/>

          <!-- Phone notch -->
          <rect x="60" y="10" width="60" height="20" rx="10" fill="#1a1a1a"/>

          <!-- Phone header -->
          <text x="90" y="56" class="phone-header">Messages</text>

          <!-- Contact header -->
          <rect x="16" y="70" width="148" height="36" rx="8" fill="#f5f5f4"/>
          <circle cx="36" cy="88" r="12" fill="{colors.blue}"/>
          <text x="36" y="92" class="contact-avatar">S</text>
          <text x="56" y="84" class="contact-name">Sven</text>
          <text x="56" y="98" class="contact-status">AI Assistant</text>

          <!-- Message bubbles -->
          <g transform="translate(16, 120)">
            <!-- Incoming message (user) -->
            <g class="message-bubble incoming" class:highlight={step >= 1}>
              <rect x="0" y="0" width="120" height="44" rx="16" class="bubble-in"/>
              <text x="12" y="18" class="bubble-text">Hey what's the</text>
              <text x="12" y="34" class="bubble-text">weather today?</text>
            </g>

            <!-- Outgoing message (response) - appears at step 6 -->
            <g class="message-bubble outgoing" class:visible={step >= 6} transform="translate(28, 60)">
              <rect x="0" y="0" width="120" height="44" rx="16" class="bubble-out"/>
              <text x="12" y="18" class="bubble-text-out">It's 45°F and</text>
              <text x="12" y="34" class="bubble-text-out">cloudy today! ☁️</text>
            </g>
          </g>

          <!-- Typing indicator at step 5 -->
          {#if step === 5}
            <g transform="translate(28, 224)">
              <rect x="0" y="0" width="60" height="28" rx="14" class="bubble-out" opacity="0.7"/>
              <circle cx="16" cy="14" r="4" fill="white" opacity="0.6">
                <animate attributeName="opacity" values="0.3;1;0.3" dur="1s" repeatCount="indefinite"/>
              </circle>
              <circle cx="30" cy="14" r="4" fill="white" opacity="0.6">
                <animate attributeName="opacity" values="0.3;1;0.3" dur="1s" repeatCount="indefinite" begin="0.2s"/>
              </circle>
              <circle cx="44" cy="14" r="4" fill="white" opacity="0.6">
                <animate attributeName="opacity" values="0.3;1;0.3" dur="1s" repeatCount="indefinite" begin="0.4s"/>
              </circle>
            </g>
          {/if}
        </g>

        <!-- ═══════════════ INCOMING PATH: PHONE → DAEMON → AGENT ═══════════════ -->
        <g class="flow-incoming">
          <!-- Path line: Phone → Daemon -->
          <path d="M 220 160 L 320 160" class="flow-path-static incoming"/>
          <!-- Arrowhead -->
          <polygon points="320,160 310,154 310,166" fill="{colors.blue}"/>

          <!-- Path line: Daemon → Agent (via inject-prompt) -->
          <path d="M 560 160 C 590 160, 600 100, 620 100" class="flow-path-static incoming"/>
          <!-- Arrowhead -->
          <polygon points="620,100 610,94 610,106" fill="{colors.blue}"/>

          <!-- Label: inject-prompt -->
          <g transform="translate(570, 130)">
            <rect x="-40" y="-10" width="80" height="20" rx="4" fill="{colors.blue}" opacity="0.15"/>
            <text x="0" y="4" class="flow-label" fill="{colors.blue}">inject-prompt</text>
          </g>

          <!-- Animated packet during animation -->
          {#if step >= 1 && step < 5}
            <circle r="8" fill="{colors.blue}" filter="url(#glow)">
              {#if step < 3}
                <animateMotion dur="0.6s" fill="freeze" path="M 220 160 L 320 160"/>
              {:else}
                <animateMotion dur="0.6s" fill="freeze" path="M 560 160 C 590 160, 600 100, 620 100"/>
              {/if}
            </circle>
          {/if}
        </g>

        <!-- ═══════════════ OUTGOING PATH: AGENT → PHONE ═══════════════ -->
        <g class="flow-outgoing">
          <!-- Path line: Agent → Phone (via send-sms) - curves below -->
          <path d="M 620 140 C 500 180, 400 280, 220 200" class="flow-path-static outgoing"/>
          <!-- Arrowhead at phone end -->
          <polygon points="220,200 232,196 228,206" fill="{colors.green}"/>

          <!-- Label: send-sms -->
          <g transform="translate(420, 240)">
            <rect x="-35" y="-10" width="70" height="20" rx="4" fill="{colors.green}" opacity="0.15"/>
            <text x="0" y="4" class="flow-label" fill="{colors.green}">send-sms</text>
          </g>

          <!-- Animated packet during animation -->
          {#if step >= 6}
            <circle r="8" fill="{colors.green}" filter="url(#glow)">
              <animateMotion dur="0.8s" fill="freeze" path="M 620 140 C 500 180, 400 280, 220 200"/>
            </circle>
          {/if}
        </g>

        <!-- ═══════════════ CENTER: DAEMON ═══════════════ -->
        <g transform="translate(320, 100)">
          <g class="daemon" class:active={step >= 2 && step <= 4}>
            <rect x="0" y="0" width="240" height="160" rx="12" class="daemon-box"/>
            <text x="120" y="32" class="daemon-title">Manager Daemon</text>

            <!-- Daemon internals -->
            <g transform="translate(16, 50)">
              <rect x="0" y="0" width="208" height="32" rx="6" class="daemon-step" class:active={step === 2}/>
              <text x="104" y="20" class="daemon-step-text">① Contact Lookup</text>

              <rect x="0" y="40" width="208" height="32" rx="6" class="daemon-step" class:active={step === 3}/>
              <text x="104" y="60" class="daemon-step-text">② Tier Check → admin</text>

              <rect x="0" y="80" width="208" height="32" rx="6" class="daemon-step" class:active={step === 4}/>
              <text x="104" y="100" class="daemon-step-text">③ Route to Session</text>
            </g>
          </g>
        </g>

        <!-- ═══════════════ RIGHT: AGENT SESSIONS ═══════════════ -->
        <g transform="translate(620, 40)">
          <text x="120" y="16" class="section-label">Agent Sessions</text>

          <!-- Admin session (active) -->
          <g transform="translate(0, 30)" class="session" class:active={step >= 4}>
            <rect x="0" y="0" width="240" height="120" rx="10" class="session-box"/>
            <rect x="0" y="0" width="240" height="32" rx="10" fill="{colors.orange}"/>
            <rect x="0" y="16" width="240" height="16" fill="{colors.orange}"/>
            <text x="16" y="22" class="session-title">Nikhil</text>
            <text x="224" y="22" class="session-tier">admin</text>

            <!-- Session internals -->
            <g transform="translate(12, 42)">
              <text x="0" y="14" class="session-path">~/transcripts/imessage/_1617...</text>
              <rect x="0" y="24" width="216" height="44" rx="4" class="session-work" class:active={step >= 5}/>
              <text x="8" y="42" class="session-work-text">🔧 Checking weather API...</text>
              <text x="8" y="60" class="session-work-text">✓ Got response: 45°F cloudy</text>
            </g>
          </g>

          <!-- Partner session (inactive) -->
          <g transform="translate(0, 170)" class="session inactive">
            <rect x="0" y="0" width="240" height="80" rx="10" class="session-box-inactive"/>
            <rect x="0" y="0" width="240" height="28" rx="10" fill="{colors.purple}" opacity="0.5"/>
            <rect x="0" y="14" width="240" height="14" fill="{colors.purple}" opacity="0.5"/>
            <text x="16" y="20" class="session-title-inactive">Partner</text>
            <text x="224" y="20" class="session-tier-inactive">partner</text>
            <text x="120" y="56" class="session-idle">idle</text>
          </g>

          <!-- Family session (inactive) -->
          <g transform="translate(0, 270)" class="session inactive">
            <rect x="0" y="0" width="240" height="80" rx="10" class="session-box-inactive"/>
            <rect x="0" y="0" width="240" height="28" rx="10" fill="{colors.teal}" opacity="0.5"/>
            <rect x="0" y="14" width="240" height="14" fill="{colors.teal}" opacity="0.5"/>
            <text x="16" y="20" class="session-title-inactive">Family</text>
            <text x="224" y="20" class="session-tier-inactive">family</text>
            <text x="120" y="56" class="session-idle">idle</text>
          </g>
        </g>


        <!-- ═══════════════ WATCHDOG (below daemon) ═══════════════ -->
        <g transform="translate(320, 280)">
          <g class="watchdog">
            <!-- Watchdog box -->
            <rect x="0" y="0" width="240" height="100" rx="12" class="watchdog-box"/>

            <!-- Header -->
            <rect x="0" y="0" width="240" height="32" rx="12" fill="{colors.red}" opacity="0.9"/>
            <rect x="0" y="16" width="240" height="16" fill="{colors.red}" opacity="0.9"/>
            <text x="16" y="22" class="watchdog-title">🛡️ Watchdog</text>
            <text x="224" y="22" class="watchdog-interval">every 60s</text>

            <!-- Watchdog internals -->
            <g transform="translate(12, 44)">
              <text x="0" y="14" class="watchdog-text">Monitors daemon health</text>
              <text x="0" y="32" class="watchdog-text">On crash → spawns healer Claude</text>
              <text x="0" y="50" class="watchdog-text">Exponential backoff on failures</text>
            </g>

            <!-- Health check arrow (watchdog → daemon) -->
            <path d="M 120 0 L 120 -20" stroke="{colors.red}" stroke-width="2" stroke-dasharray="4 2" fill="none" opacity="0.6"/>
            <circle cx="120" cy="-24" r="4" fill="{colors.red}" opacity="0.6"/>
          </g>
        </g>

        <!-- ═══════════════ BOTTOM: EXPLANATION ═══════════════ -->
        <g transform="translate(40, 480)">
          <rect x="0" y="0" width="820" height="220" rx="12" class="explain-box"/>

          <text x="20" y="32" class="explain-title">How inject-prompt works</text>

          <g transform="translate(20, 50)">
            <!-- Before -->
            <rect x="0" y="0" width="240" height="80" rx="8" class="code-box"/>
            <text x="12" y="24" class="code-label">Raw message</text>
            <text x="12" y="50" class="code-string">"Hey what's the weather</text>
            <text x="12" y="68" class="code-string">today?"</text>

            <!-- Arrow -->
            <g transform="translate(260, 30)">
              <path d="M 0 10 L 40 10" stroke="{colors.orange}" stroke-width="3" fill="none"/>
              <polygon points="40,10 32,4 32,16" fill="{colors.orange}"/>
            </g>

            <!-- After -->
            <rect x="320" y="0" width="280" height="80" rx="8" class="code-box"/>
            <text x="332" y="24" class="code-label">Wrapped for Claude</text>
            <text x="332" y="44" class="code-tag">---SMS FROM Nikhil (admin)---</text>
            <text x="332" y="60" class="code-string">"Hey what's the weather today?"</text>
            <text x="332" y="76" class="code-tag">---END SMS---</text>
          </g>

          <g transform="translate(20, 150)">
            <text x="0" y="16" class="explain-note">Each contact gets their own isolated session in</text>
            <text x="0" y="36" class="explain-path">~/transcripts/&#123;backend&#125;/&#123;chat_id&#125;/</text>
            <text x="0" y="56" class="explain-note">Sessions persist across restarts. No shared state between contacts.</text>
          </g>
        </g>

        <!-- Legend -->
        <g transform="translate(720, 500)">
          <g transform="translate(0, 0)">
            <circle r="6" cx="6" cy="6" fill="{colors.blue}"/>
            <text x="20" y="10" class="legend-text">Message in</text>
          </g>
          <g transform="translate(0, 24)">
            <circle r="6" cx="6" cy="6" fill="{colors.green}"/>
            <text x="20" y="10" class="legend-text">Response out</text>
          </g>
          <g transform="translate(0, 48)">
            <rect x="0" y="0" width="12" height="12" rx="3" fill="{colors.orange}"/>
            <text x="20" y="10" class="legend-text">Active session</text>
          </g>
          <g transform="translate(0, 72)">
            <rect x="0" y="0" width="12" height="12" rx="3" fill="{colors.red}"/>
            <text x="20" y="10" class="legend-text">Watchdog</text>
          </g>
        </g>
      </svg>
    </div>
  </section>
</article>

<style>
  .page {
    max-width: 960px;
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
    margin-bottom: var(--space-8);
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
    overflow-x: auto;
  }

  .architecture-svg {
    width: 100%;
    min-width: 860px;
    height: auto;
    display: block;
  }

  /* Phone styles */
  .phone-frame {
    fill: #1a1a1a;
    filter: url(#shadow);
  }

  .phone-screen {
    fill: white;
  }

  .phone-header {
    font-family: var(--font-sans);
    font-size: 14px;
    font-weight: 600;
    fill: #292524;
    text-anchor: middle;
  }

  .contact-avatar {
    font-family: var(--font-sans);
    font-size: 12px;
    font-weight: 600;
    fill: white;
    text-anchor: middle;
    dominant-baseline: middle;
  }

  .contact-name {
    font-family: var(--font-sans);
    font-size: 12px;
    font-weight: 600;
    fill: #292524;
  }

  .contact-status {
    font-family: var(--font-sans);
    font-size: 10px;
    fill: #78716c;
  }

  .bubble-in {
    fill: #e7e5e4;
  }

  .bubble-out {
    fill: #4e79a7;
  }

  .bubble-text {
    font-family: var(--font-sans);
    font-size: 11px;
    fill: #292524;
  }

  .bubble-text-out {
    font-family: var(--font-sans);
    font-size: 11px;
    fill: white;
  }

  .message-bubble.incoming.highlight .bubble-in {
    fill: #4e79a7;
    transition: fill 0.3s ease;
  }

  .message-bubble.incoming.highlight .bubble-text {
    fill: white;
  }

  .message-bubble.outgoing {
    opacity: 0;
    transition: opacity 0.5s ease;
  }

  .message-bubble.outgoing.visible {
    opacity: 1;
  }

  /* Flow paths */
  .flow-path {
    fill: none;
    stroke: #d6d3d1;
    stroke-width: 3;
    stroke-linecap: round;
  }

  .flow-path.active {
    stroke: #4e79a7;
  }

  .flow-path.response {
    stroke: #59a14f;
    stroke-dasharray: 8 4;
  }

  .flow-path-static {
    fill: none;
    stroke-width: 2;
    stroke-linecap: round;
  }

  .flow-path-static.incoming {
    stroke: #4e79a7;
  }

  .flow-path-static.outgoing {
    stroke: #59a14f;
    stroke-dasharray: 6 3;
  }

  .flow-label {
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 500;
    text-anchor: middle;
  }

  .packet-text {
    font-family: var(--font-sans);
    font-size: 10px;
    font-weight: 500;
    fill: white;
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
    font-size: 16px;
    font-weight: 600;
    fill: #292524;
    text-anchor: middle;
  }

  .daemon-step {
    fill: #f5f5f4;
    stroke: #e7e5e4;
    stroke-width: 1;
    transition: all 0.2s ease;
  }

  .daemon-step.active {
    fill: #4e79a7;
    stroke: #4e79a7;
  }

  .daemon-step-text {
    font-family: var(--font-mono);
    font-size: 11px;
    fill: #57534e;
    text-anchor: middle;
  }

  .daemon-step.active + text,
  .daemon-step.active ~ text {
    fill: white;
  }

  /* Session styles */
  .section-label {
    font-family: var(--font-sans);
    font-size: 12px;
    font-weight: 600;
    fill: #78716c;
    text-anchor: middle;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

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

  .session-box-inactive {
    fill: #fafaf9;
    stroke: #e7e5e4;
    stroke-width: 1;
  }

  .session-title {
    font-family: var(--font-sans);
    font-size: 13px;
    font-weight: 600;
    fill: white;
  }

  .session-title-inactive {
    font-family: var(--font-sans);
    font-size: 12px;
    font-weight: 600;
    fill: white;
    opacity: 0.8;
  }

  .session-tier {
    font-family: var(--font-mono);
    font-size: 10px;
    fill: rgba(255,255,255,0.8);
    text-anchor: end;
  }

  .session-tier-inactive {
    font-family: var(--font-mono);
    font-size: 9px;
    fill: rgba(255,255,255,0.6);
    text-anchor: end;
  }

  .session-path {
    font-family: var(--font-mono);
    font-size: 10px;
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
    font-size: 10px;
    fill: #78350f;
  }

  .session-idle {
    font-family: var(--font-mono);
    font-size: 11px;
    fill: #a8a29e;
    text-anchor: middle;
  }

  /* Explanation box */
  .explain-box {
    fill: white;
    stroke: #e7e5e4;
    stroke-width: 1;
  }

  .explain-title {
    font-family: var(--font-sans);
    font-size: 14px;
    font-weight: 600;
    fill: #292524;
  }

  .code-box {
    fill: #1c1917;
  }

  .code-label {
    font-family: var(--font-mono);
    font-size: 10px;
    fill: #78716c;
  }

  .code-string {
    font-family: var(--font-mono);
    font-size: 11px;
    fill: #a3e635;
  }

  .code-tag {
    font-family: var(--font-mono);
    font-size: 10px;
    fill: #f28e2c;
  }

  .explain-note {
    font-family: var(--font-sans);
    font-size: 12px;
    fill: #57534e;
  }

  .explain-path {
    font-family: var(--font-mono);
    font-size: 12px;
    fill: #292524;
    font-weight: 500;
  }

  .legend-text {
    font-family: var(--font-sans);
    font-size: 11px;
    fill: #57534e;
  }

  /* Watchdog styles */
  .watchdog-box {
    fill: white;
    stroke: #e7e5e4;
    stroke-width: 2;
    filter: url(#shadow);
  }

  .watchdog-title {
    font-family: var(--font-sans);
    font-size: 13px;
    font-weight: 600;
    fill: white;
  }

  .watchdog-interval {
    font-family: var(--font-mono);
    font-size: 10px;
    fill: rgba(255,255,255,0.8);
    text-anchor: end;
  }

  .watchdog-text {
    font-family: var(--font-sans);
    font-size: 10px;
    fill: #57534e;
  }

  @media (max-width: 900px) {
    .diagram-container {
      padding: var(--space-2);
    }
  }
</style>
