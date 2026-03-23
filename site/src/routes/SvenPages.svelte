<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Sven Pages</h1>
    <p class="lead">Publish HTML content with per-folder access control.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      Sven Pages is a hosting system for publishing HTML folders (reports, dashboards,
      visualizations) with fine-grained access control. Content is published to
      Cloudflare and served with per-folder ACLs. Default is <strong>private</strong> (admin-only).
    </p>
  </section>

  <section>
    <h2>Access Control</h2>
    <table>
      <thead>
        <tr>
          <th>Mode</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Private</strong> (default)</td>
          <td>Admin-only access</td>
        </tr>
        <tr>
          <td><strong>Email-based</strong></td>
          <td>Specific email addresses can access</td>
        </tr>
        <tr>
          <td><strong>Public</strong></td>
          <td>Anyone with the URL can access</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section>
    <h2>Publishing</h2>
    <p>
      Content is published by uploading an HTML folder. Each folder gets its own URL
      and access settings. The skill handles deployment, ACL configuration, and URL generation.
    </p>
    <pre><code># Publish a folder (private by default)
# The sven-pages skill handles deployment when invoked

# Example workflow:
# 1. Generate HTML content (report, dashboard, etc.)
# 2. Publish via Sven Pages skill
# 3. Share the URL with contacts via iMessage or Dispatch App</code></pre>
  </section>

  <section>
    <h2>Content Sources</h2>
    <p>
      Several skills generate HTML content designed for publishing via Sven Pages:
    </p>
    <ul>
      <li><strong>html-reports</strong> — dark-themed reports and dashboards</li>
      <li><strong>bus-dashboard</strong> — event flow visualizations from the message bus</li>
      <li><strong>newspaper</strong> — newspaper-style broadsheet layouts</li>
      <li><strong>shader-video</strong> — shader visualization previews</li>
    </ul>
    <p>
      Any HTML folder can be published — these are just the most common sources.
    </p>
  </section>

  <section>
    <h2>Sharing</h2>
    <p>
      Published pages can be shared via any messaging backend. The URL is returned
      after publishing and can be sent directly to contacts. For email-based ACLs,
      the recipient's email must be added before they can access the content.
    </p>
  </section>

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('skills')}>
        <span class="related-label">Skills</span>
        <span class="related-desc">Available skills</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('messaging')}>
        <span class="related-label">Messaging</span>
        <span class="related-desc">Sharing via chat</span>
      </button>
    </div>
  </section>
</article>
