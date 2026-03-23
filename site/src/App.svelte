<script>
  import { onMount } from 'svelte'
  import './app.css'
  import Sidebar from './lib/Sidebar.svelte'
  import Home from './routes/Home.svelte'
  import Setup from './routes/Setup.svelte'
  import Tiers from './routes/Tiers.svelte'
  import Skills from './routes/Skills.svelte'
  import CLI from './routes/CLI.svelte'
  import Architecture from './routes/Architecture.svelte'
  import Configuration from './routes/Configuration.svelte'
  import Philosophy from './routes/Philosophy.svelte'
  import Messaging from './routes/Messaging.svelte'
  import MessageBus from './routes/MessageBus.svelte'
  import Memory from './routes/Memory.svelte'
  import HealthHealing from './routes/HealthHealing.svelte'
  import Analytics from './routes/Analytics.svelte'
  import Postmortems from './routes/Postmortems.svelte'
  import Scheduling from './routes/Scheduling.svelte'
  import DispatchApp from './routes/DispatchApp.svelte'
  import Discord from './routes/Discord.svelte'
  import SvenPages from './routes/SvenPages.svelte'
  import Voice from './routes/Voice.svelte'

  const pages = {
    'home': Home,
    'philosophy': Philosophy,
    'setup': Setup,
    'tiers': Tiers,
    'skills': Skills,
    'cli': CLI,
    'architecture': Architecture,
    'configuration': Configuration,
    'messaging': Messaging,
    'dispatch-app': DispatchApp,
    'discord': Discord,
    'message-bus': MessageBus,
    'memory': Memory,
    'voice': Voice,
    'health': HealthHealing,
    'analytics': Analytics,
    'postmortems': Postmortems,
    'scheduling': Scheduling,
    'sven-pages': SvenPages,
  }

  const pageTitles = {
    'home': 'Dispatch',
    'philosophy': 'Dispatch — Philosophy',
    'setup': 'Dispatch — Setup Guide',
    'tiers': 'Dispatch — Tiers & Permissions',
    'skills': 'Dispatch — Skills',
    'cli': 'Dispatch — CLI Reference',
    'architecture': 'Dispatch — Architecture',
    'configuration': 'Dispatch — Configuration',
    'messaging': 'Dispatch — Messaging',
    'dispatch-app': 'Dispatch — Mobile App',
    'discord': 'Dispatch — Discord',
    'message-bus': 'Dispatch — Message Bus',
    'memory': 'Dispatch — Memory',
    'voice': 'Dispatch — Voice & TTS',
    'health': 'Dispatch — Health & Healing',
    'analytics': 'Dispatch — Analytics',
    'postmortems': 'Dispatch — Postmortems',
    'scheduling': 'Dispatch — Scheduling & Tasks',
    'sven-pages': 'Dispatch — Sven Pages',
  }

  // Redirects for old routes
  const redirects = {
    'getting-started': 'setup',
  }

  let currentPage = 'home'

  function getPageFromHash() {
    const hash = window.location.hash.replace('#', '').split('/')[0]
    // Handle redirects
    if (redirects[hash]) {
      window.location.hash = redirects[hash]
      return redirects[hash]
    }
    return pages[hash] ? hash : 'home'
  }

  function navigateTo(page) {
    currentPage = page
    if (page === 'home') {
      history.replaceState(null, '', window.location.pathname)
    } else {
      window.location.hash = page
    }
    window.scrollTo({ top: 0, behavior: 'instant' })
  }

  function handleHashChange() {
    currentPage = getPageFromHash()
    window.scrollTo({ top: 0, behavior: 'instant' })
  }

  onMount(() => {
    currentPage = getPageFromHash()
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  })

  $: pageComponent = pages[currentPage]
  $: document.title = pageTitles[currentPage] || 'Dispatch'
</script>

<div class="layout">
  <Sidebar {currentPage} onNavigate={navigateTo} />

  <main class="main">
    <div class="content">
      <svelte:component this={pageComponent} {navigateTo} />
    </div>
  </main>
</div>

<style>
  .layout {
    display: flex;
    min-height: 100vh;
    min-height: 100dvh;
  }

  .main {
    flex: 1;
    margin-left: var(--sidebar-width);
    padding: var(--space-8);
    padding-bottom: var(--space-12);
  }

  .content {
    max-width: var(--content-max-width);
  }

  @media (max-width: 768px) {
    .main {
      margin-left: 0;
      margin-top: var(--nav-height);
      padding: var(--space-6) var(--space-4);
      max-width: 100vw;
      overflow-x: hidden;
    }

    .content {
      max-width: 100%;
      overflow-x: hidden;
    }
  }
</style>
