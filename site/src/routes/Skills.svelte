<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Skills</h1>
    <p class="lead">Modular capabilities for Claude.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      Skills are capability modules in <code>~/.claude/skills/</code>. Each skill contains
      a <code>SKILL.md</code> (documentation with YAML frontmatter) and optional <code>scripts/</code>.
    </p>
  </section>

  <section>
    <h2>Built-in Skills</h2>

    <div class="category">
      <div class="category-header">Messaging</div>
      <div class="skill-list">
        <div class="skill">
          <code>sms-assistant</code>
          <span>Messaging guidelines and tier rules</span>
        </div>
        <div class="skill">
          <code>signal</code>
          <span>Signal via signal-cli daemon</span>
        </div>
        <div class="skill">
          <code>contacts</code>
          <span>Contact lookup and tier management</span>
        </div>
        <div class="skill">
          <code>discord</code>
          <span>Discord messaging backend</span>
        </div>
        <div class="skill">
          <code>dispatch-app</code>
          <span>Mobile app messaging integration</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Browser</div>
      <div class="skill-list">
        <div class="skill">
          <code>chrome-control</code>
          <span>Full browser automation</span>
        </div>
        <div class="skill">
          <code>webfetch</code>
          <span>Fetch pages with headless browser</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Smart Home</div>
      <div class="skill-list">
        <div class="skill">
          <code>hue</code>
          <span>Philips Hue lights</span>
        </div>
        <div class="skill">
          <code>lutron</code>
          <span>Caseta dimmers and shades</span>
        </div>
        <div class="skill">
          <code>sonos</code>
          <span>Speaker control, TTS</span>
        </div>
        <div class="skill">
          <code>vivint</code>
          <span>Security cameras, RTSP</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Development</div>
      <div class="skill-list">
        <div class="skill">
          <code>cad</code>
          <span>3D CAD model generation</span>
        </div>
        <div class="skill">
          <code>blender</code>
          <span>3D rendering</span>
        </div>
        <div class="skill">
          <code>touchdesigner</code>
          <span>Generative art</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Mobile App</div>
      <div class="skill-list">
        <div class="skill">
          <code>dispatch-app</code>
          <span>Expo/React Native app frontend</span>
        </div>
        <div class="skill">
          <code>ios-app</code>
          <span>iOS dev and TestFlight</span>
        </div>
        <div class="skill">
          <code>appstore-connect</code>
          <span>App Store Connect API</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">AI &amp; Vision</div>
      <div class="skill-list">
        <div class="skill">
          <code>gemini</code>
          <span>Google Gemini chat/vision</span>
        </div>
        <div class="skill">
          <code>midjourney</code>
          <span>Image generation</span>
        </div>
        <div class="skill">
          <code>nano-banana</code>
          <span>Gemini image generation/editing</span>
        </div>
        <div class="skill">
          <code>vision</code>
          <span>Segmentation, depth, edges</span>
        </div>
        <div class="skill">
          <code>image-to-video</code>
          <span>Video from images</span>
        </div>
        <div class="skill">
          <code>image-to-3d</code>
          <span>3D models from images</span>
        </div>
        <div class="skill">
          <code>image-to-splat</code>
          <span>Gaussian splatting from images</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Productivity</div>
      <div class="skill-list">
        <div class="skill">
          <code>memory</code>
          <span>Persistent FTS search</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Communication Tools</div>
      <div class="skill-list">
        <div class="skill">
          <code>google-suite</code>
          <span>Gmail, Calendar, Drive, Docs</span>
        </div>
        <div class="skill">
          <code>notes-app</code>
          <span>Apple Notes management</span>
        </div>
        <div class="skill">
          <code>reminders</code>
          <span>Reminder management</span>
        </div>
        <div class="skill">
          <code>tts</code>
          <span>Text-to-speech (Kokoro, Qwen3)</span>
        </div>
        <div class="skill">
          <code>transcribe</code>
          <span>Audio transcription</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Media &amp; Entertainment</div>
      <div class="skill-list">
        <div class="skill">
          <code>plex</code>
          <span>Media server control</span>
        </div>
        <div class="skill">
          <code>podcast</code>
          <span>Podcast feed management</span>
        </div>
        <div class="skill">
          <code>dj-buyer</code>
          <span>DJ track purchasing</span>
        </div>
        <div class="skill">
          <code>sheet-music</code>
          <span>Find piano sheet music</span>
        </div>
        <div class="skill">
          <code>passthepopcorn</code>
          <span>Movie torrents</span>
        </div>
        <div class="skill">
          <code>broadcasthenet</code>
          <span>TV show torrents</span>
        </div>
        <div class="skill">
          <code>seedbox</code>
          <span>Seedbox management</span>
        </div>
        <div class="skill">
          <code>chess</code>
          <span>Chess.com automation</span>
        </div>
        <div class="skill">
          <code>imdb-lookup</code>
          <span>Movie/TV info</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Self-Improvement</div>
      <div class="skill-list">
        <div class="skill">
          <code>bug-finder</code>
          <span>Parallel bug discovery</span>
        </div>
        <div class="skill">
          <code>latency-finder</code>
          <span>Performance bottleneck analysis</span>
        </div>
        <div class="skill">
          <code>skillify</code>
          <span>Skill mining and improvement</span>
        </div>
        <div class="skill">
          <code>skill-builder</code>
          <span>Build and improve skills</span>
        </div>
        <div class="skill">
          <code>skill-finder</code>
          <span>Discover skills from marketplace</span>
        </div>
        <div class="skill">
          <code>infra-self-improvement</code>
          <span>Safely improve core system</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">System &amp; Debug</div>
      <div class="skill-list">
        <div class="skill">
          <code>perf</code>
          <span>Performance metrics</span>
        </div>
        <div class="skill">
          <code>bus</code>
          <span>Message bus reference</span>
        </div>
        <div class="skill">
          <code>bus-dashboard</code>
          <span>Event visualization</span>
        </div>
        <div class="skill">
          <code>debug</code>
          <span>System diagnostics</span>
        </div>
        <div class="skill">
          <code>system-info</code>
          <span>Resource monitoring</span>
        </div>
        <div class="skill">
          <code>ccusage</code>
          <span>API usage tracking</span>
        </div>
        <div class="skill">
          <code>computer-use</code>
          <span>Screen interaction</span>
        </div>
        <div class="skill">
          <code>axctl</code>
          <span>macOS accessibility CLI</span>
        </div>
        <div class="skill">
          <code>screen-clicking</code>
          <span>Native app automation</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Shopping &amp; Services</div>
      <div class="skill-list">
        <div class="skill">
          <code>deals</code>
          <span>Deal comparison</span>
        </div>
        <div class="skill">
          <code>cooking</code>
          <span>Recipe and grocery</span>
        </div>
        <div class="skill">
          <code>grubhub</code>
          <span>Food delivery</span>
        </div>
        <div class="skill">
          <code>payments</code>
          <span>Online purchasing</span>
        </div>
        <div class="skill">
          <code>airbnb</code>
          <span>Vacation rental search</span>
        </div>
        <div class="skill">
          <code>books</code>
          <span>Free ebook downloads</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Travel &amp; Places</div>
      <div class="skill-list">
        <div class="skill">
          <code>places</code>
          <span>Google Places search</span>
        </div>
        <div class="skill">
          <code>flight-tracker</code>
          <span>Flight status</span>
        </div>
        <div class="skill">
          <code>vacation-house</code>
          <span>Property search</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Hosting &amp; Deployment</div>
      <div class="skill-list">
        <div class="skill">
          <code>sven-pages</code>
          <span>HTML hosting with ACLs</span>
        </div>
        <div class="skill">
          <code>modal</code>
          <span>Serverless GPU functions</span>
        </div>
        <div class="skill">
          <code>tailscale</code>
          <span>VPN/networking info</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Automation &amp; Research</div>
      <div class="skill-list">
        <div class="skill">
          <code>autoresearch</code>
          <span>Autonomous research loops</span>
        </div>
        <div class="skill">
          <code>manual-test</code>
          <span>Manual testing orchestrator</span>
        </div>
        <div class="skill">
          <code>plan</code>
          <span>Project planning</span>
        </div>
        <div class="skill">
          <code>html-reports</code>
          <span>Report generation</span>
        </div>
        <div class="skill">
          <code>newspaper</code>
          <span>Newspaper-style formatting</span>
        </div>
        <div class="skill">
          <code>figma</code>
          <span>Design integration</span>
        </div>
        <div class="skill">
          <code>webgpu-forge</code>
          <span>Browser ML models</span>
        </div>
        <div class="skill">
          <code>shader-video</code>
          <span>Shader visualizations</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Payments &amp; Security</div>
      <div class="skill-list">
        <div class="skill">
          <code>passwords</code>
          <span>macOS Keychain credentials</span>
        </div>
      </div>
    </div>

    <p class="more">Representative selection of 95+ total skills</p>
  </section>

  <section>
    <h2>Skill Structure</h2>
    <pre><code>~/.claude/skills/my-skill/
├── SKILL.md           # Required
└── scripts/           # Optional
    └── main-command</code></pre>

    <h3>SKILL.md Format</h3>
    <pre><code>---
name: my-skill
description: What this skill does. Include trigger words.
---

# My Skill

Usage documentation...</code></pre>
  </section>

  <section>
    <h2>Creating a Skill</h2>

    <h3>1. Create directory</h3>
    <pre><code>mkdir -p ~/.claude/skills/my-skill/scripts</code></pre>

    <h3>2. Write SKILL.md</h3>
    <pre><code>---
name: my-skill
description: Does something. Trigger: do thing.
---

# My Skill

Run `scripts/do-thing` to do the thing.</code></pre>

    <h3>3. Create scripts</h3>
    <pre><code>#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["httpx"]
# ///

import httpx

def main():
    pass

if __name__ == "__main__":
    main()</code></pre>

    <h3>4. Make executable</h3>
    <pre><code>chmod +x ~/.claude/skills/my-skill/scripts/do-thing</code></pre>
  </section>

  <section>
    <h2>Template Variables</h2>
    <table>
      <thead>
        <tr>
          <th>Variable</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>&#123;&#123;CONTACT_NAME&#125;&#125;</code></td>
          <td>Current contact's name</td>
        </tr>
        <tr>
          <td><code>&#123;&#123;TIER&#125;&#125;</code></td>
          <td>Current contact's tier</td>
        </tr>
        <tr>
          <td><code>&#123;&#123;CHAT_ID&#125;&#125;</code></td>
          <td>Current chat identifier</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('tiers')}>
        <span class="related-label">Contact Tiers</span>
        <span class="related-desc">Which tiers access which skills</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('cli')}>
        <span class="related-label">CLI Reference</span>
        <span class="related-desc">Skill commands</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('configuration')}>
        <span class="related-label">Configuration</span>
        <span class="related-desc">Skill settings</span>
      </button>
    </div>
  </section>
</article>

<style>
  .category {
    margin: var(--space-4) 0;
    border: 1px solid var(--border-default);
    background: var(--bg-elevated);
  }

  .category-header {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-tertiary);
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--border-subtle);
    background: var(--bg-surface);
  }

  .skill-list {
    display: flex;
    flex-direction: column;
  }

  .skill {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: var(--space-2) var(--space-4);
    font-size: 12px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .skill:last-child {
    border-bottom: none;
  }

  .skill code {
    font-size: 12px;
  }

  .skill span {
    color: var(--text-tertiary);
    text-align: right;
  }

  .more {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: var(--space-4);
  }

  @media (max-width: 480px) {
    .skill {
      flex-direction: column;
      gap: var(--space-1);
    }

    .skill span {
      text-align: left;
    }
  }
</style>
