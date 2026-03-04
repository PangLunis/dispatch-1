<script>
  let animatingMessage = false;
  let messageStep = 0;
  let hoveredNode = null;

  // Observable-style Tableau 10 colors
  const colors = {
    blue: '#4e79a7',
    orange: '#f28e2c',
    red: '#e15759',
    teal: '#76b7b2',
    green: '#59a14f',
    yellow: '#edc949',
    purple: '#af7aa1',
    pink: '#ff9da7',
    brown: '#9c755f',
    gray: '#bab0ab'
  };

  function simulateMessage() {
    if (animatingMessage) return;
    animatingMessage = true;
    messageStep = 0;

    const steps = [1, 2, 3, 4, 5, 6, 7];
    let i = 0;
    const interval = setInterval(() => {
      messageStep = steps[i];
      i++;
      if (i >= steps.length) {
        clearInterval(interval);
        setTimeout(() => {
          animatingMessage = false;
          messageStep = 0;
        }, 2000);
      }
    }, 600);
  }
</script>

<article class="page">
  <header class="page-header">
    <h1>Architecture</h1>
    <p class="lead">How Dispatch isolates contacts and orchestrates agent sessions</p>
  </header>

  <section class="diagram-section">
    <div class="diagram-header">
      <button class="simulate-btn" on:click={simulateMessage} disabled={animatingMessage}>
        {animatingMessage ? 'Simulating...' : '▶ Trace Message Flow'}
      </button>
    </div>

    <div class="diagram-container">
      <svg viewBox="0 0 880 780" class="architecture-svg">
        <defs>
          <!-- Glow filter for animated elements -->
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="blur"/>
            <feMerge>
              <feMergeNode in="blur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>

          <!-- Gradient for flow lines -->
          <linearGradient id="flowGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="{colors.blue}" stop-opacity="0.8"/>
            <stop offset="100%" stop-color="{colors.teal}" stop-opacity="0.8"/>
          </linearGradient>
        </defs>

        <!-- ═══════════════ STAGE 1: SOURCES ═══════════════ -->
        <g transform="translate(40, 30)">
          <text x="0" y="0" class="stage-label">① sources</text>
        </g>

        <!-- iMessage node -->
        <g transform="translate(80, 50)"
           class="node"
           class:active={messageStep >= 1}
           on:mouseenter={() => hoveredNode = 'imessage'}
           on:mouseleave={() => hoveredNode = null}
           role="button"
           tabindex="0">
          <rect x="0" y="0" width="140" height="56" rx="4" class="node-box" style="--node-color: {colors.blue}"/>
          <text x="70" y="28" class="node-title">iMessage</text>
          <text x="70" y="44" class="node-detail">polls chat.db</text>
        </g>

        <!-- Signal node -->
        <g transform="translate(260, 50)" class="node">
          <rect x="0" y="0" width="140" height="56" rx="4" class="node-box" style="--node-color: {colors.teal}"/>
          <text x="70" y="28" class="node-title">Signal</text>
          <text x="70" y="44" class="node-detail">JSON-RPC socket</text>
        </g>

        <!-- chat_id reference -->
        <g transform="translate(500, 50)">
          <rect x="0" y="0" width="200" height="56" rx="4" class="reference-box"/>
          <text x="100" y="18" class="reference-label">chat_id formats</text>
          <text x="16" y="36" class="code mono">+16175969496</text>
          <text x="130" y="36" class="code-hint">individual</text>
          <text x="16" y="50" class="code mono">b3d258b9a4de...</text>
          <text x="130" y="50" class="code-hint">group</text>
        </g>

        <!-- Flow line: sources → daemon -->
        <path d="M 150 106 C 150 140, 150 140, 200 170"
              class="flow-line" class:active={messageStep >= 2}/>
        <path d="M 330 106 C 330 140, 330 140, 280 170"
              class="flow-line"/>

        {#if messageStep >= 2}
          <circle r="6" fill="{colors.blue}" filter="url(#glow)">
            <animateMotion dur="0.4s" fill="freeze" path="M 150 106 C 150 140, 150 140, 200 170"/>
          </circle>
        {/if}

        <!-- ═══════════════ STAGE 2: DAEMON ═══════════════ -->
        <g transform="translate(40, 150)">
          <text x="0" y="0" class="stage-label">② manager daemon</text>
        </g>

        <!-- Daemon node -->
        <g transform="translate(80, 170)"
           class="node primary"
           class:active={messageStep >= 2 && messageStep <= 4}>
          <rect x="0" y="0" width="320" height="72" rx="4" class="node-box-primary"/>
          <text x="160" y="28" class="node-title-primary">Manager Daemon</text>
          <text x="160" y="48" class="node-detail-primary">contact lookup • tier check • session routing</text>
          <text x="160" y="62" class="node-detail-primary">inject-prompt wraps messages</text>
        </g>

        <!-- Contacts.app -->
        <g transform="translate(460, 170)">
          <rect x="0" y="0" width="180" height="72" rx="4" class="reference-box"/>
          <text x="90" y="18" class="reference-label">Contacts.app</text>
          <text x="16" y="38" class="code mono small">phone → name</text>
          <text x="16" y="52" class="code mono small">phone → tier (admin, family...)</text>
          <text x="16" y="66" class="code mono small">phone → notes</text>
        </g>

        <path d="M 400 206 L 460 206" class="connector-line" class:active={messageStep >= 3}/>

        <!-- Flow line: daemon → inject-prompt -->
        <path d="M 240 242 L 240 290" class="flow-line" class:active={messageStep >= 4}/>

        <!-- ═══════════════ STAGE 3: INJECT-PROMPT ═══════════════ -->
        <g transform="translate(40, 270)">
          <text x="0" y="0" class="stage-label">③ inject-prompt</text>
        </g>

        <g transform="translate(80, 290)">
          <rect x="0" y="0" width="560" height="110" rx="4" class="code-box"/>

          <!-- Before transformation -->
          <text x="16" y="24" class="code-comment"># incoming message</text>
          <text x="16" y="44" class="code-string">"hey what's the weather?"</text>

          <!-- Arrow -->
          <g transform="translate(250, 30)">
            <path d="M 0 14 L 30 14" stroke="{colors.orange}" stroke-width="2" fill="none"/>
            <polygon points="30,14 24,10 24,18" fill="{colors.orange}"/>
          </g>

          <!-- After transformation -->
          <text x="300" y="24" class="code-comment"># wrapped with context</text>
          <text x="300" y="44" class="code-tag">---SMS FROM Nikhil (admin)---</text>
          <text x="300" y="60" class="code-string">"hey what's the weather?"</text>
          <text x="300" y="76" class="code-tag">---END SMS---</text>

          <text x="16" y="100" class="code-hint">Tags identify sender, tier, separate from tool output</text>
        </g>

        <!-- Flow line: inject-prompt → session -->
        <path d="M 240 400 L 240 450" class="flow-line" class:active={messageStep >= 5}/>
        {#if messageStep >= 5}
          <circle r="6" fill="{colors.blue}" filter="url(#glow)">
            <animateMotion dur="0.3s" fill="freeze" path="M 240 400 L 240 450"/>
          </circle>
        {/if}

        <!-- ═══════════════ STAGE 4: SESSION ═══════════════ -->
        <g transform="translate(40, 430)">
          <text x="0" y="0" class="stage-label">④ sdk session</text>
        </g>

        <!-- Session detail -->
        <g transform="translate(80, 450)" class="node" class:active={messageStep >= 5}>
          <rect x="0" y="0" width="380" height="180" rx="4" class="node-box" style="--node-color: {colors.orange}"/>

          <!-- Session header -->
          <rect x="0" y="0" width="380" height="32" rx="4" fill="{colors.orange}"/>
          <rect x="0" y="16" width="380" height="16" fill="{colors.orange}"/>
          <text x="16" y="22" class="session-name">imessage/_16175969496</text>
          <text x="364" y="22" class="session-tier">admin</text>

          <!-- Transcript simulation -->
          <g transform="translate(12, 42)">
            <text x="0" y="14" class="code-comment small"># what claude sees</text>

            <!-- Hidden turns -->
            <rect x="0" y="22" width="356" height="20" rx="2" class="transcript-row hidden"/>
            <text x="8" y="36" class="transcript-text dim">Assistant: [tool call] Read("/weather.json")</text>

            <rect x="0" y="46" width="356" height="20" rx="2" class="transcript-row hidden"/>
            <text x="8" y="60" class="transcript-text dim">Tool result: &#123;"temp": 45, "condition": "cloudy"&#125;</text>

            <rect x="0" y="70" width="356" height="20" rx="2" class="transcript-row hidden"/>
            <text x="8" y="84" class="transcript-text dim">Assistant: [thinking] The weather is...</text>

            <!-- Visible turn -->
            <rect x="0" y="98" width="356" height="32" rx="2" class="transcript-row visible"/>
            <text x="8" y="112" class="transcript-text bright">Human: ---SMS FROM Nikhil (admin)---</text>
            <text x="8" y="126" class="transcript-text bright">"hey what's the weather?"</text>
          </g>
        </g>

        <!-- Transcript structure -->
        <g transform="translate(500, 450)">
          <rect x="0" y="0" width="220" height="180" rx="4" class="reference-box"/>
          <text x="110" y="20" class="reference-label">~/transcripts/</text>

          <!-- Tree structure -->
          <g transform="translate(16, 36)">
            <!-- imessage branch -->
            <text x="0" y="12" class="folder-name">imessage/</text>
            <path d="M 8 18 L 8 56 M 8 30 L 20 30 M 8 48 L 20 48" class="tree-connector"/>

            <text x="24" y="34" class="folder-item">_16175969496/</text>
            <rect x="112" y="22" width="48" height="16" rx="8" fill="rgba(242, 142, 44, 0.2)"/>
            <text x="136" y="34" class="tier-pill" style="fill: {colors.orange}">admin</text>

            <text x="24" y="52" class="folder-item">b3d258b9.../</text>
            <rect x="100" y="40" width="48" height="16" rx="8" fill="rgba(118, 183, 178, 0.2)"/>
            <text x="124" y="52" class="tier-pill" style="fill: {colors.teal}">group</text>

            <!-- signal branch -->
            <text x="0" y="80" class="folder-name">signal/</text>
            <path d="M 8 86 L 8 124 M 8 98 L 20 98 M 8 116 L 20 116" class="tree-connector"/>

            <text x="24" y="102" class="folder-item">_16175969496/</text>
            <rect x="112" y="90" width="48" height="16" rx="8" fill="rgba(242, 142, 44, 0.2)"/>
            <text x="136" y="102" class="tier-pill" style="fill: {colors.orange}">admin</text>

            <text x="24" y="120" class="folder-item">group-b64.../</text>
            <rect x="100" y="108" width="48" height="16" rx="8" fill="rgba(89, 161, 79, 0.2)"/>
            <text x="124" y="120" class="tier-pill" style="fill: {colors.green}">group</text>
          </g>

          <text x="110" y="170" class="folder-note">+ replaced with _ in paths</text>
        </g>

        <!-- Flow line: session → response -->
        <path d="M 240 630 L 240 680" class="flow-line" class:active={messageStep >= 6}/>

        <!-- ═══════════════ STAGE 5: RESPONSE ═══════════════ -->
        <g transform="translate(40, 660)">
          <text x="0" y="0" class="stage-label">⑤ response</text>
        </g>

        <g transform="translate(80, 680)" class:active={messageStep >= 6}>
          <rect x="0" y="0" width="560" height="70" rx="4" class="code-box"/>
          <text x="16" y="26" class="code-comment"># claude sends response</text>
          <text x="16" y="48" class="code mono">send-sms "+16175969496" "It's 45°F and cloudy"</text>
          <text x="16" y="64" class="code-hint">→ AppleScript → Messages.app → user's phone</text>
        </g>

        <!-- Response arc back to top -->
        {#if messageStep >= 7}
          <g class="response-flow">
            <path d="M 640 710 Q 780 710, 780 400 Q 780 90, 700 90"
                  class="response-arc" fill="none"/>
            <circle r="6" fill="{colors.green}" filter="url(#glow)">
              <animateMotion dur="0.7s" fill="freeze" path="M 640 710 Q 780 710, 780 400 Q 780 90, 700 90"/>
            </circle>
          </g>
        {/if}

        <!-- Legend -->
        <g transform="translate(720, 680)">
          <rect x="0" y="0" width="120" height="70" rx="4" class="legend-box"/>
          <text x="60" y="18" class="legend-title">Legend</text>
          <g transform="translate(12, 28)">
            <circle r="5" cx="5" cy="6" fill="{colors.blue}"/>
            <text x="18" y="10" class="legend-item">message in</text>
          </g>
          <g transform="translate(12, 46)">
            <circle r="5" cx="5" cy="6" fill="{colors.green}"/>
            <text x="18" y="10" class="legend-item">response out</text>
          </g>
        </g>
      </svg>
    </div>
  </section>

  <!-- Concepts -->
  <section>
    <h2>Key Concepts</h2>
    <div class="concepts">
      <div class="concept">
        <div class="concept-marker" style="background: {colors.orange}"></div>
        <div class="concept-content">
          <h3>inject-prompt</h3>
          <p>The daemon wraps incoming messages with <code>---SMS FROM---</code> tags so Claude knows who sent them and their permission tier.</p>
        </div>
      </div>
      <div class="concept">
        <div class="concept-marker" style="background: {colors.blue}"></div>
        <div class="concept-content">
          <h3>Hidden vs Visible</h3>
          <p>Tool calls and internal reasoning are hidden. Only injected SMS messages appear as "Human:" turns. Responses go via <code>send-sms</code>.</p>
        </div>
      </div>
      <div class="concept">
        <div class="concept-marker" style="background: {colors.teal}"></div>
        <div class="concept-content">
          <h3>Session Isolation</h3>
          <p>Each contact gets their own SDK session in <code>~/transcripts/&#123;backend&#125;/&#123;chat_id&#125;/</code>. Sessions persist across daemon restarts.</p>
        </div>
      </div>
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

  section {
    margin-bottom: var(--space-8);
  }

  section h2 {
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text-muted);
    margin: 0 0 var(--space-4);
  }

  /* Diagram */
  .diagram-section {
    margin-bottom: var(--space-8);
  }

  .diagram-header {
    display: flex;
    justify-content: flex-end;
    margin-bottom: var(--space-3);
  }

  .simulate-btn {
    background: transparent;
    color: var(--text-secondary);
    border: 1px solid var(--border-default);
    padding: var(--space-2) var(--space-4);
    font-family: var(--font-sans);
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
    border-radius: 4px;
  }

  .simulate-btn:hover:not(:disabled) {
    border-color: #4e79a7;
    color: #4e79a7;
    background: rgba(78, 121, 167, 0.05);
  }

  .simulate-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .diagram-container {
    background: #fafafa;
    border: 1px solid var(--border-default);
    border-radius: 6px;
    padding: var(--space-4);
    overflow-x: auto;
  }

  .architecture-svg {
    width: 100%;
    min-width: 840px;
    height: auto;
    display: block;
  }

  /* SVG styles */
  .stage-label {
    font-family: var(--font-sans);
    font-size: 11px;
    font-weight: 600;
    fill: #78716c;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .node-box {
    fill: white;
    stroke: var(--node-color, #d6d3d1);
    stroke-width: 1.5;
    transition: all 0.15s ease;
  }

  .node.active .node-box {
    stroke-width: 2.5;
    filter: drop-shadow(0 2px 8px rgba(0,0,0,0.1));
  }

  .node-box-primary {
    fill: #292524;
    stroke: none;
  }

  .node.primary.active .node-box-primary {
    filter: drop-shadow(0 2px 12px rgba(0,0,0,0.2));
  }

  .node-title {
    font-family: var(--font-sans);
    font-size: 13px;
    font-weight: 600;
    fill: #292524;
    text-anchor: middle;
  }

  .node-title-primary {
    font-family: var(--font-sans);
    font-size: 14px;
    font-weight: 600;
    fill: white;
    text-anchor: middle;
  }

  .node-detail {
    font-family: var(--font-mono);
    font-size: 10px;
    fill: #78716c;
    text-anchor: middle;
  }

  .node-detail-primary {
    font-family: var(--font-mono);
    font-size: 10px;
    fill: rgba(255,255,255,0.6);
    text-anchor: middle;
  }

  .reference-box {
    fill: #f5f5f4;
    stroke: #e7e5e4;
    stroke-width: 1;
  }

  .reference-label {
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 500;
    fill: #78716c;
    text-anchor: middle;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .code-box {
    fill: #1c1917;
    stroke: #292524;
    stroke-width: 1;
  }

  .code {
    font-family: var(--font-mono);
    font-size: 11px;
    fill: #a8a29e;
  }

  .code.mono {
    fill: #e7e5e4;
  }

  .code.mono.small {
    font-size: 10px;
  }

  .code-hint {
    font-family: var(--font-mono);
    font-size: 10px;
    fill: #78716c;
  }

  .code-comment {
    font-family: var(--font-mono);
    font-size: 10px;
    fill: #6b7280;
  }

  .code-comment.small {
    font-size: 9px;
  }

  .code-string {
    font-family: var(--font-mono);
    font-size: 11px;
    fill: #a3e635;
  }

  .code-tag {
    font-family: var(--font-mono);
    font-size: 11px;
    fill: #f28e2c;
  }

  .flow-line {
    fill: none;
    stroke: #d6d3d1;
    stroke-width: 2;
    stroke-linecap: round;
    transition: stroke 0.2s ease;
  }

  .flow-line.active {
    stroke: #4e79a7;
  }

  .connector-line {
    fill: none;
    stroke: #d6d3d1;
    stroke-width: 1.5;
    stroke-dasharray: 4 3;
  }

  .connector-line.active {
    stroke: #4e79a7;
  }

  .session-name {
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 500;
    fill: white;
  }

  .session-tier {
    font-family: var(--font-mono);
    font-size: 9px;
    fill: rgba(255,255,255,0.7);
    text-anchor: end;
  }

  .transcript-row {
    stroke: none;
  }

  .transcript-row.hidden {
    fill: rgba(0,0,0,0.03);
  }

  .transcript-row.visible {
    fill: rgba(242, 142, 44, 0.1);
    stroke: #f28e2c;
    stroke-width: 1;
  }

  .transcript-text {
    font-family: var(--font-mono);
    font-size: 9px;
  }

  .transcript-text.dim {
    fill: #a8a29e;
  }

  .transcript-text.bright {
    fill: #f28e2c;
  }

  .folder-name {
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 500;
    fill: #57534e;
  }

  .folder-item {
    font-family: var(--font-mono);
    font-size: 10px;
    fill: #78716c;
  }

  .folder-note {
    font-family: var(--font-mono);
    font-size: 9px;
    fill: #a8a29e;
    text-anchor: middle;
  }

  .tree-connector {
    stroke: #d6d3d1;
    stroke-width: 1;
    fill: none;
  }

  .tier-pill {
    font-family: var(--font-mono);
    font-size: 8px;
    font-weight: 500;
    text-anchor: middle;
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }

  .response-arc {
    stroke: #59a14f;
    stroke-width: 2;
    stroke-dasharray: 6 4;
  }

  .legend-box {
    fill: white;
    stroke: #e7e5e4;
    stroke-width: 1;
  }

  .legend-title {
    font-family: var(--font-sans);
    font-size: 10px;
    font-weight: 600;
    fill: #78716c;
    text-anchor: middle;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .legend-item {
    font-family: var(--font-sans);
    font-size: 10px;
    fill: #57534e;
  }

  /* Concepts */
  .concepts {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .concept {
    display: flex;
    gap: var(--space-4);
    padding: var(--space-4);
    background: white;
    border: 1px solid var(--border-default);
    border-radius: 6px;
  }

  .concept-marker {
    width: 4px;
    flex-shrink: 0;
    border-radius: 2px;
  }

  .concept-content h3 {
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 600;
    margin: 0 0 var(--space-1);
    color: var(--text-primary);
  }

  .concept-content p {
    font-size: 13px;
    color: var(--text-secondary);
    margin: 0;
    line-height: 1.5;
  }

  .concept-content code {
    font-size: 11px;
    background: #f5f5f4;
    padding: 1px 5px;
    border-radius: 3px;
  }

  @media (max-width: 900px) {
    .diagram-container {
      padding: var(--space-2);
    }
  }
</style>
