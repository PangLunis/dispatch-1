<script>
  export let currentPage;
  export let onNavigate;

  const navGroups = [
    {
      title: 'Getting Started',
      items: [
        { id: 'home', label: 'Overview' },
        { id: 'setup', label: 'Setup Guide' },
        { id: 'configuration', label: 'Configuration' },
        { id: 'philosophy', label: 'Philosophy' },
      ],
    },
    {
      title: 'Core Systems',
      items: [
        { id: 'architecture', label: 'Architecture' },
        { id: 'messaging', label: 'Messaging' },
        { id: 'dispatch-app', label: 'Mobile App' },
        { id: 'discord', label: 'Discord' },
        { id: 'tiers', label: 'Tiers & Permissions' },
        { id: 'skills', label: 'Skills' },
        { id: 'memory', label: 'Memory' },
        { id: 'voice', label: 'Voice & TTS' },
        { id: 'cli', label: 'CLI Reference' },
      ],
    },
    {
      title: 'Operations',
      items: [
        { id: 'scheduling', label: 'Scheduling & Tasks' },
        { id: 'message-bus', label: 'Message Bus' },
        { id: 'health', label: 'Health & Healing' },
        { id: 'analytics', label: 'Analytics' },
        { id: 'postmortems', label: 'Postmortems' },
        { id: 'sven-pages', label: 'Sven Pages' },
      ],
    },
  ];

  let mobileMenuOpen = false;

  function handleNav(id) {
    onNavigate(id);
    mobileMenuOpen = false;
  }
</script>

<!-- Mobile header -->
<header class="mobile-header">
  <button class="mobile-menu-btn" on:click={() => mobileMenuOpen = !mobileMenuOpen} aria-label="Toggle menu">
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
      {#if mobileMenuOpen}
        <path d="M5 5l10 10M15 5L5 15" />
      {:else}
        <path d="M3 5h14M3 10h14M3 15h14" />
      {/if}
    </svg>
  </button>
  <span class="mobile-title">Dispatch</span>
</header>

<!-- Sidebar -->
<aside class="sidebar" class:mobile-open={mobileMenuOpen}>
  <div class="sidebar-header">
    <span class="logo">Dispatch</span>
    <span class="version">v2.8</span>
  </div>

  <nav class="nav">
    {#each navGroups as group}
      <div class="nav-section">
        <div class="nav-section-title">{group.title}</div>
        {#each group.items as item}
          <button
            class="nav-item"
            class:active={currentPage === item.id}
            on:click={() => handleNav(item.id)}
          >
            {item.label}
            {#if currentPage === item.id}
              <span class="nav-indicator"></span>
            {/if}
          </button>
        {/each}
      </div>
    {/each}
  </nav>

  <div class="sidebar-footer">
    <a href="https://github.com/svenflow/dispatch" target="_blank" rel="noopener" class="footer-link">
      GitHub
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M3.5 8.5l5-5M4 3.5h4.5V8" />
      </svg>
    </a>
  </div>
</aside>

<!-- Mobile overlay -->
{#if mobileMenuOpen}
  <button class="mobile-overlay" on:click={() => mobileMenuOpen = false} aria-label="Close menu"></button>
{/if}

<style>
  /* Mobile header */
  .mobile-header {
    display: none;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: var(--nav-height);
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border-default);
    padding: 0 var(--space-4);
    align-items: center;
    gap: var(--space-3);
    z-index: 200;
  }

  .mobile-menu-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    background: none;
    border: 1px solid var(--border-default);
    color: var(--text-primary);
    cursor: pointer;
    transition: border-color var(--transition-fast);
  }

  .mobile-menu-btn:hover {
    border-color: var(--border-strong);
  }

  .mobile-title {
    font-weight: 600;
    font-size: 14px;
    color: var(--text-primary);
  }

  .mobile-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.3);
    z-index: 99;
    border: none;
    padding: 0;
    cursor: pointer;
  }

  /* Sidebar */
  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    width: var(--sidebar-width);
    height: 100vh;
    height: 100dvh;
    background: var(--bg-surface);
    border-right: 1px solid var(--border-default);
    display: flex;
    flex-direction: column;
    z-index: 100;
  }

  .sidebar-header {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    padding: var(--space-6) var(--space-4);
    border-bottom: 1px solid var(--border-subtle);
  }

  .logo {
    font-weight: 600;
    font-size: 14px;
    color: var(--text-primary);
    letter-spacing: -0.01em;
  }

  .version {
    font-size: 11px;
    color: var(--text-muted);
    font-family: var(--font-mono);
  }

  /* Navigation */
  .nav {
    flex: 1;
    overflow-y: auto;
    padding: var(--space-4) 0;
  }

  .nav-section {
    padding: 0 var(--space-3);
    margin-bottom: var(--space-4);
  }

  .nav-section:last-child {
    margin-bottom: 0;
  }

  .nav-section-title {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    padding: var(--space-2) var(--space-3);
    margin-bottom: var(--space-1);
  }

  .nav-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: var(--space-2) var(--space-3);
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 13px;
    font-family: inherit;
    cursor: pointer;
    transition: color var(--transition-fast);
    text-align: left;
    position: relative;
  }

  .nav-item:hover {
    color: var(--text-primary);
  }

  .nav-item.active {
    color: var(--text-primary);
    font-weight: 500;
  }

  .nav-indicator {
    position: absolute;
    top: 0;
    left: 0;
    width: 2px;
    height: 100%;
    background: var(--accent);
  }

  /* Footer */
  .sidebar-footer {
    padding: var(--space-4);
    border-top: 1px solid var(--border-subtle);
  }

  .footer-link {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    font-size: 12px;
    color: var(--text-tertiary);
    transition: color var(--transition-fast);
  }

  .footer-link:hover {
    color: var(--text-primary);
  }

  .footer-link svg {
    opacity: 0.6;
  }

  /* Mobile responsive */
  @media (max-width: 768px) {
    .mobile-header {
      display: flex;
    }

    .mobile-overlay {
      display: block;
    }

    .sidebar {
      transform: translateX(-100%);
      transition: transform var(--transition-smooth);
      top: var(--nav-height);
      height: calc(100vh - var(--nav-height));
      height: calc(100dvh - var(--nav-height));
    }

    .sidebar.mobile-open {
      transform: translateX(0);
    }
  }
</style>
