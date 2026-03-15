<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Postmortems</h1>
    <p class="lead">Incident logs and lessons learned to prevent repeating mistakes.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      Dispatch maintains a postmortem log at <code>~/dispatch/POSTMORTEMS.md</code>.
      These are read by the bug-finder skill, debug sessions, and future sessions to
      build institutional memory of past failures. Every significant incident gets
      documented so the system learns from its mistakes.
    </p>
  </section>

  <section>
    <h2>Postmortem Format</h2>
    <p>
      Each postmortem follows a standard template with these fields:
    </p>
    <div class="field-list">
      <div class="field">
        <div class="field-name">Severity</div>
        <div class="field-desc">Critical, High, Medium, Low</div>
      </div>
      <div class="field">
        <div class="field-name">Duration</div>
        <div class="field-desc">How long the incident lasted</div>
      </div>
      <div class="field">
        <div class="field-name">Impact</div>
        <div class="field-desc">What was affected</div>
      </div>
      <div class="field">
        <div class="field-name">Timeline</div>
        <div class="field-desc">Timestamped sequence of events</div>
      </div>
      <div class="field">
        <div class="field-name">Root Cause</div>
        <div class="field-desc">What actually went wrong</div>
      </div>
      <div class="field">
        <div class="field-name">Fixes Applied</div>
        <div class="field-desc">What was done to resolve</div>
      </div>
      <div class="field">
        <div class="field-name">Lessons</div>
        <div class="field-desc">What we learned</div>
      </div>
      <div class="field">
        <div class="field-name">Action Items</div>
        <div class="field-desc">Follow-up work (checkboxed)</div>
      </div>
    </div>
  </section>

  <section>
    <h2>Example Incident</h2>
    <div class="callout">
      <div class="callout-header">
        <span class="callout-title">Disk Full (99.7%) from Zombie Processes</span>
        <span class="callout-severity critical">Critical</span>
      </div>
      <div class="callout-body">
        <p>
          System became unresponsive, requiring HEALME intervention.
          <strong>30 zombie llama-cli processes</strong> were holding 500GB of deleted files
          open via file descriptors, preventing the OS from reclaiming disk space.
        </p>
        <div class="callout-detail">
          <div class="callout-detail-label">Root Cause</div>
          <p>
            Killed llama-cli processes left behind zombie children that held open file
            descriptors to large model files. The files were deleted from disk but space
            was not freed because the processes still referenced them.
          </p>
        </div>
        <div class="callout-detail">
          <div class="callout-detail-label">Key Lessons</div>
          <ul>
            <li>Deleting files doesn't free space if processes hold them open — use <code>lsof +L1</code> to check</li>
            <li>Cache directories grow unbounded without maintenance (uv 103GB, huggingface 83GB, memory-search 51GB)</li>
          </ul>
        </div>
        <div class="callout-detail">
          <div class="callout-detail-label">Fix Applied</div>
          <p>Added disk space monitoring to health checks — warns at 90%, critical at 95%.</p>
        </div>
      </div>
    </div>
  </section>

  <section>
    <h2>How Postmortems Are Used</h2>
    <ul>
      <li><strong>Bug-finder skill</strong> reads <code>POSTMORTEMS.md</code> to avoid known failure patterns</li>
      <li><strong>Debug sessions</strong> reference past incidents for context</li>
      <li><strong>New sessions</strong> inherit institutional knowledge</li>
      <li><strong>Prevention</strong> — the system avoids repeating the same mistakes</li>
    </ul>
  </section>

  <section>
    <h2>Writing a Postmortem</h2>
    <ul>
      <li>Triggered after any significant incident</li>
      <li>Focus on root cause, not blame</li>
      <li>Include actionable lessons and follow-up items</li>
      <li>Check off action items as they're completed</li>
    </ul>
    <p>
      The goal is to make the system smarter over time. Each postmortem is a lesson
      that every future session can learn from, preventing the same class of failure
      from recurring.
    </p>
  </section>

  <section>
    <h2>Current Action Items</h2>
    <p>Example of tracked follow-up work from past incidents:</p>
    <div class="action-items">
      <div class="action-item">
        <span class="checkbox">&#9744;</span>
        <span>Add <code>lsof +L1</code> check to HEALME for deleted-but-held files</span>
      </div>
      <div class="action-item">
        <span class="checkbox">&#9744;</span>
        <span>Add orphaned child process detection to session cleanup</span>
      </div>
      <div class="action-item">
        <span class="checkbox">&#9744;</span>
        <span>Investigate memory-search 51GB sqlite (needs VACUUM)</span>
      </div>
      <div class="action-item">
        <span class="checkbox">&#9744;</span>
        <span>Add zombie process detection to health checks</span>
      </div>
    </div>
  </section>

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('health')}>
        <span class="related-label">Health & Healing</span>
        <span class="related-desc">Recovery system</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('analytics')}>
        <span class="related-label">Analytics</span>
        <span class="related-desc">Incident metrics</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('architecture')}>
        <span class="related-label">Architecture</span>
        <span class="related-desc">System design</span>
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

  /* Field list for postmortem format */
  .field-list {
    border: 1px solid var(--border-default);
    margin: var(--space-4) 0;
  }

  .field {
    display: flex;
    align-items: baseline;
    padding: var(--space-2) var(--space-4);
    border-bottom: 1px solid var(--border-subtle);
    font-size: 13px;
  }

  .field:last-child {
    border-bottom: none;
  }

  .field-name {
    font-weight: 600;
    min-width: 120px;
    color: var(--text-primary);
  }

  .field-desc {
    color: var(--text-secondary);
  }

  /* Callout card for example incident */
  .callout {
    border: 1px solid var(--border-default);
    border-radius: 8px;
    overflow: hidden;
    margin: var(--space-4) 0;
    background: var(--bg-elevated);
  }

  .callout-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-3) var(--space-4);
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border-subtle);
  }

  .callout-title {
    font-weight: 600;
    font-size: 14px;
    color: var(--text-primary);
  }

  .callout-severity {
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 4px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .callout-severity.critical {
    background: rgba(225, 87, 89, 0.15);
    color: #e15759;
  }

  .callout-body {
    padding: var(--space-4);
  }

  .callout-body > p:first-child {
    margin-top: 0;
  }

  .callout-detail {
    margin-top: var(--space-4);
  }

  .callout-detail-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-tertiary);
    margin-bottom: var(--space-1);
  }

  .callout-detail p {
    margin: 0;
    font-size: 13px;
  }

  .callout-detail ul {
    margin: var(--space-1) 0 0;
    padding-left: var(--space-4);
  }

  .callout-detail li {
    margin: var(--space-1) 0;
    font-size: 13px;
  }

  /* Action items */
  .action-items {
    border: 1px solid var(--border-default);
    margin: var(--space-4) 0;
  }

  .action-item {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-4);
    border-bottom: 1px solid var(--border-subtle);
    font-size: 13px;
  }

  .action-item:last-child {
    border-bottom: none;
  }

  .checkbox {
    font-size: 14px;
    color: var(--text-tertiary);
    flex-shrink: 0;
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
