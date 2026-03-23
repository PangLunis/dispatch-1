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
      <svg viewBox="0 0 720 870" class="architecture-svg" role="img" aria-label="Architecture diagram showing the message flow through Dispatch: messages arrive via iMessage, Signal, Discord, and Dispatch App, flow through the Manager Daemon for contact lookup and tier checking, fan out to individual Claude SDK sessions, get processed with inject-prompt, and responses are sent back via backend-specific reply commands.">
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
        <!-- ROW 1: CHATS - 4 message sources -->
        <!-- ════════════════════════════════════════════════════════════ -->

        <!-- iMessage - iPhone mockup -->
        <g transform="translate(15, 5)">
          <rect x="0" y="0" width="140" height="90" rx="14" fill="#1a1a1a"/>
          <rect x="50" y="4" width="40" height="10" rx="5" fill="#000"/>
          <rect x="4" y="16" width="132" height="70" rx="10" fill="#f2f2f7"/>
          <rect x="4" y="16" width="132" height="16" rx="10" fill="#f9f9f9"/>
          <rect x="4" y="26" width="132" height="6" fill="#f9f9f9"/>
          <text x="70" y="27" class="iphone-nav-title">Alice</text>
          <g transform="translate(10, 38)">
            <rect x="0" y="0" width="55" height="16" rx="8" fill="#e5e5ea"/>
            <text x="8" y="11" class="imessage-text">weather?</text>
            <rect x="67" y="0" width="55" height="16" rx="8" fill="#0b93f6"/>
            <text x="75" y="11" class="imessage-text-sent">45°F ☀️</text>
          </g>
          <rect x="4" y="74" width="132" height="12" rx="0 0 10 10" fill="rgba(242,142,44,0.15)"/>
          <text x="70" y="83" class="phone-tier admin">admin</text>
        </g>

        <!-- Signal - iPhone mockup -->
        <g transform="translate(185, 5)">
          <rect x="0" y="0" width="140" height="90" rx="14" fill="#1a1a1a"/>
          <rect x="50" y="4" width="40" height="10" rx="5" fill="#000"/>
          <rect x="4" y="16" width="132" height="70" rx="10" fill="#f2f2f7"/>
          <rect x="4" y="16" width="132" height="16" rx="10" fill="#f9f9f9"/>
          <rect x="4" y="26" width="132" height="6" fill="#f9f9f9"/>
          <text x="70" y="27" class="iphone-nav-title">Family (3)</text>
          <g transform="translate(10, 38)">
            <rect x="0" y="0" width="45" height="16" rx="8" fill="#e5e5ea"/>
            <text x="6" y="11" class="imessage-text">Mom: hi!</text>
            <rect x="50" y="0" width="50" height="16" rx="8" fill="#e5e5ea"/>
            <text x="56" y="11" class="imessage-text">Dad: hey</text>
          </g>
          <rect x="4" y="74" width="132" height="12" rx="0 0 10 10" fill="rgba(118,183,178,0.2)"/>
          <text x="70" y="83" class="phone-tier">family</text>
        </g>

        <!-- Discord - chat app style box -->
        <g transform="translate(395, 5)">
          <rect x="0" y="0" width="140" height="90" rx="10" fill="#5865F2"/>
          <!-- Header bar -->
          <rect x="0" y="0" width="140" height="22" rx="10" fill="#4752C4"/>
          <rect x="0" y="12" width="140" height="10" fill="#4752C4"/>
          <text x="14" y="16" class="discord-channel"># general</text>
          <!-- Chat messages -->
          <g transform="translate(8, 30)">
            <circle cx="6" cy="6" r="6" fill="#7289DA" opacity="0.6"/>
            <text x="16" y="9" class="discord-text">Bob: hey bot</text>
            <circle cx="6" cy="22" r="6" fill="#57F287" opacity="0.6"/>
            <text x="16" y="25" class="discord-text">Dispatch: on it</text>
          </g>
          <!-- Tier badge -->
          <rect x="4" y="74" width="132" height="12" rx="0 0 8 8" fill="rgba(175,122,161,0.2)"/>
          <text x="70" y="83" class="phone-tier">favorite</text>
        </g>

        <!-- Dispatch App - mobile app style box -->
        <g transform="translate(565, 5)">
          <rect x="0" y="0" width="140" height="90" rx="14" fill="#1a1a1a"/>
          <rect x="50" y="4" width="40" height="10" rx="5" fill="#000"/>
          <rect x="4" y="16" width="132" height="70" rx="10" fill="#292524"/>
          <!-- App header -->
          <rect x="4" y="16" width="132" height="16" rx="10" fill="#44403c"/>
          <rect x="4" y="26" width="132" height="6" fill="#44403c"/>
          <text x="70" y="27" class="dispatch-app-title">Dispatch</text>
          <!-- Chat bubbles (dark theme) -->
          <g transform="translate(10, 38)">
            <rect x="0" y="0" width="60" height="16" rx="8" fill="#44403c"/>
            <text x="8" y="11" class="dispatch-app-text">remind me</text>
            <rect x="65" y="0" width="50" height="16" rx="8" fill="{colors.blue}"/>
            <text x="73" y="11" class="imessage-text-sent">done!</text>
          </g>
          <rect x="4" y="74" width="132" height="12" rx="0 0 10 10" fill="rgba(242,142,44,0.15)"/>
          <text x="70" y="83" class="phone-tier admin">admin</text>
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- INGESTION SOURCES (below chats) -->
        <!-- ════════════════════════════════════════════════════════════ -->
        <g transform="translate(20, 100)">
          <rect x="0" y="0" width="95" height="70" rx="8" class="db-box"/>
          <text x="47" y="25" class="db-label">💾 chat.db</text>
          <text x="47" y="42" class="db-sublabel">Messages.app</text>
          <text x="47" y="55" class="db-sublabel">database</text>
        </g>

        <g transform="translate(190, 100)">
          <rect x="0" y="0" width="95" height="70" rx="8" class="db-box"/>
          <text x="47" y="25" class="db-label">🔌 Socket</text>
          <text x="47" y="42" class="db-sublabel">signal-cli</text>
          <text x="47" y="55" class="db-sublabel">JSON-RPC</text>
        </g>

        <g transform="translate(410, 100)">
          <rect x="0" y="0" width="95" height="70" rx="8" class="db-box discord-source"/>
          <text x="47" y="25" class="db-label">🤖 Gateway</text>
          <text x="47" y="42" class="db-sublabel">Discord</text>
          <text x="47" y="55" class="db-sublabel">WebSocket</text>
        </g>

        <g transform="translate(590, 100)">
          <rect x="0" y="0" width="95" height="70" rx="8" class="db-box"/>
          <text x="47" y="25" class="db-label">📡 API</text>
          <text x="47" y="42" class="db-sublabel">dispatch-api</text>
          <text x="47" y="55" class="db-sublabel">:9091</text>
        </g>

        <!-- Arrows from chats DOWN to ingestion sources -->
        <g class="flow-to-db">
          <path d="M 85 95 L 68 100" class="flow-path-thin" marker-end="url(#arrowGray)"/>
          <path d="M 255 95 L 238 100" class="flow-path-thin" marker-end="url(#arrowGray)"/>
          <path d="M 465 95 L 458 100" class="flow-path-thin" marker-end="url(#arrowGray)"/>
          <path d="M 635 95 L 638 100" class="flow-path-thin" marker-end="url(#arrowGray)"/>
          {#if step === 1}
            <circle r="5" fill="{colors.blue}" filter="url(#glow)">
              <animateMotion dur="0.5s" fill="freeze" path="M 85 95 L 68 100"/>
            </circle>
          {/if}
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- DAEMON polls/listens to sources -->
        <!-- ════════════════════════════════════════════════════════════ -->

        <!-- Arrows from ingestion sources down to daemon -->
        <g class="flow-poll">
          <path d="M 68 170 L 180 195" class="flow-path-solid incoming" marker-end="url(#arrowBlue)"/>
          <text x="80" y="195" class="flow-label-small" fill="{colors.gray}">polls</text>
          <path d="M 238 170 L 270 195" class="flow-path-solid incoming" marker-end="url(#arrowBlue)"/>
          <text x="220" y="195" class="flow-label-small" fill="{colors.gray}">listens</text>
          <path d="M 458 170 L 430 195" class="flow-path-solid incoming" marker-end="url(#arrowBlue)"/>
          <text x="450" y="195" class="flow-label-small" fill="{colors.gray}">gateway</text>
          <path d="M 638 170 L 530 195" class="flow-path-solid incoming" marker-end="url(#arrowBlue)"/>
          <text x="590" y="195" class="flow-label-small" fill="{colors.gray}">webhook</text>
          {#if step === 2}
            <circle r="5" fill="{colors.blue}" filter="url(#glow)">
              <animateMotion dur="0.4s" fill="freeze" path="M 68 170 L 180 195"/>
            </circle>
          {/if}
        </g>

        <!-- Daemon -->
        <g transform="translate(155, 195)">
          <g class="daemon" class:active={step >= 3 && step <= 4}>
            <rect x="0" y="0" width="400" height="100" rx="12" class="daemon-box"/>
            <text x="200" y="24" class="daemon-title">Manager Daemon</text>

            <!-- Contact lookup -->
            <g transform="translate(25, 38)">
              <rect x="0" y="0" width="160" height="50" rx="8" class="daemon-inner-box" class:active={step === 3}/>
              <text x="80" y="18" class="daemon-inner-title">🔍 Lookup</text>
              <text x="80" y="35" class="daemon-inner-result" class:visible={step >= 3}>+1617... → Alice</text>
            </g>

            <!-- ACL check -->
            <g transform="translate(210, 38)">
              <rect x="0" y="0" width="160" height="50" rx="8" class="daemon-inner-box" class:active={step === 4}/>
              <text x="80" y="18" class="daemon-inner-title">🛡️ ACL</text>
              <text x="80" y="35" class="daemon-inner-result tier-admin" class:visible={step >= 4}>tier → admin ✓</text>
            </g>
          </g>
        </g>

        <!-- Watchdog -->
        <g transform="translate(20, 220)">
          <rect x="0" y="0" width="95" height="50" rx="6" fill="{colors.red}" opacity="0.15"/>
          <text x="47" y="18" class="watchdog-label">🛡️ Watchdog</text>
          <text x="47" y="32" class="watchdog-desc">monitors health</text>
          <text x="47" y="44" class="watchdog-desc">auto-restarts</text>
          <path d="M 95 25 L 135 25" class="watchdog-line" stroke-dasharray="3,3"/>
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- FAN OUT: Daemon to Sessions -->
        <!-- ════════════════════════════════════════════════════════════ -->
        <g class="fan-out">
          <!-- Main line down from daemon -->
          <path d="M 355 295 L 355 325" class="flow-path-solid incoming"/>

          <!-- Branch node (small circle) -->
          <circle cx="355" cy="330" r="5" fill="{colors.blue}"/>

          <!-- Fan lines from branch node - faded for idle sessions -->
          <path d="M 355 335 L 150 385" class="flow-path-thin faded" marker-end="url(#arrowGray)"/>
          <path d="M 355 335 L 270 385" class="flow-path-thin faded" marker-end="url(#arrowGray)"/>
          <!-- Active/selected session path - highlighted in orange -->
          <path d="M 355 335 L 420 385" class="flow-path-solid" stroke="{colors.orange}" stroke-width="2.5" marker-end="url(#arrowOrange)"/>

          {#if step === 5}
            <circle r="4" fill="{colors.orange}" filter="url(#glow)">
              <animateMotion dur="0.5s" fill="freeze" path="M 355 335 L 420 385"/>
            </circle>
          {/if}
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- SESSION BUBBLES -->
        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- Family Group session (faded) -->
        <g transform="translate(105, 385)">
          <rect x="0" y="0" width="90" height="50" rx="8" class="session-bubble faded"/>
          <rect x="0" y="0" width="90" height="18" rx="8" fill="{colors.teal}" opacity="0.3"/>
          <rect x="0" y="10" width="90" height="8" fill="{colors.teal}" opacity="0.3"/>
          <text x="45" y="13" class="session-bubble-name faded">Family</text>
          <text x="45" y="33" class="session-bubble-tier faded">group</text>
          <text x="45" y="45" class="session-bubble-status">idle</text>
        </g>

        <!-- Friend session (faded) -->
        <g transform="translate(225, 385)">
          <rect x="0" y="0" width="90" height="50" rx="8" class="session-bubble faded"/>
          <rect x="0" y="0" width="90" height="18" rx="8" fill="{colors.purple}" opacity="0.3"/>
          <rect x="0" y="10" width="90" height="8" fill="{colors.purple}" opacity="0.3"/>
          <text x="45" y="13" class="session-bubble-name faded">Friend</text>
          <text x="45" y="33" class="session-bubble-tier faded">favorite</text>
          <text x="45" y="45" class="session-bubble-status">idle</text>
        </g>

        <!-- Active 1:1 session (Alice) -->
        <g transform="translate(370, 385)">
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
        <path d="M 420 435 L 420 465" class="flow-path-solid incoming"/>

        <g transform="translate(280, 470)">
          <rect x="0" y="0" width="220" height="30" rx="6" fill="{colors.blue}" class:glow={step === 6}/>
          <text x="110" y="19" class="inject-label">inject-prompt(tier=admin)</text>
        </g>

        <g class="flow-down">
          <path d="M 390 500 L 390 535" class="flow-path-solid incoming" marker-end="url(#arrowBlue)"/>
          <text x="405" y="522" class="flow-label-small" fill="{colors.blue}">to Claude</text>
          {#if step === 6}
            <circle r="5" fill="{colors.blue}" filter="url(#glow)">
              <animateMotion dur="0.4s" fill="freeze" path="M 390 500 L 390 535"/>
            </circle>
          {/if}
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- AGENT SESSION (active work) -->
        <!-- ════════════════════════════════════════════════════════════ -->
        <g transform="translate(190, 545)">
          <g class="session" class:active={step >= 7}>
            <rect x="0" y="0" width="340" height="100" rx="10" class="session-box"/>
            <rect x="0" y="0" width="340" height="30" rx="10" fill="{colors.orange}"/>
            <rect x="0" y="15" width="340" height="15" fill="{colors.orange}"/>
            <text x="15" y="21" class="session-title">Alice</text>
            <text x="325" y="21" class="session-tier-label">admin</text>

            <g transform="translate(15, 40)">
              <text x="0" y="12" class="session-path">~/transcripts/imessage/_16175969496/</text>
              <rect x="0" y="18" width="310" height="32" rx="4" class="session-work" class:active={step >= 7}/>
              <text x="8" y="34" class="session-work-text">🔧 "what's the weather?"</text>
              <text x="8" y="46" class="session-work-text">✓ "45°F and cloudy!"</text>
            </g>
          </g>
        </g>

        <!-- Arrow to reply commands -->
        <g class="flow-down">
          <path d="M 360 645 L 360 680" class="flow-path-solid outgoing" marker-end="url(#arrowGreen)"/>
          <text x="375" y="668" class="flow-label-small" fill="{colors.green}">reply</text>
          {#if step === 8}
            <circle r="5" fill="{colors.green}" filter="url(#glow)">
              <animateMotion dur="0.4s" fill="freeze" path="M 360 645 L 360 680"/>
            </circle>
          {/if}
        </g>

        <!-- ════════════════════════════════════════════════════════════ -->
        <!-- REPLY COMMANDS (backend-specific) -->
        <!-- ════════════════════════════════════════════════════════════ -->
        <g transform="translate(130, 690)">
          <rect x="0" y="0" width="460" height="50" rx="8" fill="{colors.green}"/>
          <text x="230" y="18" class="node-label">Backend-Specific Reply</text>
          <text x="230" y="36" class="node-sublabel">send-sms · send-signal · send-discord · reply-app</text>
        </g>

        <!-- Return path - goes RIGHT side, up to sources -->
        <g class="flow-return">
          <path d="M 590 715 L 690 715 L 690 105 L 85 105 L 85 95"
                class="flow-path-solid outgoing" marker-end="url(#arrowGreen)"/>
          <text x="700" y="400" class="flow-label-vertical" fill="{colors.green}">response</text>
          {#if step === 9}
            <circle r="5" fill="{colors.green}" filter="url(#glow)">
              <animateMotion dur="1.0s" fill="freeze"
                path="M 590 715 L 690 715 L 690 105 L 85 105 L 85 95"/>
            </circle>
          {/if}
        </g>

        <!-- Legend -->
        <g transform="translate(40, 850)">
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
      The <strong>Manager Daemon</strong> is a single Python async event loop that ingests
      messages from four backends: it polls iMessage's <code>chat.db</code> every 100ms,
      listens on Signal's JSON-RPC socket for push notifications, connects to Discord
      via a Gateway WebSocket (<code>discord_listener.py</code>), and receives webhooks
      from the Dispatch App's FastAPI backend (<code>dispatch-api</code> on port 9091).
      All four backends feed into the same pipeline.
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
      Responses are routed back through backend-specific reply commands:
      <code>send-sms</code> for iMessage, <code>send-signal</code> for Signal,
      <code>send-discord</code> for Discord (via REST API), and
      <code>reply-app</code> for the Dispatch App. Sessions can also use the
      universal <code>reply</code> CLI which auto-detects the backend from
      the transcript directory.
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
        <span class="related-desc">iMessage, Signal, Discord &amp; Dispatch App backends</span>
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
  .page-header h1 {
    margin-bottom: var(--space-1);
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

  /* Discord channel text */
  .discord-channel {
    font-family: var(--font-sans);
    font-size: 9px;
    font-weight: 600;
    fill: rgba(255,255,255,0.9);
  }

  .discord-text {
    font-family: var(--font-sans);
    font-size: 7px;
    fill: rgba(255,255,255,0.85);
  }

  /* Dispatch App text */
  .dispatch-app-title {
    font-family: var(--font-sans);
    font-size: 9px;
    font-weight: 600;
    fill: #fafaf9;
    text-anchor: middle;
  }

  .dispatch-app-text {
    font-family: var(--font-sans);
    font-size: 7px;
    fill: #d6d3d1;
  }

  .discord-source {
    fill: #eef2ff;
    stroke: #818cf8;
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
    border-radius: 0;
    font-size: 12px;
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
