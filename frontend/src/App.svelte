<script lang="ts">
  import { onMount } from 'svelte'
  import Icon, { type IconName } from './components/Icon.svelte'
  import { router, type Page } from './lib/router.svelte'
  import { layout } from './lib/layout.svelte'
  import { app } from './lib/state.svelte'
  import NewJobs from './pages/NewJobs.svelte'
  import Queue from './pages/Queue.svelte'
  import Fix from './pages/Fix.svelte'
  import Log from './pages/Log.svelte'
  import Settings from './pages/Settings.svelte'

  const NAV: { page: Page; label: string; icon: IconName }[] = [
    { page: 'new', label: 'New jobs', icon: 'new' },
    { page: 'queue', label: 'Queue', icon: 'queue' },
    { page: 'fix', label: 'Fix release', icon: 'fix' },
    { page: 'log', label: 'Log', icon: 'log' },
    { page: 'settings', label: 'Settings', icon: 'settings' },
  ]

  let startError = $state('')

  onMount(() => {
    app.start().catch(e => (startError = String(e)))
  })

  const running = $derived(app.jobs.find(j => j.status === 'running'))
</script>

<div class="flex h-full">
  <nav class="flex {layout.navCollapsed ? 'w-14' : 'w-48'} shrink-0 flex-col border-r border-line bg-panel">
    <div class="flex items-center gap-2 py-4 {layout.navCollapsed ? 'justify-center' : 'px-4'}">
      <img src="/favicon.svg" alt="" class="h-6 w-6" />
      {#if !layout.navCollapsed}<span class="text-base font-semibold tracking-wide">VideoForge</span>{/if}
    </div>
    {#each NAV as item (item.page)}
      <button
        class="relative mx-2 flex items-center gap-3 rounded-md py-2 text-left text-sm
          {layout.navCollapsed ? 'justify-center px-0' : 'px-3'}
          {router.page === item.page ? 'bg-accent-strong/20 text-accent' : 'text-muted hover:bg-raised hover:text-text'}"
        onclick={() => router.go(item.page)}
        title={layout.navCollapsed ? item.label : undefined}
      >
        <Icon name={item.icon} size={18} />
        {#if !layout.navCollapsed}{item.label}{/if}
        {#if item.page === 'queue' && app.jobs.length}
          <span
            class="rounded bg-raised px-1.5 text-xs text-muted
              {layout.navCollapsed ? 'absolute -top-0.5 right-0 px-1 text-[10px]' : 'ml-auto'}">{app.jobs.length}</span
          >
        {/if}
      </button>
    {/each}

    <button
      class="mx-2 mt-auto mb-1 flex items-center gap-3 rounded-md py-1.5 text-xs text-muted hover:bg-raised hover:text-text
        {layout.navCollapsed ? 'justify-center' : 'px-3'}"
      onclick={() => (layout.navCollapsed = !layout.navCollapsed)}
      title={layout.navCollapsed ? 'Expand the menu' : 'Collapse the menu'}
    >
      <Icon name={layout.navCollapsed ? 'right' : 'left'} size={16} />
      {#if !layout.navCollapsed}Collapse{/if}
    </button>
    {#if layout.navCollapsed}
      <div class="flex flex-col items-center gap-1 border-t border-line py-3 text-xs">
        {#if running}
          <span class="text-info" title="Running {running.name}{running.progress ? `: ${running.progress.step}` : ''}"
            >{running.progress ? Math.round(running.progress.overall * 100) + '%' : '▶'}</span
          >
        {/if}
        <span class={app.connected ? 'text-ok' : 'text-bad'} title={app.connected ? 'Connected' : 'Reconnecting…'}>●</span>
      </div>
    {:else}
    <div class="space-y-1 border-t border-line p-3 text-xs text-muted">
      {#if running}
        <div class="truncate text-info" title={running.name}>▶ {running.name}</div>
        {#if running.progress}
          <div class="h-1.5 overflow-hidden rounded bg-raised">
            <div class="h-full bg-info" style="width: {running.progress.overall * 100}%"></div>
          </div>
          <div class="truncate">{running.progress.step}</div>
        {/if}
      {:else}
        <div>{app.queue.queued ? `${app.queue.queued} queued` : 'Idle'}</div>
      {/if}
      <div class={app.connected ? 'text-ok' : 'text-bad'}>{app.connected ? '● connected' : '● reconnecting…'}</div>
    </div>
    {/if}
  </nav>

  <main class="min-w-0 flex-1 overflow-hidden">
    {#if startError}
      <div class="m-6 rounded-lg border border-bad/50 bg-bad/10 p-4 text-bad">
        Couldn't reach the VideoForge server: {startError}
      </div>
    {:else if router.page === 'new'}
      <NewJobs />
    {:else if router.page === 'queue'}
      <Queue />
    {:else if router.page === 'fix'}
      <Fix />
    {:else if router.page === 'settings'}
      <Settings />
    {:else}
      <Log />
    {/if}
  </main>
</div>
