<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Memory</h1>
    <p class="lead">Persistent memory with full-text search across all conversations.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      Dispatch maintains persistent memory about contacts, preferences, and context.
      Memory is stored in macOS Contacts.app notes, CLAUDE.md per-contact files, and searchable via bus FTS5.
      Sessions auto-populate memories from conversations rather than requiring manual entry.
    </p>
  </section>

  <section>
    <h2>Contact Memory</h2>
    <p>
      Each contact's memory is stored in the <strong>Notes</strong> field of their macOS Contacts.app entry.
      These notes are automatically synced into session <code>CLAUDE.md</code> files so that every
      session has full context about the person it is talking to.
    </p>
    <p>
      Memory is formatted as bullet points of facts, preferences, and context:
    </p>
    <pre><code># Alice Smith

What I know about them:

- Prefers CLI tools over inline scripts
- Working on a React project with TypeScript
- Has a dog named Max

---
*5 memories &middot; Last synced: 2026-03-15*</code></pre>
  </section>

  <section>
    <h2>Transcript Storage</h2>
    <p>
      All conversations are stored on disk with one directory per contact:
    </p>
    <pre><code>~/transcripts/{'{backend}'}/{'{sanitized_chat_id}'}/</code></pre>

    <table>
      <thead>
        <tr>
          <th>Field</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>backend</code></td>
          <td><code>imessage</code>, <code>signal</code>, or <code>test</code></td>
        </tr>
        <tr>
          <td><code>sanitized_chat_id</code></td>
          <td>Phone number with <code>+</code> replaced by <code>_</code></td>
        </tr>
      </tbody>
    </table>

    <p>
      Each transcript directory contains the full conversation history for that contact.
      A symlink <code>.claude -&gt; ~/.claude</code> gives every session access to all skills.
    </p>
    <pre><code>~/transcripts/imessage/_16175551234/
├── .claude -> ~/.claude
├── CLAUDE.md          # Contact memory + rules
└── transcript.jsonl   # Conversation history</code></pre>
  </section>

  <section>
    <h2>Full-Text Search</h2>
    <p>
      Bus FTS5 provides full-text search across all bus events (messages, sessions, system events).
      Integrated directly into <code>bus.db</code> via SQLAlchemy/Alembic migrations.
    </p>
    <ul>
      <li>SQLite FTS5 with Porter stemming for fast full-text search</li>
      <li>Indexes records, records_archive, sdk_events, and sdk_events_archive</li>
      <li>Triggers keep FTS in sync automatically on INSERT/DELETE</li>
      <li>Supports phrase queries, prefix matching, and boolean operators</li>
      <li>CLI: <code>cd ~/dispatch && uv run -m bus.cli search "query"</code></li>
    </ul>
  </section>

  <section>
    <h2>Session Persistence</h2>
    <p>
      SDK sessions use resume tokens so conversations survive daemon restarts.
      The session registry maps each <code>chat_id</code> to its session metadata.
    </p>
    <pre><code>~/dispatch/state/sessions.json</code></pre>

    <table>
      <thead>
        <tr>
          <th>Field</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>session_id</code></td>
          <td>SDK session identifier</td>
        </tr>
        <tr>
          <td><code>session_name</code></td>
          <td>Human-readable name (e.g. <code>imessage/_16175551234</code>)</td>
        </tr>
        <tr>
          <td><code>tier</code></td>
          <td>Contact tier (admin, partner, family, favorite, bots)</td>
        </tr>
        <tr>
          <td><code>resume_id</code></td>
          <td>Token for resuming the conversation after restart</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section>
    <h2>Memory Auto-Population</h2>
    <p>
      Memories are extracted from natural conversation flow. There are no manual
      "remember this" commands -- as new facts about a contact emerge during conversation,
      they are automatically added to the contact's notes.
    </p>
    <ul>
      <li>Memories extracted from natural conversation flow</li>
      <li>No manual commands needed</li>
      <li>Contact notes updated automatically as new facts emerge</li>
      <li>Synced to session context on every restart</li>
    </ul>
  </section>

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('skills')}>
        <span class="related-label">Skills</span>
        <span class="related-desc">Memory skill</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('messaging')}>
        <span class="related-label">Messaging</span>
        <span class="related-desc">Conversation storage</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('configuration')}>
        <span class="related-label">Configuration</span>
        <span class="related-desc">Search daemon settings</span>
      </button>
    </div>
  </section>
</article>
