<script lang="ts">
  import { onMount } from 'svelte'
  import Icon, { type IconName } from './components/Icon.svelte'
  import { router, type Page } from './lib/router.svelte'
  import { app } from './lib/state.svelte'
  import NewJobs from './pages/NewJobs.svelte'
  import Queue from './pages/Queue.svelte'
  import Fix from './pages/Fix.svelte'
  import Log from './pages/Log.svelte'

  const NAV: { page: Page; label: string; icon: IconName }[] = [
    { page: 'new', label: 'New jobs', icon: 'new' },
    { page: 'queue', label: 'Queue', icon: 'queue' },
    { page: 'fix', label: 'Fix release', icon: 'fix' },
    { page: 'log', label: 'Log', icon: 'log' },
  ]

  let startError = $state('')

  onMount(() => {
    app.start().catch(e => (startError = String(e)))
  })

  const running = $derived(app.jobs.find(j => j.status === 'running'))
</script>

<div class="flex h-full">
  <nav class="flex w-48 shrink-0 flex-col border-r border-line bg-panel">
    <div class="flex items-center gap-2 px-4 py-4">
      <img src="/favicon.svg" alt="" class="h-6 w-6" />
      <span class="text-base font-semibold tracking-wide">VideoForge</span>
    </div>
    {#each NAV as item (item.page)}
      <button
        class="mx-2 flex items-center gap-3 rounded-md px-3 py-2 text-left text-sm
          {router.page === item.page ? 'bg-accent-strong/20 text-accent' : 'text-muted hover:bg-raised hover:text-text'}"
        onclick={() => router.go(item.page)}
      >
        <Icon name={item.icon} size={18} />
        {item.label}
        {#if item.page === 'queue' && app.jobs.length}
          <span class="ml-auto rounded bg-raised px-1.5 text-xs text-muted">{app.jobs.length}</span>
        {/if}
      </button>
    {/each}

    <div class="mt-auto space-y-1 border-t border-line p-3 text-xs text-muted">
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
    {:else}
      <Log />
    {/if}
  </main>
</div>
