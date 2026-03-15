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
          <code>ios-app</code>
          <span>iOS dev and TestFlight</span>
        </div>
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
      <div class="category-header">AI &amp; Vision</div>
      <div class="skill-list">
        <div class="skill">
          <code>gemini</code>
          <span>Google Gemini chat/vision</span>
        </div>
        <div class="skill">
          <code>vision</code>
          <span>Segmentation, depth, edges</span>
        </div>
        <div class="skill">
          <code>image-to-3d</code>
          <span>3D models from images</span>
        </div>
        <div class="skill">
          <code>image-to-video</code>
          <span>Video from images</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Productivity</div>
      <div class="skill-list">
        <div class="skill">
          <code>reminders</code>
          <span>Scheduling and reminders (JSON-based)</span>
        </div>
        <div class="skill">
          <code>notes-app</code>
          <span>Apple Notes</span>
        </div>
        <div class="skill">
          <code>google-suite</code>
          <span>Gmail, Calendar, Drive, Docs</span>
        </div>
        <div class="skill">
          <code>memory</code>
          <span>Persistent FTS search</span>
        </div>
      </div>
    </div>

    <div class="category">
      <div class="category-header">Media</div>
      <div class="skill-list">
        <div class="skill">
          <code>tts</code>
          <span>Text-to-speech (Kokoro, Qwen3)</span>
        </div>
        <div class="skill">
          <code>transcribe</code>
          <span>Audio transcription</span>
        </div>
        <div class="skill">
          <code>podcast</code>
          <span>Podcast feed management</span>
        </div>
      </div>
    </div>

    <p class="more">67+ skills total</p>
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
