<script>
  import './app.css'
  import Sidebar from './lib/Sidebar.svelte'
  import Home from './routes/Home.svelte'
  import GettingStarted from './routes/GettingStarted.svelte'
  import Tiers from './routes/Tiers.svelte'
  import Skills from './routes/Skills.svelte'
  import CLI from './routes/CLI.svelte'
  import Architecture from './routes/Architecture.svelte'
  import Configuration from './routes/Configuration.svelte'

  let currentPage = $state('home')

  function navigateTo(page) {
    currentPage = page
    window.scrollTo({ top: 0, behavior: 'instant' })
  }

  const pages = {
    'home': Home,
    'getting-started': GettingStarted,
    'tiers': Tiers,
    'skills': Skills,
    'cli': CLI,
    'architecture': Architecture,
    'configuration': Configuration,
  }

  let pageComponent = $derived(pages[currentPage])
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
